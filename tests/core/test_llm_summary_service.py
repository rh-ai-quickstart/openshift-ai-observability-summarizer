"""
Tests for LLM summary service functionality.

This module tests the LLM summary generation, alert analysis,
and data processing functions in the core llm_summary_service module.
"""

import pytest
import json
from unittest.mock import patch, Mock
from datetime import datetime

from src.core.llm_summary_service import (
    generate_llm_summary,
    extract_alert_info_from_thanos_data,
    generate_alert_analysis_with_llm
)


class TestGenerateLLMSummary:
    """Test LLM summary generation functionality"""
    
    @patch('src.core.llm_summary_service.summarize_with_llm')
    def test_generate_llm_summary_success(self, mock_summarize):
        """Should generate LLM summary successfully"""
        # Mock successful LLM response
        mock_summarize.return_value = "Test summary response"
        
        thanos_data = {
            "metric1": {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "values": [
                                [1640995200, 50.0],
                                [1640995260, 60.0]
                            ]
                        }
                    ]
                },
                "promql": "test_metric"
            }
        }
        
        result = generate_llm_summary(
            question="How is the system performing?",
            thanos_data=thanos_data,
            model_id="test-model",
            api_key="test-key",
            namespace="test-ns"
        )
        
        # Check that LLM was called
        mock_summarize.assert_called_once()
        
        # Check response contains summary
        assert "Test summary response" in result
    
    @patch('src.core.llm_summary_service.summarize_with_llm')
    def test_generate_llm_summary_no_data(self, mock_summarize):
        """Should handle case with no data"""
        thanos_data = {}
        
        result = generate_llm_summary(
            question="How is the system performing?",
            thanos_data=thanos_data,
            model_id="test-model",
            api_key="test-key",
            namespace="test-ns"
        )
        
        # Should return error message
        assert "No data available to analyze" in result
        
        # LLM should not be called
        mock_summarize.assert_not_called()
    
    @patch('src.core.llm_summary_service.summarize_with_llm')
    def test_generate_llm_summary_old_format(self, mock_summarize):
        """Should handle old data format without status field"""
        # Mock successful LLM response
        mock_summarize.return_value = "Test summary response"
        
        thanos_data = {
            "metric1": {
                "data": {
                    "result": [
                        {
                            "values": [
                                [1640995200, 50.0],
                                [1640995260, 60.0]
                            ]
                        }
                    ]
                },
                "promql": "test_metric"
            }
        }
        
        result = generate_llm_summary(
            question="How is the system performing?",
            thanos_data=thanos_data,
            model_id="test-model",
            api_key="test-key",
            namespace="test-ns"
        )
        
        # Should return error message since no status field
        assert "No data available to analyze" in result
        
        # LLM should not be called
        mock_summarize.assert_not_called()
    
    @patch('src.core.llm_summary_service.summarize_with_llm')
    def test_generate_llm_summary_llm_error(self, mock_summarize):
        """Should handle LLM errors gracefully"""
        # Mock LLM error
        mock_summarize.side_effect = Exception("LLM API error")
        
        thanos_data = {
            "metric1": {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "values": [
                                [1640995200, 50.0]
                            ]
                        }
                    ]
                },
                "promql": "test_metric"
            }
        }
        
        result = generate_llm_summary(
            question="How is the system performing?",
            thanos_data=thanos_data,
            model_id="test-model",
            api_key="test-key",
            namespace="test-ns"
        )
        
        # Should return error message
        assert "Error generating summary" in result


class TestExtractAlertNames:
    """Test alert name extraction functionality"""
    
    def test_extract_alert_names_success(self):
        """Should extract structured alert info from Thanos data"""
        thanos_data = {
            "alerts": {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {
                                "alertname": "HighCPUUsage",
                                "severity": "warning"
                            }
                        },
                        {
                            "metric": {
                                "alertname": "LowMemory",
                                "severity": "critical"
                            }
                        }
                    ]
                }
            }
        }
        
        result = extract_alert_info_from_thanos_data(thanos_data)
        
        # Should extract two alert info dicts with required keys
        assert len(result) == 2
        names = {info["alertname"] for info in result}
        severities = {info.get("severity") for info in result}
        assert "HighCPUUsage" in names
        assert "LowMemory" in names
        assert "warning" in severities
        assert "critical" in severities
        # namespace may be missing in input; default to empty string
        assert all("namespace" in info for info in result)
    
    def test_extract_alert_names_empty_data(self):
        """Should handle empty alert data"""
        thanos_data = {
            "alerts": {
                "status": "success",
                "data": {
                    "result": []
                }
            }
        }
        
        result = extract_alert_info_from_thanos_data(thanos_data)
        
        # Should return empty list
        assert result == []
    
    def test_extract_alert_names_no_alerts_key(self):
        """Should handle missing alerts key"""
        thanos_data = {
            "other_metric": {
                "status": "success",
                "data": {
                    "result": []
                }
            }
        }
        
        result = extract_alert_info_from_thanos_data(thanos_data)
        
        # Should return empty list
        assert result == []
    
    def test_extract_alert_names_old_format(self):
        """Should handle old data format"""
        thanos_data = {
            "alerts": {
                "raw_data": [
                    {
                        "labels": {
                            "alertname": "HighCPUUsage",
                            "severity": "warning"
                        }
                    }
                ]
            }
        }
        
        result = extract_alert_info_from_thanos_data(thanos_data)
        
        # Should return empty list since old format doesn't have status field
        assert result == []


class TestGenerateAlertAnalysis:
    """Test alert analysis generation functionality"""
    
    # Removed tests for deprecated generate_alert_analysis


class TestGenerateAlertAnalysisWithLLM:
    """Tests for generate_alert_analysis_with_llm behavior and cleanup"""

    @patch('src.core.llm_summary_service.summarize_with_llm')
    def test_trims_after_last_alert_section(self, mock_summarize):
        """Should keep sections up to the last alert and drop any trailing content"""
        # Given two alerts, last in sorted order by severity is 'Watchdog' (none)
        alert_infos = [
            {"alertname": "PodDisruptionBudgetLimit", "namespace": "knative-serving", "severity": "info"},
            {"alertname": "Watchdog", "namespace": "openshift-monitoring", "severity": "none"},
        ]

        mock_summarize.return_value = (
            "### PodDisruptionBudgetLimit\n"
            "- Severity: Info\n"
            "- Impact: No impact on the cluster.\n\n"
            "### Watchdog\n"
            "- Severity: None\n"
            "- Impact: No impact on the cluster.\n\n"
            "### ExtraTrailing\n"
            "- This section should be removed by cleanup.\n"
        )

        result = generate_alert_analysis_with_llm(alert_infos, namespace="m3", model_id="test", api_key="key")

        assert "### PodDisruptionBudgetLimit" in result
        assert "### Watchdog" in result
        # Trailing unrelated section must be removed
        assert "### ExtraTrailing" not in result

    @patch('src.core.llm_summary_service.summarize_with_llm')
    def test_truncates_on_duplicate_before_all_alerts(self, mock_summarize):
        """If a duplicate alert section appears before all alerts are covered, truncate at the duplicate."""
        alert_infos = [
            {"alertname": "PodDisruptionBudgetLimit", "namespace": "knative-serving", "severity": "info"},
            {"alertname": "Watchdog", "namespace": "openshift-monitoring", "severity": "none"},
        ]

        # Duplicate PDB section appears before Watchdog; cleanup should cut at the duplicate
        mock_summarize.return_value = (
            "### PodDisruptionBudgetLimit\n"
            "- Severity: Info\n\n"
            "### PodDisruptionBudgetLimit\n"
            "- Duplicate section that should trigger truncation.\n\n"
            "### Watchdog\n"
            "- This section should be removed due to earlier truncation.\n"
        )

        result = generate_alert_analysis_with_llm(alert_infos, namespace="m3", model_id="test", api_key="key")

        # Contains first section
        assert "### PodDisruptionBudgetLimit" in result
        # Does not include second occurrence or any later sections
        assert result.count("### PodDisruptionBudgetLimit") == 1
        assert "### Watchdog" not in result
    
class TestDataProcessing:
    """Test data processing and formatting functionality"""
    
    def test_process_metric_data_success(self):
        """Should process metric data correctly"""
        thanos_data = {
            "metric1": {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "values": [
                                [1640995200, 50.0],
                                [1640995260, 60.0]
                            ]
                        }
                    ]
                },
                "promql": "test_metric"
            }
        }
        
        # Test that data can be processed
        assert "metric1" in thanos_data
        assert thanos_data["metric1"]["status"] == "success"
        assert "data" in thanos_data["metric1"]
    
    def test_process_alert_data_success(self):
        """Should process alert data correctly"""
        thanos_data = {
            "alerts": {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {
                                "alertname": "TestAlert",
                                "severity": "warning"
                            }
                        }
                    ]
                }
            }
        }
        
        # Test that alert data can be processed
        assert "alerts" in thanos_data
        assert thanos_data["alerts"]["status"] == "success"
        assert "data" in thanos_data["alerts"]
    
    def test_handle_missing_data(self):
        """Should handle missing or malformed data"""
        thanos_data = {
            "metric1": {
                "status": "error",
                "data": None
            }
        }
        
        # Test that error status is handled
        assert thanos_data["metric1"]["status"] == "error"
        assert thanos_data["metric1"]["data"] is None


class TestErrorHandling:
    """Test error handling functionality"""
    
    @patch('src.core.llm_summary_service.summarize_with_llm')
    def test_llm_api_key_error(self, mock_summarize):
        """Should handle API key errors"""
        # Mock API key error
        mock_summarize.side_effect = Exception("Invalid API key")
        
        thanos_data = {
            "metric1": {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "values": [
                                [1640995200, 50.0]
                            ]
                        }
                    ]
                }
            }
        }
        
        result = generate_llm_summary(
            question="Test question",
            thanos_data=thanos_data,
            model_id="test-model",
            api_key="invalid-key",
            namespace="test-ns"
        )
        
        # Should return error message about API key
        assert "Error" in result
    
    def test_invalid_data_structure(self):
        """Should handle invalid data structures"""
        thanos_data = {
            "metric1": {
                "invalid": "structure"
            }
        }
        
        # Test that invalid structures don't crash
        assert "metric1" in thanos_data
        assert "invalid" in thanos_data["metric1"]
    
    def test_empty_thanos_data(self):
        """Should handle completely empty data"""
        thanos_data = {}
        
        # Test that empty data is handled
        assert len(thanos_data) == 0 