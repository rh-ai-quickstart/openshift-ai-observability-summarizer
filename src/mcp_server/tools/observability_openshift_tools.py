from typing import Dict, Any, List, Optional
import os
import re
import json
import pandas as pd

from .observability_vllm_tools import _resp, resolve_time_range
from core.metrics import (
    analyze_openshift_metrics,
    NAMESPACE_SCOPED,
    CLUSTER_WIDE,
    get_openshift_metrics,
    get_namespace_specific_metrics,
    fetch_openshift_metrics,
)
from core.llm_client import build_openshift_prompt, summarize_with_llm
from core.response_validator import ResponseType
from core.config import MODEL_CONFIG

def analyze_openshift(
    metric_category: str,
    scope: str = "cluster_wide",
    namespace: Optional[str] = None,
    time_range: Optional[str] = None,
    start_datetime: Optional[str] = None,
    end_datetime: Optional[str] = None,
    summarize_model_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Analyze OpenShift metrics for a category and scope.

    Returns a text block with the LLM summary and basic metadata.
    """
    try:
        if scope not in (CLUSTER_WIDE, NAMESPACE_SCOPED):
            return _resp("Invalid scope. Use 'cluster_wide' or 'namespace_scoped'.")
        if scope == NAMESPACE_SCOPED and not namespace:
            return _resp("Namespace is required when scope is 'namespace_scoped'.")

        # Resolve time range uniformly (string inputs → epoch seconds)
        start_ts, end_ts = resolve_time_range(
            time_range=time_range,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
        )

        result = analyze_openshift_metrics(
            metric_category=metric_category,
            scope=scope,
            namespace=namespace or "",
            start_ts=start_ts,
            end_ts=end_ts,
            summarize_model_id=summarize_model_id or os.getenv("DEFAULT_SUMMARIZE_MODEL", ""),
            api_key=api_key or os.getenv("LLM_API_TOKEN", ""),
        )

        # Format the response for MCP consumers
        summary = result.get("llm_summary", "")
        scope_desc = result.get("scope", scope)
        ns_desc = result.get("namespace", namespace or "")
        header = f"OpenShift Analysis ({metric_category}) — {scope_desc}"
        if scope == NAMESPACE_SCOPED and ns_desc:
            header += f" (namespace={ns_desc})"

        content = f"{header}\n\n{summary}".strip()
        return _resp(content)
    except Exception as e:
        return _resp(f"Error running analyze_openshift: {str(e)}", is_error=True)


def list_openshift_metric_groups() -> List[Dict[str, Any]]:
    """Return OpenShift metric group categories (cluster-wide)."""
    try:
        groups = list(get_openshift_metrics().keys())
        header = "Available OpenShift Metric Groups (cluster-wide):\n\n"
        body = "\n".join([f"• {g}" for g in groups])
        return _resp(header + body if groups else "No OpenShift metric groups available.")
    except Exception as e:
        return _resp(f"Error retrieving OpenShift metric groups: {str(e)}", is_error=True)


def list_openshift_namespace_metric_groups() -> List[Dict[str, Any]]:
    """Return OpenShift metric groups that support namespace-scoped analysis."""
    try:
        groups = [
            "Workloads & Pods",
            "Storage & Networking",
            "Application Services",
        ]
        header = "Available OpenShift Namespace Metric Groups:\n\n"
        body = "\n".join([f"• {g}" for g in groups])
        return _resp(header + body)
    except Exception as e:
        return _resp(
            f"Error retrieving OpenShift namespace metric groups: {str(e)}",
            is_error=True,
        )

def chat_openshift(
    metric_category: str,
    question: str,
    scope: str = "cluster_wide",
    namespace: Optional[str] = None,
    time_range: Optional[str] = None,
    start_datetime: Optional[str] = None,
    end_datetime: Optional[str] = None,
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
    summarize_model_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Chat about OpenShift metrics for a specific category/scope.

    Returns a text block including PromQL (if provided) and the LLM summary.
    """
    try:
        # Validate inputs
        if scope not in (CLUSTER_WIDE, NAMESPACE_SCOPED):
            return _resp("Invalid scope. Use 'cluster_wide' or 'namespace_scoped'.")
        if scope == NAMESPACE_SCOPED and not namespace:
            return _resp("Namespace is required when scope is 'namespace_scoped'.")

        # Resolve time range (supports epoch or strings)
        start_ts_resolved, end_ts_resolved = resolve_time_range(
            time_range=time_range,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            start_ts=start_ts,
            end_ts=end_ts,
        )

        openshift_metrics = get_openshift_metrics()

        # Determine metric set based on scope
        if scope == NAMESPACE_SCOPED and namespace:
            namespace_metrics = get_namespace_specific_metrics(metric_category)
            if not namespace_metrics:
                if metric_category not in openshift_metrics:
                    return _resp(f"Invalid metric category: {metric_category}")
                metrics_to_fetch = openshift_metrics[metric_category]
            else:
                metrics_to_fetch = namespace_metrics
        else:
            if metric_category not in openshift_metrics:
                return _resp(f"Invalid metric category: {metric_category}")
            metrics_to_fetch = openshift_metrics[metric_category]

        # Fetch metrics frames
        namespace_for_query = namespace if scope == NAMESPACE_SCOPED else None
        metric_dfs: Dict[str, Any] = {}
        for label, query in metrics_to_fetch.items():
            try:
                df = fetch_openshift_metrics(query, start_ts_resolved, end_ts_resolved, namespace_for_query)
                metric_dfs[label] = df
            except Exception:
                metric_dfs[label] = pd.DataFrame()

        # If no data at all, avoid LLM call and return helpful message
        has_any_data = any(isinstance(df, pd.DataFrame) and not df.empty for df in metric_dfs.values())
        if not has_any_data:
            summary = (
                "No metric data found for the selected category/scope in the time window. "
                "Try a broader window (e.g., last 6h) or a different category."
            )
            payload = {
                "metric_category": metric_category,
                "scope": scope,
                "namespace": namespace or "",
                "start_ts": start_ts_resolved,
                "end_ts": end_ts_resolved,
                "promql": "",
                "summary": summary,
            }
            return _resp(json.dumps(payload))

        # Build scope description for prompt
        scope_description = f"{scope.replace('_', ' ').title()}"
        if scope == NAMESPACE_SCOPED and namespace:
            scope_description += f" ({namespace})"

        # Metrics summary for the LLM
        metrics_data_summary = build_openshift_prompt(
            metric_dfs, metric_category, namespace_for_query, scope_description
        )

        # Create a simple chat prompt for OpenShift
        context_description = (
            f"OpenShift {metric_category} metrics for **{scope_description}**"
        )
        prompt = f"""
            You are a senior Site Reliability Engineer (SRE) analyzing {context_description}.
            Current Metrics:
            {metrics_data_summary}
            User Question: {question}
            Provide a concise technical response focusing on operational insights and recommendations.
            Your response should be in JSON format: {{"promql": "relevant_query_if_applicable", "summary": "your_analysis"}}
            Do not add any additional text or commentary.
        """
        # Use the same call pattern as analyze_openshift (symmetry)
        smid = summarize_model_id or ""
        ak = api_key or ""
        llm_response = summarize_with_llm(
            prompt, smid, ResponseType.OPENSHIFT_ANALYSIS, ak
        )
        # Try to extract JSON
        promql = ""
        summary = llm_response
        try:
            json_match = re.search(r"\{.*\}", llm_response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                promql = (parsed.get("promql") or "").strip()
                summary = (parsed.get("summary") or llm_response).strip()

                # Add namespace filter when needed
                if promql and namespace and "namespace=" not in promql:
                    if "{" in promql:
                        promql = promql.replace("{", f'{{namespace="{namespace}", ', 1)
                    else:
                        promql = f'{promql}{{namespace="{namespace}"}}'
        except json.JSONDecodeError:
            pass

        # Return structured JSON for easier API consumption
        payload = {
            "metric_category": metric_category,
            "scope": scope,
            "namespace": namespace or "",
            "start_ts": start_ts_resolved,
            "end_ts": end_ts_resolved,
            "promql": promql,
            "summary": summary,
        }
        return _resp(json.dumps(payload))
    except Exception as e:
        return _resp(f"Error in chat_openshift: {str(e)}", is_error=True)


