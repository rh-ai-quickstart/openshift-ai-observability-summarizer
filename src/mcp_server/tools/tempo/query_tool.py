"""Tempo query tool for interacting with Tempo trace data."""

import httpx
import re
from typing import Dict, Any, List
from datetime import datetime

from common.pylogger import get_python_logger

from .models import QueryResponse, TraceDetailsResponse
from .error_handling import TempoErrorClassifier

logger = get_python_logger()


class TempoQueryTool:
    """Tool for querying Tempo traces with async support."""

    # Configuration constants
    SLOW_TRACE_THRESHOLD_MS = 1000  # Traces slower than this are considered "slow"
    MAX_PER_SERVICE_LIMIT = 50  # Maximum traces to fetch per service in wildcard queries
    DEFAULT_CHAT_QUERY_LIMIT = 50  # Default limit for chat tool queries
    DEFAULT_QUERY_LIMIT = 20  # Default limit for regular queries
    REQUEST_TIMEOUT_SECONDS = 30.0  # HTTP request timeout

    # Default configuration values
    DEFAULT_TEMPO_URL = "https://tempo-tempostack-gateway.observability-hub.svc.cluster.local:8080"
    DEFAULT_TENANT_ID = "dev"
    DEFAULT_NAMESPACE = "observability-hub"

    # Kubernetes service account token path
    K8S_SERVICE_ACCOUNT_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    DEV_FALLBACK_TOKEN = "dev-token"

    def __init__(self):
        # Tempo configuration based on deploy/helm/observability/tempo/values.yaml
        # Use environment variable for local development or OpenShift deployment
        import os
        self.tempo_url = os.getenv("TEMPO_URL", self.DEFAULT_TEMPO_URL)
        # Tenant ID required for multi-tenant Tempo API endpoints
        self.tenant_id = os.getenv("TEMPO_TENANT_ID", self.DEFAULT_TENANT_ID)
        self.namespace = self.DEFAULT_NAMESPACE

    def _get_service_account_token(self) -> str:
        """Get the service account token for authentication."""
        try:
            with open(self.K8S_SERVICE_ACCOUNT_TOKEN_PATH, 'r') as f:
                return f.read().strip()
        except FileNotFoundError:
            # Fallback for local development - use TEMPO_TOKEN if available
            import os
            tempo_token = os.getenv("TEMPO_TOKEN")
            if tempo_token:
                return tempo_token
            return self.DEV_FALLBACK_TOKEN

    def _get_request_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers for Tempo API requests.

        Returns:
            Dict[str, str]: Headers including tenant ID and optional auth token
        """
        headers = {
            "X-Scope-OrgID": self.tenant_id,
            "Content-Type": "application/json"
        }

        # Add service account token if running in cluster
        try:
            token = self._get_service_account_token()
            if token and token != self.DEV_FALLBACK_TOKEN:
                headers["Authorization"] = f"Bearer {token}"
        except Exception as e:
            logger.debug(f"No service account token available: {e}")

        return headers

    def _extract_root_service(self, trace: Dict[str, Any]) -> str:
        """Extract the root service name from a Jaeger trace."""
        if "processes" in trace and trace["processes"]:
            # Get the first process (usually the root service)
            first_process = list(trace["processes"].values())[0]
            return first_process.get("serviceName", "unknown")
        return "unknown"

    def _calculate_duration(self, trace: Dict[str, Any]) -> int:
        """Calculate trace duration in milliseconds from Jaeger trace."""
        if "spans" in trace and trace["spans"]:
            # Find the span with the earliest start time and latest end time
            min_start = float('inf')
            max_end = 0

            for span in trace["spans"]:
                start_time = span.get("startTime", 0)
                duration = span.get("duration", 0)
                end_time = start_time + duration

                min_start = min(min_start, start_time)
                max_end = max(max_end, end_time)

            if min_start != float('inf') and max_end > min_start:
                # Convert from microseconds to milliseconds
                return int((max_end - min_start) / 1000)

        return 0

    def _get_start_time(self, trace: Dict[str, Any]) -> int:
        """Get the start time of the trace from Jaeger trace."""
        if "spans" in trace and trace["spans"]:
            # Find the earliest start time
            min_start = float('inf')
            for span in trace["spans"]:
                start_time = span.get("startTime", 0)
                min_start = min(min_start, start_time)

            if min_start != float('inf'):
                return int(min_start)

        return 0

    async def get_available_services(self) -> List[str]:
        """Get list of available services from Tempo/Jaeger."""
        try:
            services_url = f"{self.tempo_url}/api/traces/v1/{self.tenant_id}/api/services"
            headers = self._get_request_headers()

            async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT_SECONDS, verify=False) as client:
                logger.info(f"Getting available services from: {services_url}")
                response = await client.get(services_url, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    services = data.get("data", [])
                    logger.info(f"Found {len(services)} available services: {services}")
                    return services
                else:
                    logger.error(f"Failed to get services: HTTP {response.status_code} - {response.text}")
                    return []

        except Exception as e:
            logger.error(f"Error getting available services: {e}")
            return []

    async def _query_single_service(self, search_url: str, params: Dict[str, Any], headers: Dict[str, str],
                                   query: str, start_time: str, end_time: str, duration_filter: int) -> Dict[str, Any]:
        """Query traces from a single service."""
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            try:
                logger.info(f"Querying Jaeger API: {search_url}")
                logger.info(f"Query parameters: {params}")
                response = await client.get(search_url, params=params, headers=headers)

                if response.status_code == 200:
                    jaeger_data = response.json()
                    logger.info(f"Jaeger API response status: {response.status_code}")
                    if "data" in jaeger_data:
                        logger.info(f"Number of traces in response: {len(jaeger_data['data']) if jaeger_data['data'] else 0}")

                    # Convert Jaeger format to our expected format
                    traces = []
                    if "data" in jaeger_data and jaeger_data["data"]:
                        for trace in jaeger_data["data"]:
                            # Extract basic trace info from Jaeger format
                            trace_info = {
                                "traceID": trace.get("traceID", ""),
                                "rootServiceName": self._extract_root_service(trace),
                                "durationMs": self._calculate_duration(trace),
                                "spanCount": len(trace.get("spans", [])),
                                "startTime": self._get_start_time(trace)
                            }

                            # Apply duration filter if specified
                            if duration_filter is None or trace_info["durationMs"] >= duration_filter:
                                traces.append(trace_info)

                    logger.info(f"Query results: {len(traces)} traces after filtering (duration_filter: {duration_filter}ms)")
                    if traces:
                        logger.info(f"Sample trace durations: {[t.get('durationMs', 0) for t in traces[:3]]}")
                    else:
                        logger.warning(f"No traces found. Raw response data: {jaeger_data}")

                    return QueryResponse(
                        success=True,
                        query=query,
                        traces=traces,
                        total=len(traces),
                        time_range=f"{start_time} to {end_time}",
                        api_endpoint=search_url,
                        service_queried=params.get("service", "unknown"),
                        duration_filter_ms=duration_filter
                    ).to_dict()
                else:
                    logger.error(f"Jaeger API query failed: HTTP {response.status_code}")
                    logger.error(f"Response text: {response.text}")
                    return QueryResponse(
                        success=False,
                        query=query,
                        error=f"Jaeger API query failed: HTTP {response.status_code} - {response.text}",
                        api_endpoint=search_url,
                        params=params,
                        headers={k: v for k, v in headers.items() if k != "Authorization"}
                    ).to_dict()

            except Exception as e:
                return QueryResponse(
                    success=False,
                    query=query,
                    error=f"Error querying Jaeger API: {str(e)}",
                    api_endpoint=search_url
                ).to_dict()

    async def _query_all_services(self, search_url: str, params: Dict[str, Any], headers: Dict[str, str],
                                 query: str, start_time: str, end_time: str, duration_filter: int, limit: int) -> Dict[str, Any]:
        """Query traces from all available services."""
        available_services = await self.get_available_services()
        if not available_services:
            return QueryResponse(
                success=False,
                query=query,
                error="No services available or could not retrieve service list",
                api_endpoint=search_url
            ).to_dict()

        logger.info(f"Querying all {len(available_services)} services for wildcard query")

        all_traces = []
        successful_services = []
        failed_services = []

        # Query each service
        for service in available_services:
            service_params = params.copy()
            service_params["service"] = service
            service_params["limit"] = min(limit, self.MAX_PER_SERVICE_LIMIT)  # Limit per service to avoid overwhelming

            result = await self._query_single_service(search_url, service_params, headers, query, start_time, end_time, duration_filter)

            if result["success"]:
                all_traces.extend(result["traces"])
                successful_services.append(service)
                logger.info(f"Service '{service}': {len(result['traces'])} traces")
            else:
                failed_services.append(service)
                logger.warning(f"Service '{service}': {result['error']}")

        # Sort all traces by duration (for fastest/slowest analysis)
        all_traces.sort(key=lambda x: x.get("durationMs", 0), reverse=True)

        # Limit total results
        if len(all_traces) > limit:
            all_traces = all_traces[:limit]

        logger.info(f"Combined results: {len(all_traces)} traces from {len(successful_services)} services")
        if failed_services:
            logger.warning(f"Failed to query {len(failed_services)} services: {failed_services}")

        return QueryResponse(
            success=True,
            query=query,
            traces=all_traces,
            total=len(all_traces),
            time_range=f"{start_time} to {end_time}",
            api_endpoint=search_url,
            service_queried=f"all services ({len(successful_services)}/{len(available_services)})",
            duration_filter_ms=duration_filter,
            services_queried=successful_services,
            failed_services=failed_services
        ).to_dict()

    async def query_traces(
        self,
        query: str,
        start_time: str,
        end_time: str,
        limit: int = DEFAULT_QUERY_LIMIT  # Use class constant as default
    ) -> Dict[str, Any]:
        """
        Query traces from Tempo using TraceQL syntax.

        Args:
            query (str): TraceQL query string. Supports:
                - Service filtering: "service.name=my-service"
                - Wildcard queries: "service.name=*"
                - Duration filtering: "duration>100ms"
                - Error filtering: "status=error"
                - Complex queries: "service.name=ui && duration>500ms"
            start_time (str): Start time in ISO 8601 format with timezone.
                Examples: "2024-01-01T10:00:00Z", "2024-01-01T10:00:00+00:00"
                The method automatically handles 'Z' suffix conversion to '+00:00'
            end_time (str): End time in ISO 8601 format with timezone.
                Examples: "2024-01-01T11:00:00Z", "2024-01-01T11:00:00+00:00"
                The method automatically handles 'Z' suffix conversion to '+00:00'
            limit (int, optional): Maximum number of traces to return. Defaults to DEFAULT_QUERY_LIMIT (20).

        Returns:
            Dict[str, Any]: Query result containing:
                - success (bool): Whether the query was successful
                - traces (List[Dict]): List of trace data if successful
                - query (str): The original query string
                - time_range (str): Formatted time range
                - error (str): Error message if unsuccessful
        """
        try:
            # Convert times to Unix timestamps
            start_ts = int(datetime.fromisoformat(start_time.replace('Z', '+00:00')).timestamp())
            end_ts = int(datetime.fromisoformat(end_time.replace('Z', '+00:00')).timestamp())

            headers = self._get_request_headers()

            # Use Jaeger API format (working endpoint from template)
            search_url = f"{self.tempo_url}/api/traces/v1/{self.tenant_id}/api/traces"

            # Parse TraceQL query to extract service name and duration filter
            # Simple parsing for service.name=value format
            service_name = None
            duration_filter = None

            if "service.name=" in query:
                # Extract service name from TraceQL query like "service.name=my-service"
                parts = query.split("service.name=")
                if len(parts) > 1:
                    extracted_name = parts[1].split()[0].strip('"\'')
                    # Handle wildcard queries - don't set service_name for wildcards
                    if extracted_name != "*" and extracted_name:
                        service_name = extracted_name
            elif "service=" in query:
                # Handle direct service= format
                parts = query.split("service=")
                if len(parts) > 1:
                    extracted_name = parts[1].split()[0].strip('"\'')
                    # Handle wildcard queries - don't set service_name for wildcards
                    if extracted_name != "*" and extracted_name:
                        service_name = extracted_name

            # Check for duration filter in query
            if "duration>" in query:
                # Extract duration filter like "duration>1s"
                duration_match = re.search(r'duration>(\d+)([smh]?)', query)
                if duration_match:
                    duration_value = int(duration_match.group(1))
                    duration_unit = duration_match.group(2) or 's'

                    # Convert to milliseconds
                    if duration_unit == 's':
                        duration_filter = duration_value * 1000
                    elif duration_unit == 'm':
                        duration_filter = duration_value * 60 * 1000
                    elif duration_unit == 'h':
                        duration_filter = duration_value * 60 * 60 * 1000
                    else:
                        duration_filter = duration_value * 1000  # default to seconds

            # Build Jaeger API parameters
            params = {
                "start": start_ts * 1000000,  # Jaeger expects microseconds
                "end": end_ts * 1000000,
                "limit": limit
            }

            if service_name:
                params["service"] = service_name
                # Query single service
                return await self._query_single_service(search_url, params, headers, query, start_time, end_time, duration_filter)
            else:
                # For wildcard queries, query all available services
                return await self._query_all_services(search_url, params, headers, query, start_time, end_time, duration_filter, limit)

        except Exception as e:
            logger.error(f"Tempo query error: {e}")
            error_msg = str(e)

            # Use robust error classification instead of hardcoded string matching
            error_type = TempoErrorClassifier.classify_error(error_msg)
            user_friendly_msg = TempoErrorClassifier.get_user_friendly_message(error_type, self.tempo_url)

            return QueryResponse(
                success=False,
                query=query,
                error=user_friendly_msg,
                tempo_url=self.tempo_url,
                error_type=error_type.value
            ).to_dict()

    async def get_trace_details(self, trace_id: str) -> Dict[str, Any]:
        """Get detailed trace information."""
        try:
            trace_url = f"{self.tempo_url}/api/traces/v1/{self.tenant_id}/api/traces/{trace_id}"
            headers = self._get_request_headers()

            async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT_SECONDS, verify=False) as client:
                response = await client.get(trace_url, headers=headers)

                if response.status_code == 200:
                    return TraceDetailsResponse(
                        success=True,
                        trace=response.json()
                    ).to_dict()
                else:
                    return TraceDetailsResponse(
                        success=False,
                        error=f"Trace fetch failed: {response.status_code} - {response.text}"
                    ).to_dict()

        except Exception as e:
            logger.error(f"Trace details error: {e}")
            return TraceDetailsResponse(
                success=False,
                error=str(e)
            ).to_dict()
