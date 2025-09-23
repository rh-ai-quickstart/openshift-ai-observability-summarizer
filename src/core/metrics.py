"""
Metrics collection and processing functions

Contains all business logic for interacting with Prometheus/Thanos,
collecting vLLM metrics, and processing observability data.
"""

import requests
import pandas as pd
import os
import json
import re
import logging
import math
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

import logging
from common.pylogger import get_python_logger

# Initialize structured logger once - other modules should use logging.getLogger(__name__)
get_python_logger()

logger = logging.getLogger(__name__)

from .config import PROMETHEUS_URL, THANOS_TOKEN, VERIFY_SSL
from fastapi import HTTPException
from .llm_client import summarize_with_llm
from .response_validator import ResponseType
from .llm_client import (
    build_openshift_prompt,
    build_openshift_metrics_context,
    build_openshift_chat_prompt,
)
NAMESPACE_SCOPED = "namespace_scoped"
CLUSTER_WIDE = "cluster_wide"

def choose_prometheus_step(
    start_ts: int,
    end_ts: int,
    max_points_per_series: int = 11000,
    min_step_seconds: int = 30,
) -> str:
    """Select an appropriate Prometheus step to keep points per series under limits.

    Returns a Prometheus duration string like "30s", "1m", "5m", "1h".
    """
    try:
        duration_seconds = max(0, int(end_ts) - int(start_ts))
        # Use (max_points - 1) because query_range is inclusive of endpoints
        raw_step_seconds = max(
            min_step_seconds,
            math.ceil(duration_seconds / max(1, (max_points_per_series - 1))),
        )

        # Round up to the next "nice" bucket
        buckets = [
            1, 2, 5, 10, 15, 30,
            60, 120, 300, 600, 900, 1800,
            3600, 7200, 14400, 21600, 43200,
        ]
        step_seconds = next((b for b in buckets if b >= raw_step_seconds), buckets[-1])

        if step_seconds % 3600 == 0:
            return f"{step_seconds // 3600}h"
        if step_seconds % 60 == 0:
            return f"{step_seconds // 60}m"
        return f"{step_seconds}s"
    except Exception:
        # Fallback to previous default on any error
        return f"{max(min_step_seconds, 30)}s"



def _auth_headers() -> Dict[str, str]:
    """Create Authorization headers only when a plausible token is present.

    Avoid sending a default file path or empty string as a token to local
    Prometheus, which can cause request failures in some setups.
    """
    try:
        token = (THANOS_TOKEN or "").strip()
        if not token:
            return {}
        # Heuristic: if token looks like a filesystem path, skip auth header
        if token.startswith("/") or token.lower().startswith("file:"):
            return {}
        return {"Authorization": f"Bearer {token}"}
    except Exception:
        return {}


def extract_first_json_object_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Extract a JSON object from arbitrary text, robust to extra prose and nesting.

    Strategy:
    - Prefer fenced code blocks (```json ... ``` or ``` ... ```)
    - Scan text with a bracket-depth parser that respects strings/escapes
    - Parse all candidates; if a list at top-level, select the first dict
    - Prefer dicts containing promql/summary; else choose the largest
    """
    candidates = []  # list of tuples: (raw_str, parsed_dict)

    def _try_add(parsed_obj, raw_str: str):
        # If a list, pick the first dict element
        if isinstance(parsed_obj, list):
            for el in parsed_obj:
                if isinstance(el, dict):
                    candidates.append((raw_str, el))
                    return
        elif isinstance(parsed_obj, dict):
            candidates.append((raw_str, parsed_obj))

    def _collect_from_string(source: str):
        # Try whole string
        try:
            _try_add(json.loads(source), source)
        except Exception:
            pass

        # Depth-aware scan for JSON objects
        n = len(source)
        i = 0
        while i < n:
            if source[i] == '{':
                depth = 0
                in_str = False
                esc = False
                j = i
                while j < n:
                    ch = source[j]
                    if in_str:
                        if esc:
                            esc = False
                        elif ch == '\\':
                            esc = True
                        elif ch == '"':
                            in_str = False
                    else:
                        if ch == '"':
                            in_str = True
                        elif ch == '{':
                            depth += 1
                        elif ch == '}':
                            depth -= 1
                            if depth == 0:
                                segment = source[i : j + 1]
                                try:
                                    _try_add(json.loads(segment), segment)
                                except Exception:
                                    pass
                                break
                    j += 1
                i = j
            i += 1

    # 1) Fenced code blocks
    for block in re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE):
        _collect_from_string(block)

    # 2) Whole text
    _collect_from_string(text)

    if not candidates:
        return None

    def _score(item):
        raw, obj = item
        keys = {str(k).lower() for k in obj.keys()}
        has_promql = 1 if ("promql" in keys or "promqls" in keys) else 0
        has_summary = 1 if ("summary" in keys) else 0
        return (has_promql + has_summary, len(raw))

    best = max(candidates, key=_score)
    return best[1]

def get_models_helper() -> List[str]:
    """
    Get list of available vLLM models from Prometheus metrics.
    
    Returns:
        List of model names in format "namespace | model_name"
    """
    try:
        headers = _auth_headers()

        # Try multiple vLLM metrics with longer time windows
        vllm_metrics_to_check = [
            "vllm:request_prompt_tokens_created",
            "vllm:request_prompt_tokens_total",
            "vllm:avg_generation_throughput_toks_per_s",
            "vllm:num_requests_running",
            "vllm:gpu_cache_usage_perc",
        ]

        model_set = set()

        # Try different time windows: 7 days, 24 hours, 1 hour
        time_windows = [7 * 24 * 3600, 24 * 3600, 3600]  # 7 days, 24 hours, 1 hour

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
                        model = entry.get("model_name", "").strip()
                        namespace = entry.get("namespace", "").strip()
                        if model and namespace:
                            model_set.add(f"{namespace} | {model}")

                    # If we found models, return them
                    if model_set:
                        return sorted(list(model_set))

                except Exception as e:
                    logger.warning(
                        f"Error checking {metric_name} with {time_window}s window: {e}"
                    )
                    continue

        return sorted(list(model_set))
    except Exception as e:
        logger.error("Error getting models", exc_info=e)
        return []


def get_namespaces_helper() -> List[str]:
    """
    Get list of namespaces that have vLLM metrics available.

    Mirrors the logic used in the FastAPI /namespaces endpoint to ensure
    consistent behavior across API and MCP tools.

    Returns:
        Sorted list of namespace names
    """
    try:
        headers = _auth_headers()

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
        time_windows = [7 * 24 * 3600, 24 * 3600, 3600]

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

                    # If we found namespaces, return them immediately
                    if namespace_set:
                        return sorted(list(namespace_set))

                except Exception as e:
                    logger.warning(
                        f"Error checking {metric_name} with {time_window}s window: {e}"
                    )
                    continue

        return sorted(list(namespace_set))
    except Exception as e:
        logger.error("Error getting namespaces", exc_info=e)
        return []


def calculate_metric_stats(data):
    """
    Calculate basic statistics (average and max) from metric data.
    
    Args:
        data: List of dictionaries with 'value' and 'timestamp' keys
        
    Returns:
        Tuple of (average, max) or (None, None) for invalid data
    """
    if not data or data is None:
        return (None, None)
    
    try:
        values = [item.get("value") for item in data if "value" in item]
        if not values:
            return (None, None)
            
        avg = sum(values) / len(values)
        max_val = max(values)
        return (float(avg), float(max_val))
    except (TypeError, ValueError, KeyError):
        return (None, None)


# --- Metric Discovery Functions ---

def discover_vllm_metrics():
    """Dynamically discover available vLLM metrics from Prometheus, including GPU metrics"""
    try:
        headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/label/__name__/values",
            headers=headers,
            verify=VERIFY_SSL,
            timeout=30,  # Add timeout
        )
        response.raise_for_status()
        all_metrics = response.json()["data"]

        # Create friendly names for metrics
        metric_mapping = {}

        # First, add GPU metrics (DCGM) that are relevant for vLLM monitoring
        gpu_metrics = {
            "GPU Temperature (°C)": "DCGM_FI_DEV_GPU_TEMP",
            "GPU Power Usage (Watts)": "DCGM_FI_DEV_POWER_USAGE",
            "GPU Memory Usage (GB)": "DCGM_FI_DEV_FB_USED / (1024*1024*1024)",
            "GPU Energy Consumption (Joules)": "DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION",
            "GPU Memory Temperature (°C)": "DCGM_FI_DEV_MEMORY_TEMP",
            "GPU Utilization (%)": "DCGM_FI_DEV_GPU_UTIL",
        }

        for friendly_name, metric_name in gpu_metrics.items():
            # Handle expressions (like memory GB conversion) by checking base metric presence
            if friendly_name == "GPU Memory Usage (GB)":
                if "DCGM_FI_DEV_FB_USED" in all_metrics:
                    metric_mapping[friendly_name] = "avg(DCGM_FI_DEV_FB_USED) / (1024*1024*1024)"
                continue

            if metric_name in all_metrics:
                metric_mapping[friendly_name] = f"avg({metric_name})"

        # If vLLM GPU cache usage is unavailable, alias GPU Usage (%) to DCGM utilization
        if "GPU Usage (%)" not in metric_mapping and "DCGM_FI_DEV_GPU_UTIL" in all_metrics:
            metric_mapping["GPU Usage (%)"] = "avg(DCGM_FI_DEV_GPU_UTIL)"

        # Build vLLM-derived queries based on available metrics
        vllm_metrics = set(m for m in all_metrics if m.startswith("vllm:"))

        # Tokens - For dashboard display, prefer current totals over increases
        # This shows accumulated tokens rather than recent activity
        if "vllm:request_prompt_tokens_sum" in vllm_metrics:
            metric_mapping["Prompt Tokens Created"] = "vllm:request_prompt_tokens_sum"
        elif "vllm:prompt_tokens_total" in vllm_metrics:
            metric_mapping["Prompt Tokens Created"] = "sum(vllm:prompt_tokens_total)"
        elif "vllm:request_prompt_tokens_created" in vllm_metrics:
            metric_mapping["Prompt Tokens Created"] = "sum(increase(vllm:request_prompt_tokens_created[1h]))"
        elif "vllm:request_prompt_tokens_total" in vllm_metrics:
            metric_mapping["Prompt Tokens Created"] = "sum(increase(vllm:request_prompt_tokens_total[1h]))"

        if "vllm:request_generation_tokens_sum" in vllm_metrics:
            metric_mapping["Output Tokens Created"] = "vllm:request_generation_tokens_sum"
        elif "vllm:generation_tokens_total" in vllm_metrics:
            metric_mapping["Output Tokens Created"] = "sum(vllm:generation_tokens_total)"
        elif "vllm:request_generation_tokens_created" in vllm_metrics:
            metric_mapping["Output Tokens Created"] = "sum(increase(vllm:request_generation_tokens_created[1h]))"
        elif "vllm:request_generation_tokens_total" in vllm_metrics:
            metric_mapping["Output Tokens Created"] = "sum(increase(vllm:request_generation_tokens_total[1h]))"

        # Requests running (gauge)
        if "vllm:num_requests_running" in vllm_metrics:
            metric_mapping["Requests Running"] = "vllm:num_requests_running"

        # GPU cache usage percent exposed by vLLM (model-scoped proxy for GPU usage)
        # This is preferred over DCGM_FI_DEV_GPU_UTIL as it's model-specific
        if "vllm:gpu_cache_usage_perc" in vllm_metrics:
            metric_mapping["GPU Usage (%)"] = "avg(vllm:gpu_cache_usage_perc)"
        elif "vllm:gpu_memory_usage" in vllm_metrics:
            # Alternative vLLM GPU metric
            metric_mapping["GPU Usage (%)"] = "avg(vllm:gpu_memory_usage)"

        # P95 latency from histogram buckets
        if "vllm:e2e_request_latency_seconds_bucket" in vllm_metrics:
            metric_mapping["P95 Latency (s)"] = (
                "histogram_quantile(0.95, sum(rate(vllm:e2e_request_latency_seconds_bucket[5m])) by (le))"
            )

        # Inference time average = sum(rate(sum)) / sum(rate(count))
        if (
            "vllm:request_inference_time_seconds_sum" in vllm_metrics
            and "vllm:request_inference_time_seconds_count" in vllm_metrics
        ):
            metric_mapping["Inference Time (s)"] = (
                "sum(rate(vllm:request_inference_time_seconds_sum[5m])) / "
                "sum(rate(vllm:request_inference_time_seconds_count[5m]))"
            )

        # Add any other vLLM metrics with a generic friendly name if not already mapped
        for metric in vllm_metrics:
            if metric in (
                "vllm:request_prompt_tokens_created",
                "vllm:request_prompt_tokens_total",
                "vllm:request_generation_tokens_created",
                "vllm:request_generation_tokens_total",
                "vllm:num_requests_running",
                "vllm:e2e_request_latency_seconds_bucket",
                "vllm:request_inference_time_seconds_sum",
                "vllm:request_inference_time_seconds_count",
            ):
                continue
            friendly_name = metric.replace("vllm:", "").replace("_", " ").title()
            if friendly_name not in metric_mapping:
                metric_mapping[friendly_name] = metric

        return metric_mapping
    except Exception as e:
        logger.error("Error discovering vLLM metrics: %s", e)
        # Enhanced fallback with comprehensive GPU metrics and vLLM metrics
        return {
            "GPU Temperature (°C)": "avg(DCGM_FI_DEV_GPU_TEMP)",
            "GPU Power Usage (Watts)": "avg(DCGM_FI_DEV_POWER_USAGE)",
            "GPU Memory Usage (GB)": "avg(DCGM_FI_DEV_FB_USED) / (1024*1024*1024)",
            "GPU Energy Consumption (Joules)": "avg(DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION)",
            "GPU Memory Temperature (°C)": "avg(DCGM_FI_DEV_MEMORY_TEMP)",
            "GPU Usage (%)": "avg(DCGM_FI_DEV_GPU_UTIL)",
            "Prompt Tokens Created": "vllm:request_prompt_tokens_sum",
            "Output Tokens Created": "vllm:request_generation_tokens_sum",
            "Requests Running": "vllm:num_requests_running",
            "P95 Latency (s)": "histogram_quantile(0.95, sum(rate(vllm:e2e_request_latency_seconds_bucket[5m])) by (le))",
            "Inference Time (s)": "sum(rate(vllm:request_inference_time_seconds_sum[5m])) / sum(rate(vllm:request_inference_time_seconds_count[5m]))",
        }


def discover_dcgm_metrics():
    """Dynamically discover available GPU metrics (DCGM, nvidia_smi, or alternatives)"""
    try:
        headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/label/__name__/values",
            headers=headers,
            verify=VERIFY_SSL,
            timeout=30,  # Add timeout
        )
        response.raise_for_status()
        all_metrics = response.json()["data"]

        # Filter for different types of GPU metrics
        dcgm_metrics = [metric for metric in all_metrics if metric.startswith("DCGM_")]
        nvidia_metrics = [metric for metric in all_metrics if "nvidia" in metric.lower()]
        gpu_metrics = [metric for metric in all_metrics if "gpu" in metric.lower() and not metric.startswith("vllm:")]

        logger.info("Found %d DCGM metrics, %d NVIDIA metrics, %d GPU metrics", len(dcgm_metrics), len(nvidia_metrics), len(gpu_metrics))

        # Create a mapping of useful GPU metrics for fleet monitoring
        gpu_mapping = {}
        fb_used_metric = None

        # Priority 1: DCGM metrics (most comprehensive)
        for metric in dcgm_metrics:
            if "GPU_TEMP" in metric:
                gpu_mapping["GPU Temperature (°C)"] = f"avg({metric})"
            elif "POWER_USAGE" in metric:
                gpu_mapping["GPU Power Usage (Watts)"] = f"avg({metric})"
            elif "GPU_UTIL" in metric:
                gpu_mapping["GPU Utilization (%)"] = f"avg({metric})"
            elif "MEMORY_TEMP" in metric:
                gpu_mapping["GPU Memory Temperature (°C)"] = f"avg({metric})"
            elif "TOTAL_ENERGY_CONSUMPTION" in metric:
                gpu_mapping["GPU Energy Consumption (Joules)"] = f"avg({metric})"
            elif "FB_USED" in metric:
                fb_used_metric = metric
                gpu_mapping["GPU Memory Used (bytes)"] = f"avg({metric})"
            elif "FB_TOTAL" in metric:
                gpu_mapping["GPU Memory Total (bytes)"] = f"avg({metric})"
            elif "SM_CLOCK" in metric:
                gpu_mapping["GPU SM Clock (MHz)"] = f"avg({metric})"
            elif "MEM_CLOCK" in metric:
                gpu_mapping["GPU Memory Clock (MHz)"] = f"avg({metric})"

        # Add GPU Memory Usage in GB if we found the FB_USED metric
        if fb_used_metric:
            gpu_mapping["GPU Memory Usage (GB)"] = (
                f"avg({fb_used_metric}) / (1024*1024*1024)"
            )

        # Priority 2: nvidia-smi or alternative metrics if DCGM not available
        if not gpu_mapping:
            logger.info("No DCGM metrics found, checking for alternative GPU metrics...")
            
            # Look for common GPU metric patterns
            gpu_patterns = {
                "GPU Temperature (°C)": ["nvidia_smi_temperature", "gpu_temperature", "gpu_temp"],
                "GPU Utilization (%)": ["nvidia_smi_utilization", "gpu_utilization", "gpu_usage_percent"],
                "GPU Power Usage (Watts)": ["nvidia_smi_power", "gpu_power", "gpu_power_usage"],
                "GPU Memory Usage (%)": ["nvidia_smi_memory_used", "gpu_memory_usage", "gpu_mem_used"],
                "GPU Memory Free (bytes)": ["nvidia_smi_memory_free", "gpu_memory_free"],
                "GPU Fan Speed (%)": ["nvidia_smi_fan_speed", "gpu_fan"],
            }
            
            for friendly_name, pattern_list in gpu_patterns.items():
                for pattern in pattern_list:
                    matching_metrics = [m for m in all_metrics if pattern in m.lower()]
                    if matching_metrics:
                        # Use the first matching metric
                        gpu_mapping[friendly_name] = f"avg({matching_metrics[0]})"
                        logger.info("Found alternative GPU metric: %s -> %s", friendly_name, matching_metrics[0])
                        break

        # Priority 3: Generic GPU metrics
        if not gpu_mapping:
            logger.info("No specific GPU metrics found, checking for generic patterns...")
            for metric in gpu_metrics:
                metric_lower = metric.lower()
                if "temperature" in metric_lower or "temp" in metric_lower:
                    gpu_mapping["GPU Temperature"] = f"avg({metric})"
                elif "utilization" in metric_lower or "usage" in metric_lower:
                    gpu_mapping["GPU Utilization"] = f"avg({metric})"
                elif "power" in metric_lower:
                    gpu_mapping["GPU Power"] = f"avg({metric})"
                elif "memory" in metric_lower and "used" in metric_lower:
                    gpu_mapping["GPU Memory Used"] = f"avg({metric})"

        if gpu_mapping:
            logger.info("Successfully discovered %d GPU metrics", len(gpu_mapping))
        else:
            logger.warning("No GPU metrics found - cluster may not have GPUs or GPU monitoring")

        return gpu_mapping
    except Exception as e:
        logger.error("Error discovering GPU metrics", exc_info=e)
        return {}


def discover_openshift_metrics():
    """Return comprehensive OpenShift/Kubernetes metrics organized by category"""
    return {
        "Fleet Overview": {
            # Core cluster-wide metrics
            "Total Pods Running": "sum(kube_pod_status_phase{phase='Running'})",
            "Total Pods Failed": "sum(kube_pod_status_phase{phase='Failed'})",
            "Total Deployments": "sum(kube_deployment_status_replicas_ready)",
            "Cluster CPU Usage (%)": "100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[5m])) * 100)",
            "Cluster Memory Usage (%)": "100 - (sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes) * 100)",
            "Container Images": "count(count by (image)(container_spec_image))",
            "Total Services": "sum(kube_service_info)",
            "Total Nodes": "sum(kube_node_info)",
            # Key GPU metrics for fleet overview
            "GPU Utilization (%)": "avg(DCGM_FI_DEV_GPU_UTIL)",
            "GPU Temperature (°C)": "avg(DCGM_FI_DEV_GPU_TEMP)",
        },
        "Services & Networking": {
            # Services, ingress, and networking metrics
            "Services Running": "sum(kube_service_info)",
            "Service Endpoints": "sum(kube_endpoint_address_available)",
            "Ingress Rules": "sum(kube_ingress_info)",
            "Network Policies": "sum(kube_networkpolicy_labels)",
            "Load Balancer Services": "sum(kube_service_spec_type{type='LoadBalancer'})",
            "ClusterIP Services": "sum(kube_service_spec_type{type='ClusterIP'})",
        },
        "Jobs & Workloads": {
            # Jobs, cronjobs, and other workload types
            "Jobs Running": "sum(kube_job_status_active)",
            "Jobs Completed": "sum(kube_job_status_succeeded)",
            "Jobs Failed": "sum(kube_job_status_failed)", 
            "CronJobs": "sum(kube_cronjob_info)",
            "DaemonSets": "sum(kube_daemonset_status_number_ready)",
            "StatefulSets": "sum(kube_statefulset_status_replicas_ready)",
        },
        "Storage & Config": {
            # Storage and configuration resources
            "Persistent Volumes": "sum(kube_persistentvolume_info)",
            "PV Claims": "sum(kube_persistentvolumeclaim_info)",
            "ConfigMaps": "sum(kube_configmap_info)",
            "Secrets": "sum(kube_secret_info)",
            "Storage Classes": "sum(kube_storageclass_info)",
            "Volume Snapshots": "sum(kube_volumesnapshot_info)",
        },
        "Workloads & Pods": {
            # 6 most important pod/container metrics
            "Pods Running": "sum(kube_pod_status_phase{phase='Running'})",
            "Pods Pending": "sum(kube_pod_status_phase{phase='Pending'})",
            "Pods Failed": "sum(kube_pod_status_phase{phase='Failed'})",
            "Pod Restarts (Rate)": "sum(rate(kube_pod_container_status_restarts_total[5m]))",
            "Container CPU Usage": "sum(rate(container_cpu_usage_seconds_total[5m]))",
            "Container Memory Usage": "sum(container_memory_usage_bytes)",
        },
        "GPU & Accelerators": {
            # 🚀 Comprehensive GPU fleet monitoring with DCGM metrics
            "GPU Temperature (°C)": "avg(DCGM_FI_DEV_GPU_TEMP)",
            "GPU Power Usage (Watts)": "avg(DCGM_FI_DEV_POWER_USAGE)",
            "GPU Utilization (%)": "avg(DCGM_FI_DEV_GPU_UTIL)",
            "GPU Memory Usage (GB)": "avg(DCGM_FI_DEV_FB_USED) / (1024*1024*1024)",
            "GPU Energy Consumption (Joules)": "avg(DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION)",
            "GPU Memory Temperature (°C)": "avg(DCGM_FI_DEV_MEMORY_TEMP)",
        },
        "Storage & Networking": {
            # 6 storage and network metrics
            "PV Available Space": "sum(kube_persistentvolume_capacity_bytes)",
            "PVC Bound": "sum(kube_persistentvolumeclaim_status_phase{phase='Bound'})",
            "Storage I/O Rate": "sum(rate(container_fs_reads_total[5m]) + rate(container_fs_writes_total[5m]))",
            "Network Receive Rate": "sum(rate(container_network_receive_bytes_total[5m]))",
            "Network Transmit Rate": "sum(rate(container_network_transmit_bytes_total[5m]))",
            "Network Errors": "sum(rate(container_network_receive_errors_total[5m]) + rate(container_network_transmit_errors_total[5m]))",
        },
        "Application Services": {
            # 6 application-level metrics
            "HTTP Request Rate": "sum(rate(http_requests_total[5m]))",
            "HTTP Error Rate (%)": "sum(rate(http_requests_total{status=~'5..'}[5m])) / sum(rate(http_requests_total[5m])) * 100",
            "HTTP P95 Latency": "histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))",
            "Services Available": "sum(up)",
            "Ingress Request Rate": "sum(rate(nginx_ingress_controller_requests[5m]))",
            "Load Balancer Backends": "sum(haproxy_server_up)",
        },
    } 


# Cache discovered metrics to avoid repeated API calls
_vllm_metrics_cache = None
_openshift_metrics_cache = None
_cache_timestamp = None
CACHE_TTL = 300  # 5 minutes


def get_vllm_metrics():
    """Get vLLM metrics with caching"""
    global _vllm_metrics_cache, _cache_timestamp

    current_time = datetime.now().timestamp()
    if (
        _vllm_metrics_cache is None
        or _cache_timestamp is None
        or (current_time - _cache_timestamp) > CACHE_TTL
    ):
        _vllm_metrics_cache = discover_vllm_metrics()
        _cache_timestamp = current_time

    return _vllm_metrics_cache


def get_openshift_metrics():
    """Get OpenShift metrics with caching"""
    global _openshift_metrics_cache, _cache_timestamp

    current_time = datetime.now().timestamp()
    if (
        _openshift_metrics_cache is None
        or _cache_timestamp is None
        or (current_time - _cache_timestamp) > CACHE_TTL
    ):
        _openshift_metrics_cache = discover_openshift_metrics()
        _cache_timestamp = current_time

    return _openshift_metrics_cache


def discover_cluster_metrics_dynamically():
    """Dynamically discover cluster metrics from Prometheus"""
    try:
        headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/label/__name__/values",
            headers=headers,
            verify=VERIFY_SSL,
            timeout=30,
        )
        response.raise_for_status()
        all_metrics = response.json()["data"]

        # Filter for Kubernetes/OpenShift metrics
        cluster_metrics = {}
        kube_prefixes = ["kube_", "node_", "container_", "apiserver_", "etcd_", "scheduler_", "kubelet_"]
        
        for metric in all_metrics:
            if any(metric.startswith(prefix) for prefix in kube_prefixes):
                # Create a friendly name
                friendly_name = metric.replace("_", " ").title()
                cluster_metrics[friendly_name] = f"sum({metric})"

        # Limit to first 50 metrics to avoid overwhelming UI
        limited_metrics = dict(list(cluster_metrics.items())[:50])
        return limited_metrics
    except Exception as e:
        logger.error("Error discovering cluster metrics", exc_info=e)
        return {}


def get_all_metrics():
    """Get all available metrics (vLLM, OpenShift, GPU) combined"""
    all_metrics = {}
    
    # Add vLLM metrics
    vllm_metrics = get_vllm_metrics()
    for label, query in vllm_metrics.items():
        all_metrics[f"vLLM: {label}"] = query
    
    # Add GPU/DCGM metrics
    dcgm_metrics = discover_dcgm_metrics()
    for label, query in dcgm_metrics.items():
        all_metrics[f"GPU: {label}"] = query
    
    # Add OpenShift metrics (flattened from categories)
    openshift_metrics = get_openshift_metrics()
    for category, metrics in openshift_metrics.items():
        for label, query in metrics.items():
            all_metrics[f"OpenShift {category}: {label}"] = query
    
    return all_metrics


def get_namespace_specific_metrics(category):
    """Get metrics that actually have namespace labels for namespace-specific analysis"""

    namespace_aware_metrics = {
        "Fleet Overview": {
            # Metrics that work with namespace filtering
            "Deployment Replicas Ready": "sum(kube_deployment_status_replicas_ready)",
            "Pods Running": "sum(kube_pod_status_phase{phase='Running'})",
            "Pods Failed": "sum(kube_pod_status_phase{phase='Failed'})",
            "Container CPU Usage": "sum(rate(container_cpu_usage_seconds_total[5m]))",
            "Container Memory Usage": "sum(container_memory_usage_bytes)",
            "Pod Restart Rate": "sum(rate(kube_pod_container_status_restarts_total[5m]))",
        },
        "Workloads & Pods": {
            # Pod and container metrics naturally have namespace labels
            "Pods Running": "sum(kube_pod_status_phase{phase='Running'})",
            "Pods Pending": "sum(kube_pod_status_phase{phase='Pending'})",
            "Pods Failed": "sum(kube_pod_status_phase{phase='Failed'})",
            "Pod Restarts (Rate)": "sum(rate(kube_pod_container_status_restarts_total[5m]))",
            "Container CPU Usage": "sum(rate(container_cpu_usage_seconds_total[5m]))",
            "Container Memory Usage": "sum(container_memory_usage_bytes)",
        },
        "Compute & Resources": {
            # Container-level compute and resource metrics
            "Container CPU Throttling": "sum(container_cpu_cfs_throttled_seconds_total)",
            "Container Memory Failures": "sum(container_memory_failcnt)",
            "OOM Events": "sum(container_oom_events_total)",
            "Container Processes": "sum(container_processes)",
            "Container Threads": "sum(container_threads)",
            "Container File Descriptors": "sum(container_file_descriptors)",
        },
        "Storage & Networking": {
            # Storage and network metrics that have namespace context
            "PV Claims Bound": "sum(kube_persistentvolumeclaim_status_phase{phase='Bound'})",
            "PV Claims Pending": "sum(kube_persistentvolumeclaim_status_phase{phase='Pending'})",
            "Container Network Receive": "sum(rate(container_network_receive_bytes_total[5m]))",
            "Container Network Transmit": "sum(rate(container_network_transmit_bytes_total[5m]))",
            "Network Errors": "sum(rate(container_network_receive_errors_total[5m]) + rate(container_network_transmit_errors_total[5m]))",
            "Filesystem Usage": "sum(container_fs_usage_bytes)",
        },
        "Application Services": {
            # Application metrics that work at namespace level
            "HTTP Request Rate": "sum(rate(http_requests_total[5m]))",
            "HTTP Error Rate (%)": "sum(rate(http_requests_total{status=~'5..'}[5m])) / sum(rate(http_requests_total[5m])) * 100",
            "Available Endpoints": "sum(kube_endpoint_address_available)",
            "Container Processes": "sum(container_processes)",
            "Container File Descriptors": "sum(container_file_descriptors)",
            "Container Threads": "sum(container_threads)",
        },
    }

    return namespace_aware_metrics.get(category, {})


def _select_openshift_metrics_for_scope(
    metric_category: str,
    scope: str,
    namespace: Optional[str],
) -> Tuple[Dict[str, str], Optional[str]]:
    """Select metrics dict and namespace filter based on scope/category.

    Returns (metrics_to_fetch, namespace_for_query)
    """
    openshift_metrics = get_openshift_metrics()

    if scope == NAMESPACE_SCOPED and namespace:
        namespace_metrics = get_namespace_specific_metrics(metric_category)
        metrics_to_fetch = (
            namespace_metrics if namespace_metrics else openshift_metrics.get(metric_category, {})
        )
    else:
        metrics_to_fetch = openshift_metrics.get(metric_category, {})

    namespace_for_query = namespace if scope == NAMESPACE_SCOPED else None
    return metrics_to_fetch, namespace_for_query


def analyze_openshift_metrics(
    metric_category: str,
    scope: str,
    namespace: Optional[str],
    start_ts: int,
    end_ts: int,
    summarize_model_id: Optional[str],
    api_key: Optional[str],
) -> Dict[str, Any]:
    """
    Returns a dict matching the API response fields (health_prompt, llm_summary, metrics, etc.).
    Raises HTTPException for client (400) and server (500) errors.
    """
    metrics_to_fetch, namespace_for_query = _select_openshift_metrics_for_scope(
        metric_category, scope, namespace
    )

    # Fetch metrics; if Prometheus fails, raise immediately so MCP tool can surface PROMETHEUS_ERROR
    metric_dfs: Dict[str, Any] = {}
    try:
        for label, query in metrics_to_fetch.items():
            df = fetch_openshift_metrics(
                query,
                start_ts,
                end_ts,
                namespace_for_query,
            )
            metric_dfs[label] = df
    except requests.exceptions.RequestException:
        # Bubble up Prometheus errors unchanged; MCP layer maps them to PrometheusError
        raise
    # Build scope description
    scope_description = f"{scope.replace('_', ' ').title()}"
    if scope == NAMESPACE_SCOPED and namespace:
        scope_description += f" ({namespace})"

    # Build OpenShift metrics prompt
    prompt = build_openshift_prompt(
        metric_dfs, metric_category, namespace_for_query, scope_description
    )
    # Summarize; if LLM service fails, raise HTTPException to be mapped to LLMServiceError by MCP
    try:
        summary = summarize_with_llm(
            prompt, summarize_model_id or "", ResponseType.OPENSHIFT_ANALYSIS, api_key or ""
        )
    except requests.exceptions.RequestException:
        # Re-raise so MCP layer can classify as LLM service error
        raise
 
    # Serialize metric DataFrames
    serialized_metrics: Dict[str, Any] = {}
    for label, df in metric_dfs.items():
            if "timestamp" not in df.columns:
                df["timestamp"] = pd.Series(dtype="datetime64[ns]")
            if "value" not in df.columns:
                df["value"] = pd.Series(dtype="float")
            serialized_metrics[label] = df[["timestamp", "value"]].to_dict(orient="records")

    return {
        "metric_category": metric_category,
        "scope": scope,
        "namespace": namespace,
        "health_prompt": prompt,
        "llm_summary": summary,
        "metrics": serialized_metrics,
    }


def chat_openshift_metrics(
    metric_category: str,
    question: str,
    scope: str,
    namespace: Optional[str],
    start_ts: int,
    end_ts: int,
    summarize_model_id: Optional[str],
    api_key: Optional[str],
) -> Dict[str, Any]:
    """
    Build a chat-oriented OpenShift analysis:
    - Validates inputs (raises HTTPException on errors)
    - Fetches metrics per category/scope
    - Builds prompt and invokes LLM
    - Parses LLM JSON to extract promql and summary
    Returns dict with at least: {"promql": str, "summary": str}
    """
    # Select metrics without raising (validation is done by callers)
    metrics_to_fetch, namespace_for_query = _select_openshift_metrics_for_scope(
        metric_category, scope, namespace
    )
    metric_dfs: Dict[str, Any] = {}
    for label, query in metrics_to_fetch.items():
        # Allow Prometheus connectivity/request exceptions to propagate so callers
        # (e.g., MCP tools) can surface structured PROMETHEUS_ERROR instead of
        # falling back to a generic "no data" message.
        df = fetch_openshift_metrics(query, start_ts, end_ts, namespace_for_query)
        metric_dfs[label] = df

    # If no data at all, avoid LLM call and return helpful message
    has_any_data = any(isinstance(df, pd.DataFrame) and not df.empty for df in metric_dfs.values())
    if not has_any_data:
        return {
            "promql": "",
            "summary": (
                "No metric data found for the selected category/scope in the time window. "
                "Try a broader window (e.g., last 6h) or a different category."
            ),
        }

    # Build scope description and prompt
    scope_description = f"{scope.replace('_', ' ').title()}"
    if scope == NAMESPACE_SCOPED and namespace:
        scope_description += f" ({namespace})"

    metrics_data_summary = build_openshift_metrics_context(
        metric_dfs, metric_category, namespace_for_query, scope_description
    )

    chat_scope_value = "fleet_wide" if scope == CLUSTER_WIDE else "namespace_specific"
    prompt = build_openshift_chat_prompt(
        question=question,
        metrics_context=metrics_data_summary,
        time_range_info=None,
        chat_scope=chat_scope_value,
        target_namespace=namespace_for_query if scope == NAMESPACE_SCOPED else None,
        alerts_context="",
    )

    llm_response = summarize_with_llm(
        prompt, summarize_model_id or "", ResponseType.OPENSHIFT_ANALYSIS, api_key or ""
    )
    # Parse JSON content robustly (handles extra text and fenced code blocks)
    promql = ""
    summary = llm_response
    parsed = extract_first_json_object_from_text(llm_response)
    if isinstance(parsed, dict):
        # Allow both a single promql and a list of promqls (take first)
        promql_value = parsed.get("promql")
        if not promql_value and isinstance(parsed.get("promqls"), list) and parsed["promqls"]:
            promql_value = parsed["promqls"][0]
        promql = (promql_value or "").strip() if isinstance(promql_value, str) else (promql_value or "")
        if not isinstance(promql, str):
            promql = ""
        summary = (parsed.get("summary") or llm_response).strip()

        # Add namespace filter when needed
        if promql and namespace and "namespace=" not in promql:
            if "{" in promql:
                promql = promql.replace("{", f'{{namespace="{namespace}", ', 1)
            else:
                promql = f'{promql}{{namespace="{namespace}"}}'
    return {
        "promql": promql,
        "summary": summary,
    }

# --- Metric Fetching Functions ---

def fetch_metrics(query, model_name, start, end, namespace=None):
    """Fetch metrics from Prometheus for vLLM models"""
    promql_query = query

    # Inject labels for vLLM metrics inside rate()/histogram_quantile expressions
    def _inject_labels(expr: str, model: str, ns: Optional[str]) -> str:
        # Helper to build label matcher
        if "|" in model:
            model_ns, actual_model = map(str.strip, model.split("|", 1))
        else:
            model_ns, actual_model = None, model.strip()

        ns_value = (ns or model_ns or "").strip()
        label_clause = f'model_name="{actual_model}"' + (f', namespace="{ns_value}"' if ns_value else "")

        # Match complete vllm metric names that don't already have labels
        # Use inline lambda to make the dependency on label_clause explicit
        expr = re.sub(
            r"\b(vllm:[\w:]+)(?!\{)",
            lambda m: f"{m.group(1)}{{{label_clause}}}",
            expr,
        )
        
        return expr

    # GPU metrics are global; inject only for vLLM metrics
    if "vllm:" in promql_query:
        promql_query = _inject_labels(promql_query, model_name, namespace)

    headers = _auth_headers()
    try:
        step = choose_prometheus_step(start, end)
        logger.debug("Fetching Prometheus metrics for vLLM, query: %s, start: %s, end: %s: step: %s", query, start, end, step)
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            headers=headers,
            params={"query": promql_query, "start": start, "end": end, "step": step},
            verify=VERIFY_SSL,
            timeout=30,  # Add timeout
        )
        response.raise_for_status()
        result = response.json()["data"]["result"]

    except requests.exceptions.ConnectionError as e:
        logger.warning("Prometheus connection error for query '%s': %s", promql_query, e)
        return pd.DataFrame()  # Return empty DataFrame on connection error
    except requests.exceptions.Timeout as e:
        logger.warning("Prometheus timeout for query '%s': %s", promql_query, e)
        return pd.DataFrame()  # Return empty DataFrame on timeout
    except requests.exceptions.RequestException as e:
        logger.warning("Prometheus request error for query '%s': %s", promql_query, e)
        return pd.DataFrame()  # Return empty DataFrame on other request errors

    rows = []
    for series in result:
        for val in series["values"]:
            ts = datetime.fromtimestamp(float(val[0]))
            value = float(val[1])

            # Handle NaN values that can't be JSON serialized
            if pd.isna(value) or value != value:  # Check for NaN
                value = 0.0  # Convert NaN to 0 for JSON compatibility

            row = dict(series["metric"])
            row["timestamp"] = ts
            row["value"] = value
            rows.append(row)

    return pd.DataFrame(rows)


def fetch_openshift_metrics(query, start, end, namespace=None):
    """Fetch OpenShift metrics with optional namespace filtering.

    Network/request exceptions are raised to allow callers (e.g., MCP tools)
    to convert them into structured errors for the UI.
    """
    headers = _auth_headers()
    # Add namespace filter to the query if specified
    if namespace:
        # Skip if namespace already exists in the query
        if f'namespace="{namespace}"' in query:
            pass  # Already has the correct namespace
        else:
            # Simple string replacements for common patterns

            # Pattern 1: sum(metric_name)
            pattern1 = r"sum\(([a-zA-Z_:][a-zA-Z0-9_:]*)\)"
            if re.search(pattern1, query):
                query = re.sub(pattern1, f'sum(\\1{{namespace="{namespace}"}})', query)

            # Pattern 2: sum(rate(metric_name[5m]))
            elif re.search(r"sum\(rate\([a-zA-Z_:][a-zA-Z0-9_:]*\[[^\]]+\]\)\)", query):
                pattern2 = r"sum\(rate\(([a-zA-Z_:][a-zA-Z0-9_:]*)\[([^\]]+)\]\)\)"
                query = re.sub(
                    pattern2, f'sum(rate(\\1{{namespace="{namespace}"}}[\\2]))', query
                )

            # Pattern 3: rate(metric_name[5m])
            elif re.search(r"rate\([a-zA-Z_:][a-zA-Z0-9_:]*\[[^\]]+\]\)", query):
                pattern3 = r"rate\(([a-zA-Z_:][a-zA-Z0-9_:]*)\[([^\]]+)\]\)"
                query = re.sub(
                    pattern3, f'rate(\\1{{namespace="{namespace}"}}[\\2])', query
                )

            # Pattern 4: metric_name{existing_labels}
            elif re.search(r"[a-zA-Z_:][a-zA-Z0-9_:]*\{[^}]*\}", query):
                pattern4 = r"([a-zA-Z_:][a-zA-Z0-9_:]*)\{([^}]*)\}"
                query = re.sub(pattern4, f'\\1{{namespace="{namespace}",\\2}}', query)

            # Pattern 5: simple metric_name (no labels)
            elif re.search(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$", query):
                query = f'{query}{{namespace="{namespace}"}}'

            # Pattern 6: handle other aggregations (avg, count, etc.)
            else:
                for func in ["avg", "count", "max", "min"]:
                    pattern = f"{func}\\(([a-zA-Z_:][a-zA-Z0-9_:]*)\\)"
                    if re.search(pattern, query):
                        query = re.sub(
                            pattern, f'{func}(\\1{{namespace="{namespace}"}})', query
                        )
                        break

    try:
        step = choose_prometheus_step(start, end)
        logger.debug("Fetching Prometheus metrics for OpenShift, query: %s, start: %s, end: %s: step: %s", query, start, end, step)
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            headers=headers,
            params={"query": query, "start": start, "end": end, "step": step},
            verify=VERIFY_SSL,
            timeout=30,  # Add timeout
        )
        response.raise_for_status()
        result = response.json()["data"]["result"]
        logger.debug("Metrics fetched successfully")
    except requests.exceptions.ConnectionError as e:
        logger.warning("Prometheus connection error for OpenShift query '%s': %s", query, e)
        raise
    except requests.exceptions.Timeout as e:
        logger.warning("Prometheus timeout for OpenShift query '%s': %s", query, e)
        raise
    except requests.exceptions.RequestException as e:
        logger.warning("Prometheus request error for OpenShift query '%s': %s", query, e)
        raise

    rows = []
    for series in result:
        for val in series["values"]:
            ts = datetime.fromtimestamp(float(val[0]))
            value = float(val[1])

            # Handle NaN values that can't be JSON serialized
            if pd.isna(value) or value != value:  # Check for NaN
                value = 0.0  # Convert NaN to 0 for JSON compatibility

            row = dict(series["metric"])
            row["timestamp"] = ts
            row["value"] = value
            rows.append(row)

    return pd.DataFrame(rows) 