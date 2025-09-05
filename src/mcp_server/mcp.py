import logging

from .settings import settings
from mcp_server.utils.pylogger import get_python_logger, force_reconfigure_all_loggers


class ObservabilityMCPServer:
    def __init__(self) -> None:
        # Lazy import to avoid import-time circulars when fastmcp pulls in mcp.types
        from fastmcp import FastMCP  # type: ignore

        get_python_logger(settings.PYTHON_LOG_LEVEL)
        self.mcp = FastMCP("metrics-observability")
        # Ensure third-party loggers are reconfigured after FastMCP init
        force_reconfigure_all_loggers(settings.PYTHON_LOG_LEVEL)
        self._register_mcp_tools()
        logging.getLogger(__name__).info("Observability MCP Server initialized")

    def _register_mcp_tools(self) -> None:
        from .tools.observability_vllm_tools import (
            list_models,
            list_namespaces,
            get_model_config,
            get_vllm_metrics_tool,
            analyze_vllm,
            calculate_metrics,
        )
        from .tools.observability_openshift_tools import (
            analyze_openshift,
            list_openshift_metric_groups,
            list_openshift_namespace_metric_groups,
        )

        self.mcp.tool()(list_models)
        self.mcp.tool()(list_namespaces)
        self.mcp.tool()(get_model_config)
        self.mcp.tool()(get_vllm_metrics_tool)
        self.mcp.tool()(analyze_vllm)
        self.mcp.tool()(calculate_metrics)
        self.mcp.tool()(analyze_openshift)
        self.mcp.tool()(list_openshift_metric_groups)
        self.mcp.tool()(list_openshift_namespace_metric_groups)

