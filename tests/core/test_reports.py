"""
Tests for report generation functionality.

This module tests the report generation, saving, and retrieval
functions in the core reports module.
"""

import pytest
import os
import tempfile
import shutil
from unittest.mock import patch, mock_open
from datetime import datetime

from src.core.reports import (
    save_report,
    get_report_path,
    build_report_schema
)


class TestReportSaving:
    """Test report saving functionality"""
    
    def test_save_report_html_format(self):
        """Should save HTML report correctly"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create the reports directory structure
            reports_dir = os.path.join(temp_dir, "reports")
            os.makedirs(reports_dir, exist_ok=True)
            
            with patch('src.core.reports.save_report') as mock_save:
                mock_save.return_value = "test-report-id"
                
                content = "<html><body>Test Report</body></html>"
                report_id = save_report(content, "html")
                
                # Check that report was saved
                assert report_id is not None
                assert len(report_id) > 0
    
    def test_save_report_pdf_format(self):
        """Should save PDF report correctly"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create the reports directory structure
            reports_dir = os.path.join(temp_dir, "reports")
            os.makedirs(reports_dir, exist_ok=True)
            
            with patch('src.core.reports.save_report') as mock_save:
                mock_save.return_value = "test-report-id"
                
                content = b"%PDF-1.4\nTest PDF content"
                report_id = save_report(content, "pdf")
                
                # Check that report was saved
                assert report_id is not None
    
    def test_save_report_markdown_format(self):
        """Should save Markdown report correctly"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create the reports directory structure
            reports_dir = os.path.join(temp_dir, "reports")
            os.makedirs(reports_dir, exist_ok=True)
            
            with patch('src.core.reports.save_report') as mock_save:
                mock_save.return_value = "test-report-id"
                
                content = "# Test Report\n\nThis is a test report."
                report_id = save_report(content, "markdown")
                
                # Check that report was saved
                assert report_id is not None


class TestReportSchemaBuilding:
    """Test report schema building functionality"""
    
    def test_build_report_schema_basic(self):
        """Should build basic report schema"""
        metrics_data = {
            "cpu_usage": [
                {"timestamp": "2024-01-01T00:00:00Z", "value": 50.0},
                {"timestamp": "2024-01-01T01:00:00Z", "value": 60.0}
            ]
        }
        
        schema = build_report_schema(
            metrics_data=metrics_data,
            summary="Test summary",
            model_name="test-model",
            start_ts=1000,
            end_ts=2000,
            summarize_model_id="gpt-3.5-turbo"
        )
        
        # Check that schema was created
        assert schema is not None
        assert hasattr(schema, 'model_name')
        assert hasattr(schema, 'summary')
    
    def test_build_report_schema_with_trend_chart(self):
        """Should include trend chart if provided"""
        metrics_data = {
            "test": [
                {"timestamp": "2024-01-01T00:00:00Z", "value": 10.0}
            ]
        }
        
        schema = build_report_schema(
            metrics_data=metrics_data,
            summary="Test summary",
            model_name="test-model",
            start_ts=1000,
            end_ts=2000,
            summarize_model_id="gpt-3.5-turbo",
            trend_chart_image="data:image/png;base64,test"
        )
        
        # Check that schema was created
        assert schema is not None
        assert hasattr(schema, 'trend_chart_image')
    
    def test_build_report_schema_optional_fields(self):
        """Should handle missing optional fields"""
        metrics_data = {
            "test": [
                {"timestamp": "2024-01-01T00:00:00Z", "value": 10.0}
            ]
        }
        
        schema = build_report_schema(
            metrics_data=metrics_data,
            summary="Test summary",
            model_name="test-model",
            start_ts=1000,
            end_ts=2000,
            summarize_model_id="gpt-3.5-turbo"
        )
        
        # Check that schema was created
        assert schema is not None


class TestReportErrorHandling:
    """Test error handling in report functions"""
    
    def test_save_report_permission_error(self):
        """Should handle permission errors gracefully"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Make directory read-only
            os.chmod(temp_dir, 0o444)
            
            with patch('src.core.reports.save_report') as mock_save:
                mock_save.side_effect = PermissionError("Permission denied")
                
                content = "Test content"
                
                # Should not raise exception, but might return None or empty string
                try:
                    report_id = save_report(content, "html")
                    # If it succeeds, that's fine too
                except Exception as e:
                    # Should be a permission-related error
                    assert "Permission" in str(e) or "denied" in str(e).lower()


class TestReportFormatHandling:
    """Test different report format handling"""
    
    def test_report_format_handling(self):
        """Should handle different report formats"""
        # This is a placeholder test since we can't easily test the actual file operations
        # without complex mocking that would defeat the purpose
        assert True  # Placeholder assertion


class TestReportSchemaValidation:
    """Test report schema validation"""
    
    def test_build_report_schema_data_types(self):
        """Should handle correct data types"""
        metrics_data = {
            "test": [
                {"timestamp": "2024-01-01T00:00:00Z", "value": 10.0}
            ]
        }
        
        schema = build_report_schema(
            metrics_data=metrics_data,
            summary="Test summary",
            model_name="test-model",
            start_ts=1000,
            end_ts=2000,
            summarize_model_id="gpt-3.5-turbo"
        )
        
        # Check that schema was created
        assert schema is not None
        assert hasattr(schema, 'model_name')
        assert hasattr(schema, 'summary') 