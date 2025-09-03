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
            if result and isinstance(result, list) and len(result) > 0:
                response_text = result[0].get("text", "")
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
        if result and isinstance(result, list) and len(result) > 0:
            response_text = result[0].get("text", "")
            
            # Parse the MCP response text back into dict format
            return parse_model_config_text(response_text)
        
        logger.warning("No response from MCP get_model_config tool")
        return {}
        
    except Exception as e:
        logger.error(f"Error fetching model config via MCP: {e}")
        return {}



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
