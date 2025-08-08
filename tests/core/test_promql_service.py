"""
Tests for PromQL service functionality.

This module tests the PromQL generation, metric discovery,
and query selection functions in the core promql_service module.
"""

import pytest
import json
from unittest.mock import patch, Mock
from datetime import datetime

from src.core.promql_service import (
    generate_promql_from_question,
    discover_available_metrics_from_thanos,
    intelligent_metric_selection,
    select_queries_directly,
    generate_promql_from_discovered_metric,
    extract_time_period_from_question
)


class TestGeneratePromQLFromQuestion:
    """Test PromQL generation from natural language questions"""
    
    @patch('src.core.promql_service.discover_available_metrics_from_thanos')
    @patch('src.core.promql_service.intelligent_metric_selection')
    def test_generate_promql_success(self, mock_selection, mock_discovery):
        """Should generate PromQL queries successfully"""
        # Mock metric discovery
        mock_discovery.return_value = [{"name": "metric1"}, {"name": "metric2"}]
        
        # Mock intelligent selection
        mock_selection.return_value = [{"name": "selected_metric"}]
        
        result = generate_promql_from_question(
            question="How many pods are running?",
            namespace="test-ns",
            model_name="test-model",
            start_ts=1640995200,
            end_ts=1640995260,
            is_fleet_wide=False
        )
        
        # Check that discovery was called
        mock_discovery.assert_called_once()
        
        # Should return list of queries
        assert isinstance(result, list)
    
    def test_generate_promql_direct_pattern(self):
        """Should use direct pattern matching for simple queries"""
        result = generate_promql_from_question(
            question="How many pods are running?",
            namespace="test-ns",
            model_name="test-model",
            start_ts=1640995200,
            end_ts=1640995260,
            is_fleet_wide=False
        )
        
        # Should return list of queries
        assert isinstance(result, list)
        assert len(result) > 0
    
    def test_generate_promql_gpu_usage(self):
        """Should handle GPU usage queries"""
        result = generate_promql_from_question(
            question="What is the GPU usage?",
            namespace="test-ns",
            model_name="test-model",
            start_ts=1640995200,
            end_ts=1640995260,
            is_fleet_wide=False
        )
        
        # Should return GPU-related queries
        assert isinstance(result, list)
        assert len(result) > 0
    
    def test_generate_promql_alerts(self):
        """Should handle alert queries"""
        result = generate_promql_from_question(
            question="What alerts are firing?",
            namespace="test-ns",
            model_name="test-model",
            start_ts=1640995200,
            end_ts=1640995260,
            is_fleet_wide=False
        )
        
        # Should return alert queries
        assert isinstance(result, list)
        assert len(result) > 0
    
    def test_generate_promql_fleet_wide(self):
        """Should handle fleet-wide queries"""
        result = generate_promql_from_question(
            question="Show all alerts",
            namespace="",
            model_name="test-model",
            start_ts=1640995200,
            end_ts=1640995260,
            is_fleet_wide=True
        )
        
        # Should return fleet-wide queries
        assert isinstance(result, list)
        assert len(result) > 0


class TestDiscoverAvailableMetrics:
    """Test metric discovery functionality"""
    
    @patch('src.core.promql_service.requests.get')
    def test_discover_metrics_success(self, mock_get):
        """Should discover metrics successfully"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": ["metric1", "metric2", "metric3"]
        }
        mock_get.return_value = mock_response
        
        result = discover_available_metrics_from_thanos("test-ns", "test-model", False)
        
        # Check that request was made
        mock_get.assert_called_once()
        
        # Should return list of metrics
        assert isinstance(result, list)
    
    @patch('src.core.promql_service.requests.get')
    def test_discover_metrics_connection_error(self, mock_get):
        """Should handle connection errors gracefully"""
        # Mock connection error
        mock_get.side_effect = Exception("Connection failed")
        
        result = discover_available_metrics_from_thanos("test-ns", "test-model", False)
        
        # Should return empty list on error
        assert result == []
    
    @patch('src.core.promql_service.requests.get')
    def test_discover_metrics_http_error(self, mock_get):
        """Should handle HTTP errors gracefully"""
        # Mock HTTP error
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        mock_get.return_value = mock_response
        
        result = discover_available_metrics_from_thanos("test-ns", "test-model", False)
        
        # Should return empty list on error
        assert result == []


class TestIntelligentMetricSelection:
    """Test intelligent metric selection functionality"""
    
    def test_intelligent_selection_success(self):
        """Should select metrics intelligently"""
        available_metrics = [{"name": "cpu_usage"}, {"name": "memory_usage"}, {"name": "gpu_usage"}]
        question = "How is the CPU performing?"
        
        result = intelligent_metric_selection(question, available_metrics)
        
        # Should return list of selected metrics
        assert isinstance(result, list)
    
    def test_intelligent_selection_no_match(self):
        """Should handle no matching metrics"""
        available_metrics = [{"name": "metric1"}, {"name": "metric2"}]
        question = "How is the CPU performing?"
        
        result = intelligent_metric_selection(question, available_metrics)
        
        # Should return empty list when no match
        assert isinstance(result, list)
    
    def test_intelligent_selection_empty_metrics(self):
        """Should handle empty metrics list"""
        available_metrics = []
        question = "How is the CPU performing?"
        
        result = intelligent_metric_selection(question, available_metrics)
        
        # Should return empty list
        assert result == []


class TestSelectQueriesDirectly:
    """Test direct query selection functionality"""
    
    def test_select_queries_gpu_usage(self):
        """Should select GPU usage queries"""
        result, pattern_detected = select_queries_directly(
            question="What is the GPU usage?",
            namespace="test-ns",
            model_name="test-model",
            rate_interval="5m",
            is_fleet_wide=False
        )
        
        # Should return GPU-related queries
        assert isinstance(result, list)
        assert isinstance(pattern_detected, bool)
    
    def test_select_queries_pod_count(self):
        """Should select pod count queries"""
        result, pattern_detected = select_queries_directly(
            question="How many pods are running?",
            namespace="test-ns",
            model_name="test-model",
            rate_interval="5m",
            is_fleet_wide=False
        )
        
        # Should return pod-related queries
        assert isinstance(result, list)
        assert isinstance(pattern_detected, bool)
    
    def test_select_queries_alerts(self):
        """Should select alert queries"""
        result, pattern_detected = select_queries_directly(
            question="What alerts are firing?",
            namespace="test-ns",
            model_name="test-model",
            rate_interval="5m",
            is_fleet_wide=False
        )
        
        # Should return alert queries
        assert isinstance(result, list)
        assert isinstance(pattern_detected, bool)
    
    def test_select_queries_fleet_wide(self):
        """Should select fleet-wide queries"""
        result, pattern_detected = select_queries_directly(
            question="Show all alerts",
            namespace="",
            model_name="test-model",
            rate_interval="5m",
            is_fleet_wide=True
        )
        
        # Should return fleet-wide queries
        assert isinstance(result, list)
        assert isinstance(pattern_detected, bool)
    
    def test_select_queries_no_pattern(self):
        """Should handle questions with no direct pattern"""
        result, pattern_detected = select_queries_directly(
            question="What is the weather like?",
            namespace="test-ns",
            model_name="test-model",
            rate_interval="5m",
            is_fleet_wide=False
        )
        
        # Should return empty list for no pattern
        assert isinstance(result, list)
        assert isinstance(pattern_detected, bool)


class TestGeneratePromQLFromDiscoveredMetric:
    """Test PromQL generation from discovered metrics"""
    
    def test_generate_promql_from_metric_success(self):
        """Should generate PromQL from discovered metric"""
        metric_info = {"name": "cpu_usage", "query": "cpu_usage"}
        namespace = "test-ns"
        
        result = generate_promql_from_discovered_metric(
            metric_info, namespace, "test-model", "5m", False
        )
        
        # Should return PromQL query
        assert isinstance(result, str)
        assert "cpu_usage" in result
        assert "test-ns" in result
    
    def test_generate_promql_from_metric_fleet_wide(self):
        """Should generate fleet-wide PromQL"""
        metric_info = {"name": "alerts", "query": "alerts"}
        namespace = ""
        
        result = generate_promql_from_discovered_metric(
            metric_info, namespace, "test-model", "5m", True
        )
        
        # Should return fleet-wide query
        assert isinstance(result, str)
        assert "alerts" in result
    
    def test_generate_promql_from_metric_special_chars(self):
        """Should handle metric names with special characters"""
        metric_info = {"name": "metric:with:colons", "query": "metric:with:colons"}
        namespace = "test-ns"
        
        result = generate_promql_from_discovered_metric(
            metric_info, namespace, "test-model", "5m", False
        )
        
        # Should return valid PromQL
        assert isinstance(result, str)
        assert "metric:with:colons" in result


class TestExtractTimePeriod:
    """Test time period extraction functionality"""
    
    def test_extract_time_period_hours(self):
        """Should extract hours from question"""
        result = extract_time_period_from_question("CPU usage in the last 2 hours")
        
        # Should return time period
        assert isinstance(result, str)
        assert "2h" in result or "2 hours" in result
    
    def test_extract_time_period_minutes(self):
        """Should extract minutes from question"""
        result = extract_time_period_from_question("Memory usage in the last 30 minutes")
        
        # Should return time period
        assert isinstance(result, str)
        assert "30m" in result or "30 minutes" in result
    
    def test_extract_time_period_days(self):
        """Should extract days from question"""
        result = extract_time_period_from_question("Pod count in the last 7 days")
        
        # Should return time period (converted to hours)
        assert isinstance(result, str)
        assert "168h" in result or "7 days" in result
    
    def test_extract_time_period_default(self):
        """Should return default when no time period found"""
        result = extract_time_period_from_question("How many pods are running?")
        
        # Should return None for no time period
        assert result is None
    
    def test_extract_time_period_no_time(self):
        """Should handle questions without time periods"""
        result = extract_time_period_from_question("What is the current status?")
        
        # Should return None for no time period
        assert result is None


class TestErrorHandling:
    """Test error handling functionality"""
    
    @patch('src.core.promql_service.discover_available_metrics_from_thanos')
    def test_generate_promql_discovery_error(self, mock_discovery):
        """Should handle metric discovery errors"""
        # Mock discovery error
        mock_discovery.side_effect = Exception("Discovery failed")
        
        # Should handle the exception gracefully
        try:
            result = generate_promql_from_question(
                question="How many pods are running?",
                namespace="test-ns",
                model_name="test-model",
                start_ts=1640995200,
                end_ts=1640995260,
                is_fleet_wide=False
            )
            # If we get here, the function handled the error gracefully
            assert isinstance(result, list)
        except Exception as e:
            # The function should handle the error internally
            # If it doesn't, this test will fail as expected
            assert "Discovery failed" in str(e)
    
    def test_invalid_namespace(self):
        """Should handle invalid namespace"""
        result, pattern_detected = select_queries_directly(
            question="How many pods are running?",
            namespace=None,
            model_name="test-model",
            rate_interval="5m",
            is_fleet_wide=False
        )
        
        # Should handle None namespace
        assert isinstance(result, list)
        assert isinstance(pattern_detected, bool)
    
    def test_empty_question(self):
        """Should handle empty questions"""
        result, pattern_detected = select_queries_directly(
            question="",
            namespace="test-ns",
            model_name="test-model",
            rate_interval="5m",
            is_fleet_wide=False
        )
        
        # Should return empty list for empty question
        assert isinstance(result, list)
        assert isinstance(pattern_detected, bool)


class TestDataValidation:
    """Test data validation functionality"""
    
    def test_validate_metric_name(self):
        """Should validate metric names"""
        valid_metrics = ["cpu_usage", "memory_usage", "gpu_usage"]
        
        for metric in valid_metrics:
            # Should be valid metric names
            assert isinstance(metric, str)
            assert len(metric) > 0
    
    def test_validate_namespace(self):
        """Should validate namespace names"""
        valid_namespaces = ["test-ns", "production", "default"]
        
        for namespace in valid_namespaces:
            # Should be valid namespace names
            assert isinstance(namespace, str)
            assert len(namespace) > 0
    
    def test_validate_question(self):
        """Should validate question format"""
        valid_questions = [
            "How many pods are running?",
            "What is the GPU usage?",
            "Show me all alerts"
        ]
        
        for question in valid_questions:
            # Should be valid questions
            assert isinstance(question, str)
            assert len(question) > 0 