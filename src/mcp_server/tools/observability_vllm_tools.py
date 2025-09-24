"""Observability tools for OpenShift AI monitoring and analysis (vLLM-focused).

This module provides MCP tools for interacting with observability data:
- list_models: Get available AI models
- list_namespaces: List monitored namespaces
- get_model_config: Show configured LLM models for summarization
- get_vllm_metrics_tool: Get available vLLM metrics with friendly names
- analyze_vllm: Analyze vLLM metrics and summarize using LLM
- calculate_metrics: Calculate statistics for provided metrics data

OpenShift-specific tools live in observability_openshift_tools.py
"""

import json
import os
import pandas as pd
from typing import Dict, Any, List, Optional

# Import core observability services
from core.metrics import get_models_helper, get_namespaces_helper, get_vllm_metrics, fetch_metrics
from core.llm_client import build_prompt, summarize_with_llm, extract_time_range_with_info
from core.models import AnalyzeRequest
from core.response_validator import ResponseType
from core.metrics import NAMESPACE_SCOPED, CLUSTER_WIDE
from core.config import PROMETHEUS_URL, THANOS_TOKEN, VERIFY_SSL, DEFAULT_TIME_RANGE_DAYS
import requests
from datetime import datetime

# Import structured logger from MCP server utilities
from common.pylogger import get_python_logger

# Import MCP exception handling framework
from mcp_server.exceptions import (
    handle_mcp_exception,
    ValidationError,
    PrometheusError,
    LLMServiceError,
    ConfigurationError,
    MCPException,
    MCPErrorCode,
    validate_required_params,
    validate_time_range,
    safe_json_loads,
    parse_prometheus_error,
    parse_llm_error
)

# Configure structured logging
logger = get_python_logger()


def _resp(content: str, is_error: bool = False) -> List[Dict[str, Any]]:
    """Helper to format MCP tool responses consistently."""
    return [{"type": "text", "text": content}]


def resolve_time_range(
    time_range: Optional[str] = None,
    start_datetime: Optional[str] = None,
    end_datetime: Optional[str] = None,
) -> tuple[int, int]:
    """Resolve various time inputs into start/end epoch seconds.

    Precedence:
    1) time_range natural language → use extract_time_range_with_info
    2) ISO datetime strings (start_datetime/end_datetime)
    3) Default to last 1 hour
    """
    try:
        # 1) Natural language time range
        if time_range:
            start_ts2, end_ts2, _info = extract_time_range_with_info(time_range, None, None)
            return start_ts2, end_ts2

        # 2) ISO datetime strings
        if start_datetime and end_datetime:
            rs = int(datetime.fromisoformat(start_datetime.replace("Z", "+00:00")).timestamp())
            re = int(datetime.fromisoformat(end_datetime.replace("Z", "+00:00")).timestamp())
            return rs, re

        # 3) Default: last DEFAULT_TIME_RANGE_DAYS days
        now = int(datetime.utcnow().timestamp())
        return now - (DEFAULT_TIME_RANGE_DAYS * 24 * 3600), now
    except Exception as e:
        # Log the error for debugging
        logger.error(f"Error in resolve_time_range: {e}")
        logger.error(f"Inputs: time_range={time_range}, start_datetime={start_datetime}, end_datetime={end_datetime}")
        # Safe fallback to default range on any parsing error
        now = int(datetime.utcnow().timestamp())
        return now - (DEFAULT_TIME_RANGE_DAYS * 24 * 3600), now


def list_models() -> List[Dict[str, Any]]:
    """List all available AI models for analysis.
    
    Returns information about both local and external AI models available
    for generating observability analysis and summaries.
    
    Returns:
        List of available models with their configurations
    """
    try:
        models = get_models_helper()
        
        if not models:
            return _resp("No models are currently available.")
        
        model_list = [f"• {model}" for model in models]
        response = f"Available AI Models ({len(models)} total):\n\n" + "\n".join(model_list)
        return _resp(response)
    except Exception as e:
        error = MCPException(
            message=f"Failed to retrieve models: {str(e)}",
            error_code=MCPErrorCode.CONFIGURATION_ERROR,
            recovery_suggestion="Please check the model configuration and try again."
        )
        return error.to_mcp_response()


def list_namespaces() -> List[Dict[str, Any]]:
    """Get list of monitored Kubernetes namespaces.
    
    Retrieves all namespaces that have observability data available
    in the Prometheus/Thanos monitoring system.
    
    Returns:
        List of namespace names with monitoring status
    """
    try:
        namespaces = get_namespaces_helper()
        if not namespaces:
            return _resp("No monitored namespaces found.")
        namespace_list = "\n".join([f"• {ns}" for ns in namespaces])
        response_text = f"Monitored Namespaces ({len(namespaces)} total):\n\n{namespace_list}"
        return _resp(response_text)
    except Exception as e:
        error = MCPException(
            message=f"Failed to retrieve namespaces: {str(e)}",
            error_code=MCPErrorCode.PROMETHEUS_ERROR,
            recovery_suggestion="Please check Prometheus/Thanos connectivity."
        )
        return error.to_mcp_response()


def get_model_config() -> List[Dict[str, Any]]:
    """Get available LLM models for summarization and analysis.
    
    Uses the exact same logic as the metrics API's /model_config endpoint:
    - Reads MODEL_CONFIG from environment (JSON string)
    - Parses to dict and sorts with external:false models first
    - Returns a human-readable list formatted for MCP
    """
    try:
        model_config_str = os.getenv("MODEL_CONFIG", "{}")
        model_config = safe_json_loads(model_config_str, "MODEL_CONFIG environment variable")
        model_config = dict(
            sorted(model_config.items(), key=lambda x: x[1].get("external", True))
        )
    except ValidationError:
        logger.warning("Could not parse MODEL_CONFIG environment variable, using empty configuration")
        model_config = {}

    if not model_config:
        return _resp("No LLM models configured for summarization.")

    response = f"Available Model Config ({len(model_config)} total):\n\n"
    for model_name, config in model_config.items():
        response += f"• {model_name}\n"
        for key, value in config.items():
            response += f"  - {key}: {value}\n"
        response += "\n"

    return _resp(response.strip())


def get_vllm_metrics_tool() -> List[Dict[str, Any]]:
    """Get available vLLM metrics with friendly names.
    
    Dynamically discovers available vLLM and GPU metrics from Prometheus
    and returns them as a mapping of friendly names to PromQL queries.
    
    Returns:
        Formatted list of available metrics with their PromQL queries
    """
    try:
        # Get the vLLM metrics mapping from the core function
        vllm_metrics_dict = get_vllm_metrics()
        
        if not vllm_metrics_dict:
            return _resp("No vLLM metrics are currently available from Prometheus.")

        # Format the response with categories for better organization
        content = f"Available vLLM Metrics ({len(vllm_metrics_dict)} total):\n\n"
        
        # Group metrics by type for better presentation
        gpu_metrics = {}
        vllm_core_metrics = {}
        other_metrics = {}
        
        for friendly_name, promql_query in vllm_metrics_dict.items():
            if any(gpu_term in friendly_name.lower() for gpu_term in ['gpu', 'temperature', 'power', 'memory', 'energy', 'utilization']):
                gpu_metrics[friendly_name] = promql_query
            elif any(vllm_term in friendly_name.lower() for vllm_term in ['prompt', 'token', 'latency', 'request', 'inference']):
                vllm_core_metrics[friendly_name] = promql_query
            else:
                other_metrics[friendly_name] = promql_query
        
        # Display GPU metrics first
        if gpu_metrics:
            content += "📊 **GPU Metrics:**\n"
            for friendly_name, promql_query in sorted(gpu_metrics.items()):
                content += f"• {friendly_name}\n  Query: `{promql_query}`\n\n"
        
        # Display vLLM core metrics
        if vllm_core_metrics:
            content += "🚀 **vLLM Performance Metrics:**\n"
            for friendly_name, promql_query in sorted(vllm_core_metrics.items()):
                content += f"• {friendly_name}\n  Query: `{promql_query}`\n\n"
        
        # Display other metrics
        if other_metrics:
            content += "🔧 **Other Metrics:**\n"
            for friendly_name, promql_query in sorted(other_metrics.items()):
                content += f"• {friendly_name}\n  Query: `{promql_query}`\n\n"

        # Add summary stats
        content += f"\n**Summary:**\n"
        content += f"- GPU Metrics: {len(gpu_metrics)}\n"
        content += f"- vLLM Performance: {len(vllm_core_metrics)}\n"
        content += f"- Other: {len(other_metrics)}\n"
        content += f"- Total: {len(vllm_metrics_dict)}\n"

        return _resp(content)

    except Exception as e:
        error = MCPException(
            message=f"Failed to retrieve vLLM metrics: {str(e)}",
            error_code=MCPErrorCode.PROMETHEUS_ERROR,
            recovery_suggestion="Check Prometheus/Thanos connectivity and vLLM metrics availability."
        )
        return error.to_mcp_response()


def analyze_vllm(
    model_name: str,
    summarize_model_id: str,
    time_range: Optional[str] = None,
    start_datetime: Optional[str] = None,
    end_datetime: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Analyze vLLM metrics and summarize using LLM. Using the same core functions:
    - get_vllm_metrics() to discover metrics
    - fetch_metrics() to fetch time series
    - build_prompt() to build the analysis prompt
    - summarize_with_llm() to generate the summary

    Returns an MCP-friendly text response containing model, prompt, summary,
    and a compact metrics preview.
    """
    # Validate required parameters
    try:
        validate_required_params(model_name=model_name, summarize_model_id=summarize_model_id)
    except ValidationError as e:
        return e.to_mcp_response()
    except Exception as e:
        error = MCPException(
            message=f"Parameter validation failed: {str(e)}",
            error_code=MCPErrorCode.INVALID_INPUT,
            recovery_suggestion="Please check the input parameters and try again."
        )
        return error.to_mcp_response()

    # Resolve time range → start_ts/end_ts via common helper
    try:
        resolved_start, resolved_end = resolve_time_range(
            time_range=time_range,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
        )
    except Exception as e:
        error = MCPException(
            message=f"Time range resolution failed: {str(e)}",
            error_code=MCPErrorCode.INVALID_INPUT,
            recovery_suggestion="Please check the time range parameters and try again."
        )
        return error.to_mcp_response()

    # Validate time range
    try:
        validate_time_range(resolved_start, resolved_end)
    except ValidationError as e:
        return e.to_mcp_response()
    except Exception as e:
        error = MCPException(
            message=f"Time range validation failed: {str(e)}",
            error_code=MCPErrorCode.INVALID_INPUT,
            recovery_suggestion="Please check the time range and try again."
        )
        return error.to_mcp_response()

    # Collect metrics and perform analysis
    try:
        vllm_metrics = get_vllm_metrics()
        
        metric_dfs: Dict[str, Any] = {
            label: fetch_metrics(query, model_name, resolved_start, resolved_end)
                for label, query in vllm_metrics.items()
        }

        # Build prompt and summarize
        prompt = build_prompt(metric_dfs, model_name)
        summary = summarize_with_llm(
            prompt,
            summarize_model_id,
            ResponseType.VLLM_ANALYSIS,
            api_key,
        )

        # Create a compact metrics preview (latest values)
        preview_lines: List[str] = []
        for label, df in metric_dfs.items():
            try:
                if df is not None and not df.empty and "value" in df.columns:
                    latest_value = df["value"].iloc[-1]
                    preview_lines.append(f"- {label}: {latest_value}")
                else:
                    preview_lines.append(f"- {label}: no data")
            except Exception:
                preview_lines.append(f"- {label}: error reading data")

        # Convert DataFrame metrics to list format for UI consumption
        metrics_for_ui = {}
        for label, df in metric_dfs.items():
            if df is not None and not df.empty and "timestamp" in df.columns and "value" in df.columns:
                # Convert DataFrame to list of {timestamp, value} objects
                data_points = []
                for _, row in df.iterrows():
                    try:
                        # Convert timestamp to ISO format string
                        timestamp_str = row["timestamp"].isoformat() if hasattr(row["timestamp"], "isoformat") else str(row["timestamp"])
                        value = float(row["value"]) if pd.notna(row["value"]) else None
                        if value is not None:
                            data_points.append({
                                "timestamp": timestamp_str,
                                "value": value
                            })
                    except (ValueError, TypeError):
                        continue
                metrics_for_ui[label] = data_points
            else:
                metrics_for_ui[label] = []

        # Create structured response with both summary and metrics data
        structured_response = {
            "health_prompt": prompt,
            "llm_summary": summary,
            "metrics": metrics_for_ui
        }

        content = (
            f"Model: {model_name}\n\n"
            f"Prompt Used:\n{prompt}\n\n"
            f"Summary:\n{summary}\n\n"
            f"Metrics Preview (latest values):\n" + "\n".join(preview_lines) +
            f"\n\nSTRUCTURED_DATA:\n{json.dumps(structured_response)}"
        )

        return _resp(content)
        
    except PrometheusError as e:
        return e.to_mcp_response()
    except LLMServiceError as e:
        return e.to_mcp_response()
    except Exception as e:
        error = MCPException(
            message=f"Analysis failed: {str(e)}",
            error_code=MCPErrorCode.INTERNAL_ERROR,
            recovery_suggestion="Please try again. If the problem persists, contact support."
        )
        return error.to_mcp_response()


def calculate_metrics(
    metrics_data_json: str,
) -> List[Dict[str, Any]]:
    """Calculate statistics for provided metrics data.

    This function mirrors the /calculate-metrics REST API endpoint functionality.
    Takes metrics data and returns calculated statistics in JSON format for UI consumption.

    Args:
        metrics_data_json: JSON string containing metrics data in the format:
            {
                "GPU Temperature (°C)": [
                    {"timestamp": "2024-01-01T10:00:00", "value": 45.2},
                    {"timestamp": "2024-01-01T10:01:00", "value": 46.1}
                ]
            }

    Returns:
        JSON string with calculated statistics matching REST API format
    """
    try:
        # Parse the JSON input
        try:
            metrics_data = json.loads(metrics_data_json)
        except json.JSONDecodeError as e:
            error = ValidationError(
                message=f"Invalid JSON format: {str(e)}",
                field="metrics_data_json",
                value=metrics_data_json[:100] + "..." if len(metrics_data_json) > 100 else metrics_data_json
            )
            return error.to_mcp_response()

        if not isinstance(metrics_data, dict):
            error = ValidationError(
                message="Expected metrics_data to be a dictionary",
                field="metrics_data_json"
            )
            return error.to_mcp_response()

        calculated_metrics = {}

        # Use same logic as REST API /calculate-metrics endpoint
        for label, data_points in metrics_data.items():
            if not data_points:
                calculated_metrics[label] = {
                    "avg": None,
                    "min": None,
                    "max": None,
                    "latest": None,
                    "count": 0
                }
                continue

            # Extract values from data points (same logic as REST API)
            values = []
            for point in data_points:
                if isinstance(point, dict) and "value" in point:
                    try:
                        value = float(point["value"])
                        if pd.notna(value):  # Check for non-NaN
                            values.append(value)
                    except (ValueError, TypeError):
                        continue

            if values:
                calculated_metrics[label] = {
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "latest": values[-1],
                    "count": len(values)
                }
            else:
                calculated_metrics[label] = {
                    "avg": None,
                    "min": None,
                    "max": None,
                    "latest": None,
                    "count": 0
                }

        # Return as JSON string (same format as REST API response)
        result = {"calculated_metrics": calculated_metrics}
        return _resp(json.dumps(result))

    except Exception as e:
        error = MCPException(
            message=f"Failed to calculate metrics: {str(e)}",
            error_code=MCPErrorCode.DATA_PROCESSING_ERROR,
            recovery_suggestion="Check the metrics data format and try again."
        )
        return error.to_mcp_response()
