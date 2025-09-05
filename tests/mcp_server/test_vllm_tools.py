from unittest.mock import patch

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
    """Test calculate_metrics function with invalid JSON"""
    result = tools.calculate_metrics("invalid json")
    
    text = _texts(result)[0]
    assert "Error: Invalid JSON format" in text


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
    """Test get_vllm_metrics_tool with error"""
    mock_get_vllm_metrics.side_effect = Exception("Connection error")
    
    result = tools.get_vllm_metrics_tool()
    texts = _texts(result)
    
    assert "Error retrieving vLLM metrics: Connection error" in "\n".join(texts)


