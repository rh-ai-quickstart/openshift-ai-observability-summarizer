"""Pure Prometheus MCP Tools for Chat with Prometheus.

This module provides MCP tools for direct Prometheus interaction.
FIXED: Now follows the same pattern as working vLLM and OpenShift tools.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from core.response_utils import make_mcp_text_response

# Import core business logic - SAME PATTERN AS WORKING TOOLS
from core.chat_with_prometheus import (
    search_metrics_by_pattern,
    get_metric_metadata as core_get_metric_metadata,
    get_label_values as core_get_label_values,
    execute_promql_query,
    explain_query_results,
    suggest_related_queries,
    select_best_metric_for_question,
    find_best_metric_with_metadata as core_find_best_metric_with_metadata,
)

# Configure logging
logger = logging.getLogger(__name__)

def search_metrics(
    pattern: str = "",
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Search for metrics using semantic understanding."""
    try:
        if limit <= 0 or limit > 1000:
            return make_mcp_text_response("Limit must be between 1 and 1000", is_error=True)
        
        # Direct call to core business logic - SAME AS WORKING TOOLS
        result = search_metrics_by_pattern(pattern, limit)
        return make_mcp_text_response(json.dumps(result, indent=2))
        
    except Exception as e:
        logger.error(f"Error searching metrics: {e}")
        return make_mcp_text_response(f"Error searching metrics: {str(e)}", is_error=True)


def get_metric_metadata(metric_name: str) -> List[Dict[str, Any]]:
    """Get detailed metadata for a specific metric."""
    try:
        if not metric_name:
            return make_mcp_text_response("metric_name is required", is_error=True)
        
        # Direct call to core business logic - SAME AS WORKING TOOLS
        result = core_get_metric_metadata(metric_name)
        return make_mcp_text_response(json.dumps(result, indent=2))
        
    except ValueError as e:
        return make_mcp_text_response(f"Metric not found: {e}", is_error=True)
    except Exception as e:
        logger.error(f"Error getting metric metadata: {e}")
        return make_mcp_text_response(f"Error getting metric metadata: {str(e)}", is_error=True)


def get_label_values(
    metric_name: str,
    label_name: str
) -> List[Dict[str, Any]]:
    """Get all possible values for a specific label of a metric."""
    try:
        if not metric_name or not label_name:
            return make_mcp_text_response("Both metric_name and label_name are required", is_error=True)
        
        # Direct call to core business logic - SAME AS WORKING TOOLS
        result = core_get_label_values(metric_name, label_name)
        return make_mcp_text_response(json.dumps(result, indent=2))
        
    except Exception as e:
        logger.error(f"Error getting label values: {e}")
        return make_mcp_text_response(f"Error getting label values: {str(e)}", is_error=True)


def execute_promql(
    query: str,
    time_range: Optional[str] = None,
    start_datetime: Optional[str] = None,
    end_datetime: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Execute a PromQL query and return structured results."""
    try:
        if not query:
            return make_mcp_text_response("query is required", is_error=True)
        
        # Convert parameters to what our core function expects
        start_time = start_datetime
        end_time = end_datetime
        
        # Handle time_range parameter conversion
        if time_range:
            from datetime import datetime, timedelta
            end_time = datetime.now().isoformat() + "Z"
            
            if "5m" in time_range or "5 min" in time_range:
                start_time = (datetime.now() - timedelta(minutes=5)).isoformat() + "Z"
            elif "1h" in time_range or "1 hour" in time_range:
                start_time = (datetime.now() - timedelta(hours=1)).isoformat() + "Z"
            elif "now" in time_range:
                start_time = (datetime.now() - timedelta(minutes=5)).isoformat() + "Z"
            else:
                start_time = (datetime.now() - timedelta(hours=1)).isoformat() + "Z"
        
        # Direct call to core business logic - SAME AS WORKING TOOLS
        result = execute_promql_query(query, start_time, end_time)
        
        # Format response for Claude (like working tools)
        status = result.get("status", "unknown")
        results = result.get("results", [])
        result_type = result.get("result_type", "unknown")
        
        if status == "success" and results:
            # Create human-readable summary like working tools
            content = f"**PromQL Query Executed:** `{query}`\n\n"
            content += f"**Status:** {status}\n"
            content += f"**Result Type:** {result_type}\n"
            content += f"**Data Points:** {len(results)}\n\n"
            
            # Show sample data points for Claude to understand
            content += "**Sample Results:**\n"
            for i, res in enumerate(results[:5]):  # Show first 5 results
                metric_name = res.get("metric", {}).get("__name__", "unknown")
                labels = {k: v for k, v in res.get("metric", {}).items() if k != "__name__"}
                value = res.get("value", ["", ""])[1] if res.get("value") else "N/A"
                
                content += f"{i+1}. **{metric_name}**: {value}\n"
                if labels:
                    # Show key labels
                    key_labels = {k: v for k, v in labels.items() if k in ["instance", "job", "namespace", "pod", "device"]}
                    if key_labels:
                        content += f"   Labels: {key_labels}\n"
            
            if len(results) > 5:
                content += f"... and {len(results) - 5} more results\n"
            
            content += f"\n**Raw Data Available:** {len(results)} time series with current values\n"
            content += f"\n**Technical Details:**\n```json\n{json.dumps(result, indent=2)}\n```"
            
            return make_mcp_text_response(content)
        else:
            return make_mcp_text_response(f"Query '{query}' returned no data. Status: {status}")
        
    except Exception as e:
        logger.error(f"Error executing PromQL query: {e}")
        return make_mcp_text_response(f"Error executing PromQL query: {str(e)}", is_error=True)


def explain_results(
    query_results: str,
    user_question: str = ""
) -> List[Dict[str, Any]]:
    """Explain PromQL query results in natural language."""
    try:
        if not query_results:
            return make_mcp_text_response("query_results is required", is_error=True)
        
        # Parse query results
        try:
            results_dict = json.loads(query_results)
        except json.JSONDecodeError as e:
            return make_mcp_text_response(f"Invalid JSON in query_results: {e}", is_error=True)
        
        # Direct call to core business logic - SAME AS WORKING TOOLS
        explanation = explain_query_results(results_dict, user_question)
        return make_mcp_text_response(explanation)
        
    except Exception as e:
        logger.error(f"Error explaining results: {e}")
        return make_mcp_text_response(f"Error explaining results: {str(e)}", is_error=True)


def suggest_queries(
    user_intent: str,
    base_metric: str = ""
) -> List[Dict[str, Any]]:
    """Suggest related PromQL queries based on user intent."""
    try:
        if not user_intent:
            return make_mcp_text_response("user_intent is required", is_error=True)
        
        # Direct call to core business logic - SAME AS WORKING TOOLS
        suggestions = suggest_related_queries(user_intent, base_metric)
        
        result = {
            "user_intent": user_intent,
            "base_metric": base_metric,
            "suggested_queries": suggestions,
            "total_suggestions": len(suggestions)
        }
        
        return make_mcp_text_response(json.dumps(result, indent=2))
        
    except Exception as e:
        logger.error(f"Error generating suggestions: {e}")
        return make_mcp_text_response(f"Error generating suggestions: {str(e)}", is_error=True)


def select_best_metric(
    user_intent: str,
    available_metrics: List[str],
    context: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Select the best metric for a user question using semantic analysis."""
    try:
        if not user_intent:
            return make_mcp_text_response("user_intent is required", is_error=True)
        if not isinstance(available_metrics, list):
            return make_mcp_text_response("available_metrics must be a list", is_error=True)
        
        # Direct call to core business logic - SAME AS WORKING TOOLS
        best_metric = select_best_metric_for_question(user_intent, available_metrics, context)
        
        result = {
            "user_intent": user_intent,
            "best_metric": best_metric,
            "context": context,
            "total_candidates": len(available_metrics)
        }
        
        return make_mcp_text_response(json.dumps(result, indent=2))
        
    except Exception as e:
        logger.error(f"Error selecting metric: {e}")
        return make_mcp_text_response(f"Error selecting metric: {str(e)}", is_error=True)


def find_best_metric_with_metadata(
    user_question: str,
    max_candidates: int = 10
) -> List[Dict[str, Any]]:
    """Find the best metric for a user question using comprehensive metadata analysis."""
    try:
        if not user_question:
            return make_mcp_text_response("user_question is required", is_error=True)
        if max_candidates <= 0 or max_candidates > 50:
            return make_mcp_text_response("max_candidates must be between 1 and 50", is_error=True)
        
        # Direct call to core business logic - SAME AS WORKING TOOLS
        result = core_find_best_metric_with_metadata(user_question, max_candidates)
        return make_mcp_text_response(json.dumps(result, indent=2))
        
    except ValueError as e:
        return make_mcp_text_response(f"No suitable metrics found: {e}", is_error=True)
    except Exception as e:
        logger.error(f"Error analyzing metrics: {e}")
        return make_mcp_text_response(f"Error analyzing metrics: {str(e)}", is_error=True)


def find_best_metric_with_metadata_v2(
    user_question: str,
    max_candidates: int = 10
) -> List[Dict[str, Any]]:
    """Enhanced version of find_best_metric_with_metadata with improved analysis."""
    try:
        if not user_question:
            return make_mcp_text_response("user_question is required", is_error=True)
        if max_candidates <= 0 or max_candidates > 50:
            return make_mcp_text_response("max_candidates must be between 1 and 50", is_error=True)
        
        # Direct call to core business logic - SAME AS WORKING TOOLS
        result = core_find_best_metric_with_metadata(user_question, max_candidates)
        
        # Add version info and enhanced formatting
        result["version"] = "v2"
        result["enhanced_features"] = [
            "Improved semantic analysis",
            "Better metadata scoring",
            "Enhanced query suggestions"
        ]
        
        return make_mcp_text_response(json.dumps(result, indent=2))
        
    except ValueError as e:
        return make_mcp_text_response(f"No suitable metrics found: {e}", is_error=True)
    except Exception as e:
        logger.error(f"Error analyzing metrics: {e}")
        return make_mcp_text_response(f"Error analyzing metrics: {str(e)}", is_error=True)