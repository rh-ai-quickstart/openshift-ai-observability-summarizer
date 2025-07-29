"""
Report generation and file management utilities.

This module contains utilities for saving, retrieving, and building 
report schemas for the observability summarizer. Functions handle
file operations and data structure creation for report generation.
"""

import os
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
import sys

# Import ReportSchema and MetricCard - using try/except for robust import
try:
    # Try direct import first (for when running from API context)
    from report_assets.report_renderer import ReportSchema, MetricCard
except ImportError:
    # Add path for report_assets import when running independently
    current_dir = os.path.dirname(os.path.abspath(__file__))
    api_dir = os.path.join(os.path.dirname(current_dir), 'api')
    sys.path.insert(0, api_dir)
    from report_assets.report_renderer import ReportSchema, MetricCard
from .metrics import calculate_metric_stats


def save_report(report_content, format: str) -> str:
    """
    Save report content to a file and return unique report ID.
    
    Args:
        report_content: Report content (string or bytes)
        format: File format extension (e.g., 'html', 'pdf', 'md')
        
    Returns:
        Unique report ID (UUID string)
    """
    report_id = str(uuid.uuid4())
    reports_dir = "/tmp/reports"
    os.makedirs(reports_dir, exist_ok=True)

    report_path = os.path.join(reports_dir, f"{report_id}.{format.lower()}")

    # Handle both string and bytes content
    if isinstance(report_content, bytes):
        with open(report_path, "wb") as f:
            f.write(report_content)
    else:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)

    return report_id


def get_report_path(report_id: str) -> str:
    """
    Get file path for a report ID.
    
    Args:
        report_id: Unique report identifier
        
    Returns:
        Full file path to the report
        
    Raises:
        FileNotFoundError: If report ID is not found
    """
    reports_dir = "/tmp/reports"

    # Try to find the file with any extension
    for file in os.listdir(reports_dir):
        if file.startswith(report_id):
            return os.path.join(reports_dir, file)

    raise FileNotFoundError(f"Report {report_id} not found")


def build_report_schema(
    metrics_data: Dict[str, Any],
    summary: str,
    model_name: str,
    start_ts: int,
    end_ts: int,
    summarize_model_id: str,
    trend_chart_image: Optional[str] = None,
) -> ReportSchema:
    """
    Build a structured report schema from metrics data and metadata.
    
    Args:
        metrics_data: Dictionary of metric names to data points
        summary: AI-generated summary text
        model_name: Name of the analyzed model
        start_ts: Start timestamp (Unix epoch)
        end_ts: End timestamp (Unix epoch)
        summarize_model_id: ID of the model used for summarization
        trend_chart_image: Optional base64 encoded chart image
        
    Returns:
        ReportSchema object ready for report generation
    """
    # Extract available metrics from the metrics_data dictionary
    key_metrics = list(metrics_data.keys())
    metric_cards = []
    
    for metric_name in key_metrics:
        data = metrics_data.get(metric_name, [])
        avg_val, max_val = calculate_metric_stats(data)
        metric_cards.append(
            MetricCard(
                name=metric_name,
                avg=avg_val,
                max=max_val,
                values=data,
            )
        )
    
    return ReportSchema(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        model_name=model_name,
        start_date=datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M:%S"),
        end_date=datetime.fromtimestamp(end_ts).strftime("%Y-%m-%d %H:%M:%S"),
        summarize_model_id=summarize_model_id,
        summary=summary,
        metrics=metric_cards,
        trend_chart_image=trend_chart_image,
    ) 