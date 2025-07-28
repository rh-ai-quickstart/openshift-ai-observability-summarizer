"""
Core data models and schemas for the observability summarizer.

This module contains all Pydantic models used across the application,
providing a centralized location for data validation and serialization.
"""

from pydantic import BaseModel
from typing import List, Dict, Any, Optional


# --- Request Models ---

class AnalyzeRequest(BaseModel):
    """Request model for analyzing vLLM metrics"""
    model_name: str
    start_ts: int
    end_ts: int
    summarize_model_id: str
    api_key: Optional[str] = None


class ChatRequest(BaseModel):
    """Request model for chat-based metric analysis"""
    model_name: str
    prompt_summary: str
    question: str
    summarize_model_id: str
    api_key: Optional[str] = None


class ChatPrometheusRequest(BaseModel):
    """Request model for Prometheus-based chat queries"""
    model_name: str
    question: str
    start_ts: Optional[int] = None
    end_ts: Optional[int] = None
    namespace: str
    summarize_model_id: str
    api_key: Optional[str] = None
    messages: Optional[List[Dict[str, str]]] = None


class ChatMetricsRequest(BaseModel):
    """Request model for metrics-specific chat queries"""
    model_name: str
    question: str
    start_ts: Optional[int] = None
    end_ts: Optional[int] = None
    namespace: str
    summarize_model_id: str
    api_key: Optional[str] = None
    chat_scope: Optional[str] = "namespace_specific"  # "fleet_wide" or "namespace_specific"


class OpenShiftAnalyzeRequest(BaseModel):
    """Request model for OpenShift metrics analysis"""
    metric_category: str  # Specific category
    scope: str  # "cluster_wide" or "namespace_scoped"
    namespace: Optional[str] = None  # Required if scope is "namespace_scoped"
    start_ts: int
    end_ts: int
    summarize_model_id: str
    api_key: Optional[str] = None


class OpenShiftChatRequest(BaseModel):
    """Request model for OpenShift chat queries"""
    metric_category: str  # Specific category
    scope: str  # "cluster_wide" or "namespace_scoped"
    question: str
    namespace: Optional[str] = None  # Required if scope is "namespace_scoped"
    start_ts: int
    end_ts: int
    summarize_model_id: str
    api_key: Optional[str] = None


class ReportRequest(BaseModel):
    """Request model for report generation"""
    model_name: str
    start_ts: int
    end_ts: int
    summarize_model_id: str
    format: str
    api_key: Optional[str] = None
    health_prompt: Optional[str] = None
    llm_summary: Optional[str] = None
    metrics_data: Optional[Dict[str, Any]] = None
    trend_chart_image: Optional[str] = None


class MetricsCalculationRequest(BaseModel):
    """Request model for metrics calculations"""
    metrics_data: Dict[str, List[Dict[str, Any]]]


class MetricsCalculationResponse(BaseModel):
    """Response model for metrics calculations"""
    calculated_metrics: Dict[str, Dict[str, Optional[float]]] 