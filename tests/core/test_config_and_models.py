"""
Tests for core configuration and data models.

This module tests the configuration management and Pydantic models
used throughout the application.
"""

import pytest
import os
import json
from unittest.mock import patch, mock_open
from pydantic import ValidationError

from src.core.config import (
    load_model_config,
    load_thanos_token,
    get_ca_verify_setting,
    PROMETHEUS_URL,
    LLAMA_STACK_URL,
    LLM_API_TOKEN
)
from src.core.models import (
    AnalyzeRequest,
    ChatRequest,
    ChatPrometheusRequest,
    ChatMetricsRequest,
    OpenShiftAnalyzeRequest,
    OpenShiftChatRequest,
    ReportRequest,
    MetricsCalculationRequest,
    MetricsCalculationResponse
)


class TestConfigFunctions:
    """Test configuration loading functions"""
    
    def test_load_model_config_valid_json(self):
        """Should load valid JSON model config"""
        with patch.dict(os.environ, {"MODEL_CONFIG": '{"test": "value"}'}):
            result = load_model_config()
            assert result == {"test": "value"}
    
    def test_load_model_config_invalid_json(self):
        """Should return empty dict for invalid JSON"""
        with patch.dict(os.environ, {"MODEL_CONFIG": 'invalid json'}):
            result = load_model_config()
            assert result == {}
    
    def test_load_model_config_missing_env(self):
        """Should return empty dict when env var is missing"""
        with patch.dict(os.environ, {}, clear=True):
            result = load_model_config()
            assert result == {}
    
    def test_load_thanos_token_from_file(self):
        """Should load token from file when path exists"""
        mock_token = "test-token-content"
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=mock_token)):
                result = load_thanos_token()
                assert result == mock_token
    
    def test_load_thanos_token_from_env(self):
        """Should return env var when file doesn't exist"""
        test_token = "env-token"
        with patch("os.path.exists", return_value=False):
            with patch.dict(os.environ, {"THANOS_TOKEN": test_token}):
                result = load_thanos_token()
                assert result == test_token
    
    def test_get_ca_verify_setting_with_bundle(self):
        """Should return bundle path when CA bundle exists"""
        with patch("os.path.exists", return_value=True):
            result = get_ca_verify_setting()
            assert result == "/etc/pki/ca-trust/extracted/pem/ca-bundle.crt"
    
    def test_get_ca_verify_setting_without_bundle(self):
        """Should return True when CA bundle doesn't exist"""
        with patch("os.path.exists", return_value=False):
            result = get_ca_verify_setting()
            assert result is True


class TestEnvironmentVariables:
    """Test environment variable defaults"""
    
    def test_prometheus_url_default(self):
        """Should have correct default Prometheus URL"""
        assert PROMETHEUS_URL == os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    
    def test_llama_stack_url_default(self):
        """Should have correct default LLama stack URL"""
        assert LLAMA_STACK_URL == os.getenv("LLAMA_STACK_URL", "http://localhost:8321/v1/openai/v1")
    
    def test_llm_api_token_default(self):
        """Should have empty default LLM API token"""
        assert LLM_API_TOKEN == os.getenv("LLM_API_TOKEN", "")


class TestAnalyzeRequest:
    """Test AnalyzeRequest model validation"""
    
    def test_valid_analyze_request(self):
        """Should accept valid request data"""
        data = {
            "model_name": "test-model",
            "start_ts": 1000,
            "end_ts": 2000,
            "summarize_model_id": "gpt-3.5-turbo",
            "api_key": "test-key"
        }
        request = AnalyzeRequest(**data)
        assert request.model_name == "test-model"
        assert request.start_ts == 1000
        assert request.end_ts == 2000
        assert request.summarize_model_id == "gpt-3.5-turbo"
        assert request.api_key == "test-key"
    
    def test_analyze_request_without_api_key(self):
        """Should accept request without API key"""
        data = {
            "model_name": "test-model",
            "start_ts": 1000,
            "end_ts": 2000,
            "summarize_model_id": "gpt-3.5-turbo"
        }
        request = AnalyzeRequest(**data)
        assert request.api_key is None
    
    def test_analyze_request_missing_required_fields(self):
        """Should raise validation error for missing required fields"""
        with pytest.raises(ValidationError):
            AnalyzeRequest(model_name="test")


class TestChatRequest:
    """Test ChatRequest model validation"""
    
    def test_valid_chat_request(self):
        """Should accept valid chat request data"""
        data = {
            "model_name": "test-model",
            "prompt_summary": "Test summary",
            "question": "What is the status?",
            "summarize_model_id": "gpt-3.5-turbo",
            "api_key": "test-key"
        }
        request = ChatRequest(**data)
        assert request.model_name == "test-model"
        assert request.prompt_summary == "Test summary"
        assert request.question == "What is the status?"
        assert request.summarize_model_id == "gpt-3.5-turbo"
        assert request.api_key == "test-key"


class TestChatMetricsRequest:
    """Test ChatMetricsRequest model validation"""
    
    def test_valid_chat_metrics_request(self):
        """Should accept valid chat metrics request"""
        data = {
            "model_name": "test-model",
            "question": "How many pods?",
            "namespace": "test-ns",
            "summarize_model_id": "gpt-3.5-turbo",
            "chat_scope": "namespace_specific"
        }
        request = ChatMetricsRequest(**data)
        assert request.model_name == "test-model"
        assert request.question == "How many pods?"
        assert request.namespace == "test-ns"
        assert request.chat_scope == "namespace_specific"
    
    def test_chat_metrics_request_fleet_wide(self):
        """Should accept fleet-wide scope"""
        data = {
            "model_name": "test-model",
            "question": "Show all alerts",
            "namespace": "",
            "summarize_model_id": "gpt-3.5-turbo",
            "chat_scope": "fleet_wide"
        }
        request = ChatMetricsRequest(**data)
        assert request.chat_scope == "fleet_wide"
    
    def test_chat_metrics_request_default_scope(self):
        """Should default to namespace_specific"""
        data = {
            "model_name": "test-model",
            "question": "How many pods?",
            "namespace": "test-ns",
            "summarize_model_id": "gpt-3.5-turbo"
        }
        request = ChatMetricsRequest(**data)
        assert request.chat_scope == "namespace_specific"


class TestOpenShiftRequestModels:
    """Test OpenShift-specific request models"""
    
    def test_valid_openshift_analyze_request(self):
        """Should accept valid OpenShift analyze request"""
        data = {
            "metric_category": "Workloads & Pods",
            "scope": "cluster_wide",
            "start_ts": 1000,
            "end_ts": 2000,
            "summarize_model_id": "gpt-3.5-turbo"
        }
        request = OpenShiftAnalyzeRequest(**data)
        assert request.metric_category == "Workloads & Pods"
        assert request.scope == "cluster_wide"
        assert request.namespace is None
    
    def test_openshift_analyze_request_namespace_scoped(self):
        """Should accept namespace-scoped request"""
        data = {
            "metric_category": "Storage & Networking",
            "scope": "namespace_scoped",
            "namespace": "test-ns",
            "start_ts": 1000,
            "end_ts": 2000,
            "summarize_model_id": "gpt-3.5-turbo"
        }
        request = OpenShiftAnalyzeRequest(**data)
        assert request.scope == "namespace_scoped"
        assert request.namespace == "test-ns"
    
    def test_valid_openshift_chat_request(self):
        """Should accept valid OpenShift chat request"""
        data = {
            "metric_category": "Application Services",
            "scope": "cluster_wide",
            "question": "What's the status?",
            "start_ts": 1000,
            "end_ts": 2000,
            "summarize_model_id": "gpt-3.5-turbo"
        }
        request = OpenShiftChatRequest(**data)
        assert request.metric_category == "Application Services"
        assert request.question == "What's the status?"


class TestReportRequest:
    """Test ReportRequest model validation"""
    
    def test_valid_report_request(self):
        """Should accept valid report request"""
        data = {
            "model_name": "test-model",
            "start_ts": 1000,
            "end_ts": 2000,
            "summarize_model_id": "gpt-3.5-turbo",
            "format": "html",
            "health_prompt": "Test prompt",
            "llm_summary": "Test summary",
            "metrics_data": {"test": "data"}
        }
        request = ReportRequest(**data)
        assert request.model_name == "test-model"
        assert request.format == "html"
        assert request.health_prompt == "Test prompt"
        assert request.llm_summary == "Test summary"
        assert request.metrics_data == {"test": "data"}


class TestMetricsCalculationModels:
    """Test metrics calculation request/response models"""
    
    def test_valid_metrics_calculation_request(self):
        """Should accept valid metrics calculation request"""
        data = {
            "metrics_data": {
                "cpu_usage": [
                    {"timestamp": "2024-01-01T00:00:00Z", "value": 50.0},
                    {"timestamp": "2024-01-01T01:00:00Z", "value": 60.0}
                ]
            }
        }
        request = MetricsCalculationRequest(**data)
        assert len(request.metrics_data) == 1
        assert "cpu_usage" in request.metrics_data
    
    def test_valid_metrics_calculation_response(self):
        """Should accept valid metrics calculation response"""
        data = {
            "calculated_metrics": {
                "cpu_usage": {
                    "avg": 55.0,
                    "min": 50.0,
                    "max": 60.0,
                    "latest": 60.0,
                    "count": 2
                }
            }
        }
        response = MetricsCalculationResponse(**data)
        assert len(response.calculated_metrics) == 1
        assert "cpu_usage" in response.calculated_metrics
        assert response.calculated_metrics["cpu_usage"]["avg"] == 55.0


class TestModelSerialization:
    """Test model serialization and deserialization"""
    
    def test_analyze_request_serialization(self):
        """Should serialize and deserialize correctly"""
        original = AnalyzeRequest(
            model_name="test-model",
            start_ts=1000,
            end_ts=2000,
            summarize_model_id="gpt-3.5-turbo"
        )
        
        # Serialize to dict
        data = original.model_dump()
        assert data["model_name"] == "test-model"
        assert data["start_ts"] == 1000
        
        # Deserialize from dict
        reconstructed = AnalyzeRequest(**data)
        assert reconstructed.model_name == original.model_name
        assert reconstructed.start_ts == original.start_ts
    
    def test_chat_metrics_request_json_serialization(self):
        """Should handle JSON serialization"""
        request = ChatMetricsRequest(
            model_name="test-model",
            question="How many pods?",
            namespace="test-ns",
            summarize_model_id="gpt-3.5-turbo"
        )
        
        # Convert to JSON and back
        json_data = request.model_dump_json()
        parsed_data = json.loads(json_data)
        reconstructed = ChatMetricsRequest(**parsed_data)
        
        assert reconstructed.model_name == request.model_name
        assert reconstructed.question == request.question
        assert reconstructed.namespace == request.namespace 