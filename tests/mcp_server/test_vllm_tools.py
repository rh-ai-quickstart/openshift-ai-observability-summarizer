import sys
import os
from unittest.mock import patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import src.mcp_server.tools.observability_vllm_tools as tools


def _texts(result):
    return [part.get("text") for part in result]


@patch("src.mcp_server.tools.observability_vllm_tools.get_models_helper", return_value=["a", "b"])  # type: ignore[arg-type]
def test_list_models_success(_):
    out = tools.list_models()
    texts = _texts(out)
    assert any("Available AI Models" in t for t in texts)
    assert any("a" in t for t in texts)
    assert any("b" in t for t in texts)


@patch("src.mcp_server.tools.observability_vllm_tools.get_models_helper", return_value=[])  # type: ignore[arg-type]
def test_list_models_empty(_):
    out = tools.list_models()
    texts = _texts(out)
    assert any("No models are currently available" in t for t in texts)


@patch("src.mcp_server.tools.observability_vllm_tools.get_namespaces_helper", return_value=["ns1", "ns2"])  # type: ignore[arg-type]
def test_list_namespaces_success(_):
    out = tools.list_namespaces()
    texts = _texts(out)
    assert any("Monitored Namespaces" in t for t in texts)
    assert any("ns1" in t for t in texts)
    assert any("ns2" in t for t in texts)


@patch("src.mcp_server.tools.observability_vllm_tools.get_namespaces_helper", return_value=[])  # type: ignore[arg-type]
def test_list_namespaces_empty(_):
    out = tools.list_namespaces()
    texts = _texts(out)
    assert any("No monitored namespaces found" in t for t in texts)


@patch("os.getenv", return_value='{"m1": {"external": false}, "m2": {"external": true}}')
def test_get_model_config_success(_):
    out = tools.get_model_config()
    text = "\n".join(_texts(out))
    assert "Available Model Config" in text
    # external:false first means m1 should appear before m2
    assert text.find("m1") < text.find("m2")


@patch("os.getenv", return_value="{}")
def test_get_model_config_empty(_):
    out = tools.get_model_config()
    texts = _texts(out)
    assert any("No LLM models configured" in t for t in texts)
@patch("src.mcp_server.tools.observability_vllm_tools.get_vllm_metrics", return_value={"latency": "q1", "tps": "q2"})
@patch("src.mcp_server.tools.observability_vllm_tools.fetch_metrics")
@patch("src.mcp_server.tools.observability_vllm_tools.build_prompt", return_value="PROMPT")
@patch("src.mcp_server.tools.observability_vllm_tools.summarize_with_llm", return_value="SUMMARY")
@patch("src.mcp_server.tools.observability_vllm_tools.extract_time_range_with_info", return_value=(1, 2, {}))
def test_analyze_vllm_success(_, __, ___, mock_fetch, ____):
    # Create proper DataFrame-like mock objects
    import pandas as pd
    from datetime import datetime
    
    # Mock DataFrame with required columns
    mock_df1 = pd.DataFrame({
        "timestamp": [datetime.now(), datetime.now()],
        "value": [1.0, 2.0]
    })
    mock_df2 = pd.DataFrame({
        "timestamp": [datetime.now(), datetime.now()],
        "value": [3.0, 4.0]
    })
    
    mock_fetch.side_effect = [mock_df1, mock_df2]
    
    out = tools.analyze_vllm("model", "summarizer", time_range="last 1h")
    text = "\n".join(_texts(out))
    assert "Model: model" in text
    assert "PROMPT" in text
    assert "SUMMARY" in text
    assert "Metrics Preview" in text


def test_calculate_metrics_success():
    """Test calculate_metrics function with valid data"""
    import json
    
    # Test data mimicking UI format
    test_data = {
        "GPU Temperature (°C)": [
            {"timestamp": "2024-01-01T10:00:00", "value": 45.2},
            {"timestamp": "2024-01-01T10:01:00", "value": 46.1},
            {"timestamp": "2024-01-01T10:02:00", "value": 44.8}
        ],
        "GPU Power Usage (Watts)": [
            {"timestamp": "2024-01-01T10:00:00", "value": 250.5},
            {"timestamp": "2024-01-01T10:01:00", "value": 255.0}
        ]
    }
    
    metrics_json = json.dumps(test_data)
    result = tools.calculate_metrics(metrics_json)
    
    # Extract text from MCP response
    text = _texts(result)[0]
    response_data = json.loads(text)
    
    assert "calculated_metrics" in response_data
    calculated = response_data["calculated_metrics"]
    
    # Check GPU Temperature calculations
    temp_stats = calculated["GPU Temperature (°C)"]
    assert abs(temp_stats["avg"] - 45.366666666666667) < 0.001  # (45.2 + 46.1 + 44.8) / 3
    assert temp_stats["min"] == 44.8
    assert temp_stats["max"] == 46.1
    assert temp_stats["latest"] == 44.8
    assert temp_stats["count"] == 3
    
    # Check GPU Power calculations
    power_stats = calculated["GPU Power Usage (Watts)"]
    assert power_stats["avg"] == 252.75  # (250.5 + 255.0) / 2
    assert power_stats["min"] == 250.5
    assert power_stats["max"] == 255.0
    assert power_stats["latest"] == 255.0
    assert power_stats["count"] == 2


def test_calculate_metrics_empty_data():
    """Test calculate_metrics function with empty data"""
    import json
    
    test_data = {
        "Empty Metric": []
    }
    
    metrics_json = json.dumps(test_data)
    result = tools.calculate_metrics(metrics_json)
    
    text = _texts(result)[0]
    response_data = json.loads(text)
    calculated = response_data["calculated_metrics"]
    
    empty_stats = calculated["Empty Metric"]
    assert empty_stats["avg"] is None
    assert empty_stats["min"] is None
    assert empty_stats["max"] is None
    assert empty_stats["latest"] is None
    assert empty_stats["count"] == 0


def test_calculate_metrics_invalid_json():
    """Test calculate_metrics function with invalid JSON - now returns structured MCPException"""
    result = tools.calculate_metrics("invalid json")

    text = _texts(result)[0]
    assert "❌ **Error (INVALID_INPUT)**" in text
    assert "Invalid JSON format" in text


def test_calculate_metrics_invalid_data_format():
    """Test calculate_metrics function with invalid data points"""
    import json
    
    test_data = {
        "Invalid Metric": [
            {"timestamp": "2024-01-01T10:00:00"},  # Missing value
            {"value": "not_a_number", "timestamp": "2024-01-01T10:01:00"},  # Invalid value
            {"timestamp": "2024-01-01T10:02:00", "value": 45.2}  # Valid point
        ]
    }
    
    metrics_json = json.dumps(test_data)
    result = tools.calculate_metrics(metrics_json)
    
    text = _texts(result)[0]
    response_data = json.loads(text)
    calculated = response_data["calculated_metrics"]
    
    # Should only count the valid data point
    stats = calculated["Invalid Metric"]
    assert stats["avg"] == 45.2
    assert stats["count"] == 1


def test_analyze_vllm_with_structured_data():
    """Test that analyze_vllm returns structured data in the response"""
    import pandas as pd
    from datetime import datetime
    
    with patch("src.mcp_server.tools.observability_vllm_tools.get_vllm_metrics", return_value={"GPU Temperature (°C)": "query1"}):
        with patch("src.mcp_server.tools.observability_vllm_tools.extract_time_range_with_info", return_value=(1, 2, {})):
            with patch("src.mcp_server.tools.observability_vllm_tools.build_prompt", return_value="TEST_PROMPT"):
                with patch("src.mcp_server.tools.observability_vllm_tools.summarize_with_llm", return_value="TEST_SUMMARY"):
                    with patch("src.mcp_server.tools.observability_vllm_tools.fetch_metrics") as mock_fetch:
                        # Create mock DataFrame with realistic data
                        mock_df = pd.DataFrame({
                            "timestamp": [datetime(2024, 1, 1, 10, 0), datetime(2024, 1, 1, 10, 1)],
                            "value": [45.2, 46.1]
                        })
                        mock_fetch.return_value = mock_df
                        
                        result = tools.analyze_vllm("test-model", "test-summarizer", time_range="last 1h")
                        
                        text = _texts(result)[0]
                        
                        # Check that structured data is included
                        assert "STRUCTURED_DATA:" in text
                        
                        # Extract and parse the structured data
                        structured_start = text.find("STRUCTURED_DATA:") + len("STRUCTURED_DATA:")
                        json_data = text[structured_start:].strip()
                        
                        import json
                        structured = json.loads(json_data)
                        
                        assert "health_prompt" in structured
                        assert "llm_summary" in structured
                        assert "metrics" in structured
                        
                        assert structured["health_prompt"] == "TEST_PROMPT"
                        assert structured["llm_summary"] == "TEST_SUMMARY"
                        
                        # Check metrics structure
                        metrics = structured["metrics"]
                        assert "GPU Temperature (°C)" in metrics
                        
                        data_points = metrics["GPU Temperature (°C)"]
                        assert len(data_points) == 2
                        assert data_points[0]["value"] == 45.2
                        assert data_points[1]["value"] == 46.1


@patch("src.mcp_server.tools.observability_vllm_tools.get_vllm_metrics")
def test_get_vllm_metrics_tool_success(mock_get_vllm_metrics):
    """Test get_vllm_metrics_tool with successful response"""
    mock_get_vllm_metrics.return_value = {
        "GPU Temperature (°C)": "avg(DCGM_FI_DEV_GPU_TEMP)",
        "P95 Latency (s)": "vllm:e2e_request_latency_seconds_sum",
        "Requests Running": "vllm:num_requests_running"
    }
    
    result = tools.get_vllm_metrics_tool()
    text = "\n".join(_texts(result))
    
    assert "Available vLLM Metrics (3 total):" in text
    assert "GPU Temperature (°C)" in text
    assert "avg(DCGM_FI_DEV_GPU_TEMP)" in text
    assert "P95 Latency (s)" in text
    assert "vllm:e2e_request_latency_seconds_sum" in text
    assert "Requests Running" in text
    assert "vllm:num_requests_running" in text
    assert "📊 **GPU Metrics:**" in text
    assert "🚀 **vLLM Performance Metrics:**" in text


@patch("src.mcp_server.tools.observability_vllm_tools.get_vllm_metrics")
def test_get_vllm_metrics_tool_empty(mock_get_vllm_metrics):
    """Test get_vllm_metrics_tool with empty response"""
    mock_get_vllm_metrics.return_value = {}
    
    result = tools.get_vllm_metrics_tool()
    texts = _texts(result)
    
    assert "No vLLM metrics are currently available" in "\n".join(texts)


@patch("src.mcp_server.tools.observability_vllm_tools.get_vllm_metrics")
def test_get_vllm_metrics_tool_error(mock_get_vllm_metrics):
    """Test get_vllm_metrics_tool with error - now returns structured MCPException"""
    mock_get_vllm_metrics.side_effect = Exception("Connection error")

    result = tools.get_vllm_metrics_tool()
    texts = _texts(result)
    full_text = "\n".join(texts)

    assert "❌ **Error (PROMETHEUS_ERROR)**" in full_text
    assert "Failed to retrieve vLLM metrics: Connection error" in full_text


# --- New MCP tools tests ---

@patch("src.mcp_server.tools.observability_vllm_tools.get_summarization_models", return_value=["m1", "m2"])  # type: ignore[arg-type]
def test_list_summarization_models_success(_):
    out = tools.list_summarization_models()
    text = "\n".join(_texts(out))
    assert "Available Summarization Models (2 total):" in text
    assert "• m1" in text
    assert "• m2" in text


@patch("src.mcp_server.tools.observability_vllm_tools.get_summarization_models", return_value=[])  # type: ignore[arg-type]
def test_list_summarization_models_empty(_):
    out = tools.list_summarization_models()
    text = "\n".join(_texts(out))
    assert "No summarization models configured" in text


@patch("src.mcp_server.tools.observability_vllm_tools.get_cluster_gpu_info")
def test_get_gpu_info_success(mock_gpu_info):
    mock_gpu_info.return_value = {
        "total_gpus": 2,
        "vendors": ["NVIDIA"],
        "models": ["GPU"],
        "temperatures": [45.0, 50.0],
        "power_usage": []
    }
    out = tools.get_gpu_info()
    import json as _json
    data = _json.loads(_texts(out)[0])
    assert data["total_gpus"] == 2
    assert data["temperatures"] == [45.0, 50.0]
    assert data["vendors"] == ["NVIDIA"]


def test_get_deployment_info_success():
    payload = {
        "is_new_deployment": True,
        "deployment_date": "2025-01-01",
        "message": "msg",
        "namespace": "ns",
        "model": "m"
    }
    with patch("src.mcp_server.tools.observability_vllm_tools.get_namespace_model_deployment_info", return_value=payload):
        out = tools.get_deployment_info("ns", "m")
        import json as _json
        data = _json.loads(_texts(out)[0])
        assert data == payload


def test_get_deployment_info_validation_error():
    # Force validate_required_params to raise a ValidationError
    with patch("src.mcp_server.tools.observability_vllm_tools.validate_required_params", side_effect=tools.ValidationError(message="missing", field="namespace")):
        out = tools.get_deployment_info("", "m")
        text = "\n".join(_texts(out))
        assert "❌ **Error (INVALID_INPUT)**" in text
        assert "missing" in text


# --- Test MCP tool: chat_vllm ---

@patch("core.llm_client.build_chat_prompt", return_value="CHAT_PROMPT")
@patch("src.mcp_server.tools.observability_vllm_tools.summarize_with_llm", return_value="CHAT_RESPONSE")
@patch("core.llm_client._clean_llm_summary_string", return_value="CLEANED_RESPONSE")
def test_chat_vllm_success(mock_clean, mock_summarize, mock_build_prompt):
    """Test chat_vllm with successful response"""
    out = tools.chat_vllm(
        model_name="dev | llama-3.2-3b-instruct",
        prompt_summary="GPU usage is at 85%, latency is 2.5s",
        question="What is the average latency?",
        summarize_model_id="meta-llama/Llama-3.2-3B-Instruct",
        api_key="test-key"
    )
    
    text = "\n".join(_texts(out))
    assert "CLEANED_RESPONSE" in text
    
    # Verify that build_chat_prompt was called correctly
    mock_build_prompt.assert_called_once_with(
        user_question="What is the average latency?",
        metrics_summary="GPU usage is at 85%, latency is 2.5s"
    )
    
    # Verify summarize_with_llm was called
    mock_summarize.assert_called_once()
    assert mock_summarize.call_args[0][0] == "CHAT_PROMPT"
    assert mock_summarize.call_args[0][1] == "meta-llama/Llama-3.2-3B-Instruct"


@patch("core.llm_client.build_chat_prompt", return_value="CHAT_PROMPT")
@patch("src.mcp_server.tools.observability_vllm_tools.summarize_with_llm", return_value="CHAT_RESPONSE")
@patch("core.llm_client._clean_llm_summary_string", return_value="CLEANED_RESPONSE")
def test_chat_vllm_without_api_key(mock_clean, mock_summarize, mock_build_prompt):
    """Test chat_vllm without API key (for internal models)"""
    out = tools.chat_vllm(
        model_name="test-model",
        prompt_summary="Test summary",
        question="Test question?",
        summarize_model_id="internal-model"
    )
    
    text = "\n".join(_texts(out))
    assert "CLEANED_RESPONSE" in text


def test_chat_vllm_missing_model_name():
    """Test chat_vllm with missing model_name - validation error"""
    out = tools.chat_vllm(
        model_name="",
        prompt_summary="Test summary",
        question="Test question?",
        summarize_model_id="test-model"
    )
    
    text = "\n".join(_texts(out))
    assert "❌ **Error (INVALID_INPUT)**" in text
    assert "model_name" in text.lower()


def test_chat_vllm_missing_question():
    """Test chat_vllm with missing question - validation error"""
    out = tools.chat_vllm(
        model_name="test-model",
        prompt_summary="Test summary",
        question="",
        summarize_model_id="test-model"
    )
    
    text = "\n".join(_texts(out))
    assert "❌ **Error (INVALID_INPUT)**" in text
    assert "question" in text.lower()


def test_chat_vllm_missing_prompt_summary():
    """Test chat_vllm with missing prompt_summary - validation error"""
    out = tools.chat_vllm(
        model_name="test-model",
        prompt_summary="",
        question="Test question?",
        summarize_model_id="test-model"
    )
    
    text = "\n".join(_texts(out))
    assert "❌ **Error (INVALID_INPUT)**" in text
    assert "prompt_summary" in text.lower()


def test_chat_vllm_missing_summarize_model_id():
    """Test chat_vllm with missing summarize_model_id - validation error"""
    out = tools.chat_vllm(
        model_name="test-model",
        prompt_summary="Test summary",
        question="Test question?",
        summarize_model_id=""
    )
    
    text = "\n".join(_texts(out))
    assert "❌ **Error (INVALID_INPUT)**" in text
    assert "summarize_model_id" in text.lower()


@patch("core.llm_client.build_chat_prompt", return_value="CHAT_PROMPT")
@patch("src.mcp_server.tools.observability_vllm_tools.summarize_with_llm", side_effect=Exception("LLM service unavailable"))
def test_chat_vllm_llm_service_error(mock_summarize, mock_build_prompt):
    """Test chat_vllm when LLM service fails - returns structured MCPException"""
    out = tools.chat_vllm(
        model_name="test-model",
        prompt_summary="Test summary",
        question="Test question?",
        summarize_model_id="test-model"
    )
    
    text = "\n".join(_texts(out))
    assert "❌ **Error (LLM_SERVICE_ERROR)**" in text
    assert "Failed to generate chat response" in text
    assert "LLM service unavailable" in text
    assert "Please check your API key or try again later" in text


@patch("core.llm_client.build_chat_prompt", side_effect=Exception("Prompt building failed"))
def test_chat_vllm_prompt_building_error(mock_build_prompt):
    """Test chat_vllm when prompt building fails"""
    out = tools.chat_vllm(
        model_name="test-model",
        prompt_summary="Test summary",
        question="Test question?",
        summarize_model_id="test-model"
    )
    
    text = "\n".join(_texts(out))
    assert "❌ **Error (LLM_SERVICE_ERROR)**" in text
    assert "Failed to generate chat response" in text


@patch("core.llm_client.build_chat_prompt", return_value="CHAT_PROMPT")
@patch("src.mcp_server.tools.observability_vllm_tools.summarize_with_llm", return_value="Response with markdown **bold** and *italic*")
@patch("core.llm_client._clean_llm_summary_string", side_effect=lambda x: x.strip())
def test_chat_vllm_with_markdown_response(mock_clean, mock_summarize, mock_build_prompt):
    """Test chat_vllm with markdown-formatted response"""
    out = tools.chat_vllm(
        model_name="test-model",
        prompt_summary="Test summary",
        question="Explain the metrics",
        summarize_model_id="test-model"
    )
    
    text = "\n".join(_texts(out))
    assert "Response with markdown **bold** and *italic*" in text
