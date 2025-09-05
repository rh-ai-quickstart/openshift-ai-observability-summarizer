"""Tests for UI MCP client helper functions."""

import pytest
from unittest.mock import patch, MagicMock
import json
import sys
import os

# Add src to path to import the UI modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

# Import the module under test
import ui.mcp_client_helper as mcp_helper


class TestMCPClientHelper:
    """Test MCP client helper functions"""

    @pytest.fixture
    def mock_mcp_client(self):
        """Mock MCP client for testing"""
        mock_client = MagicMock()
        mock_client.check_server_health.return_value = True
        return mock_client

    @pytest.fixture
    def sample_mcp_response(self):
        """Sample MCP response format"""
        return [{"type": "text", "text": "Sample response text"}]

    def test_parse_list_response_success(self):
        """Test successful parsing of list response"""
        test_result = [{"type": "text", "text": "Available items:\n• Item 1\n• Item 2\n• Item 3"}]
        
        client = mcp_helper.MCPClientHelper("http://test")
        items = client.parse_list_response(test_result, "•")
        
        assert len(items) == 3
        assert "Item 1" in items
        assert "Item 2" in items
        assert "Item 3" in items

    def test_parse_list_response_empty(self):
        """Test parsing empty list response"""
        test_result = [{"type": "text", "text": "No items found"}]
        
        client = mcp_helper.MCPClientHelper("http://test")
        items = client.parse_list_response(test_result, "•")
        
        assert len(items) == 0

    def test_parse_list_response_nested_json(self):
        """Test parsing response with nested JSON"""
        # Create a simple test with escaped newlines like what actually happens
        test_result = [{"type": "text", "text": "Items:\\n• Dev\\n• Main\\n• Test"}]
        
        client = mcp_helper.MCPClientHelper("http://test")
        items = client.parse_list_response(test_result, "•")
        
        assert len(items) == 3
        assert "Dev" in items

    @patch('ui.mcp_client_helper.mcp_client')
    def test_get_namespaces_mcp_success(self, mock_client):
        """Test successful namespace retrieval"""
        mock_client.check_server_health.return_value = True
        mock_client.call_tool_sync.return_value = [
            {"type": "text", "text": "Monitored Namespaces (3 total):\n• dev\n• main\n• test"}
        ]
        
        # Mock the parse_list_response method
        mock_client.parse_list_response.return_value = ["dev", "main", "test"]
        
        namespaces = mcp_helper.get_namespaces_mcp()
        
        assert len(namespaces) == 3
        assert "dev" in namespaces
        assert "main" in namespaces
        assert "test" in namespaces

    @patch('ui.mcp_client_helper.mcp_client')
    def test_get_models_mcp_success(self, mock_client):
        """Test successful model retrieval"""
        mock_client.check_server_health.return_value = True
        mock_client.call_tool_sync.return_value = [
            {"type": "text", "text": "Available AI Models (2 total):\n• dev | llama-model\n• main | gpt-model"}
        ]
        
        # Mock the parse_list_response method
        mock_client.parse_list_response.return_value = ["dev | llama-model", "main | gpt-model"]
        
        models = mcp_helper.get_models_mcp()
        
        assert len(models) == 2
        assert "dev | llama-model" in models
        assert "main | gpt-model" in models

    @patch('ui.mcp_client_helper.mcp_client')
    def test_get_model_config_mcp_success(self, mock_client):
        """Test successful model config retrieval"""
        config_text = """Available Model Config (2 total):

• meta-llama/Llama-3.2-3B-Instruct
  - external: False
  - requiresApiKey: False
  - serviceName: llama-service

• openai/gpt-4o-mini
  - external: True
  - requiresApiKey: True
  - apiUrl: https://api.openai.com/v1/chat/completions"""

        mock_client.check_server_health.return_value = True
        mock_client.call_tool_sync.return_value = [{"type": "text", "text": config_text}]
        
        config = mcp_helper.get_model_config_mcp()
        
        assert isinstance(config, dict)
        assert "meta-llama/Llama-3.2-3B-Instruct" in config
        assert "openai/gpt-4o-mini" in config
        
        llama_config = config["meta-llama/Llama-3.2-3B-Instruct"]
        assert llama_config["external"] is False
        assert llama_config["requiresApiKey"] is False
        assert llama_config["serviceName"] == "llama-service"

    def test_parse_model_config_text(self):
        """Test parsing model config text format"""
        config_text = """Available Model Config (1 total):

• test-model
  - external: True
  - requiresApiKey: False
  - cost: {"input": 0.01, "output": 0.02}"""

        config = mcp_helper.parse_model_config_text(config_text)
        
        assert "test-model" in config
        model_config = config["test-model"]
        assert model_config["external"] is True
        assert model_config["requiresApiKey"] is False
        assert isinstance(model_config["cost"], dict)

    @patch('ui.mcp_client_helper.mcp_client')
    def test_calculate_metrics_mcp_success(self, mock_client):
        """Test successful metrics calculation via MCP"""
        mock_client.check_server_health.return_value = True
        
        # Mock response with structured JSON
        response_data = {
            "calculated_metrics": {
                "GPU Temperature (°C)": {
                    "avg": 45.5,
                    "min": 44.0,
                    "max": 47.0,
                    "latest": 46.0,
                    "count": 3
                }
            }
        }
        
        mock_client.call_tool_sync.return_value = [
            {"type": "text", "text": json.dumps(response_data)}
        ]
        
        test_metrics = {
            "GPU Temperature (°C)": [
                {"timestamp": "2024-01-01T10:00:00", "value": 45.0},
                {"timestamp": "2024-01-01T10:01:00", "value": 46.0}
            ]
        }
        
        result = mcp_helper.calculate_metrics_mcp(test_metrics)
        
        assert "GPU Temperature (°C)" in result
        stats = result["GPU Temperature (°C)"]
        assert stats["avg"] == 45.5
        assert stats["count"] == 3

    @patch('ui.mcp_client_helper.mcp_client')
    def test_calculate_metrics_mcp_server_down(self, mock_client):
        """Test calculate_metrics when MCP server is down (fallback to local)"""
        mock_client.check_server_health.return_value = False
        
        test_metrics = {
            "GPU Temperature (°C)": [
                {"timestamp": "2024-01-01T10:00:00", "value": 45.0},
                {"timestamp": "2024-01-01T10:01:00", "value": 46.0}
            ]
        }
        
        # The function should fallback to local calculation automatically
        result = mcp_helper.calculate_metrics_mcp(test_metrics)
        
        # Should use local fallback calculation
        assert "GPU Temperature (°C)" in result
        stats = result["GPU Temperature (°C)"]
        assert stats["avg"] == 45.5  # (45.0 + 46.0) / 2
        assert stats["count"] == 2

    def test_calculate_metrics_locally(self):
        """Test local metrics calculation fallback"""
        test_metrics = {
            "GPU Temperature (°C)": [
                {"timestamp": "2024-01-01T10:00:00", "value": 45.0},
                {"timestamp": "2024-01-01T10:01:00", "value": 46.0},
                {"timestamp": "2024-01-01T10:02:00", "value": 47.0}
            ],
            "Empty Metric": [],
            "Invalid Metric": [
                {"timestamp": "2024-01-01T10:00:00"},  # Missing value
                {"timestamp": "2024-01-01T10:01:00", "value": "invalid"}  # Invalid value
            ]
        }
        
        result = mcp_helper.calculate_metrics_locally(test_metrics)
        
        # Check valid metric
        temp_stats = result["GPU Temperature (°C)"]
        assert temp_stats["avg"] == 46.0  # (45 + 46 + 47) / 3
        assert temp_stats["min"] == 45.0
        assert temp_stats["max"] == 47.0
        assert temp_stats["latest"] == 47.0
        assert temp_stats["count"] == 3
        
        # Check empty metric
        empty_stats = result["Empty Metric"]
        assert empty_stats["avg"] is None
        assert empty_stats["count"] == 0
        
        # Check invalid metric
        invalid_stats = result["Invalid Metric"]
        assert invalid_stats["avg"] is None
        assert invalid_stats["count"] == 0

    @patch('ui.mcp_client_helper.mcp_client')
    def test_analyze_vllm_mcp_success(self, mock_client):
        """Test successful vLLM analysis via MCP"""
        mock_client.check_server_health.return_value = True
        
        # Mock response with structured data
        structured_data = {
            "health_prompt": "Test prompt",
            "llm_summary": "Test summary",
            "metrics": {
                "GPU Temperature (°C)": [
                    {"timestamp": "2024-01-01T10:00:00", "value": 45.0}
                ]
            }
        }
        
        response_text = f"Analysis complete\n\nSTRUCTURED_DATA:\n{json.dumps(structured_data)}"
        mock_client.call_tool_sync.return_value = [{"type": "text", "text": response_text}]
        
        result = mcp_helper.analyze_vllm_mcp(
            model_name="test | model",
            summarize_model_id="summarizer",
            start_ts=1640995200,
            end_ts=1640995800,
            api_key=None
        )
        
        assert result["health_prompt"] == "Test prompt"
        assert result["llm_summary"] == "Test summary"
        assert "GPU Temperature (°C)" in result["metrics"]
        assert len(result["metrics"]["GPU Temperature (°C)"]) == 1

    def test_parse_analyze_response_structured_data(self):
        """Test parsing analyze response with structured data"""
        structured_data = {
            "health_prompt": "Test prompt",
            "llm_summary": "Test summary",
            "metrics": {"temp": [{"value": 45}]}
        }
        
        response_text = f"Model analysis\n\nSTRUCTURED_DATA:\n{json.dumps(structured_data)}"
        
        result = mcp_helper.parse_analyze_response(response_text)
        
        assert result["health_prompt"] == "Test prompt"
        assert result["llm_summary"] == "Test summary"
        assert "temp" in result["metrics"]

    def test_parse_analyze_response_fallback(self):
        """Test parsing analyze response without structured data (fallback mode)"""
        response_text = """Model: test-model

Prompt Used:
Test prompt content

Summary:
**Performance Summary**
Test summary content

Metrics Preview:
- GPU TEMPERATURE: 45.0"""
        
        result = mcp_helper.parse_analyze_response(response_text)
        
        assert "Test prompt content" in result["health_prompt"]
        assert "Test summary content" in result["llm_summary"]
        assert "gpu_temp_analyzed" in result["metrics"]
        assert result["metrics"]["gpu_temp_analyzed"] == "true"

    @patch('ui.mcp_client_helper.mcp_client')
    def test_mcp_client_server_health_check(self, mock_client):
        """Test MCP client health check functionality"""
        # Test healthy server
        mock_client.check_server_health.return_value = True
        assert mcp_helper.get_namespaces_mcp() is not None
        
        # Test unhealthy server
        mock_client.check_server_health.return_value = False
        result = mcp_helper.get_namespaces_mcp()
        assert result == []

    def test_mcp_client_helper_initialization(self):
        """Test MCP client helper initialization"""
        client = mcp_helper.MCPClientHelper("http://test:8080")
        # The MCPClientHelper stores URL info but may not expose base_url directly
        # Test that it can be created without error
        assert client is not None
        assert hasattr(client, 'check_server_health')


    @patch.object(mcp_helper.mcp_client, 'check_server_health', return_value=True)
    @patch.object(mcp_helper.mcp_client, 'call_tool_sync')
    def test_get_vllm_metrics_mcp_success(self, mock_call_tool, mock_health_check):
        """Test get_vllm_metrics_mcp with successful response"""
        mock_call_tool.return_value = [{
            "type": "text",
            "text": "Available vLLM Metrics (2 total):\n\n📊 **GPU Metrics:**\n• GPU Temperature (°C)\n  Query: `avg(DCGM_FI_DEV_GPU_TEMP)`\n\n🚀 **vLLM Performance Metrics:**\n• P95 Latency (s)\n  Query: `vllm:e2e_request_latency_seconds_sum`\n\n"
        }]
        
        result = mcp_helper.get_vllm_metrics_mcp()
        
        mock_call_tool.assert_called_once_with("get_vllm_metrics_tool", {})
        assert isinstance(result, dict)
        assert len(result) == 2
        assert "GPU Temperature (°C)" in result
        assert result["GPU Temperature (°C)"] == "avg(DCGM_FI_DEV_GPU_TEMP)"
        assert "P95 Latency (s)" in result
        assert result["P95 Latency (s)"] == "vllm:e2e_request_latency_seconds_sum"


    @patch.object(mcp_helper.mcp_client, 'check_server_health', return_value=False)
    def test_get_vllm_metrics_mcp_server_down(self, mock_health_check):
        """Test get_vllm_metrics_mcp when server is down"""
        result = mcp_helper.get_vllm_metrics_mcp()
        
        assert isinstance(result, dict)
        assert len(result) == 0


    def test_parse_vllm_metrics_text(self):
        """Test parse_vllm_metrics_text function"""
        sample_text = """Available vLLM Metrics (3 total):

📊 **GPU Metrics:**
• GPU Temperature (°C)
  Query: `avg(DCGM_FI_DEV_GPU_TEMP)`

• GPU Power Usage (Watts)
  Query: `avg(DCGM_FI_DEV_POWER_USAGE)`

🚀 **vLLM Performance Metrics:**
• P95 Latency (s)
  Query: `vllm:e2e_request_latency_seconds_sum`

**Summary:**
- GPU Metrics: 2
- vLLM Performance: 1
- Total: 3
"""
        
        result = mcp_helper.parse_vllm_metrics_text(sample_text)
        
        assert isinstance(result, dict)
        assert len(result) == 3
        assert "GPU Temperature (°C)" in result
        assert result["GPU Temperature (°C)"] == "avg(DCGM_FI_DEV_GPU_TEMP)"
        assert "GPU Power Usage (Watts)" in result
        assert result["GPU Power Usage (Watts)"] == "avg(DCGM_FI_DEV_POWER_USAGE)"
        assert "P95 Latency (s)" in result
        assert result["P95 Latency (s)"] == "vllm:e2e_request_latency_seconds_sum"


    def test_parse_vllm_metrics_text_empty(self):
        """Test parse_vllm_metrics_text with empty text"""
        result = mcp_helper.parse_vllm_metrics_text("")
        
        assert isinstance(result, dict)
        assert len(result) == 0
