import logging

from .settings import settings
from common.pylogger import get_python_logger, force_reconfigure_all_loggers


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
            list_summarization_models,
            get_gpu_info,
            get_deployment_info,
            chat_vllm,
        )
        from .tools.observability_openshift_tools import (
            analyze_openshift,
            list_openshift_metric_groups,
            list_openshift_namespace_metric_groups,
            chat_openshift,
        )
        from .tools.prometheus_tools import (
            search_metrics,                    # Search metrics by pattern
            get_metric_metadata,              # Get metric metadata  
            get_label_values,                 # Get label values
            execute_promql,                   # Execute PromQL queries
            explain_results,                  # Explain query results
            suggest_queries,                  # Suggest related queries
            select_best_metric,               # Select best metric
            find_best_metric_with_metadata_v2,  # Smart metric selection v2
            find_best_metric_with_metadata,   # Smart metric selection v1
        )
        from .tools.tempo import (
            query_tempo_tool,
            get_trace_details_tool,
            chat_tempo_tool,
        )

        # Register vLLM tools
        self.mcp.tool()(list_models)
        self.mcp.tool()(list_namespaces)
        self.mcp.tool()(get_model_config)
        self.mcp.tool()(get_vllm_metrics_tool)
        self.mcp.tool()(analyze_vllm)
        self.mcp.tool()(calculate_metrics)
        self.mcp.tool()(list_summarization_models)
        self.mcp.tool()(get_gpu_info)
        self.mcp.tool()(get_deployment_info)
        self.mcp.tool()(chat_vllm)
        
        # Register OpenShift tools
        self.mcp.tool()(analyze_openshift)
        self.mcp.tool()(list_openshift_metric_groups)
        self.mcp.tool()(list_openshift_namespace_metric_groups)
        self.mcp.tool()(chat_openshift)

        # Register Prometheus tools one by one
        self.mcp.tool()(search_metrics)                    # Search metrics by pattern
        self.mcp.tool()(get_metric_metadata)              # Get metric metadata
        self.mcp.tool()(get_label_values)                 # Get label values
        self.mcp.tool()(execute_promql)                   # Execute PromQL queries
        self.mcp.tool()(explain_results)                  # Explain query results
        self.mcp.tool()(suggest_queries)                  # Suggest related queries
        self.mcp.tool()(select_best_metric)               # Select best metric
        self.mcp.tool()(find_best_metric_with_metadata_v2)  # Smart metric selection v2
        self.mcp.tool()(find_best_metric_with_metadata)   # Smart metric selection v1

        # Register Tempo query tools
        self.mcp.tool()(query_tempo_tool)
        self.mcp.tool()(get_trace_details_tool)
        self.mcp.tool()(chat_tempo_tool)
