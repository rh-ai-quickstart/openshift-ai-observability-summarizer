from unittest.mock import patch

import mcp_server.tools.observability_openshift_tools as tools


def _texts(result):
    return [part.get("text") for part in result]


@patch(
    "mcp_server.tools.observability_openshift_tools.analyze_openshift_metrics",
    return_value={
        "llm_summary": "OK",
        "scope": "cluster_wide",
        "namespace": "",
        "metrics": {"Pods Running": []},
    },
)  # type: ignore[arg-type]
def test_analyze_openshift_cluster_wide_success(_):
    out = tools.analyze_openshift(
        metric_category="Fleet Overview",
        scope="cluster_wide",
        namespace=None,
        time_range="last 1h",
        summarize_model_id="summarizer",
        api_key="key",
    )
    text = "\n".join(_texts(out))
    # Header should include scope as returned (cluster_wide)
    assert "openshift analysis (fleet overview) — cluster_wide" in text.lower()
    assert "ok" in text.lower()


@patch(
    "mcp_server.tools.observability_openshift_tools.analyze_openshift_metrics",
    return_value={
        "llm_summary": "OK",
        "scope": "namespace_scoped",
        "namespace": "myns",
        "metrics": {"Pods Running": []},
    },
)  # type: ignore[arg-type]
def test_analyze_openshift_namespace_scoped_success(_):
    out = tools.analyze_openshift(
        metric_category="Workloads & Pods",
        scope="namespace_scoped",
        namespace="myns",
        start_datetime="2024-01-01T00:00:00Z",
        end_datetime="2024-01-01T01:00:00Z",
        summarize_model_id="summarizer",
        api_key="key",
    )
    text = "\n".join(_texts(out))
    # Header should include scope as returned (namespace_scoped)
    assert (
        "openshift analysis (workloads & pods) — namespace_scoped (namespace=myns)"
        in text.lower()
    )
    assert "ok" in text.lower()


def test_analyze_openshift_invalid_scope():
    out = tools.analyze_openshift(
        metric_category="Fleet Overview",
        scope="bad_scope",
        namespace=None,
        time_range="last 1h",
        summarize_model_id="summarizer",
    )
    text = "\n".join(_texts(out))
    assert "Invalid scope" in text


def test_analyze_openshift_missing_namespace_for_namespace_scope():
    out = tools.analyze_openshift(
        metric_category="Fleet Overview",
        scope="namespace_scoped",
        namespace=None,
        time_range="last 1h",
        summarize_model_id="summarizer",
    )
    text = "\n".join(_texts(out))
    assert "Namespace is required" in text


# --- Test MCP tools: metric groups ---

@patch(
    "mcp_server.tools.observability_openshift_tools.get_openshift_metrics",
    return_value={
        "Fleet Overview": {},
        "GPU & Accelerators": {},
    },
)
def test_list_openshift_metric_groups_success(_):
    out = tools.list_openshift_metric_groups()
    text = "\n".join(_texts(out))
    assert "Available OpenShift Metric Groups (cluster-wide):" in text
    assert "Fleet Overview" in text
    assert "GPU & Accelerators" in text


@patch(
    "mcp_server.tools.observability_openshift_tools.get_openshift_metrics",
    return_value={},
)
def test_list_openshift_metric_groups_empty(_):
    out = tools.list_openshift_metric_groups()
    text = "\n".join(_texts(out))
    assert "No OpenShift metric groups available" in text


def test_list_openshift_namespace_metric_groups():
    out = tools.list_openshift_namespace_metric_groups()
    text = "\n".join(_texts(out))
    assert "Available OpenShift Namespace Metric Groups:" in text
    assert "Workloads & Pods" in text
    assert "Storage & Networking" in text
    assert "Application Services" in text


