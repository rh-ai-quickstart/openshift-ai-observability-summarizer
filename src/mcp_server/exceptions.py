"""
MCP Server Exception Handling Framework

Provides standardized exception handling for MCP tools with proper error categorization,
logging, and structured responses that can be properly handled by UIs.

Features:
- Specific exception types for different error categories
- Structured error responses with error codes and context
- Automatic logging integration
- Recovery suggestions for common issues
- MCP-compliant error formatting
"""

import logging
from typing import Dict, Any, List, Optional, Union
from enum import Enum
import traceback
import json

logger = logging.getLogger(__name__)


class MCPErrorCode(Enum):
    """Standardized error codes for MCP operations."""
    
    # Input/Validation Errors (4xx equivalent)
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_PARAMETER = "MISSING_PARAMETER"
    INVALID_TIME_RANGE = "INVALID_TIME_RANGE"
    INVALID_MODEL_NAME = "INVALID_MODEL_NAME"
    INVALID_NAMESPACE = "INVALID_NAMESPACE"
    
    # Authentication/Authorization Errors (4xx equivalent)
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    
    # External Service Errors (5xx equivalent)
    PROMETHEUS_ERROR = "PROMETHEUS_ERROR"
    THANOS_ERROR = "THANOS_ERROR"
    LLM_SERVICE_ERROR = "LLM_SERVICE_ERROR"
    KUBERNETES_API_ERROR = "KUBERNETES_API_ERROR"
    
    # Internal Errors (5xx equivalent)
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    DATA_PROCESSING_ERROR = "DATA_PROCESSING_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    
    # Network/Connectivity Errors
    CONNECTION_ERROR = "CONNECTION_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    
    # Resource Errors
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"


class MCPException(Exception):
    """Base exception class for MCP operations."""
    
    def __init__(
        self,
        message: str,
        error_code: MCPErrorCode,
        details: Optional[Dict[str, Any]] = None,
        recovery_suggestion: Optional[str] = None,
        original_exception: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.recovery_suggestion = recovery_suggestion
        self.original_exception = original_exception
        
    def to_mcp_response(self) -> List[Dict[str, Any]]:
        """Convert exception to MCP-compliant error response."""
        error_data = {
            "error": True,
            "error_code": self.error_code.value,
            "message": self.message,
            "details": self.details
        }
        
        if self.recovery_suggestion:
            error_data["recovery_suggestion"] = self.recovery_suggestion
            
        content = f"❌ **Error ({self.error_code.value})**\n\n{self.message}"
        
        if self.recovery_suggestion:
            content += f"\n\n💡 **Suggestion**: {self.recovery_suggestion}"
            
        if self.details:
            content += f"\n\n📋 **Details**: {json.dumps(self.details, indent=2)}"
            
        return [{"type": "text", "text": content}]


class ValidationError(MCPException):
    """Raised when input validation fails."""
    
    def __init__(self, message: str, field: Optional[str] = None, value: Optional[Any] = None, details: Optional[Dict[str, Any]] = None):
        combined_details = details or {}
        if field:
            combined_details["field"] = field
        if value is not None:
            combined_details["provided_value"] = str(value)
            
        super().__init__(
            message=message,
            error_code=MCPErrorCode.INVALID_INPUT,
            details=combined_details,
            recovery_suggestion="Please check the input parameters and try again."
        )


class PrometheusError(MCPException):
    """Raised when Prometheus/Thanos operations fail."""
    
    def __init__(self, message: str, query: Optional[str] = None, status_code: Optional[int] = None):
        details = {}
        if query:
            details["prometheus_query"] = query
        if status_code:
            details["http_status"] = status_code
            
        # Provide specific recovery suggestions based on HTTP status codes
        if status_code == 400:
            recovery_suggestion = "Check query syntax and parameter format."
        elif status_code == 401:
            recovery_suggestion = "Verify authentication credentials and token validity."
        elif status_code == 403:
            recovery_suggestion = "Verify authentication token and RBAC permissions."
        elif status_code == 404:
            recovery_suggestion = "Check if the metric exists and the query is correct."
        elif status_code == 408:
            recovery_suggestion = "Query timed out. Try reducing time range or simplifying the query."
        elif status_code == 413:
            recovery_suggestion = "Query result too large. Try reducing time range or aggregating data."
        elif status_code == 422:
            recovery_suggestion = "Query syntax is invalid. Check PromQL syntax and metric names."
        elif status_code == 429:
            recovery_suggestion = "Rate limit exceeded. Wait a moment and try again."
        elif status_code == 500:
            recovery_suggestion = "Prometheus server error. Check Prometheus logs and try again."
        elif status_code == 502:
            recovery_suggestion = "Bad gateway. Check if Prometheus/Thanos is accessible."
        elif status_code == 503:
            recovery_suggestion = "Service unavailable. Prometheus/Thanos may be overloaded or down."
        elif status_code == 504:
            recovery_suggestion = "Gateway timeout. Query may be too complex or service is slow."
        elif status_code and status_code >= 500:
            recovery_suggestion = "Prometheus/Thanos service may be unavailable. Try again later."
        else:
            recovery_suggestion = "Check Prometheus/Thanos connectivity and query syntax."
            
        super().__init__(
            message=message,
            error_code=MCPErrorCode.PROMETHEUS_ERROR,
            details=details,
            recovery_suggestion=recovery_suggestion
        )


class LLMServiceError(MCPException):
    """Raised when LLM service operations fail."""
    
    def __init__(self, message: str, model_id: Optional[str] = None, status_code: Optional[int] = None):
        details = {}
        if model_id:
            details["model_id"] = model_id
        is_int_status = isinstance(status_code, int)
        if is_int_status:
            details["http_status"] = status_code
        
        recovery_suggestion = "Check LLM service availability and model configuration."
        if is_int_status:
            if status_code == 400:
                recovery_suggestion = "Verify the model ID and request parameters."
            elif status_code == 404:
                recovery_suggestion = "The specified model may not be available. Check model configuration."
            elif status_code >= 500:
                recovery_suggestion = "LLM service may be unavailable. Try again later."
            
        super().__init__(
            message=message,
            error_code=MCPErrorCode.LLM_SERVICE_ERROR,
            details=details,
            recovery_suggestion=recovery_suggestion
        )


class ConfigurationError(MCPException):
    """Raised when configuration is invalid or missing."""
    
    def __init__(self, message: str, config_key: Optional[str] = None):
        details = {}
        if config_key:
            details["config_key"] = config_key
            
        super().__init__(
            message=message,
            error_code=MCPErrorCode.CONFIGURATION_ERROR,
            details=details,
            recovery_suggestion="Check environment variables and configuration files."
        )


def handle_mcp_exception(func):
    """Decorator to standardize exception handling for MCP tools."""
    import functools
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except MCPException as e:
            # Log the MCP exception with context
            logger.error(
                "MCP tool error: %s",
                e.message,
                extra={
                    "error_code": e.error_code.value,
                    "tool_name": func.__name__,
                    "details": e.details
                }
            )
            return e.to_mcp_response()
        except Exception as e:
            # Handle unexpected exceptions
            logger.exception(
                "Unexpected error in MCP tool: %s",
                func.__name__,
                extra={
                    "tool_name": func.__name__,
                    "error_type": type(e).__name__
                }
            )
            
            # Create a generic internal error
            internal_error = MCPException(
                message=f"An unexpected error occurred: {str(e)}",
                error_code=MCPErrorCode.INTERNAL_ERROR,
                details={"error_type": type(e).__name__},
                recovery_suggestion="Please try again. If the problem persists, contact support.",
                original_exception=e
            )
            return internal_error.to_mcp_response()
    
    return wrapper


def parse_prometheus_error(response, query: Optional[str] = None) -> PrometheusError:
    """Parse Prometheus HTTP error response into structured exception."""
    status_code = getattr(response, 'status_code', None)
    
    try:
        error_data = response.json()
        error_message = error_data.get('error', str(response.text))
    except:
        error_message = str(response.text) if hasattr(response, 'text') else str(response)
    
    return PrometheusError(
        message=f"Prometheus query failed: {error_message}",
        query=query,
        status_code=status_code
    )


def parse_llm_error(response, model_id: Optional[str] = None) -> LLMServiceError:
    """Parse LLM service HTTP error response into structured exception."""
    status_code = getattr(response, 'status_code', None)
    
    try:
        error_data = response.json()
        error_message = error_data.get('error', str(response.text))
    except:
        error_message = str(response.text) if hasattr(response, 'text') else str(response)
    
    return LLMServiceError(
        message=f"LLM service error: {error_message}",
        model_id=model_id,
        status_code=status_code
    )


def validate_required_params(**params) -> None:
    """Validate that required parameters are provided and not empty."""
    for param_name, param_value in params.items():
        if param_value is None or (isinstance(param_value, str) and not param_value.strip()):
            raise ValidationError(
                message=f"Required parameter '{param_name}' is missing or empty",
                field=param_name,
                value=param_value
            )


def validate_time_range(start_ts: int, end_ts: int) -> None:
    """Validate time range parameters."""
    if start_ts >= end_ts:
        raise ValidationError(
            message="Start time must be before end time",
            field="time_range",
            details={"start_ts": start_ts, "end_ts": end_ts}
        )
    
    # Check for reasonable time ranges (not more than configured MAX_TIME_RANGE_DAYS)
    from core.config import MAX_TIME_RANGE_DAYS  # Imported here to avoid circulars at module import time
    SECONDS_PER_DAY = 86400  # 24 * 60 * 60
    max_range_seconds = MAX_TIME_RANGE_DAYS * SECONDS_PER_DAY
    if end_ts - start_ts > max_range_seconds:
        raise ValidationError(
            message=f"Time range too large (maximum {MAX_TIME_RANGE_DAYS} days)",
            field="time_range",
            details={"range_days": (end_ts - start_ts) / SECONDS_PER_DAY}
        )


def safe_json_loads(json_str: str, context: str = "JSON data") -> Dict[str, Any]:
    """Safely parse JSON with proper error handling."""
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValidationError(
            message=f"Invalid JSON in {context}: {str(e)}",
            details={"json_error": str(e), "context": context}
        )
