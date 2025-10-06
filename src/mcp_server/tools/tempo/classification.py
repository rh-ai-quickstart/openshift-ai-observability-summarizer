"""Question classification and trace error detection for Tempo queries."""

import re
from typing import Dict, Any, List
from enum import Enum


class QuestionType(Enum):
    """Enumeration of different question types for better query classification."""
    ERROR_TRACES = "error_traces"
    SLOW_TRACES = "slow_traces"
    FAST_TRACES = "fast_traces"
    SERVICE_ACTIVITY = "service_activity"
    DETAILED_ANALYSIS = "detailed_analysis"
    GENERAL = "general"


class QuestionClassifier:
    """Classifies user questions to determine appropriate trace queries."""

    # TraceQL query constants
    QUERY_ERROR_TRACES = "status=error"
    QUERY_SLOW_TRACES = "duration>1s"
    QUERY_ALL_SERVICES = "service.name=*"

    # Define question patterns with their corresponding question types
    QUESTION_PATTERNS = {
        QuestionType.ERROR_TRACES: [
            r"error", r"failed", r"exception", r"fault", r"problem",
            r"issue", r"broken", r"malfunction", r"defect"
        ],
        QuestionType.SLOW_TRACES: [
            r"slow", r"slowest", r"latency", r"delay", r"performance",
            r"bottleneck", r"lag", r"timeout"
        ],
        QuestionType.FAST_TRACES: [
            r"fast", r"fastest", r"quick", r"rapid"
        ],
        QuestionType.SERVICE_ACTIVITY: [
            r"active", r"busy", r"services", r"service activity",
            r"most active", r"running", r"operational"
        ],
        QuestionType.DETAILED_ANALYSIS: [
            r"top", r"slowest", r"fastest", r"request flow",
            r"detailed analysis", r"analyze", r"analysis"
        ]
    }

    @classmethod
    def get_all_patterns(cls) -> Dict[QuestionType, List[str]]:
        """
        Get all question patterns.

        Returns:
            Dict mapping question types to their patterns
        """
        return cls.QUESTION_PATTERNS.copy()

    @classmethod
    def classify_question(cls, question: str) -> QuestionType:
        """
        Classify a user question to determine the appropriate trace query.

        Args:
            question: The user's question

        Returns:
            QuestionType: The classified question type
        """
        question_lower = question.lower()

        for question_type, patterns in cls.QUESTION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, question_lower, re.IGNORECASE):
                    return question_type

        return QuestionType.GENERAL

    @classmethod
    def get_trace_query(cls, question_type: QuestionType, question: str) -> str:
        """
        Get the appropriate TraceQL query based on the question type.

        Args:
            question_type: The classified question type
            question: The original question (for additional context)

        Returns:
            str: The appropriate TraceQL query
        """
        question_lower = question.lower()

        if question_type == QuestionType.ERROR_TRACES:
            return cls.QUERY_ERROR_TRACES
        elif question_type == QuestionType.SLOW_TRACES and "fastest" not in question_lower:
            return cls.QUERY_SLOW_TRACES
        else:
            # Default query for FAST_TRACES, SERVICE_ACTIVITY, DETAILED_ANALYSIS, and GENERAL
            return cls.QUERY_ALL_SERVICES


class TraceErrorDetector:
    """Detects errors in trace data using pattern matching."""

    # Error indicators to look for in traces
    ERROR_PATTERNS = [
        r"\berror\b",
        r"\bfailed\b",
        r"\bexception\b",
        r"\bfault\b",
        r"\bstatus[:\s]*error\b",
        r"\bstatus[:\s]*failed\b",
        r"http[:\s]*[45]\d{2}",  # HTTP 4xx/5xx status codes
    ]

    @classmethod
    def is_error_trace(cls, trace: Dict[str, Any]) -> bool:
        """
        Check if a trace contains error indicators.

        Args:
            trace: Trace data dictionary

        Returns:
            bool: True if trace appears to contain errors
        """
        trace_str = str(trace).lower()

        for pattern in cls.ERROR_PATTERNS:
            if re.search(pattern, trace_str, re.IGNORECASE):
                return True

        return False
