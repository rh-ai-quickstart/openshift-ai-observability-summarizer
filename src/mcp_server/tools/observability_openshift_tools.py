from typing import Dict, Any, List, Optional
import os
import json
import core.metrics as core_metrics
import re
import pandas as pd
import requests

from .observability_vllm_tools import _resp, resolve_time_range
from core.metrics import (
    analyze_openshift_metrics,
    chat_openshift_metrics,
    NAMESPACE_SCOPED,
    CLUSTER_WIDE,
)
from common.pylogger import get_python_logger
from mcp_server.exceptions import (
    ValidationError,
    PrometheusError,
    LLMServiceError,
    MCPException,
    MCPErrorCode,
    validate_required_params,
    validate_time_range,
    parse_prometheus_error,
)

logger = get_python_logger()


def _classify_requests_error(e: Exception) -> str:
    """Classify requests exceptions as 'prom', 'llm', or 'unknown'."""
    try:
        url = ""
        resp = getattr(e, "response", None)
        if resp is not None:
            url = getattr(resp, "url", "") or ""
        text = f"{url} {str(e)}".lower()
        if "/api/v1/query" in text or "/api/v1/query_range" in text:
            return "prom"
        if "/v1/openai" in text or "/completions" in text or "llamastack" in text or "openai" in text:
            return "llm"
        return "unknown"
    except Exception:
        return "unknown"

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
    """Analyze OpenShift metrics for a category and scope with structured error handling."""
    # Validate required parameters
    try:
        validate_required_params(metric_category=metric_category, scope=scope)
        if scope not in (CLUSTER_WIDE, NAMESPACE_SCOPED):
            raise ValidationError(
                message="Invalid scope. Use 'cluster_wide' or 'namespace_scoped'.",
                field="scope",
                value=scope,
            )
        if scope == NAMESPACE_SCOPED and not namespace:
            raise ValidationError(
                message="Namespace is required when scope is 'namespace_scoped'.",
                field="namespace",
                value=namespace,
            )
    except ValidationError as e:
        return e.to_mcp_response()
    except Exception as e:
        error = MCPException(
            message=f"Parameter validation failed: {str(e)}",
            error_code=MCPErrorCode.INVALID_INPUT,
            recovery_suggestion="Please check the input parameters and try again.",
        )
        return error.to_mcp_response()

    # Resolve time range
    try:
        start_ts, end_ts = resolve_time_range(
            time_range=time_range,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
        )
    except Exception as e:
        error = MCPException(
            message=f"Time range resolution failed: {str(e)}",
            error_code=MCPErrorCode.INVALID_INPUT,
            recovery_suggestion="Please check the time range parameters and try again.",
        )
        return error.to_mcp_response()

    # Validate time range
    try:
        validate_time_range(start_ts, end_ts)
    except ValidationError as e:
        return e.to_mcp_response()
    except Exception as e:
        error = MCPException(
            message=f"Time range validation failed: {str(e)}",
            error_code=MCPErrorCode.INVALID_INPUT,
            recovery_suggestion="Please check the time range and try again.",
        )
        return error.to_mcp_response()

    # Perform analysis
    try:
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

        # Attach structured payload so UI can render metric grids
        def _serialize_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
            out: Dict[str, Any] = {}
            try:
                for label, rows in (metrics or {}).items():
                    safe_rows = []
                    if isinstance(rows, list):
                        for r in rows:
                            if isinstance(r, dict):
                                ts = r.get("timestamp")
                                val = r.get("value")
                                # Convert timestamp to ISO 8601 string; ensure it ends with 'Z' to indicate UTC.
                                if hasattr(ts, "isoformat"):
                                    ts_str = ts.isoformat()
                                    if not ts_str.endswith("Z"):
                                        ts_str += "Z"
                                else:
                                    ts_str = str(ts) if ts is not None else ""
                                try:
                                    val_num = float(val) if val is not None else None
                                except Exception:
                                    val_num = None
                                safe_rows.append({"timestamp": ts_str, "value": val_num})
                    out[label] = safe_rows
            except Exception:
                return {}
            return out

        structured = {
            "health_prompt": result.get("health_prompt", ""),
            "llm_summary": summary,
            "metrics": _serialize_metrics(result.get("metrics", {})),
        }

        content = f"{header}\n\n{summary}\n\nSTRUCTURED_DATA:\n{json.dumps(structured)}".strip()
        return _resp(content)

    except PrometheusError as e:
        return e.to_mcp_response()
    except requests.exceptions.HTTPError as e:
        cls = _classify_requests_error(e)
        if cls == "llm":
            return LLMServiceError(message="Cannot reach LLM service.").to_mcp_response()
        # Default: treat as Prometheus HTTP error
        prom_err = parse_prometheus_error(getattr(e, 'response', None))
        return prom_err.to_mcp_response()
    except requests.exceptions.ConnectionError as e:
        cls = _classify_requests_error(e)
        if cls == "llm":
            return LLMServiceError(message="Cannot reach LLM service.").to_mcp_response()
        return PrometheusError(message="Cannot connect to Prometheus/Thanos service.").to_mcp_response()
    except requests.exceptions.Timeout as e:
        cls = _classify_requests_error(e)
        if cls == "llm":
            return LLMServiceError(message="LLM service request timed out.").to_mcp_response()
        return PrometheusError(message="Prometheus/Thanos request timed out.").to_mcp_response()
    except requests.exceptions.RequestException as e:
        cls = _classify_requests_error(e)
        if cls == "llm":
            return LLMServiceError(message="LLM service request failed.").to_mcp_response()
        return PrometheusError(message="Prometheus/Thanos request failed.").to_mcp_response()
    except LLMServiceError as e:
        return e.to_mcp_response()
    except Exception as e:
        error = MCPException(
            message=f"Error running analyze_openshift: {str(e)}",
            error_code=MCPErrorCode.INTERNAL_ERROR,
            recovery_suggestion="Please try again. If the problem persists, contact support.",
        )
        return error.to_mcp_response()


def list_openshift_metric_groups() -> List[Dict[str, Any]]:
    """Return OpenShift metric group categories (cluster-wide)."""
    groups = list(core_metrics.get_openshift_metrics().keys())
    header = "Available OpenShift Metric Groups (cluster-wide):\n\n"
    body = "\n".join([f"• {g}" for g in groups])
    return _resp(header + body if groups else "No OpenShift metric groups available.")


def list_openshift_namespace_metric_groups() -> List[Dict[str, Any]]:
    """Return OpenShift metric groups that support namespace-scoped analysis."""
    groups = [
        "Workloads & Pods",
        "Storage & Networking",
        "Application Services",
    ]
    header = "Available OpenShift Namespace Metric Groups:\n\n"
    body = "\n".join([f"• {g}" for g in groups])
    return _resp(header + body)

def chat_openshift(
    metric_category: str,
    question: str,
    scope: str = "cluster_wide",
    namespace: Optional[str] = None,
    time_range: Optional[str] = None,
    start_datetime: Optional[str] = None,
    end_datetime: Optional[str] = None,
    summarize_model_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Chat about OpenShift metrics for a specific category/scope with structured error handling.

    Returns a text block including PromQL (if provided) and the LLM summary.
    """
    # Validate inputs
    try:
        validate_required_params(metric_category=metric_category, question=question, scope=scope)
        if scope not in (CLUSTER_WIDE, NAMESPACE_SCOPED):
            raise ValidationError(
                message="Invalid scope. Use 'cluster_wide' or 'namespace_scoped'.",
                field="scope",
                value=scope,
            )
        if scope == NAMESPACE_SCOPED and not namespace:
            raise ValidationError(
                message="Namespace is required when scope is 'namespace_scoped'.",
                field="namespace",
                value=namespace,
            )
    except ValidationError as e:
        return e.to_mcp_response()
    except Exception as e:
        err = MCPException(
            message=f"Parameter validation failed: {str(e)}",
            error_code=MCPErrorCode.INVALID_INPUT,
            recovery_suggestion="Please check the input parameters and try again.",
        )
        return err.to_mcp_response()

    # Resolve and validate time range
    try:
        start_ts_resolved, end_ts_resolved = resolve_time_range(
            time_range=time_range,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
        )
    except Exception as e:
        err = MCPException(
            message=f"Time range resolution failed: {str(e)}",
            error_code=MCPErrorCode.INVALID_INPUT,
            recovery_suggestion="Please check the time range parameters and try again.",
        )
        return err.to_mcp_response()

    try:
        validate_time_range(start_ts_resolved, end_ts_resolved)
    except ValidationError as e:
        return e.to_mcp_response()
    except Exception as e:
        err = MCPException(
            message=f"Time range validation failed: {str(e)}",
            error_code=MCPErrorCode.INVALID_INPUT,
            recovery_suggestion="Please check the time range and try again.",
        )
        return err.to_mcp_response()

    # Delegate to core logic and handle provider errors
    try:
        result = chat_openshift_metrics(
            metric_category=metric_category,
            question=question,
            scope=scope,
            namespace=namespace or "",
            start_ts=start_ts_resolved,
            end_ts=end_ts_resolved,
            summarize_model_id=summarize_model_id or "",
            api_key=api_key or "",
        )
        payload = {
            "metric_category": metric_category,
            "scope": scope,
            "namespace": namespace or "",
            "start_ts": start_ts_resolved,
            "end_ts": end_ts_resolved,
            "promql": result.get("promql", ""),
            "summary": result.get("summary", ""),
        }
        return _resp(json.dumps(payload))
    except PrometheusError as e:
        return e.to_mcp_response()
    except requests.exceptions.HTTPError as e:
        cls = _classify_requests_error(e)
        if cls == "llm":
            return LLMServiceError(message="Cannot reach LLM service.").to_mcp_response()
        prom_err = parse_prometheus_error(getattr(e, 'response', None))
        return prom_err.to_mcp_response()
    except requests.exceptions.ConnectionError as e:
        cls = _classify_requests_error(e)
        if cls == "llm":
            return LLMServiceError(message="Cannot reach LLM service.").to_mcp_response()
        return PrometheusError(message="Cannot connect to Prometheus/Thanos service.").to_mcp_response()
    except requests.exceptions.Timeout as e:
        cls = _classify_requests_error(e)
        if cls == "llm":
            return LLMServiceError(message="LLM service request timed out.").to_mcp_response()
        return PrometheusError(message="Prometheus/Thanos request timed out.").to_mcp_response()
    except requests.exceptions.RequestException as e:
        cls = _classify_requests_error(e)
        if cls == "llm":
            return LLMServiceError(message="LLM service request failed.").to_mcp_response()
        return PrometheusError(message="Prometheus/Thanos request failed.").to_mcp_response()
    except LLMServiceError as e:
        return e.to_mcp_response()
    except Exception as e:
        err = MCPException(
            message=f"Error in chat_openshift: {str(e)}",
            error_code=MCPErrorCode.INTERNAL_ERROR,
            recovery_suggestion="Please try again. If the problem persists, contact support.",
        )
        return err.to_mcp_response()


