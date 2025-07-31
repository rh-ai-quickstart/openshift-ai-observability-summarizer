"""Observability tools for OpenShift AI monitoring and analysis.

This module provides MCP tools for interacting with OpenShift AI observability data:
- list_models: Get available AI models
- list_namespaces: List monitored namespaces
"""

import json
from typing import Dict, Any, List, Optional

# Import core observability services
from core.metrics import get_models_helper
from core.config import PROMETHEUS_URL, THANOS_TOKEN, VERIFY_SSL
import requests
from datetime import datetime


def _resp(content: str, is_error: bool = False) -> List[Dict[str, Any]]:
    """Helper to format MCP tool responses consistently."""
    return [{"type": "text", "text": content}]


def list_models() -> List[Dict[str, Any]]:
    """List all available AI models for analysis.
    
    Returns information about both local and external AI models available
    for generating observability analysis and summaries.
    
    Returns:
        List of available models with their configurations
    """
    try:
        # Use the same logic as the metrics API
        models = get_models_helper()
        
        if not models:
            return _resp("No models are currently available.")
        
        # Format the response for MCP
        model_list = [f"• {model}" for model in models]
        response = f"Available AI Models ({len(models)} total):\n\n" + "\n".join(model_list)
        return _resp(response)
        
    except Exception as e:
        return _resp(f"Error listing models: {str(e)}", is_error=True)


def list_namespaces() -> List[Dict[str, Any]]:
    """Get list of monitored Kubernetes namespaces.
    
    Retrieves all namespaces that have observability data available
    in the Prometheus/Thanos monitoring system.
    
    Returns:
        List of namespace names with monitoring status
    """
    try:
        # Use the exact same logic as the metrics API
        headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}

        # Try multiple vLLM metrics with longer time windows
        vllm_metrics_to_check = [
            "vllm:request_prompt_tokens_created",
            "vllm:request_prompt_tokens_total",
            "vllm:avg_generation_throughput_toks_per_s",
            "vllm:num_requests_running",
            "vllm:gpu_cache_usage_perc",
        ]

        namespace_set = set()

        # Try different time windows: 7 days, 24 hours, 1 hour
        time_windows = [7 * 24 * 3600, 24 * 3600, 3600]  # 7 days  # 24 hours  # 1 hour

        for time_window in time_windows:
            for metric_name in vllm_metrics_to_check:
                try:
                    response = requests.get(
                        f"{PROMETHEUS_URL}/api/v1/series",
                        headers=headers,
                        params={
                            "match[]": metric_name,
                            "start": int((datetime.now().timestamp()) - time_window),
                            "end": int(datetime.now().timestamp()),
                        },
                        verify=VERIFY_SSL,
                    )
                    response.raise_for_status()
                    series = response.json()["data"]

                    for entry in series:
                        namespace = entry.get("namespace", "").strip()
                        model = entry.get("model_name", "").strip()
                        if namespace and model:
                            namespace_set.add(namespace)

                    # If we found namespaces, return them
                    if namespace_set:
                        # Format for MCP with bullet points
                        namespace_list = "\n".join([f"• {ns}" for ns in sorted(namespace_set)])
                        response_text = f"Monitored Namespaces ({len(namespace_set)} total):\n\n{namespace_list}"
                        return _resp(response_text)

                except Exception as e:
                    print(
                        f"Error checking {metric_name} with {time_window}s window: {e}"
                    )
                    continue

        # If no namespaces found after all attempts
        if namespace_set:
            namespace_list = "\n".join([f"• {ns}" for ns in sorted(namespace_set)])
            response_text = f"Monitored Namespaces ({len(namespace_set)} total):\n\n{namespace_list}"
            return _resp(response_text)
        else:
            return _resp("No monitored namespaces found.")
        
    except Exception as e:
        print("Error getting namespaces:", e)
        return _resp(f"Error retrieving namespaces: {str(e)}", is_error=True)

