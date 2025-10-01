"""
Chat with Prometheus - Core Business Logic

This module contains all the business logic for interactive Prometheus querying,
metric discovery, semantic search, and PromQL generation. This was extracted
from mcp_server/tools/prometheus_tools.py to follow proper separation of concerns.

Key capabilities:
- Semantic metric search and ranking
- Intelligent metric selection based on user intent
- Metadata-driven PromQL query generation
- Query result explanation and analysis
"""

import json
import logging
import re
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union, Tuple

from .config import PROMETHEUS_URL, THANOS_TOKEN, VERIFY_SSL
from .llm_client import summarize_with_llm
from .response_validator import ResponseType

# Initialize logger
logger = logging.getLogger(__name__)


# =============================================================================
# Core Prometheus API Client Functions
# =============================================================================

def make_prometheus_request(endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
    """Make authenticated request to Prometheus/Thanos."""
    url = f"{PROMETHEUS_URL}{endpoint}"
    headers = {}
    
    if THANOS_TOKEN:
        headers["Authorization"] = f"Bearer {THANOS_TOKEN}"
    
    try:
        response = requests.get(
            url, 
            params=params, 
            headers=headers, 
            verify=VERIFY_SSL,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Prometheus request failed: {e}")
        raise


# =============================================================================
# Metric Discovery and Search Functions
# =============================================================================

def search_metrics_by_pattern(pattern: str = "", limit: int = 50) -> Dict[str, Any]:
    """Search for metrics using semantic understanding and ranking.
    
    Args:
        pattern: Search terms (e.g., "tokens", "gpu temperature", "pod status")
        limit: Maximum number of metrics to return
    
    Returns:
        Dict with total_found, metrics list, pattern, and limit
    """
    # Get all metric names
    response = make_prometheus_request("/api/v1/label/__name__/values")
    all_metrics = response.get("data", [])
    
    # Use semantic search if pattern provided
    if pattern:
        ranked_metrics = rank_metrics_by_relevance(pattern, all_metrics)
        matching_metrics = ranked_metrics[:limit]
    else:
        matching_metrics = all_metrics[:limit]
    
    # Get basic info for each metric
    metrics_info = []
    for metric in matching_metrics:
        try:
            metadata_response = make_prometheus_request(
                "/api/v1/metadata", 
                {"metric": metric}
            )
            metadata = metadata_response.get("data", {}).get(metric, [])
            
            if metadata:
                metric_info = {
                    "name": metric,
                    "type": metadata[0].get("type", "unknown"),
                    "help": metadata[0].get("help", "No description available"),
                    "unit": metadata[0].get("unit", "")
                }
            else:
                metric_info = {
                    "name": metric,
                    "type": "unknown",
                    "help": "No description available",
                    "unit": ""
                }
            
            metrics_info.append(metric_info)
        except Exception as e:
            logger.warning(f"Failed to get metadata for {metric}: {e}")
            metrics_info.append({
                "name": metric,
                "type": "unknown", 
                "help": "No description available",
                "unit": ""
            })
    
    return {
        "total_found": len(matching_metrics),
        "metrics": metrics_info,
        "pattern": pattern,
        "limit": limit
    }


def get_metric_metadata(metric_name: str) -> Dict[str, Any]:
    """Get detailed metadata for a specific metric.
    
    Args:
        metric_name: Name of the metric to get metadata for
    
    Returns:
        Detailed metadata including type, help text, unit, and available labels
    """
    # Get metric metadata
    metadata_response = make_prometheus_request(
        "/api/v1/metadata", 
        {"metric": metric_name}
    )
    metadata = metadata_response.get("data", {}).get(metric_name, [])
    
    if not metadata:
        raise ValueError(f"Metric '{metric_name}' not found")
    
    # Get available labels for this metric
    labels_response = make_prometheus_request("/api/v1/labels")
    all_labels = labels_response.get("data", [])
    
    # Get sample values for common labels
    sample_values = {}
    for label in ["instance", "job", "namespace", "pod", "node"]:
        if label in all_labels:
            try:
                values_response = make_prometheus_request(
                    f"/api/v1/label/{label}/values"
                )
                sample_values[label] = values_response.get("data", [])[:10]  # Limit to 10 samples
            except Exception:
                sample_values[label] = []
    
    return {
        "metric_name": metric_name,
        "metadata": metadata[0] if metadata else {},
        "available_labels": all_labels,
        "sample_label_values": sample_values,
        "query_examples": generate_query_examples(metric_name, metadata[0] if metadata else {})
    }


def get_label_values(metric_name: str, label_name: str) -> Dict[str, Any]:
    """Get all possible values for a specific label of a metric.
    
    Args:
        metric_name: Name of the metric
        label_name: Name of the label to get values for
    
    Returns:
        Dict with metric_name, label_name, and values list
    """
    response = make_prometheus_request(f"/api/v1/label/{label_name}/values")
    values = response.get("data", [])
    
    return {
        "metric_name": metric_name,
        "label_name": label_name,
        "values": values,
        "total_values": len(values)
    }


# =============================================================================
# PromQL Execution and Analysis
# =============================================================================

def execute_promql_query(
    query: str, 
    start_time: Optional[str] = None, 
    end_time: Optional[str] = None
) -> Dict[str, Any]:
    """Execute a PromQL query and return structured results.
    
    Args:
        query: PromQL query to execute
        start_time: Start time (ISO format or relative like "1h")
        end_time: End time (ISO format, defaults to now)
    
    Returns:
        Structured query results with metadata
    """
    # Parse time parameters
    if start_time:
        if start_time.endswith(('m', 'h', 'd')):
            # Relative time (e.g., "1h", "30m")
            now = datetime.utcnow()
            if start_time.endswith('m'):
                minutes = int(start_time[:-1])
                start_timestamp = (now - timedelta(minutes=minutes)).timestamp()
            elif start_time.endswith('h'):
                hours = int(start_time[:-1])
                start_timestamp = (now - timedelta(hours=hours)).timestamp()
            elif start_time.endswith('d'):
                days = int(start_time[:-1])
                start_timestamp = (now - timedelta(days=days)).timestamp()
        else:
            # Absolute time
            start_timestamp = datetime.fromisoformat(start_time.replace('Z', '+00:00')).timestamp()
    else:
        # Default to last 1 hour
        start_timestamp = (datetime.utcnow() - timedelta(hours=1)).timestamp()
    
    if end_time:
        end_timestamp = datetime.fromisoformat(end_time.replace('Z', '+00:00')).timestamp()
    else:
        end_timestamp = datetime.utcnow().timestamp()
    
    # Execute query - use instant query if no time range specified
    if start_time or end_time:
        # Range query
        params = {
            "query": query,
            "start": start_timestamp,
            "end": end_timestamp,
            "step": "60s"  # 1 minute resolution
        }
        response = make_prometheus_request("/api/v1/query_range", params)
    else:
        # Instant query
        params = {"query": query}
        response = make_prometheus_request("/api/v1/query", params)
    
    # Structure the response
    return {
        "query": query,
        "start_time": start_time or f"{int((datetime.utcnow() - timedelta(hours=1)).timestamp())}",
        "end_time": end_time or f"{int(datetime.utcnow().timestamp())}",
        "status": response.get("status"),
        "result_type": response.get("data", {}).get("resultType"),
        "results": response.get("data", {}).get("result", []),
        "execution_time": response.get("data", {}).get("stats", {}).get("timings", {}).get("evalTotalTime", "unknown")
    }


def explain_query_results(results: Dict[str, Any], user_question: str = "") -> str:
    """Explain PromQL query results in natural language using LLM.
    
    Args:
        results: Query results from execute_promql_query()
        user_question: Original user question for context
    
    Returns:
        Natural language explanation of the results
    """
    # Prepare context for LLM
    query = results.get("query", "")
    result_data = results.get("results", [])
    result_type = results.get("result_type", "")
    
    if not result_data:
        return "The query returned no data. This might mean:\n- The metric doesn't exist\n- No data in the time range\n- The query syntax is incorrect"
    
    # Build summary statistics
    total_series = len(result_data)
    sample_data = []
    
    for series in result_data[:5]:  # Limit to first 5 series for summary
        metric_name = series.get("metric", {}).get("__name__", "unknown")
        labels = {k: v for k, v in series.get("metric", {}).items() if k != "__name__"}
        values = series.get("values", [])
        
        if values:
            latest_value = values[-1][1] if len(values[-1]) > 1 else "N/A"
            sample_data.append({
                "metric": metric_name,
                "labels": labels,
                "latest_value": latest_value,
                "data_points": len(values)
            })
    
    # Build prompt for LLM
    prompt = f"""Explain these Prometheus query results in clear, natural language:

**Original Query:** {query}
**User Question:** {user_question or "Not provided"}

**Results Summary:**
- Result Type: {result_type}
- Total Time Series: {total_series}
- Sample Data: {json.dumps(sample_data, indent=2)}

Please provide:
1. What the query is measuring
2. Key insights from the data
3. Any patterns or anomalies
4. Actionable recommendations if applicable

Keep the explanation concise but informative."""
    
    try:
        explanation = summarize_with_llm(
            prompt, 
            model_id="", 
            response_type=ResponseType.PROMETHEUS_EXPLANATION, 
            api_key=""
        )
        return explanation
    except Exception as e:
        logger.error(f"Error generating explanation: {e}")
        return f"Query executed successfully with {total_series} time series, but explanation generation failed."


# =============================================================================
# Intelligent Metric Selection and Ranking
# =============================================================================

def rank_metrics_by_relevance(search_term: str, all_metrics: List[str]) -> List[str]:
    """Rank all metrics by relevance using semantic scoring + Prometheus metadata."""
    scored_metrics = []
    
    for metric in all_metrics:
        intent_lower = search_term.lower()
        metric_lower = metric.lower()
        
        score = 0
        
        # 1. Direct word matches (metric name)
        intent_words = set(intent_lower.replace('-', ' ').replace('_', ' ').replace(':', ' ').split())
        metric_words = set(metric_lower.replace('-', ' ').replace('_', ' ').replace(':', ' ').split())
        direct_matches = intent_words.intersection(metric_words)
        score += len(direct_matches) * 10
        
        # 2. Semantic scoring based on metric name
        score += calculate_semantic_score(intent_lower, metric_lower)
        score += calculate_type_relevance(intent_lower, metric_lower)
        score += calculate_specificity_score(metric_lower)
        
        if score > 0:  # Only include metrics with some relevance
            scored_metrics.append((metric, score))
    
    # Sort by score (descending) and return metric names
    scored_metrics.sort(key=lambda x: x[1], reverse=True)
    return [metric for metric, score in scored_metrics]


def select_best_metric_for_question(
    user_question: str, 
    available_metrics: List[str], 
    context: Optional[str] = None
) -> str:
    """Select the best metric for a user question using semantic analysis.
    
    Args:
        user_question: User's intent/question
        available_metrics: List of available metric names
        context: Additional context for selection
    
    Returns:
        Best matching metric name
    """
    if not available_metrics:
        return ""
    
    # Use our enhanced ranking system
    ranked_metrics = rank_metrics_by_relevance(user_question, available_metrics)
    
    if ranked_metrics:
        return ranked_metrics[0]
    
    # Fallback to first metric if no good matches
    return available_metrics[0]


def find_best_metric_with_metadata(
    user_question: str, 
    max_candidates: int = 10
) -> Dict[str, Any]:
    """Find the best metric for a user question using comprehensive metadata analysis.
    
    This combines search, metadata analysis, and intelligent selection to find
    the most appropriate metric for the user's question.
    
    Args:
        user_question: User's question (e.g., "What's the GPU temperature?")
        max_candidates: Maximum number of candidate metrics to analyze
    
    Returns:
        Analysis with best metric, reasoning, and suggested PromQL query
    """
    # STEP 1: Extract key concepts from user question
    question_lower = user_question.lower()
    concepts = extract_key_concepts(question_lower)
    
    # STEP 2: Search for candidate metrics using semantic ranking
    response = make_prometheus_request("/api/v1/label/__name__/values")
    all_metrics = response.get("data", [])
    
    # Get top candidates using our enhanced ranking
    candidates = rank_metrics_by_relevance(user_question, all_metrics)[:max_candidates]
    
    if not candidates:
        raise ValueError("No relevant metrics found for your question.")
    
    # STEP 3: Analyze each candidate with metadata
    analyzed_candidates = []
    for metric in candidates:
        analysis = analyze_metric_with_metadata(metric, concepts, question_lower)
        if analysis['relevance_score'] > 0:
            analyzed_candidates.append(analysis)
    
    if not analyzed_candidates:
        raise ValueError("No suitable metrics found after metadata analysis.")
    
    # STEP 4: Select the best metric based on comprehensive scoring
    best_metric = max(analyzed_candidates, key=lambda x: x['total_score'])
    
    # STEP 5: Generate intelligent PromQL query
    suggested_query = generate_metadata_driven_promql(best_metric, concepts)
    
    # STEP 6: Format comprehensive response
    return {
        "best_metric": best_metric,
        "suggested_query": suggested_query,
        "analyzed_candidates": analyzed_candidates[:5],  # Top 5 for reference
        "user_question": user_question,
        "concepts_detected": concepts
    }


# =============================================================================
# Semantic Analysis and Scoring Functions
# =============================================================================

def calculate_semantic_score(intent: str, metric: str) -> int:
    """Calculate semantic relevance score between user intent and metric name."""
    score = 0
    
    # GPU/Hardware patterns
    if any(gpu_term in intent for gpu_term in ["gpu", "graphics", "cuda", "nvidia"]):
        if any(gpu_term in metric.lower() for gpu_term in ["gpu", "dcgm", "nvidia", "cuda"]):
            score += 15
    
    # Temperature patterns
    if any(temp_term in intent for temp_term in ["temperature", "temp", "heat", "thermal"]):
        if any(temp_term in metric.lower() for temp_term in ["temp", "thermal", "heat"]):
            score += 15
    
    # Memory patterns
    if any(mem_term in intent for mem_term in ["memory", "mem", "ram"]):
        if any(mem_term in metric for mem_term in ["memory", "mem", "ram", "bytes"]):
            score += 12
    
    # Network patterns
    if any(net_term in intent for net_term in ["network", "bandwidth", "traffic", "bytes", "packets"]):
        if any(net_term in metric for net_term in ["network", "net_", "bytes", "packets", "bandwidth"]):
            score += 12
    
    # CPU patterns
    if any(cpu_term in intent for cpu_term in ["cpu", "processor", "utilization"]):
        if any(cpu_term in metric for cpu_term in ["cpu", "processor", "util"]):
            score += 12
    
    # Latency/Performance patterns
    if any(lat_term in intent for lat_term in ["latency", "response", "time", "duration", "performance"]):
        if any(lat_term in metric for lat_term in ["latency", "duration", "time", "seconds", "response"]):
            score += 10
    
    # Error patterns
    if any(err_term in intent for err_term in ["error", "fail", "exception", "problem"]):
        if any(err_term in metric for err_term in ["error", "fail", "exception", "problem"]):
            score += 10
    
    # Kubernetes patterns
    if any(k8s_term in intent for k8s_term in ["pod", "container", "node", "deployment", "service"]):
        if any(k8s_term in metric for k8s_term in ["pod", "container", "node", "kube_", "deployment"]):
            score += 8
    
    return score


def calculate_type_relevance(intent: str, metric: str) -> int:
    """Calculate relevance based on metric type patterns."""
    score = 0
    
    # Counter metrics (rates, totals)
    if any(counter_term in intent for counter_term in ["rate", "total", "count", "increase"]):
        if any(counter_term in metric for counter_term in ["total", "count", "rate"]):
            score += 8
    
    # Gauge metrics (current values)
    if any(gauge_term in intent for gauge_term in ["current", "usage", "utilization", "percentage"]):
        if any(gauge_term in metric for gauge_term in ["usage", "util", "current", "percent"]):
            score += 8
    
    # Histogram metrics (percentiles, latency)
    if any(hist_term in intent for hist_term in ["percentile", "p95", "p99", "histogram", "distribution"]):
        if any(hist_term in metric for hist_term in ["bucket", "percentile", "histogram"]):
            score += 8
    
    return score


def calculate_specificity_score(metric: str) -> int:
    """Calculate specificity score - more specific metrics get higher scores."""
    score = 0
    
    # Bonus for specific subsystems
    specific_prefixes = ["vllm:", "dcgm_", "nvidia_", "openshift_", "kube_pod_", "container_"]
    for prefix in specific_prefixes:
        if metric.startswith(prefix):
            score += 5
            break
    
    # Bonus for detailed metric names (more components)
    components = metric.replace('-', '_').split('_')
    if len(components) >= 4:
        score += 3
    elif len(components) >= 3:
        score += 2
    
    # Penalty for very generic metrics
    generic_terms = ["total", "count", "info", "up", "ready"]
    if any(term in metric.lower() for term in generic_terms):
        score -= 2
    
    return score


# =============================================================================
# Advanced Analysis Functions
# =============================================================================

def extract_key_concepts(question: str) -> Dict[str, Any]:
    """Extract key concepts from user question for semantic analysis."""
    concepts = {
        "intent_type": "current_value",  # Default
        "measurements": set(),
        "components": set(),
        "aggregations": set()
    }
    
    # Intent type detection (case insensitive)
    question_lower = question.lower()
    if any(word in question_lower for word in ["how many", "count", "total"]):
        concepts["intent_type"] = "count"
    elif any(word in question_lower for word in ["average", "avg", "mean"]):
        concepts["intent_type"] = "average"
    elif any(word in question_lower for word in ["p95", "p99", "percentile", "distribution"]):
        concepts["intent_type"] = "percentile"
    elif any(word in question_lower for word in ["current", "now", "latest", "what is"]):
        concepts["intent_type"] = "current_value"
    
    # Measurement types
    measurement_patterns = {
        "temperature": ["temperature", "temp", "heat", "thermal"],
        "memory": ["memory", "mem", "ram"],
        "cpu": ["cpu", "processor"],
        "gpu": ["gpu", "graphics", "cuda", "nvidia"],
        "network": ["network", "bandwidth", "traffic"],
        "latency": ["latency", "response time", "duration"],
        "usage": ["usage", "utilization", "percent"]
    }
    
    for measurement, patterns in measurement_patterns.items():
        if any(pattern in question for pattern in patterns):
            concepts["measurements"].add(measurement)
    
    # Component detection
    component_patterns = {
        "pod": ["pod", "pods"],
        "node": ["node", "nodes"],
        "container": ["container", "containers"],
        "namespace": ["namespace", "namespaces"],
        "service": ["service", "services"]
    }
    
    for component, patterns in component_patterns.items():
        if any(pattern in question for pattern in patterns):
            concepts["components"].add(component)
    
    return concepts


def analyze_metric_with_metadata(
    metric_name: str, 
    concepts: Dict[str, Any], 
    question: str
) -> Dict[str, Any]:
    """Analyze a metric using its metadata and user concepts."""
    try:
        # Get metric metadata
        metadata_response = make_prometheus_request(
            "/api/v1/metadata", 
            {"metric": metric_name}
        )
        metadata = metadata_response.get("data", {}).get(metric_name, [{}])[0]
        
        # Calculate relevance scores
        name_score = calculate_semantic_score(question, metric_name)
        type_score = calculate_type_relevance(question, metric_name)
        specificity_score = calculate_specificity_score(metric_name)
        
        # Metadata relevance (help text analysis)
        help_text = metadata.get("help", "").lower()
        help_score = 0
        for measurement in concepts["measurements"]:
            if measurement in help_text:
                help_score += 5
        
        relevance_score = name_score + type_score + help_score
        total_score = relevance_score + specificity_score
        
        return {
            "name": metric_name,
            "metadata": metadata,
            "name_score": name_score,
            "type_score": type_score,
            "help_score": help_score,
            "specificity_score": specificity_score,
            "relevance_score": relevance_score,
            "total_score": total_score
        }
        
    except Exception as e:
        logger.warning(f"Failed to analyze metric {metric_name}: {e}")
        return {'name': metric_name, 'total_score': 0, 'relevance_score': 0}


def generate_metadata_driven_promql(
    metric_analysis: Dict[str, Any], 
    concepts: Dict[str, Any]
) -> str:
    """Generate PromQL query based on metric metadata and user intent."""
    metric_name = metric_analysis['name']
    metric_type = metric_analysis['metadata'].get('type', '').lower()
    intent = concepts['intent_type']
    
    # Choose aggregation based on intent and metric type
    if intent == 'count':
        if metric_type == 'counter':
            return f"sum({metric_name})"
        else:
            return f"count({metric_name})"
    
    elif intent == 'current_value':
        if 'temperature' in concepts['measurements']:
            return f"avg({metric_name})"  # Temperature should be averaged
        elif 'usage' in concepts['measurements']:
            return f"avg({metric_name})"  # Usage/utilization should be averaged
        else:
            return f"{metric_name}"  # Raw current value
    
    elif intent == 'average':
        return f"avg({metric_name})"
    
    elif intent == 'percentile':
        if metric_type == 'histogram':
            return f"histogram_quantile(0.95, {metric_name}_bucket)"
        else:
            return f"quantile(0.95, {metric_name})"
    
    else:
        # Default based on metric type
        if metric_type == 'counter':
            return f"rate({metric_name}[5m])"
        elif metric_type == 'gauge':
            if 'temperature' in concepts['measurements'] or 'usage' in concepts['measurements']:
                return f"avg({metric_name})"
            else:
                return f"{metric_name}"
        else:
            return f"{metric_name}"


# =============================================================================
# Query Generation Helpers
# =============================================================================

def generate_query_examples(metric_name: str, metadata: Dict[str, Any]) -> List[str]:
    """Generate example PromQL queries for a metric based on its metadata."""
    examples = []
    metric_type = metadata.get('type', '').lower()
    
    # Basic query
    examples.append(metric_name)
    
    # Type-specific examples
    if metric_type == 'counter':
        examples.extend([
            f"rate({metric_name}[5m])",
            f"sum(rate({metric_name}[5m]))",
            f"increase({metric_name}[1h])"
        ])
    elif metric_type == 'gauge':
        examples.extend([
            f"avg({metric_name})",
            f"max({metric_name})",
            f"min({metric_name})"
        ])
    elif metric_type == 'histogram':
        examples.extend([
            f"histogram_quantile(0.95, {metric_name}_bucket)",
            f"histogram_quantile(0.99, {metric_name}_bucket)",
            f"rate({metric_name}_sum[5m]) / rate({metric_name}_count[5m])"
        ])
    
    # Add common aggregations
    examples.extend([
        f"sum by (instance) ({metric_name})",
        f"avg by (job) ({metric_name})"
    ])
    
    return examples[:6]  # Limit to 6 examples


def suggest_related_queries(user_intent: str, base_metric: str = "") -> List[str]:
    """Suggest related PromQL queries based on user intent - completely dynamic."""
    suggestions = []
    intent_lower = user_intent.lower()
    
    # If we have a base metric, build suggestions around it
    if base_metric:
        # Basic aggregations
        suggestions.extend([
            f"avg({base_metric})",
            f"max({base_metric})",
            f"min({base_metric})",
            f"sum({base_metric})"
        ])
        
        # Rate calculations for counters
        if not base_metric.startswith("rate("):
            suggestions.append(f"rate({base_metric}[5m])")
        
        # Histogram quantiles if it looks like a histogram
        if "_bucket" in base_metric or "histogram" in base_metric.lower():
            base_name = base_metric.replace("_bucket", "")
            suggestions.append(f"histogram_quantile(0.95, {base_name}_bucket)")
    
    # Intent-based generic patterns (no hardcoded metrics)
    else:
        # Generate pattern suggestions based on intent keywords
        if any(word in intent_lower for word in ["performance", "latency", "response", "duration"]):
            suggestions.extend([
                "Use search_metrics to find latency/duration metrics first",
                "Look for metrics ending in '_seconds' or '_duration'",
                "Try histogram_quantile() for percentile analysis"
            ])
        
        elif any(word in intent_lower for word in ["memory", "cpu", "resource", "usage"]):
            suggestions.extend([
                "Search for metrics containing 'usage', 'util', or 'bytes'",
                "Look for ratio calculations (used/total)",
                "Try aggregations: avg(), max(), sum()"
            ])
        
        elif any(word in intent_lower for word in ["error", "failure", "problem", "alert"]):
            suggestions.extend([
                "Search for metrics containing 'error', 'failed', or 'alert'",
                "Look for ALERTS{alertstate=\"firing\"} pattern",
                "Try rate() calculations for error rates"
            ])
        
        else:
            suggestions.extend([
                "Use find_best_metric_with_metadata_v2 to discover relevant metrics",
                "Use search_metrics with keywords from your question",
                "Start with basic metric queries, then add aggregations as needed"
            ])
    
    return suggestions[:5]  # Limit to 5 suggestions
