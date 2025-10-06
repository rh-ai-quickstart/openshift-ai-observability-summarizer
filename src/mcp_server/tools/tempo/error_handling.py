"""Error handling and classification for Tempo queries."""

import re
from enum import Enum


class ErrorType(Enum):
    """Enumeration of different error types for better error classification."""
    CONNECTION_REFUSED = "connection_refused"
    DNS_RESOLUTION_FAILED = "dns_resolution_failed"
    HTTP_ERROR = "http_error"
    TIMEOUT = "timeout"
    AUTHENTICATION_FAILED = "authentication_failed"
    SERVICE_UNAVAILABLE = "service_unavailable"
    UNKNOWN = "unknown"


class TempoErrorClassifier:
    """Classifies Tempo-related errors for better error handling and user messaging."""

    # Define error patterns with their corresponding error types
    ERROR_PATTERNS = {
        ErrorType.CONNECTION_REFUSED: [
            r"Connection refused",
            r"Connection reset",
            r"Connection aborted",
            r"Connection broken"
        ],
        ErrorType.DNS_RESOLUTION_FAILED: [
            r"nodename nor servname provided",
            r"Name or service not known",
            r"Temporary failure in name resolution",
            r"Name resolution failed"
        ],
        ErrorType.HTTP_ERROR: [
            r"HTTP\s+[45]\d{2}",  # Match HTTP 4xx and 5xx errors
            r"Bad Gateway",
            r"Gateway Timeout"
        ],
        ErrorType.TIMEOUT: [
            r"timeout",
            r"timed out",
            r"Request timeout"
        ],
        ErrorType.AUTHENTICATION_FAILED: [
            r"HTTP\s+401",
            r"\b401\b",
            r"Unauthorized",
            r"Authentication failed",
            r"Invalid credentials"
        ],
        ErrorType.SERVICE_UNAVAILABLE: [
            r"HTTP\s+503",
            r"\b503\b",
            r"Service Unavailable",
            r"Tempo service not available"
        ]
    }

    # HTTP status code to error type mapping
    HTTP_STATUS_MAPPING = {
        401: ErrorType.AUTHENTICATION_FAILED,
        403: ErrorType.AUTHENTICATION_FAILED,
        503: ErrorType.SERVICE_UNAVAILABLE,
        504: ErrorType.TIMEOUT,
    }

    @classmethod
    def classify_error(cls, error_message: str, status_code: int = None) -> ErrorType:
        """
        Classify an error message into a specific error type.

        Args:
            error_message: The error message to classify
            status_code: Optional HTTP status code for direct classification

        Returns:
            ErrorType: The classified error type
        """
        # Check HTTP status code first if provided
        if status_code and status_code in cls.HTTP_STATUS_MAPPING:
            return cls.HTTP_STATUS_MAPPING[status_code]

        error_lower = error_message.lower()

        for error_type, patterns in cls.ERROR_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, error_lower, re.IGNORECASE):
                    return error_type

        return ErrorType.UNKNOWN

    @classmethod
    def get_user_friendly_message(cls, error_type: ErrorType, tempo_url: str) -> str:
        """
        Get a user-friendly error message based on the error type.

        Args:
            error_type: The classified error type
            tempo_url: The Tempo URL that was being accessed

        Returns:
            str: A user-friendly error message
        """
        messages = {
            ErrorType.CONNECTION_REFUSED: f"Tempo service refused connection at {tempo_url}. Check if Tempo is running in the observability-hub namespace.",
            ErrorType.DNS_RESOLUTION_FAILED: f"Tempo service not reachable at {tempo_url}. This is expected when running locally. Deploy to OpenShift to access Tempo.",
            ErrorType.HTTP_ERROR: f"HTTP error accessing Tempo at {tempo_url}. Check if the service is properly configured.",
            ErrorType.TIMEOUT: f"Request to Tempo timed out at {tempo_url}. The service may be overloaded or unreachable.",
            ErrorType.AUTHENTICATION_FAILED: f"Authentication failed when accessing Tempo at {tempo_url}. Check your credentials.",
            ErrorType.SERVICE_UNAVAILABLE: f"Tempo service is temporarily unavailable at {tempo_url}. Please try again later.",
            ErrorType.UNKNOWN: f"Unexpected error accessing Tempo at {tempo_url}"
        }

        return messages.get(error_type, messages[ErrorType.UNKNOWN])
