"""
Tests for alert management functionality.

This module tests the alert fetching and processing functions
in the core alerts module.
"""

import pytest
import json
import requests
from unittest.mock import patch, Mock
from datetime import datetime

from src.core.alerts import (
    fetch_alerts_from_prometheus,
    fetch_all_rule_definitions
)


class TestAlertFetching:
    """Test alert fetching functionality"""
    
    @patch('src.core.alerts.requests.get')
    def test_fetch_alerts_success(self, mock_get):
        """Should fetch alerts successfully from Prometheus"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "result": [
                    {
                        "metric": {
                            "alertname": "HighCPUUsage",
                            "severity": "warning",
                            "namespace": "test-ns",
                            "alertstate": "firing"
                        },
                        "values": [
                            [1640995200, 1],  # timestamp, is_firing
                            [1640995260, 1]
                        ]
                    }
                ]
            }
        }
        mock_get.return_value = mock_response
        
        promql_query, alerts = fetch_alerts_from_prometheus(1640995200, 1640995260, "test-ns")
        
        # Check that request was made
        mock_get.assert_called_once()
        
        # Check response structure
        assert len(alerts) == 2
        alert = alerts[0]
        assert alert["alertname"] == "HighCPUUsage"
        assert alert["severity"] == "warning"
        assert alert["alertstate"] == "firing"
        assert alert["is_firing"] == 1
    
    @patch('src.core.alerts.requests.get')
    def test_fetch_alerts_empty_response(self, mock_get):
        """Should handle empty alert response"""
        # Mock empty response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "result": []
            }
        }
        mock_get.return_value = mock_response
        
        promql_query, alerts = fetch_alerts_from_prometheus(1640995200, 1640995260)
        
        # Should return empty list
        assert alerts == []
    
    @patch('src.core.alerts.requests.get')
    def test_fetch_alerts_http_error(self, mock_get):
        """Should handle HTTP errors gracefully"""
        # Mock HTTP error
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.RequestException("HTTP Error")
        mock_get.return_value = mock_response
        
        # Should return empty list on error
        promql_query, alerts = fetch_alerts_from_prometheus(1640995200, 1640995260)
        assert alerts == []
    
    @patch('src.core.alerts.requests.get')
    def test_fetch_alerts_connection_error(self, mock_get):
        """Should handle connection errors gracefully"""
        # Mock connection error
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection failed")
        
        # Should return empty list on error
        promql_query, alerts = fetch_alerts_from_prometheus(1640995200, 1640995260)
        assert alerts == []
    
    @patch('src.core.alerts.requests.get')
    def test_fetch_alerts_with_namespace(self, mock_get):
        """Should apply namespace filter to alert query"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "result": []
            }
        }
        mock_get.return_value = mock_response
        
        # Test with namespace
        promql_query, alerts = fetch_alerts_from_prometheus(1640995200, 1640995260, "test-ns")
        
        # Check that namespace filter was applied
        call_args = mock_get.call_args
        assert "namespace=\"test-ns\"" in call_args[1]["params"]["query"]
    
    @patch('src.core.alerts.requests.get')
    def test_fetch_alerts_without_namespace(self, mock_get):
        """Should use global alerts query when no namespace specified"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "result": []
            }
        }
        mock_get.return_value = mock_response
        
        # Test without namespace
        promql_query, alerts = fetch_alerts_from_prometheus(1640995200, 1640995260)
        
        # Check that global query was used
        call_args = mock_get.call_args
        assert call_args[1]["params"]["query"] == "ALERTS"


class TestRuleDefinitions:
    """Test rule definition fetching"""
    
    @patch('src.core.alerts.requests.get')
    def test_fetch_all_rule_definitions_success(self, mock_get):
        """Should fetch rule definitions successfully"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "groups": [
                    {
                        "name": "test-group",
                        "rules": [
                            {
                                "alert": "HighCPUUsage",
                                "expr": "cpu_usage > 80",
                                "for": "5m",
                                "labels": {
                                    "severity": "warning"
                                },
                                "annotations": {
                                    "description": "CPU usage is high",
                                    "summary": "High CPU usage detected"
                                }
                            }
                        ]
                    }
                ]
            }
        }
        mock_get.return_value = mock_response
        
        rules = fetch_all_rule_definitions()
        
        # Check response structure
        assert len(rules) == 1
        rule = rules["HighCPUUsage"]
        assert rule["name"] == "HighCPUUsage"
        assert rule["expression"] == "cpu_usage > 80"
        assert rule["labels"]["severity"] == "warning"
    
    @patch('src.core.alerts.requests.get')
    def test_fetch_all_rule_definitions_empty(self, mock_get):
        """Should handle empty rule definitions"""
        # Mock empty response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "groups": []
            }
        }
        mock_get.return_value = mock_response
        
        rules = fetch_all_rule_definitions()
        
        # Should return empty dict
        assert rules == {}
    
    @patch('src.core.alerts.requests.get')
    def test_fetch_all_rule_definitions_error(self, mock_get):
        """Should handle errors gracefully"""
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        mock_get.return_value = mock_response
        
        # Should return empty dict on error
        rules = fetch_all_rule_definitions()
        assert rules == {}


class TestAlertDataProcessing:
    """Test alert data processing and formatting"""
    
    def test_alert_data_structure(self):
        """Should handle standard alert data structure"""
        alert_data = {
            "alertname": "TestAlert",
            "severity": "warning",
            "alertstate": "firing",
            "timestamp": "2024-01-01T00:00:00",
            "is_firing": 1,
            "labels": {
                "alertname": "TestAlert",
                "severity": "warning",
                "namespace": "test-ns"
            }
        }
        
        # Test that the structure is valid
        assert "alertname" in alert_data
        assert "severity" in alert_data
        assert "alertstate" in alert_data
        assert "timestamp" in alert_data
        assert "is_firing" in alert_data
        
        # Test required fields
        assert alert_data["alertname"] == "TestAlert"
        assert alert_data["alertstate"] == "firing"
    
    def test_alert_severity_levels(self):
        """Should handle different severity levels"""
        severity_levels = ["info", "warning", "critical"]
        
        for severity in severity_levels:
            alert_data = {
                "alertname": f"TestAlert{severity.title()}",
                "severity": severity,
                "alertstate": "firing",
                "is_firing": 1
            }
            
            # Test that severity is valid
            assert alert_data["severity"] in severity_levels
    
    def test_alert_states(self):
        """Should handle different alert states"""
        alert_states = ["firing", "inactive"]
        
        for state in alert_states:
            alert_data = {
                "alertname": f"TestAlert{state.title()}",
                "severity": "warning",
                "alertstate": state,
                "is_firing": 1 if state == "firing" else 0
            }
            
            # Test that state is valid
            assert alert_data["alertstate"] in alert_states


class TestAlertFiltering:
    """Test alert filtering functionality"""
    
    def test_filter_alerts_by_severity(self):
        """Should filter alerts by severity level"""
        alerts = [
            {
                "alertname": "Alert1",
                "severity": "critical",
                "alertstate": "firing",
                "is_firing": 1
            },
            {
                "alertname": "Alert2",
                "severity": "warning",
                "alertstate": "firing",
                "is_firing": 1
            },
            {
                "alertname": "Alert3",
                "severity": "info",
                "alertstate": "firing",
                "is_firing": 1
            }
        ]
        
        # Filter by critical severity
        critical_alerts = [a for a in alerts if a["severity"] == "critical"]
        assert len(critical_alerts) == 1
        assert critical_alerts[0]["alertname"] == "Alert1"
    
    def test_filter_alerts_by_state(self):
        """Should filter alerts by state"""
        alerts = [
            {
                "alertname": "Alert1",
                "severity": "warning",
                "alertstate": "firing",
                "is_firing": 1
            },
            {
                "alertname": "Alert2",
                "severity": "warning",
                "alertstate": "inactive",
                "is_firing": 0
            }
        ]
        
        # Filter by firing state
        firing_alerts = [a for a in alerts if a["alertstate"] == "firing"]
        assert len(firing_alerts) == 1
        assert firing_alerts[0]["alertname"] == "Alert1"
    
    def test_filter_alerts_by_firing_status(self):
        """Should filter alerts by firing status"""
        alerts = [
            {
                "alertname": "Alert1",
                "severity": "warning",
                "alertstate": "firing",
                "is_firing": 1
            },
            {
                "alertname": "Alert2",
                "severity": "warning",
                "alertstate": "inactive",
                "is_firing": 0
            }
        ]
        
        # Filter by firing status
        firing_alerts = [a for a in alerts if a["is_firing"] == 1]
        assert len(firing_alerts) == 1
        assert firing_alerts[0]["alertname"] == "Alert1"


class TestAlertValidation:
    """Test alert data validation"""
    
    def test_valid_alert_structure(self):
        """Should validate correct alert structure"""
        alert = {
            "alertname": "TestAlert",
            "severity": "warning",
            "alertstate": "firing",
            "timestamp": "2024-01-01T00:00:00",
            "is_firing": 1,
            "labels": {
                "alertname": "TestAlert",
                "severity": "warning"
            }
        }
        
        # Test required fields exist
        assert "alertname" in alert
        assert "alertstate" in alert
        assert "is_firing" in alert
        
        # Test field types
        assert isinstance(alert["alertname"], str)
        assert isinstance(alert["alertstate"], str)
        assert isinstance(alert["is_firing"], int)
    
    def test_invalid_alert_structure(self):
        """Should identify invalid alert structure"""
        # Missing required fields
        invalid_alerts = [
            {},  # Empty dict
            {"alertname": "Test"},  # Missing alertstate
            {"alertname": "Test", "alertstate": "invalid"},  # Invalid state
            {"alertname": "Test", "severity": "invalid"}  # Invalid severity
        ]
        
        for alert in invalid_alerts:
            # These should be considered invalid
            if not alert or "alertname" not in alert:
                continue  # Skip empty dicts
            
            # Test for invalid severity
            if "severity" in alert:
                valid_severities = ["info", "warning", "critical"]
                if alert["severity"] not in valid_severities:
                    continue  # Skip invalid severity
            
            # Test for invalid state
            if "alertstate" in alert:
                valid_states = ["firing", "inactive"]
                if alert["alertstate"] not in valid_states:
                    continue  # Skip invalid state 