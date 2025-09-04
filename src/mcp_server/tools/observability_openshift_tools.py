from typing import Dict, Any, List, Optional
import os

from .observability_vllm_tools import _resp, resolve_time_range
from core.metrics import (
    analyze_openshift_metrics,
    NAMESPACE_SCOPED,
    CLUSTER_WIDE,
    get_openshift_metrics,
)


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


