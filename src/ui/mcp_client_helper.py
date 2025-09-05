"""MCP Client Helper for UI - FastMCP Client Integration
This module uses fastmcp.Client to call MCP tools, matching the examples in
cluster endpoint by pointing MCP_SERVER_URL accordingly.
"""

import streamlit as st
import os
import requests
import json
import asyncio
from typing import Dict, Any, List, Optional
import logging
import sys
import site
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

# MCP Server Configuration
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8085")


class MCPClientHelper:
    """Helper class to call MCP server using FastMCP client (simple like example)."""

    def __init__(self, server_url: str = MCP_SERVER_URL):
        self.server_url = server_url
        self.health_endpoint = f"{server_url}/health"
        self.config = {
            "mcpServers": {"obs_mcp_server": {"url": f"{server_url}/mcp"}}
        }
        logger.info(f"Initialized FastMCP client for server: {server_url}")

    def check_server_health(self) -> bool:
        """Check if the MCP server is healthy"""
        try:
            response = requests.get(self.health_endpoint, timeout=5)
            if response.status_code == 200:
                health_data = response.json()
                logger.info(f"MCP Server healthy: {health_data.get('service')}")
                return True
            else:
                logger.warning(f"MCP Server health check failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error connecting to MCP server: {e}")
            return False

    async def _call_tool_async(self, tool_name: str, parameters: Dict[str, Any] | None) -> Any:
        """Async call via fastmcp.Client ."""
        # Ensure site-packages (where external 'mcp' package lives) is searched before repo paths
        try:
            site_paths: List[str] = []
            try:
                site_paths.extend(site.getsitepackages())  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                user_site = site.getusersitepackages()
                if isinstance(user_site, str):
                    site_paths.append(user_site)
            except Exception:
                pass
            # Prepend site-packages paths to sys.path to avoid local module name collisions (e.g., 'mcp')
            for p in reversed([p for p in site_paths if p and p not in sys.path]):
                sys.path.insert(0, p)
        except Exception:
            # Safe to ignore; best-effort only
            pass

        # Import fastmcp lazily to avoid any import-time surprises
        import importlib
        fastmcp_module = importlib.import_module("fastmcp")
        Client = fastmcp_module.Client

        client = Client(self.config)
        async with client:
            result = await client.call_tool(tool_name, parameters or {})
            # Convert to simple list-of-text-chunks like the example prints
            if hasattr(result, "content") and result.content:
                content_list: List[Dict[str, Any]] = []
                for item in result.content:
                    text = getattr(item, "text", str(item))
                    content_list.append({"type": "text", "text": text})
                return content_list
            return []

    def call_tool_sync(self, tool_name: str, parameters: Dict[str, Any] = None) -> Any:
        """Sync wrapper for Streamlit - runs the async fastmcp call."""
        try:
            return asyncio.run(self._call_tool_async(tool_name, parameters))
        except Exception as e:
            logger.error(f"Error calling MCP tool '{tool_name}': {e}")
            return None

    def parse_list_response(self, result: Any, item_prefix: str = "•") -> List[str]:
        """Parse MCP list response and extract items"""
        try:
            response_text = extract_text_from_mcp_result(result)
            if not response_text:
                return []
            
            # Normalize escaped newlines ("\\n") to real newlines so bullets split correctly
            response_text = response_text.replace("\\n", "\n")
            if item_prefix in response_text:
                    items: List[str] = []
                    # Split on real newlines first
                    for line in response_text.split('\n'):
                        # If the provider returned multiple bullets on one logical line
                        # (e.g., because of escaped newlines), split by the bullet itself
                        if item_prefix in line:
                            parts = line.split(item_prefix)
                            # parts[0] is text before first bullet; skip it
                            for part in parts[1:]:
                                name = part.strip().strip('\r').strip()
                                if name:
                                    items.append(name)
                    # Filter out any trailing JSON-ish remnants if present
                    cleaned: List[str] = []
                    for name in items:
                        # Remove any trailing characters like '"}]' if content was stringified
                        cleaned_name = name
                        # Trim trailing quotes/brackets/braces commonly seen when stringified
                        cleaned_name = cleaned_name.rstrip('"]} ')
                        cleaned.append(cleaned_name)
                    return cleaned
            return []
        except Exception as e:
            logger.error(f"Error parsing list response: {e}")
            return []


# Global MCP client instance
mcp_client = MCPClientHelper()


def extract_text_from_mcp_result(result: Any) -> Optional[str]:
    """Helper function to extract text from MCP tool result.
    
    Args:
        result: MCP tool result (typically a list with dict items)
        
    Returns:
        Extracted text string, or None if extraction fails
    """
    try:
        if result and isinstance(result, list) and len(result) > 0:
            first_item = result[0]
            if isinstance(first_item, dict) and "text" in first_item:
                return first_item["text"]
            else:
                return str(first_item)
        return None
    except Exception as e:
        logger.error(f"Error extracting text from MCP result: {e}")
        return None


def is_double_encoded_mcp_response(parsed_json: Any) -> bool:
    """Check if the parsed JSON is a double-encoded MCP response.
    
    A double-encoded MCP response is a list containing a dict with a 'text' key
    that contains another JSON string.
    
    Args:
        parsed_json: The parsed JSON object to check
        
    Returns:
        True if this appears to be a double-encoded MCP response
    """
    if not isinstance(parsed_json, list):
        return False
        
    if len(parsed_json) == 0:
        return False
        
    first_item = parsed_json[0]
    return isinstance(first_item, dict) and "text" in first_item


def extract_from_double_encoded_response(parsed_json: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Extract content from a double-encoded MCP response.
    
    Args:
        parsed_json: The list containing the double-encoded response
        
    Returns:
        The extracted and parsed inner JSON, or None if extraction fails
    """
    try:
        inner_text = parsed_json[0]["text"]
        logger.debug(f"Found double-encoded response, trying to parse inner text: {inner_text[:100]}...")
        
        inner_json = json.loads(inner_text)
        if isinstance(inner_json, dict):
            return inner_json
        else:
            logger.error(f"Inner JSON is not a dict: {type(inner_json)}")
            return None
            
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse inner JSON from double-encoded response: {e}")
        return None
    except Exception as e:
        logger.error(f"Error extracting from double-encoded response: {e}")
        return None


def get_namespaces_mcp() -> List[str]:
    """Fetch namespaces via MCP list_namespaces tool."""
    try:
        if not mcp_client.check_server_health():
            return []
        result = mcp_client.call_tool_sync("list_namespaces")
        return mcp_client.parse_list_response(result)
    except Exception as e:
        logger.error(f"Error fetching namespaces via MCP: {e}")
        return []


def get_models_mcp() -> List[str]:
    """Fetch models via MCP list_models tool."""
    try:
        if not mcp_client.check_server_health():
            return []
        result = mcp_client.call_tool_sync("list_models")
        return mcp_client.parse_list_response(result)
    except Exception as e:
        logger.error(f"Error fetching models via MCP: {e}")
        return []


def get_model_config_mcp() -> Dict[str, Any]:
    """Fetch model configuration via MCP get_model_config tool and parse into dict format."""
    try:
        if not mcp_client.check_server_health():
            return {}
        
        result = mcp_client.call_tool_sync("get_model_config")
        response_text = extract_text_from_mcp_result(result)
        if response_text:
            # Parse the MCP response text back into dict format
            return parse_model_config_text(response_text)
        
        logger.warning("No response from MCP get_model_config tool")
        return {}
        
    except Exception as e:
        logger.error(f"Error fetching model config via MCP: {e}")
        return {}


def analyze_vllm_mcp(model_name: str, summarize_model_id: str, start_ts: int, end_ts: int, api_key: str = None) -> Dict[str, Any]:
    """Analyze vLLM metrics via MCP analyze_vllm tool."""
    try:
        if not mcp_client.check_server_health():
            return {}

        # Convert timestamps to datetime strings for MCP tool
        start_datetime = datetime.fromtimestamp(start_ts).isoformat()
        end_datetime = datetime.fromtimestamp(end_ts).isoformat()

        # Strip namespace from model name if present (e.g., "dev | model" → "model")
        clean_model_name = model_name.split(" | ")[1] if " | " in model_name else model_name

        # Prepare parameters for MCP tool
        parameters = {
            "model_name": clean_model_name,
            "summarize_model_id": summarize_model_id,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime
        }

        # Add API key if provided
        if api_key:
            parameters["api_key"] = api_key

        result = mcp_client.call_tool_sync("analyze_vllm", parameters)

        response_text = extract_text_from_mcp_result(result)
        if response_text:
            # Check if response contains an error
            if "Error during analysis:" in response_text:
                logger.error(f"MCP analyze_vllm tool returned error: {response_text}")
                raise Exception(f"Analysis failed: {response_text}")

            # Parse the MCP response to extract components
            return parse_analyze_response(response_text)

        logger.warning("No response from MCP analyze_vllm tool")
        return {}

    except Exception as e:
        logger.error(f"Error analyzing vLLM metrics via MCP: {e}")
        return {}


def calculate_metrics_mcp(metrics_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    """Calculate metrics statistics via MCP calculate_metrics tool."""
    try:
        logger.debug(f"calculate_metrics_mcp called with data keys: {list(metrics_data.keys())}")
        if not mcp_client.check_server_health():
            logger.debug("MCP server health check failed - using fallback")
            return calculate_metrics_locally(metrics_data)

        # Convert metrics data to JSON string for MCP tool
        metrics_json = json.dumps(metrics_data)

        result = mcp_client.call_tool_sync("calculate_metrics", {"metrics_data_json": metrics_json})
        logger.debug(f"MCP call_tool_sync returned: {type(result)}, content: {result}")

        response_text = extract_text_from_mcp_result(result)
        if response_text:
            logger.debug(f"Extracted response_text length: {len(response_text)}")
            logger.debug(f"Response text content: {response_text[:200]}...")

            # Parse JSON response from MCP tool
            try:
                parsed_json = json.loads(response_text)
                logger.debug(f"Successfully parsed JSON, type: {type(parsed_json)}")

                if isinstance(parsed_json, dict):
                    calculated_metrics = parsed_json.get("calculated_metrics", {})
                    logger.debug(f"Successfully extracted calculated_metrics with {len(calculated_metrics)} items")
                    return calculated_metrics
                elif isinstance(parsed_json, list):
                    # Handle case where JSON contains a list (double-encoded MCP response)
                    logger.debug(f"JSON returned a list (double-encoded response): {parsed_json}")

                    # Check if this is a double-encoded MCP response
                    if is_double_encoded_mcp_response(parsed_json):
                        inner_json = extract_from_double_encoded_response(parsed_json)
                        if inner_json:
                            calculated_metrics = inner_json.get("calculated_metrics", {})
                            logger.debug(f"Successfully extracted from double-encoded response: {len(calculated_metrics)} items")
                            return calculated_metrics

                    logger.error(f"Could not handle list response format: {parsed_json}")
                    return {}
                else:
                    logger.error(f"JSON parsing returned unexpected type {type(parsed_json)}, expected dict")
                    return {}

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON: {e}")
                logger.error(f"Response text was: {response_text[:500]}")
                return {}
        else:
            logger.debug("No valid result from MCP calculate_metrics tool")
            return {}

    except Exception as e:
        import traceback
        logger.error(f"Error calculating metrics via MCP: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")

        # Fallback to local calculation when MCP fails
        return calculate_metrics_locally(metrics_data)


def calculate_metrics_locally(metrics_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    """Calculate metrics locally using the same logic as the REST API."""
    calculated_metrics = {}

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

        # Extract values from data points
        values = []
        for point in data_points:
            if isinstance(point, dict) and "value" in point:
                try:
                    value = float(point["value"])
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

    return calculated_metrics


def parse_analyze_response(response_text: str) -> Dict[str, Any]:
    """Parse the analyze_vllm MCP tool response text into structured data matching REST API format."""
    try:
        # Handle nested JSON if present
        try:
            parsed_json = json.loads(response_text)
            if isinstance(parsed_json, list) and len(parsed_json) > 0 and "text" in parsed_json[0]:
                actual_text = parsed_json[0]["text"]
            else:
                actual_text = response_text
        except json.JSONDecodeError:
            actual_text = response_text

        # Initialize result structure to match REST API format
        result = {
            "health_prompt": "",
            "llm_summary": "",
            "metrics": {}
        }

        # Split by lines to parse structured text
        lines = actual_text.split('\n')

        # Find prompt section
        prompt_start = -1
        for i, line in enumerate(lines):
            if line.strip() == "Prompt Used:":
                prompt_start = i + 1
                break

        if prompt_start > 0:
            # Extract prompt until we hit metrics section
            prompt_lines = []
            for i in range(prompt_start, len(lines)):
                line = lines[i]
                if line.strip().startswith("Current Analysis Time:") or line.strip().startswith("METRICS DATA:"):
                    break
                prompt_lines.append(line)
            result["health_prompt"] = '\n'.join(prompt_lines).strip()

        # Find the LLM-generated summary section
        summary_start = -1
        for i, line in enumerate(lines):
            if line.strip() == "Summary:" or line.strip().startswith("**Performance Summary**"):
                summary_start = i
                break

        if summary_start > 0:
            # Extract everything from summary onwards as the LLM output
            summary_lines = []
            for i in range(summary_start, len(lines)):
                line = lines[i]
                # Stop if we hit the detailed metrics section (indicated by bullet points with colons)
                if line.strip().startswith("- ") and ":" in line and any(keyword in line for keyword in ["Created", "Count", "Sum", "Bucket"]):
                    break
                summary_lines.append(line)
            result["llm_summary"] = '\n'.join(summary_lines).strip()
        else:
            # Fallback: use the full response as summary if no structured sections found
            result["llm_summary"] = actual_text

        # Check if response contains structured data
        metrics = {}
        if "STRUCTURED_DATA:" in actual_text:
            try:
                # Extract the JSON data after STRUCTURED_DATA:
                structured_start = actual_text.find("STRUCTURED_DATA:") + len("STRUCTURED_DATA:")
                json_data = actual_text[structured_start:].strip()

                parsed_structured = json.loads(json_data)
                if isinstance(parsed_structured, dict):
                    # Override with structured data if available
                    if "health_prompt" in parsed_structured:
                        result["health_prompt"] = parsed_structured["health_prompt"]
                    if "llm_summary" in parsed_structured:
                        result["llm_summary"] = parsed_structured["llm_summary"]
                    if "metrics" in parsed_structured:
                        result["metrics"] = parsed_structured["metrics"]
                        logger.debug(f"Extracted structured metrics: {list(parsed_structured['metrics'].keys())}")
                    return result
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Failed to parse structured data: {e}")
                # Fall back to basic parsing below

        # Fallback: Extract basic metrics info (for backward compatibility)
        if "GPU TEMPERATURE" in actual_text:
            metrics["gpu_temp_analyzed"] = "true"
        if "GPU POWER USAGE" in actual_text:
            metrics["gpu_power_analyzed"] = "true"
        if "P95 LATENCY" in actual_text:
            metrics["latency_analyzed"] = "true"
        result["metrics"] = metrics

        return result

    except Exception as e:
        logger.error(f"Error parsing analyze response: {e}")
        return {
            "health_prompt": response_text,  # Fallback to raw text
            "llm_summary": "Error parsing response",
            "metrics": {}
        }


def parse_model_config_text(text: str) -> Dict[str, Any]:
    """Parse MCP get_model_config text response back into JSON dict format.
    
    Input format:
        Available Model Config (3 total):
        
        • meta-llama/Llama-3.2-3B-Instruct
          - external: False
          - requiresApiKey: False
          - serviceName: llama-3-2-3b-instruct
        
        • google/gemini-2.5-flash
          - apiUrl: https://...
          - external: True
          - requiresApiKey: True
          ...
    
    Output format:
        {
            "meta-llama/Llama-3.2-3B-Instruct": {
                "external": False,
                "requiresApiKey": False,
                "serviceName": "llama-3-2-3b-instruct"
            },
            ...
        }
    """
    try:
        # Handle nested JSON if present
        try:
            parsed_json = json.loads(text)
            if isinstance(parsed_json, list) and len(parsed_json) > 0 and "text" in parsed_json[0]:
                text = parsed_json[0]["text"]
        except json.JSONDecodeError:
            pass  # Use original text
        
        config = {}
        current_model = None
        
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            # Model name line starts with "• "
            if line.startswith("• "):
                current_model = line[2:].strip()
                if current_model:
                    config[current_model] = {}
                continue
                
            # Property line starts with "- "
            if current_model and line.startswith("- "):
                prop_line = line[2:].strip()
                if ": " in prop_line:
                    key, value = prop_line.split(": ", 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Convert string values to appropriate types
                    if value.lower() == "true":
                        value = True
                    elif value.lower() == "false":
                        value = False
                    elif value.lower() == "none":
                        value = None
                    elif value.startswith("{") or value.startswith("["):
                        try:
                            value = json.loads(value.replace("'", '"'))
                        except:
                            pass  # Keep as string if JSON parsing fails
                    
                    config[current_model][key] = value
        
        return config
        
    except Exception as e:
        logger.error(f"Error parsing model config text: {e}")
        return {}


def get_vllm_metrics_mcp() -> Dict[str, str]:
    """Get available vLLM metrics from MCP server.
    
    Returns:
        Dictionary mapping friendly metric names to PromQL queries
    """
    try:
        logger.debug("Getting vLLM metrics via MCP")
        if not mcp_client.check_server_health():
            logger.debug("MCP server health check failed")
            return {}
        
        result = mcp_client.call_tool_sync("get_vllm_metrics_tool", {})
        logger.debug(f"MCP get_vllm_metrics_tool returned: {type(result)}, content: {result}")
        
        response_text = extract_text_from_mcp_result(result)
        if response_text:
            logger.debug(f"Extracted response_text length: {len(response_text)}")
            
            # Parse the formatted text response to extract metrics
            metrics_dict = parse_vllm_metrics_text(response_text)
            logger.debug(f"Parsed {len(metrics_dict)} vLLM metrics")
            return metrics_dict
        else:
            logger.error(f"Failed to extract text from MCP response: {result}")
            return {}
        
        logger.debug("No valid result from MCP get_vllm_metrics_tool")
        return {}
        
    except Exception as e:
        import traceback
        logger.error(f"Error getting vLLM metrics via MCP: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return {}


def parse_vllm_metrics_text(response_text: str) -> Dict[str, str]:
    """Parse the vLLM metrics response text to extract metric mappings.
    
    Args:
        response_text: Formatted text response from get_vllm_metrics_tool
        
    Returns:
        Dictionary mapping friendly names to PromQL queries
    """
    try:
        metrics_dict = {}
        lines = response_text.split('\n')
        
        current_metric = None
        for line in lines:
            line = line.strip()
            
            # Look for metric lines starting with bullet point
            if line.startswith('• ') and ' Query: ' not in line:
                # This is a metric name line
                current_metric = line[2:].strip()  # Remove the bullet
                
            elif line.startswith('Query: `') and line.endswith('`') and current_metric:
                # This is the query line for the current metric
                query = line[8:-1]  # Remove 'Query: `' and trailing '`'
                metrics_dict[current_metric] = query
                current_metric = None
                
        logger.debug(f"Parsed {len(metrics_dict)} metrics from response text")
        return metrics_dict
        
    except Exception as e:
        logger.error(f"Error parsing vLLM metrics text: {e}")
        return {}
