#!/usr/bin/env python3
"""
Core PromQL Generation Service
Moved from metrics_api.py to separate business logic
"""

import os
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import requests

# Import configuration
from .config import PROMETHEUS_URL, THANOS_TOKEN, VERIFY_SSL as verify

def generate_promql_from_question(question: str, namespace: Optional[str], model_name: str, start_ts: int, end_ts: int, is_fleet_wide: bool = False) -> List[str]:
    """
    ENHANCED: Dynamically generate PromQL using intelligent context-aware system
    Falls back to existing pattern matching if enhanced system fails
    """
    question_lower = question.lower()
    queries = []
    
    print(f"🔍 Analyzing question: {question}")
    
    # Calculate time range duration for dynamic intervals
    duration_seconds = end_ts - start_ts
    duration_hours = duration_seconds / 3600
    
    # Smart interval selection based on time range
    if duration_hours <= 1:
        rate_interval = "5m"  # For 1 hour, use 5m intervals (12 data points)
    elif duration_hours <= 6:
        rate_interval = "15m"  # For up to 6 hours, use 15m intervals
    elif duration_hours <= 24:
        rate_interval = "1h"  # For up to a day, use 1h intervals
    else:
        rate_interval = "6h"   # For longer periods, use 6h intervals
    
    print(f"📊 Time range: {duration_hours:.1f} hours, using interval: {rate_interval}")
    print(f"🌐 Scope: {'Fleet-wide' if is_fleet_wide else f'Namespace: {namespace}'}")
    
    # STEP 1: Try Enhanced Dynamic System First (TEMPORARILY DISABLED)
    # try:
    #     import sys
    #     api_dir = os.path.join(os.path.dirname(__file__), '..', 'api')
    #     sys.path.insert(0, api_dir)
    #     from enhanced_metrics import enhanced_promql_generation
    #     
    #     enhanced_queries = enhanced_promql_generation(question, namespace or "m3", is_fleet_wide)
    #     if enhanced_queries:
    #         print(f"🧠 Enhanced system generated {len(enhanced_queries)} queries")
    #         queries.extend(enhanced_queries)
    #         
    #         # If enhanced system succeeded, return those queries (skip fallback)
    #         if queries:
    #             return queries
    #             
    # except Exception as e:
    #     print(f"⚠️ Enhanced system failed, falling back to original: {e}")
    print("⚠️ Enhanced system temporarily disabled, using direct pattern matching")
    
    # STEP 2: Fallback to Original System
    print("🔄 Using original pattern matching system...")
    
    # Step 1: Discover available metrics from Thanos
    available_metrics = discover_available_metrics_from_thanos(namespace, model_name, is_fleet_wide)
    print(f"🔍 Discovered {len(available_metrics)} available metrics")
    
    # Step 2: Direct pattern matching (simple and reliable)
    selected_queries, pattern_detected = select_queries_directly(question_lower, namespace, model_name, rate_interval, is_fleet_wide)
    print(f"🎯 Selected {len(selected_queries)} direct queries")
    
    # Step 3: Add the selected queries
    for query in selected_queries:
        if query and query not in queries:
            queries.append(query)
    
    # If no specific metrics discovered/selected, add intelligent defaults
    # But DON'T add defaults if user asked a SPECIFIC question that was successfully detected
    if len(queries) == 0 or (len(queries) == 1 and not pattern_detected):
        print("🔧 No specific metrics discovered, adding basic defaults")
        if is_fleet_wide:
            default_queries = [
                f'vllm:num_requests_running{{model_name="{model_name}"}}',  # No namespace filter
                'sum(kube_pod_status_phase{phase="Running"})',  # No namespace filter
                'avg(DCGM_FI_DEV_GPU_UTIL)'
            ]
        else:
            default_queries = [
                f'vllm:num_requests_running{{namespace="{namespace}", model_name="{model_name}"}}',
                f'sum(kube_pod_status_phase{{phase="Running", namespace="{namespace}"}})',
                f'avg(DCGM_FI_DEV_GPU_UTIL)'
            ]
        queries.extend(default_queries)
    
    return queries[:6]  # Limit to 6 queries


def extract_time_period_from_question(question: str) -> Optional[str]:
    """
    Extract time periods mentioned in the question and convert to PromQL rate intervals
    Examples: "1 hour" -> "1h", "30 minutes" -> "30m", "1.5 hours" -> "1h30m"
    """
    import re
    
    question_lower = question.lower()
    
    # Pattern matching for various time formats
    patterns = [
        # "1 hour", "2 hours", "1.5 hours" 
        (r'(\d+(?:\.\d+)?)\s*(?:hour|hr|hrs|hours)', lambda m: f"{int(float(m.group(1)) * 60)}m" if float(m.group(1)) < 1 else f"{int(float(m.group(1)))}h"),
        
        # "30 minutes", "45 mins"
        (r'(\d+(?:\.\d+)?)\s*(?:minute|min|mins|minutes)', lambda m: f"{int(float(m.group(1)))}m"),
        
        # "2 days", "1 day" 
        (r'(\d+(?:\.\d+)?)\s*(?:day|days)', lambda m: f"{int(float(m.group(1)) * 24)}h"),
        
        # "1h", "30m", "2d" (already in PromQL format)
        (r'(\d+(?:\.\d+)?[hdm])', lambda m: m.group(1)),
    ]
    
    for pattern, converter in patterns:
        match = re.search(pattern, question_lower)
        if match:
            try:
                result = converter(match)
                print(f"🕐 Extracted time period: '{match.group(0)}' -> '{result}'")
                return result
            except:
                continue
    
    return None


def select_queries_directly(question: str, namespace: Optional[str], model_name: str, rate_interval: str, is_fleet_wide: bool) -> tuple[List[str], bool]:
    """
    Direct pattern matching for reliable metric selection - simple and effective approach
    """
    queries = []
    question_lower = question.lower()
    pattern_detected = False  # Track if we successfully detect a specific pattern
    
    # Extract time period from question text for PromQL rate intervals
    question_rate_interval = extract_time_period_from_question(question_lower) or rate_interval
    print(f"🕐 Using rate interval: {question_rate_interval} (from question: {extract_time_period_from_question(question_lower) is not None})")
    
    # Helper function for clean label construction
    def get_vllm_labels():
        """Generate labels for vLLM metrics"""
        if is_fleet_wide:
            return f'{{model_name="{model_name}"}}' if model_name else ""
        else:
            return f'{{namespace="{namespace}", model_name="{model_name}"}}' if model_name else f'{{namespace="{namespace}"}}'
    
    # === ALERTS (HIGH PRIORITY) ===
    
    if any(word in question_lower for word in ["alert", "alerts", "firing", "warning", "critical", "yesterday", "problem", "issue"]):
        print("🎯 Detected: Alerts question")
        pattern_detected = True
        if is_fleet_wide:
            queries.append("ALERTS")  # No namespace filter for fleet-wide
        else:
            queries.append(f'ALERTS{{namespace="{namespace}"}}')  # Namespace-specific alerts
    
    # === vLLM METRICS ===
    
    # Latency patterns
    elif any(word in question_lower for word in ["latency", "p95", "p99", "percentile", "response time", "slow", "fast"]):
        print("🎯 Detected: Latency question")
        pattern_detected = True
        # Use _count metric as user specifically requested
        labels = get_vllm_labels()
        queries.append(f"rate(vllm:e2e_request_latency_seconds_count{labels}[{question_rate_interval}])")
    
    # Request patterns (specifically for vLLM requests, not Kubernetes pods)
    elif any(word in question_lower for word in ["vllm request", "model request", "inference request", "llm request"]):
        print("🎯 Detected: vLLM Request question")
        pattern_detected = True
        labels = get_vllm_labels()
        queries.append(f"vllm:num_requests_running{labels}")
    
    # Token patterns
    elif any(word in question_lower for word in ["token", "tokens", "prompt", "generation", "output"]):
        print("🎯 Detected: Token question")
        pattern_detected = True
        labels = get_vllm_labels()
        if "prompt" in question_lower:
            queries.append(f"sum(rate(vllm:request_prompt_tokens_created{labels}[{question_rate_interval}]))")
        elif "output" in question_lower or "generation" in question_lower:
            queries.append(f"sum(rate(vllm:request_generation_tokens_created{labels}[{question_rate_interval}]))")
        else:
            queries.append(f"sum(rate(vllm:request_prompt_tokens_created{labels}[{question_rate_interval}]))")
    
    # === GPU METRICS ===
    
    elif any(word in question_lower for word in ["gpu", "temperature", "utilization", "power"]):
        print("🎯 Detected: GPU question")
        pattern_detected = True
        if "temperature" in question_lower:
            queries.append("avg(DCGM_FI_DEV_GPU_TEMP)")
        elif "utilization" in question_lower or "usage" in question_lower:
            queries.append("avg(DCGM_FI_DEV_GPU_UTIL)")
        elif "power" in question_lower:
            queries.append("avg(DCGM_FI_DEV_POWER_USAGE)")
        else:
            # Default GPU question - show utilization
            queries.append("avg(DCGM_FI_DEV_GPU_UTIL)")
    
    # === KUBERNETES/OPENSHIFT METRICS ===
    
    elif any(word in question_lower for word in ["pod", "pods", "number of pods", "how many pods"]):
        print("🎯 Detected: Pod question")
        pattern_detected = True
        
        # Enhanced pod phase detection
        detected_phase = "Running"  # default
        
        if any(word in question_lower for word in ["running", "active", "up", "healthy"]):
            detected_phase = "Running"
        elif any(word in question_lower for word in ["failed", "failing", "crashed", "error", "broken"]):
            detected_phase = "Failed"
        elif any(word in question_lower for word in ["pending", "waiting", "queued", "starting"]):
            detected_phase = "Pending"
        elif any(word in question_lower for word in ["succeeded", "completed", "finished"]):
            detected_phase = "Succeeded"
        
        print(f"🔍 Detected pod phase: {detected_phase}")
        
        if is_fleet_wide:
            queries.append(f'sum(kube_pod_status_phase{{phase="{detected_phase}"}})')
        else:
            queries.append(f'sum(kube_pod_status_phase{{phase="{detected_phase}", namespace="{namespace}"}})')
    
    # Deployment patterns
    elif any(word in question_lower for word in ["deployment", "deployments", "deploy"]):
        print("🎯 Detected: Deployment question")
        pattern_detected = True
        if is_fleet_wide:
            queries.append("count(kube_deployment_status_replicas)")
        else:
            queries.append(f'count(kube_deployment_status_replicas{{namespace="{namespace}"}})')
    
    # Service patterns
    elif any(word in question_lower for word in ["service", "services", "svc"]):
        print("🎯 Detected: Service question")
        pattern_detected = True
        if is_fleet_wide:
            queries.append("count(kube_service_info)")
        else:
            queries.append(f'count(kube_service_info{{namespace="{namespace}"}})')
    
    # Node patterns
    elif any(word in question_lower for word in ["node", "nodes"]):
        print("🎯 Detected: Node question")
        pattern_detected = True
        queries.append("count(kube_node_status_condition{condition='Ready',status='true'})")
    
    # === NETWORK METRICS ===
    
    elif any(word in question_lower for word in ["network", "bandwidth", "traffic", "connection"]):
        print("🎯 Detected: Network question")
        pattern_detected = True
        queries.append("rate(container_network_receive_bytes_total[5m])")
    
    # === MEMORY METRICS ===
    
    elif any(word in question_lower for word in ["memory", "mem", "ram"]):
        print("🎯 Detected: Memory question")
        pattern_detected = True
        queries.append("container_memory_usage_bytes")
    
    # === CPU METRICS ===
    
    elif any(word in question_lower for word in ["cpu", "processor"]):
        print("🎯 Detected: CPU question")
        pattern_detected = True
        queries.append("rate(container_cpu_usage_seconds_total[5m])")
    
    # === STORAGE METRICS ===
    
    elif any(word in question_lower for word in ["storage", "disk", "volume", "persistent"]):
        print("🎯 Detected: Storage question")
        pattern_detected = True
        queries.append("kubelet_volume_stats_used_bytes")
    
    # === GENERIC/UNKNOWN PATTERNS ===
    
    else:
        print("❓ No specific pattern detected, using intelligent defaults")
        # Add some intelligent defaults based on the namespace
        if is_fleet_wide:
            queries.extend([
                f'vllm:num_requests_running{{model_name="{model_name}"}}',  # vLLM requests
                'sum(kube_pod_status_phase{phase="Running"})',  # Running pods
                'avg(DCGM_FI_DEV_GPU_UTIL)'  # GPU utilization
            ])
        else:
            queries.extend([
                f'vllm:num_requests_running{{namespace="{namespace}", model_name="{model_name}"}}',  # vLLM requests
                f'sum(kube_pod_status_phase{{phase="Running", namespace="{namespace}"}})',  # Running pods
                f'avg(DCGM_FI_DEV_GPU_UTIL)'  # GPU utilization
            ])
    
    print(f"📝 Generated {len(queries)} queries: {queries}")
    return queries, pattern_detected


def discover_available_metrics_from_thanos(namespace: Optional[str], model_name: str, is_fleet_wide: bool) -> List[Dict[str, Any]]:
    """
    1. Fetch ALL metrics from cluster
    2. Categorize EVERYTHING  
    3. Return comprehensive categorized list
    """
    try:
        headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
        
        # Step 1: Get ALL available metric names from cluster
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/label/__name__/values",
            headers=headers,
            verify=verify,
            timeout=30
        )
        response.raise_for_status()
        all_metric_names = response.json()["data"]
        
        print(f"📋 Found {len(all_metric_names)} total metrics in Thanos")
        
        # Step 2: Categorize ALL metrics (not just filtered subset)
        categorized_metrics = []
        
        for metric_name in all_metric_names:
            metric_info = categorize_any_metric(metric_name, namespace, model_name, is_fleet_wide)
            if metric_info:  # Only add if we can categorize it
                categorized_metrics.append(metric_info)
        
        print(f"🏷️  Categorized {len(categorized_metrics)} metrics into types")
        return categorized_metrics
        
    except Exception as e:
        print(f"❌ Error discovering metrics from Thanos: {e}")
        return []


def categorize_any_metric(metric_name: str, namespace: Optional[str], model_name: str, is_fleet_wide: bool) -> Optional[Dict[str, Any]]:
    """
    Comprehensive categorization of ANY metric from the cluster
    """
    # Convert to lowercase for pattern matching
    name_lower = metric_name.lower()
    
    # === vLLM/LLM Metrics (HIGHEST PRIORITY) ===
    if metric_name.startswith("vllm:") or "llm" in name_lower:
        return categorize_vllm_metric(metric_name, namespace, model_name, is_fleet_wide)
    
    # === Prometheus/Monitoring Metrics (HIGH PRIORITY - before generic latency) ===
    elif metric_name.startswith("prometheus_") or metric_name.startswith("alertmanager_"):
        return categorize_monitoring_metric(metric_name)
    
    # === Alerting Metrics ===
    elif metric_name == "ALERTS" or "alert" in name_lower:
        return {
            "name": metric_name,
            "type": "alerts",
            "category": "alerting",
            "description": "System alerts and notifications"
        }
    
    # === Kubernetes/OpenShift Metrics ===
    elif metric_name.startswith("kube_") or metric_name.startswith("openshift_"):
        return categorize_k8s_metric(metric_name, namespace, is_fleet_wide)
    
    # === GPU/Hardware Metrics ===
    elif metric_name.startswith("DCGM_") or "gpu" in name_lower or "nvidia" in name_lower:
        return categorize_gpu_metric(metric_name)
    
    # === Container/Docker Metrics ===
    elif metric_name.startswith("container_"):
        return categorize_container_metric(metric_name)
    
    # === Node/System Metrics ===
    elif metric_name.startswith("node_"):
        return categorize_node_metric(metric_name)
    
    # === Network Metrics ===
    elif any(net_keyword in name_lower for net_keyword in ["network", "net_", "tcp_", "udp_", "http_"]):
        return categorize_network_metric(metric_name)
    
    # === Storage/Disk Metrics ===
    elif any(storage_keyword in name_lower for storage_keyword in ["disk_", "filesystem_", "storage_", "volume_"]):
        return categorize_storage_metric(metric_name)
    
    # === Application/Custom Metrics (LOWER PRIORITY) ===
    elif any(app_keyword in name_lower for app_keyword in ["request", "response", "latency", "error", "rate", "duration"]):
        return categorize_application_metric(metric_name)
    
    # === Generic/Unknown Metrics ===
    else:
        return categorize_generic_metric(metric_name)


def categorize_container_metric(metric_name: str) -> Optional[Dict[str, Any]]:
    """Categorize container-related metrics"""
    if any(prefix in metric_name for prefix in ["container_", "cadvisor_"]):
        return {
            "name": metric_name,
            "type": "container",
            "category": "container_metric",
            "description": f"Container metric: {metric_name}"
        }
    return None


def categorize_node_metric(metric_name: str) -> Optional[Dict[str, Any]]:
    """Categorize node-related metrics"""
    if "node" in metric_name.lower():
        return {
            "name": metric_name,
            "type": "node",
            "category": "node_metric",
            "description": f"Node metric: {metric_name}"
        }
    return None


def categorize_network_metric(metric_name: str) -> Optional[Dict[str, Any]]:
    """Categorize network-related metrics"""
    if any(word in metric_name.lower() for word in ["network", "net_", "tcp_", "udp_", "http_"]):
        return {
            "name": metric_name,
            "type": "network",
            "category": "network_metric",
            "description": f"Network metric: {metric_name}"
        }
    return None


def categorize_storage_metric(metric_name: str) -> Optional[Dict[str, Any]]:
    """Categorize storage-related metrics"""
    if any(word in metric_name.lower() for word in ["disk_", "filesystem_", "storage_", "volume_"]):
        return {
            "name": metric_name,
            "type": "storage",
            "category": "storage_metric",
            "description": f"Storage metric: {metric_name}"
        }
    return None


def categorize_application_metric(metric_name: str) -> Optional[Dict[str, Any]]:
    """Categorize application-related metrics"""
    if any(word in metric_name.lower() for word in ["request", "response", "latency", "error", "rate", "duration"]):
        return {
            "name": metric_name,
            "type": "application",
            "category": "application_metric",
            "description": f"Application metric: {metric_name}"
        }
    return None


def categorize_monitoring_metric(metric_name: str) -> Optional[Dict[str, Any]]:
    """Categorize monitoring-related metrics"""
    if any(word in metric_name.lower() for word in ["prometheus_", "thanos_", "alert"]):
        return {
            "name": metric_name,
            "type": "monitoring",
            "category": "monitoring_metric",
            "description": f"Monitoring metric: {metric_name}"
        }
    return None


def categorize_generic_metric(metric_name: str) -> Optional[Dict[str, Any]]:
    """Categorize generic metrics"""
    return {
        "name": metric_name,
        "type": "generic",
        "category": "generic_metric",
        "description": f"Generic metric: {metric_name}"
    }


def categorize_vllm_metric(metric_name: str, namespace: Optional[str], model_name: str, is_fleet_wide: bool) -> Optional[Dict[str, Any]]:
    """
    Categorize vLLM-specific metrics with enhanced context
    """
    if not metric_name.startswith("vllm:"):
        return None
    
    # Extract metric family
    metric_family = metric_name.split(":")[1] if ":" in metric_name else metric_name
    
    # Define vLLM metric categories
    vllm_categories = {
        "num_requests_running": {
            "type": "gauge",
            "description": "Number of requests currently running",
            "aggregation": "avg",
            "priority": 1
        },
        "num_requests_total": {
            "type": "counter", 
            "description": "Total number of requests processed",
            "aggregation": "rate",
            "priority": 1
        },
        "e2e_request_latency_seconds": {
            "type": "histogram",
            "description": "End-to-end request latency",
            "aggregation": "histogram_quantile",
            "priority": 1
        },
        "num_prompt_tokens_total": {
            "type": "counter",
            "description": "Total number of prompt tokens processed",
            "aggregation": "rate", 
            "priority": 2
        },
        "num_generation_tokens_total": {
            "type": "counter",
            "description": "Total number of generation tokens produced",
            "aggregation": "rate",
            "priority": 2
        },
        "num_requests_waiting": {
            "type": "gauge",
            "description": "Number of requests waiting in queue",
            "aggregation": "avg",
            "priority": 2
        }
    }
    
    # Find matching category
    for pattern, category_info in vllm_categories.items():
        if pattern in metric_family:
            return {
                "name": metric_name,
                "type": "vllm",
                "categories": ["model_metric", "vllm_metric"],
                "description": category_info["description"],
                "aggregation": category_info["aggregation"],
                "priority": category_info["priority"],
                "metric_family": metric_family
            }
    
    # Generic vLLM metric
    return {
        "name": metric_name,
        "type": "vllm",
        "categories": ["model_metric", "vllm_metric"],
        "description": f"vLLM metric: {metric_family}",
        "aggregation": "avg",
        "priority": 3
    }


def categorize_k8s_metric(metric_name: str, namespace: Optional[str], is_fleet_wide: bool) -> Optional[Dict[str, Any]]:
    """
    Categorize Kubernetes-specific metrics
    """
    if not metric_name.startswith("kube_"):
        return None
    
    # Extract resource type from metric name
    resource_types = ["pod", "deployment", "service", "node", "namespace", "pvc", "job"]
    
    for resource_type in resource_types:
        if f"kube_{resource_type}" in metric_name:
            return {
                "name": metric_name,
                "type": "kubernetes",
                "categories": ["kubernetes_metric", f"{resource_type}_metric"],
                "description": f"Kubernetes {resource_type} metric: {metric_name}",
                "resource_type": resource_type
            }
    
    return None


def categorize_gpu_metric(metric_name: str) -> Optional[Dict[str, Any]]:
    """
    Categorize GPU-specific metrics
    """
    if not metric_name.startswith("DCGM_"):
        return None
    
    # Define GPU metric categories
    gpu_categories = {
        "DCGM_FI_DEV_GPU_TEMP": {
            "type": "gauge",
            "description": "GPU temperature",
            "aggregation": "avg",
            "unit": "celsius"
        },
        "DCGM_FI_DEV_GPU_UTIL": {
            "type": "gauge", 
            "description": "GPU utilization",
            "aggregation": "avg",
            "unit": "percent"
        },
        "DCGM_FI_DEV_MEM_COPY_UTIL": {
            "type": "gauge",
            "description": "GPU memory copy utilization", 
            "aggregation": "avg",
            "unit": "percent"
        },
        "DCGM_FI_DEV_GPU_MEM_COPY_THROUGHPUT_UTIL": {
            "type": "gauge",
            "description": "GPU memory copy throughput utilization",
            "aggregation": "avg", 
            "unit": "percent"
        }
    }
    
    # Find matching category
    for pattern, category_info in gpu_categories.items():
        if pattern in metric_name:
            return {
                "name": metric_name,
                "type": "gpu",
                "categories": ["hardware_metric", "gpu_metric"],
                "description": category_info["description"],
                "aggregation": category_info["aggregation"],
                "unit": category_info["unit"]
            }
    
    # Generic GPU metric
    return {
        "name": metric_name,
        "type": "gpu", 
        "categories": ["hardware_metric", "gpu_metric"],
        "description": f"GPU metric: {metric_name}",
        "aggregation": "avg"
    }


def intelligent_metric_selection(question: str, available_metrics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Intelligently select the most relevant metrics for a given question
    """
    question_lower = question.lower()
    selected_metrics = []
    
    # Special handling for latency queries
    if any(word in question_lower for word in ["latency", "p95", "p99", "percentile", "response time"]):
        latency_metrics = select_latency_metrics(available_metrics, question_lower)
        selected_metrics.extend(latency_metrics)
    
    # General keyword-based selection
    for metric in available_metrics:
        metric_name = metric.get("name", "").lower()
        metric_description = metric.get("description", "").lower()
        
        # Check if metric matches question keywords
        is_relevant = False
        
        # GPU-related keywords
        if any(word in question_lower for word in ["gpu", "graphics", "cuda", "nvidia", "temperature", "utilization"]):
            if any(word in metric_name for word in ["gpu", "dcgm"]) or "gpu" in metric_description:
                is_relevant = True
        
        # vLLM-related keywords  
        elif any(word in question_lower for word in ["vllm", "llm", "model", "inference", "request", "token"]):
            if "vllm:" in metric_name or any(word in metric_description for word in ["vllm", "llm", "model"]):
                is_relevant = True
        
        # Kubernetes-related keywords
        elif any(word in question_lower for word in ["pod", "pods", "deployment", "service", "node"]):
            if any(word in metric_name for word in ["kube_", "pod", "deployment", "service", "node"]):
                is_relevant = True
        
        # Alert-related keywords
        elif any(word in question_lower for word in ["alert", "alerts", "alarm", "firing"]):
            if "alert" in metric_name.lower():
                is_relevant = True
        
        # Network-related keywords
        elif any(word in question_lower for word in ["network", "bandwidth", "traffic"]):
            if any(word in metric_name for word in ["network", "net"]):
                is_relevant = True
        
        # Memory-related keywords
        elif any(word in question_lower for word in ["memory", "mem", "ram"]):
            if any(word in metric_name for word in ["memory", "mem"]):
                is_relevant = True
        
        # CPU-related keywords
        elif any(word in question_lower for word in ["cpu", "processor"]):
            if any(word in metric_name for word in ["cpu", "processor"]):
                is_relevant = True
        
        if is_relevant and metric not in selected_metrics:
            selected_metrics.append(metric)
    
    # Sort by priority and relevance
    selected_metrics.sort(key=lambda m: m.get("priority", 999))
    
    return selected_metrics[:5]  # Return top 5 most relevant


def select_latency_metrics(available_metrics: List[Dict[str, Any]], question_lower: str) -> List[Dict[str, Any]]:
    """
    Specialized selection for latency-related queries
    """
    latency_metrics = []
    
    # Priority order for latency metrics
    latency_priority = [
        "vllm:e2e_request_latency_seconds_bucket",  # vLLM latency (highest priority)
        "controller_runtime_webhook_latency_seconds_bucket",  # Controller latency
        "http_request_duration_seconds_bucket",  # HTTP latency
        "grpc_server_msg_received_total",  # gRPC latency
    ]
    
    # Find metrics by priority
    for priority_metric in latency_priority:
        for metric in available_metrics:
            if priority_metric in metric.get("name", ""):
                latency_metrics.append(metric)
                break
    
    # If no priority metrics found, look for any latency-related metrics
    if not latency_metrics:
        for metric in available_metrics:
            metric_name = metric.get("name", "").lower()
            if any(word in metric_name for word in ["latency", "duration", "response_time"]):
                latency_metrics.append(metric)
    
    # Sort by family priority
    def get_family_priority(family_name: str) -> int:
        if "vllm" in family_name:
            return 1
        elif "controller" in family_name:
            return 2
        elif "http" in family_name:
            return 3
        elif "grpc" in family_name:
            return 4
        else:
            return 5
    
    latency_metrics.sort(key=lambda m: get_family_priority(m.get("name", "")))
    
    return latency_metrics


def generate_promql_from_discovered_metric(metric_info: Dict[str, Any], namespace: Optional[str], model_name: str, rate_interval: str, is_fleet_wide: bool) -> str:
    """
    Generate PromQL query from discovered metric information
    """
    metric_name = metric_info.get("name", "")
    metric_type = metric_info.get("type", "")
    aggregation = metric_info.get("aggregation", "avg")
    
    def get_labels() -> str:
        """Generate appropriate labels based on scope"""
        if is_fleet_wide:
            return ""
        
        labels = []
        if namespace:
            labels.append(f'namespace="{namespace}"')
        if model_name and model_name != "default-model" and "vllm:" in metric_name:
            labels.append(f'model_name="{model_name}"')
        
        return "{" + ", ".join(labels) + "}" if labels else ""
    
    labels = get_labels()
    
    # Generate query based on metric type and aggregation
    if aggregation == "histogram_quantile":
        # For latency metrics (p95, p99)
        percentile = 0.95  # Default to p95
        return f"histogram_quantile({percentile}, sum(rate({metric_name}{labels}[{rate_interval}])) by (le))"
    
    elif aggregation == "rate":
        # For counter metrics
        return f"sum(rate({metric_name}{labels}[{rate_interval}]))"
    
    elif aggregation == "avg":
        # For gauge metrics
        return f"avg({metric_name}{labels})"
    
    elif aggregation == "sum":
        # For sum aggregations
        return f"sum({metric_name}{labels})"
    
    else:
        # Default to average
        return f"avg({metric_name}{labels})" 