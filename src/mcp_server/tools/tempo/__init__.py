"""Tempo query tools package for trace analysis.

This package provides tools for querying and analyzing Tempo traces:
- Models: Data structures for responses
- Error handling: Error classification and user-friendly messaging
- Classification: Question and trace error detection
- Query tool: Core Tempo query functionality
- MCP tools: High-level MCP tool functions
"""

from .models import QueryResponse, TraceDetailsResponse
from .error_handling import ErrorType, TempoErrorClassifier
from .classification import QuestionType, QuestionClassifier, TraceErrorDetector
from .query_tool import TempoQueryTool
from .mcp_tools import (
    query_tempo_tool,
    get_trace_details_tool,
    chat_tempo_tool,
    extract_time_range_from_question,
    SLOW_TRACE_THRESHOLD_MS
)

__all__ = [
    # Models
    "QueryResponse",
    "TraceDetailsResponse",
    # Error handling
    "ErrorType",
    "TempoErrorClassifier",
    # Classification
    "QuestionType",
    "QuestionClassifier",
    "TraceErrorDetector",
    # Query tool
    "TempoQueryTool",
    # MCP tools
    "query_tempo_tool",
    "get_trace_details_tool",
    "chat_tempo_tool",
    "extract_time_range_from_question",
    "SLOW_TRACE_THRESHOLD_MS",
]
