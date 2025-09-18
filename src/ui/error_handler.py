"""
UI Error Handler for MCP Structured Exceptions

Provides enhanced error handling for the Streamlit UI that can parse and display
MCP structured error responses in a user-friendly way.

Features:
- Parse MCP error responses with error codes and details
- Display contextual error messages with recovery suggestions
- Show appropriate Streamlit components (error, warning, info)
- Provide actionable guidance for different error types
- Support for both MCP structured errors and fallback handling
"""

import streamlit as st
import json
import re
from typing import Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def parse_mcp_error(mcp_response: Any) -> Optional[Dict[str, Any]]:
    """
    Parse MCP response to extract structured error information.
    
    Args:
        mcp_response: The MCP tool response (list of dicts with type/text)
        
    Returns:
        Dict with error details if it's an error response, None otherwise
    """
    try:
        if not mcp_response or not isinstance(mcp_response, list):
            return None
            
        for item in mcp_response:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                
                # Check if this is an error response (starts with ❌ **Error)
                if "❌ **Error" in text:
                    return _extract_error_details(text)
                    
    except Exception as e:
        logger.debug(f"Error parsing MCP response for errors: {e}")
        
    return None


def _extract_json_object(text: str, start_pos: int) -> Optional[str]:
    """
    Extract a JSON object substring from text starting at start_pos, handling nested braces.
    Returns the JSON string or None if not found.
    """
    if text[start_pos] != '{':
        return None
    
    brace_count = 0
    for i in range(start_pos, len(text)):
        if text[i] == '{':
            brace_count += 1
        elif text[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                return text[start_pos:i+1]
    return None


def _extract_error_details(error_text: str) -> Dict[str, Any]:
    """Extract structured error details from MCP error response text."""
    error_details = {
        "is_error": True,
        "error_code": "UNKNOWN_ERROR",
        "message": "An error occurred",
        "recovery_suggestion": None,
        "details": {}
    }
    
    try:
        # Extract error code from ❌ **Error (ERROR_CODE)**
        code_match = re.search(r"❌ \*\*Error \(([^)]+)\)\*\*", error_text)
        if code_match:
            error_details["error_code"] = code_match.group(1)
        
        # Extract main error message (first paragraph after error header)
        lines = error_text.split('\n')
        for i, line in enumerate(lines):
            if line.strip() and not line.startswith('❌') and not line.startswith('💡') and not line.startswith('📋'):
                error_details["message"] = line.strip()
                break
        
        # Extract recovery suggestion
        suggestion_match = re.search(r"💡 \*\*Suggestion\*\*: ([^\n]+)", error_text)
        if suggestion_match:
            error_details["recovery_suggestion"] = suggestion_match.group(1)
        
        # Extract details JSON (handle nested braces)
        details_marker = "📋 **Details**: "
        details_start = error_text.find(details_marker)
        if details_start != -1:
            json_start = error_text.find("{", details_start)
            if json_start != -1:
                details_json = _extract_json_object(error_text, json_start)
                if details_json:
                    try:
                        error_details["details"] = json.loads(details_json)
                    except json.JSONDecodeError:
                        pass
                
    except Exception as e:
        logger.debug(f"Error extracting error details: {e}")
    
    return error_details


def _is_mcp_list_encoded_text(text: str) -> bool:
    """Heuristically detect if a string is a JSON list of MCP text items."""
    try:
        s = str(text).lstrip()
        if not s.startswith("["):
            return False
        return '"type":"text"' in s.replace(" ", "")
    except Exception:
        return False


def _decode_mcp_list_encoded_text(text: str) -> Optional[str]:
    """If text is a JSON list of MCP {type:'text', text:'...'}, return inner text of first item."""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            return parsed[0].get("text", "")
    except Exception:
        pass
    return None


def _normalize_error_details(details: Dict[str, Any]) -> Dict[str, Any]:
    """Return a clean error_details dict with plain message and suggestion only."""
    cleaned = {
        "is_error": True,
        "error_code": details.get("error_code", "UNKNOWN_ERROR"),
        "message": details.get("message", "An error occurred"),
        "recovery_suggestion": details.get("recovery_suggestion"),
        "details": details.get("details", {}),
    }
    # Clean potential serialization artifacts
    try:
        cleaned["message"] = str(cleaned["message"]).strip()
        if _is_mcp_list_encoded_text(cleaned["message"]):
            inner_text = _decode_mcp_list_encoded_text(cleaned["message"]) or ""
            sub = _extract_error_details(inner_text) if inner_text else None
            if sub:
                cleaned["message"] = sub.get("message", cleaned["message"])  # type: ignore[index]
                if not cleaned.get("recovery_suggestion"):
                    cleaned["recovery_suggestion"] = sub.get("recovery_suggestion")
        if cleaned.get("recovery_suggestion"):
            rs = str(cleaned["recovery_suggestion"]).strip()
            rs = re.sub(r"[\]\}\"]+\s*$", "", rs)
            cleaned["recovery_suggestion"] = rs
    except Exception:
        pass
    return cleaned


def handle_client_or_mcp_error(result: Any, context: str = "Operation") -> bool:
    """Unified handler for client-side dict errors or MCP list-encoded errors.

    Returns True if an error was detected and displayed; False otherwise.
    """
    try:
        # Client-side dict error (preferred path)
        if isinstance(result, dict) and "error" in result:
            details = result.get("error_details")
            if isinstance(details, dict):
                display_mcp_error(details)
                return True

            msg = str(result.get("error", f"{context} failed"))
            if _is_mcp_list_encoded_text(msg):
                inner_text = _decode_mcp_list_encoded_text(msg) or ""
                ed = _extract_error_details(inner_text) if inner_text else None
                if ed:
                    display_mcp_error(ed)
                    return True
            # Fallback plain error
            st.error(f"❌ {context} failed: {msg}")
            return True

        # Fallback to MCP list-based response handling
        return display_error_with_context(result, None, context)
    except Exception as e:
        st.error(f"❌ {context} failed: {e}")
        return True

def display_mcp_error(error_details: Dict[str, Any]) -> None:
    """
    Display MCP error in appropriate Streamlit components.
    
    Args:
        error_details: Parsed error details from parse_mcp_error()
    """
    error_details = _normalize_error_details(error_details)
    error_code = error_details.get("error_code", "UNKNOWN_ERROR")
    message = error_details.get("message", "An error occurred")
    suggestion = error_details.get("recovery_suggestion")
    details = error_details.get("details", {})

    # Determine severity and icon based on error code
    severity, icon = _get_error_severity(error_code)

    # Display main error message
    if severity == "error":
        st.error(f"{icon} **{error_code}**: {message}")
    elif severity == "warning":
        st.warning(f"{icon} **{error_code}**: {message}")
    else:
        st.info(f"{icon} **{error_code}**: {message}")

    # Display recovery suggestion if available
    if suggestion:
        st.info(f"💡 **How to fix**: {suggestion}")

    # Display technical details in an expander for advanced users
    if details:
        with st.expander("🔍 Technical Details"):
            st.json(details)


def _get_error_severity(error_code: str) -> Tuple[str, str]:
    """Determine severity level and icon based on error code."""
    error_mapping = {
        # User input errors (info level - user can fix)
        "INVALID_INPUT": ("info", "📝"),
        "MISSING_PARAMETER": ("info", "📝"),
        "INVALID_TIME_RANGE": ("info", "📅"),
        "INVALID_MODEL_NAME": ("info", "🤖"),
        "INVALID_NAMESPACE": ("info", "🏷️"),
        
        # Authentication errors (warning level - user needs to check config)
        "AUTHENTICATION_ERROR": ("warning", "🔐"),
        "AUTHORIZATION_ERROR": ("warning", "🔐"),
        "TOKEN_EXPIRED": ("warning", "⏰"),
        
        # External service errors (error level - service issues)
        "PROMETHEUS_ERROR": ("error", "📊"),
        "THANOS_ERROR": ("error", "📊"),
        "LLM_SERVICE_ERROR": ("error", "🧠"),
        "KUBERNETES_API_ERROR": ("error", "☸️"),
        
        # Configuration errors (warning level - admin needs to fix)
        "CONFIGURATION_ERROR": ("warning", "⚙️"),
        
        # Network/connectivity (error level - infrastructure issues)
        "CONNECTION_ERROR": ("error", "🌐"),
        "TIMEOUT_ERROR": ("error", "⏱️"),
        
        # Resource errors (warning level - might be temporary)
        "RESOURCE_NOT_FOUND": ("warning", "🔍"),
        "RESOURCE_UNAVAILABLE": ("warning", "🚫"),
        
        # Internal/processing errors (error level - system issues)
        "DATA_PROCESSING_ERROR": ("error", "⚙️"),
        "INTERNAL_ERROR": ("error", "💥"),
    }
    
    return error_mapping.get(error_code, ("error", "❌"))


def display_error_with_context(
    mcp_response: Any = None,
    fallback_message: str = None,
    context: str = "Operation"
) -> bool:
    """
    Comprehensive error display that handles both MCP structured errors and fallbacks.
    Args:
        mcp_response: MCP tool response to check for errors
        fallback_message: Fallback error message if no structured error found
        context: Context description for the operation that failed

    Returns:
        bool: True if an error was displayed, False otherwise
    """
    # First, try to parse MCP structured error
    if mcp_response:
        error_details = parse_mcp_error(mcp_response)
        if error_details:
            display_mcp_error(_normalize_error_details(error_details))
            return True

    # Fallback to generic error message
    if fallback_message:
        st.error(f"❌ {context} failed: {fallback_message}")
        return True

    return False


def create_error_recovery_guidance(error_code: str) -> None:
    """Create contextual help based on error type."""
    guidance = {
        "INVALID_INPUT": {
            "title": "Input Validation Help",
            "tips": [
                "Check that all required fields are filled out",
                "Verify model names match available models",
                "Ensure time ranges are in correct format"
            ]
        },
        "PROMETHEUS_ERROR": {
            "title": "Metrics Service Help", 
            "tips": [
                "Check if Prometheus/Thanos is accessible",
                "Verify the model name exists in metrics",
                "Try a smaller time range",
                "Contact administrator if problem persists"
            ]
        },
        "LLM_SERVICE_ERROR": {
            "title": "AI Model Service Help",
            "tips": [
                "Verify the AI model is available and running",
                "Check if the model ID is correct",
                "Try a different model if available",
                "Contact administrator if problem persists"
            ]
        },
        "AUTHENTICATION_ERROR": {
            "title": "Authentication Help",
            "tips": [
                "Check your API key is correct",
                "Verify API key has not expired",
                "Contact administrator for new credentials"
            ]
        },
        "CONNECTION_ERROR": {
            "title": "Connectivity Help",
            "tips": [
                "Check your internet connection",
                "Verify services are running",
                "Try again in a few moments",
                "Contact administrator if issue persists"
            ]
        }
    }
    
    if error_code in guidance:
        guide = guidance[error_code]
        with st.expander(f"🆘 {guide['title']}"):
            for tip in guide["tips"]:
                st.write(f"• {tip}")


def handle_mcp_tool_error(tool_name: str, mcp_response: Any, exception: Exception = None) -> None:
    """
    Specialized error handler for MCP tool calls.
    
    Args:
        tool_name: Name of the MCP tool that was called
        mcp_response: Response from the MCP tool
        exception: Any exception that was caught during the call
    """
    # Try structured error handling first
    error_details = parse_mcp_error(mcp_response) if mcp_response else None
    
    if error_details:
        st.subheader(f"Issue with {tool_name}")
        display_mcp_error(error_details)
        create_error_recovery_guidance(error_details.get("error_code", ""))
    elif exception:
        # Fallback to exception-based error handling
        st.error(f"❌ {tool_name} failed: {str(exception)}")
        
        # Provide some basic troubleshooting
        with st.expander("🔧 Troubleshooting"):
            st.write("• Check your network connection")
            st.write("• Verify all input parameters are correct")
            st.write("• Try again in a few moments")
            st.write("• Contact support if the problem persists")
    else:
        # Generic failure
        st.error(f"❌ {tool_name} did not return expected results")


def wrap_mcp_call(func, *args, **kwargs):
    """
    Function wrapper for MCP calls that provides automatic error handling.
    
    Args:
        func: The MCP function to call
        *args: Positional arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function
    
    Usage:
        result = wrap_mcp_call(analyze_vllm_mcp, model_name="test", ...)
    
    Returns:
        The result of the function call, or None if an error occurred
    """
    try:
        result = func(*args, **kwargs)
        
        # Check if result contains an error
        if result:
            error_details = parse_mcp_error(result)
            if error_details:
                handle_mcp_tool_error(func.__name__, result)
                return None
                
        return result
        
    except Exception as e:
        handle_mcp_tool_error(func.__name__, None, e)
        return None
