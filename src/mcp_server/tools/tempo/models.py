"""Data models for Tempo query responses."""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class QueryResponse:
    """Response structure for trace queries."""
    success: bool
    query: str
    traces: Optional[List[Dict[str, Any]]] = None
    total: Optional[int] = None
    time_range: Optional[str] = None
    api_endpoint: Optional[str] = None
    service_queried: Optional[str] = None
    duration_filter_ms: Optional[int] = None
    services_queried: Optional[List[str]] = None
    failed_services: Optional[List[str]] = None
    error: Optional[str] = None
    tempo_url: Optional[str] = None
    error_type: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class TraceDetailsResponse:
    """Response structure for trace details."""
    success: bool
    trace: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}
