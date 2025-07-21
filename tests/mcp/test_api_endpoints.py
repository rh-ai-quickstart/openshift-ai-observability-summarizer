import pytest
from unittest.mock import patch, MagicMock, mock_open
from fastapi.testclient import TestClient

# Import the FastAPI app
from metric_ui.mcp.mcp import app


class TestBase:
    """Base test class with shared fixtures and utilities"""
    
    @pytest.fixture
    def client(self):
        """Create FastAPI test client"""
        return TestClient(app)

    @pytest.fixture
    def mock_prometheus_response(self):
        """Mock Prometheus API responses"""
        return {
            "data": {
                "result": [
                    {
                        "metric": {"model_name": "test-model", "namespace": "test-ns"},
                        "values": [
                            [1640995200, "10.5"],  # timestamp, value
                            [1640995230, "11.2"],
                            [1640995260, "12.1"]
                        ]
                    }
                ]
            }
        }

    @pytest.fixture  
    def mock_llm_response(self):
        """Mock LLM API responses"""
        return {
            "choices": [
                {
                    "text": "The system appears healthy with stable metrics."
                }
            ]
        }


class TestInfrastructureEndpoints(TestBase):
    """Test basic infrastructure and configuration endpoints"""
    
    def test_health_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    
    @patch('metric_ui.mcp.mcp.MODEL_CONFIG', {
        "test-model": {
            "external": False,
            "modelName": "test-model"
        },
        "gpt-4": {
            "external": True,
            "provider": "openai", 
            "apiUrl": "https://api.openai.com/v1/chat/completions",
            "modelName": "gpt-4"
        }
    })
    def test_model_config_endpoint(self, client):
        """Test model configuration endpoint"""
        response = client.get("/model_config")
        assert response.status_code == 200
        data = response.json()
        assert "test-model" in data
        assert data["test-model"]["external"] is False


class TestDiscoveryEndpoints(TestBase):
    """Test model and namespace discovery endpoints"""
    
    @patch('metric_ui.mcp.mcp.requests.get')
    def test_models_endpoint_success(self, mock_get, client):
        """Test models endpoint with successful Prometheus response"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "data": [
                {"model_name": "llama-7b", "namespace": "production"},
                {"model_name": "gpt-3.5", "namespace": "staging"}
            ]
        }
        mock_get.return_value = mock_response
        
        response = client.get("/models")
        assert response.status_code == 200
        models = response.json()
        assert isinstance(models, list)
    
    @patch('metric_ui.mcp.mcp.requests.get')
    def test_models_endpoint_prometheus_error(self, mock_get, client):
        """Test models endpoint when Prometheus is unavailable"""
        mock_get.side_effect = Exception("Connection error")
        
        response = client.get("/models")
        assert response.status_code == 200
        assert response.json() == []  # Should return empty list on error
    
    @patch('metric_ui.mcp.mcp.requests.get')
    def test_namespaces_endpoint_success(self, mock_get, client):
        """Test namespaces endpoint with successful response"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "data": [
                {"namespace": "production", "model_name": "llama-7b"},
                {"namespace": "staging", "model_name": "gpt-3.5"}
            ]
        }
        mock_get.return_value = mock_response
        
        response = client.get("/namespaces")
        assert response.status_code == 200
        namespaces = response.json()
        assert isinstance(namespaces, list)
    
    @patch('metric_ui.mcp.mcp.MODEL_CONFIG', {"model1": {}, "model2": {}})
    def test_multi_models_endpoint(self, client):
        """Test multi models endpoint returns configuration keys"""
        response = client.get("/multi_models")
        assert response.status_code == 200
        models = response.json()
        assert "model1" in models
        assert "model2" in models


class TestMetricsDiscoveryEndpoints(TestBase):
    """Test metrics discovery and information endpoints"""
    
    @patch('metric_ui.mcp.mcp.get_vllm_metrics')
    def test_vllm_metrics_endpoint(self, mock_get_metrics, client):
        """Test vLLM metrics endpoint"""
        mock_get_metrics.return_value = {
            "Prompt Tokens": "vllm:request_prompt_tokens_created",
            "GPU Usage": "vllm:gpu_cache_usage_perc"
        }
        
        response = client.get("/vllm-metrics")
        assert response.status_code == 200
        metrics = response.json()
        assert "Prompt Tokens" in metrics
        assert "GPU Usage" in metrics
    
    @patch('metric_ui.mcp.mcp.discover_dcgm_metrics')
    def test_dcgm_metrics_endpoint(self, mock_discover, client):
        """Test DCGM metrics endpoint"""
        mock_discover.return_value = {
            "GPU Temperature": "avg(DCGM_FI_DEV_GPU_TEMP)",
            "GPU Power": "avg(DCGM_FI_DEV_POWER_USAGE)"
        }
        
        response = client.get("/dcgm-metrics")
        assert response.status_code == 200
        metrics = response.json()
        assert "GPU Temperature" in metrics
    
    @patch('metric_ui.mcp.mcp.requests.get')
    def test_gpu_info_endpoint_success(self, mock_get, client):
        """Test GPU info endpoint with successful response"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "data": {
                "result": [
                    {"metric": {"vendor": "NVIDIA"}, "value": [1640995200, "75.5"]},
                    {"metric": {"vendor": "NVIDIA"}, "value": [1640995200, "80.2"]}
                ]
            }
        }
        mock_get.return_value = mock_response
        
        response = client.get("/gpu-info")
        assert response.status_code == 200
        gpu_info = response.json()
        assert "total_gpus" in gpu_info
        assert "vendors" in gpu_info
    
    @patch('metric_ui.mcp.mcp.requests.get')
    def test_gpu_info_endpoint_error(self, mock_get, client):
        """Test GPU info endpoint when Prometheus fails"""
        mock_get.side_effect = Exception("Connection error")
        
        response = client.get("/gpu-info")
        assert response.status_code == 200
        gpu_info = response.json()
        assert gpu_info["total_gpus"] == 0
        assert gpu_info["vendors"] == []


class TestOpenShiftDiscoveryEndpoints(TestBase):
    """Test OpenShift-specific discovery endpoints"""
    
    def test_openshift_metric_groups(self, client):
        """Test OpenShift metric groups endpoint"""
        response = client.get("/openshift-metric-groups")
        assert response.status_code == 200
        groups = response.json()
        assert isinstance(groups, list)
        assert "Fleet Overview" in groups
        assert "GPU & Accelerators" in groups
    
    def test_openshift_namespace_metric_groups(self, client):
        """Test namespace-specific metric groups"""
        response = client.get("/openshift-namespace-metric-groups") 
        assert response.status_code == 200
        groups = response.json()
        assert isinstance(groups, list)
        assert "Workloads & Pods" in groups
    
    @patch('metric_ui.mcp.mcp.requests.get')
    def test_openshift_namespaces_success(self, mock_get, client):
        """Test OpenShift namespaces discovery"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "data": [
                {"namespace": "production"},
                {"namespace": "staging"},
                {"namespace": "kube-system"}  # Should be filtered out
            ]
        }
        mock_get.return_value = mock_response
        
        response = client.get("/openshift-namespaces")
        assert response.status_code == 200
        namespaces = response.json()
        assert "production" in namespaces
        assert "staging" in namespaces
        assert "kube-system" not in namespaces  # System namespace filtered


class TestAnalysisEndpoints(TestBase):
    """Test metric analysis endpoints for both vLLM and OpenShift"""
    
    @patch('metric_ui.mcp.mcp.requests.get')
    @patch('metric_ui.mcp.mcp.requests.post')
    def test_analyze_vllm_success(self, mock_post, mock_get, client, mock_prometheus_response, mock_llm_response):
        """Test successful vLLM analysis with local model"""
        # Mock Prometheus metrics discovery
        mock_prometheus_discover = MagicMock()
        mock_prometheus_discover.raise_for_status.return_value = None
        mock_prometheus_discover.json.return_value = {"data": ["vllm:request_prompt_tokens_created"]}
        
        # Mock Prometheus metrics query  
        mock_prometheus_query = MagicMock()
        mock_prometheus_query.raise_for_status.return_value = None
        mock_prometheus_query.json.return_value = mock_prometheus_response
        
        mock_get.side_effect = [mock_prometheus_discover, mock_prometheus_query]
        
        # Mock LLM response
        mock_llm_resp = MagicMock()
        mock_llm_resp.raise_for_status.return_value = None  
        mock_llm_resp.json.return_value = mock_llm_response
        mock_post.return_value = mock_llm_resp
        
        response = client.post("/analyze", json={
            "model_name": "test-model",
            "start_ts": 1640995200,
            "end_ts": 1640995800, 
            "summarize_model_id": "test-model"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "model_name" in data
        assert "health_prompt" in data
        assert "llm_summary" in data
        assert "metrics" in data
        assert data["model_name"] == "test-model"
    
    def test_analyze_vllm_missing_fields(self, client):
        """Test vLLM analyze endpoint with missing required fields"""
        response = client.post("/analyze", json={
            "model_name": "test-model"
            # Missing required fields
        })
        assert response.status_code == 422  # Validation error
    
    @patch('metric_ui.mcp.mcp.requests.post')  
    def test_analyze_vllm_llm_api_error(self, mock_post, client):
        """Test vLLM analyze endpoint when LLM API fails"""
        mock_post.side_effect = Exception("LLM API error")
        
        response = client.post("/analyze", json={
            "model_name": "test-model",
            "start_ts": 1640995200,
            "end_ts": 1640995800,
            "summarize_model_id": "test-model" 
        })
        
        assert response.status_code == 500
        assert "Please check your API Key" in response.json()["detail"]
    
    @patch('metric_ui.mcp.mcp.requests.get')
    @patch('metric_ui.mcp.mcp.requests.post')
    def test_analyze_openshift_cluster_wide(self, mock_post, mock_get, client, mock_prometheus_response, mock_llm_response):
        """Test OpenShift analysis with cluster-wide scope"""
        # Mock Prometheus response
        mock_prometheus_query = MagicMock()
        mock_prometheus_query.raise_for_status.return_value = None
        mock_prometheus_query.json.return_value = mock_prometheus_response
        mock_get.return_value = mock_prometheus_query
        
        # Mock LLM response
        mock_llm_resp = MagicMock()
        mock_llm_resp.raise_for_status.return_value = None
        mock_llm_resp.json.return_value = mock_llm_response
        mock_post.return_value = mock_llm_resp
        
        response = client.post("/analyze-openshift", json={
            "metric_category": "Fleet Overview",
            "scope": "cluster_wide",
            "start_ts": 1640995200,
            "end_ts": 1640995800,
            "summarize_model_id": "test-model"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "metric_category" in data
        assert "scope" in data
        assert "llm_summary" in data
        assert data["metric_category"] == "Fleet Overview"
    
    def test_analyze_openshift_invalid_category(self, client):
        """Test OpenShift analysis with invalid metric category"""
        response = client.post("/analyze-openshift", json={
            "metric_category": "Invalid Category",
            "scope": "cluster_wide",
            "start_ts": 1640995200,
            "end_ts": 1640995800,
            "summarize_model_id": "test-model"
        })
        
        assert response.status_code == 400
        assert "Invalid metric category" in response.json()["detail"]


class TestChatEndpoints(TestBase):
    """Test interactive chat endpoints"""
    
    @patch('metric_ui.mcp.mcp.requests.post')
    def test_chat_success(self, mock_post, client, mock_llm_response):
        """Test successful basic chat interaction"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = mock_llm_response
        mock_post.return_value = mock_resp
        
        response = client.post("/chat", json={
            "model_name": "test-model",
            "prompt_summary": "System is running normally with stable metrics.",
            "question": "Can I send more load?",
            "summarize_model_id": "test-model"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert isinstance(data["response"], str)
    
    def test_chat_validation_error(self, client):
        """Test chat with invalid request data"""
        response = client.post("/chat", json={
            "question": "What's the status?"
            # Missing required fields
        })
        assert response.status_code == 422


class TestReportEndpoints(TestBase):
    """Test report generation and download endpoints"""
    
    def test_generate_report_missing_data(self, client):
        """Test report generation without analysis data"""
        response = client.post("/generate_report", json={
            "model_name": "test-model",
            "start_ts": 1640995200,
            "end_ts": 1640995800,
            "summarize_model_id": "test-model",
            "format": "html"
        })
        
        assert response.status_code == 400
        assert "No analysis data provided" in response.json()["detail"]
    
    @patch('metric_ui.mcp.mcp.generate_html_report')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.makedirs')
    def test_generate_html_report_success(self, mock_makedirs, mock_file, mock_generate, client):
        """Test successful HTML report generation"""
        mock_generate.return_value = "<html>Test Report</html>"
        
        response = client.post("/generate_report", json={
            "model_name": "test-model", 
            "start_ts": 1640995200,
            "end_ts": 1640995800,
            "summarize_model_id": "test-model",
            "format": "html",
            "health_prompt": "Test prompt",
            "llm_summary": "Test summary", 
            "metrics_data": {"cpu": [{"value": 10, "timestamp": "2023-01-01T00:00:00Z"}]}
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "report_id" in data
        assert "download_url" in data
        assert data["download_url"].startswith("/download_report/")
    
    def test_generate_report_invalid_format(self, client):
        """Test report generation with invalid format"""
        response = client.post("/generate_report", json={
            "model_name": "test-model",
            "start_ts": 1640995200, 
            "end_ts": 1640995800,
            "summarize_model_id": "test-model",
            "format": "invalid-format",
            "health_prompt": "Test prompt",
            "llm_summary": "Test summary",
            "metrics_data": {}
        })
        
        assert response.status_code == 400
        assert "Unsupported format" in response.json()["detail"]

    @patch('metric_ui.mcp.mcp.get_report_path')
    @patch('os.path.exists')
    def test_download_report_success(self, mock_exists, mock_get_path, client):
        """Test successful report download"""
        mock_exists.return_value = True
        mock_get_path.return_value = "/tmp/reports/test-report.html"
        
        with patch('metric_ui.mcp.mcp.FileResponse') as mock_file_response:
            mock_file_response.return_value = MagicMock()
            response = client.get("/download_report/test-report-id")
            assert response.status_code == 200
            mock_file_response.assert_called_once()


class TestCalculateMetricsEndpoints(TestBase):
    """Test metrics calculation endpoints"""
    
    def test_calculate_metrics_success(self, client):
        """Test successful metrics calculation"""
        response = client.post("/calculate-metrics", json={
            "metrics_data": {
                "CPU Usage": [
                    {"value": 10, "timestamp": "2023-01-01T00:00:00Z"},
                    {"value": 20, "timestamp": "2023-01-01T00:01:00Z"},
                    {"value": 30, "timestamp": "2023-01-01T00:02:00Z"}
                ],
                "Memory Usage": [
                    {"value": 50, "timestamp": "2023-01-01T00:00:00Z"},
                    {"value": 60, "timestamp": "2023-01-01T00:01:00Z"}
                ]
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "calculated_metrics" in data
        
        metrics = data["calculated_metrics"]
        assert "CPU Usage" in metrics
        assert "Memory Usage" in metrics
        
        assert metrics["CPU Usage"]["avg"] == 20.0
        assert metrics["CPU Usage"]["max"] == 30.0
        assert metrics["Memory Usage"]["avg"] == 55.0
        assert metrics["Memory Usage"]["max"] == 60.0
    
    def test_calculate_metrics_empty_data(self, client):
        """Test metrics calculation with empty data"""
        response = client.post("/calculate-metrics", json={
            "metrics_data": {
                "Empty Metric": []
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        metrics = data["calculated_metrics"] 
        assert metrics["Empty Metric"]["avg"] is None
        assert metrics["Empty Metric"]["max"] is None
