"""Tests for core/chat_with_prometheus.py business logic module."""

import pytest
import json
from unittest.mock import Mock, patch
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


class TestSemanticAnalysis:
    """Test semantic analysis functions."""
    
    def test_calculate_semantic_score(self):
        """Test semantic scoring for various patterns."""
        from core.chat_with_prometheus import calculate_semantic_score
        
        # GPU patterns
        assert calculate_semantic_score("gpu temperature", "DCGM_FI_DEV_GPU_TEMP") > 0
        assert calculate_semantic_score("gpu usage", "nvidia_gpu_utilization") > 0
        
        # Temperature patterns
        assert calculate_semantic_score("temperature", "cpu_temp") > 0
        assert calculate_semantic_score("thermal", "thermal_zone_temp") > 0
        
        # Memory patterns
        assert calculate_semantic_score("memory usage", "memory_bytes") > 0
        assert calculate_semantic_score("ram", "node_memory_ram") > 0
        
        # Non-matching should score 0 or low
        assert calculate_semantic_score("gpu", "kube_pod_status") == 0
    
    def test_calculate_type_relevance(self):
        """Test metric type relevance scoring."""
        from core.chat_with_prometheus import calculate_type_relevance
        
        # Counter patterns
        assert calculate_type_relevance("rate", "requests_total") > 0
        assert calculate_type_relevance("count", "error_count") > 0
        
        # Gauge patterns
        assert calculate_type_relevance("current usage", "cpu_usage_percent") > 0
        assert calculate_type_relevance("utilization", "memory_util") > 0
        
        # Histogram patterns
        assert calculate_type_relevance("p95", "latency_bucket") > 0
        assert calculate_type_relevance("percentile", "response_histogram") > 0
    
    def test_calculate_specificity_score(self):
        """Test specificity scoring."""
        from core.chat_with_prometheus import calculate_specificity_score
        
        # Specific metrics should score higher
        specific_score = calculate_specificity_score("vllm:token_generation_rate")
        generic_score = calculate_specificity_score("up")
        
        assert specific_score > generic_score
        
        # DCGM metrics should get specificity bonus
        dcgm_score = calculate_specificity_score("DCGM_FI_DEV_GPU_TEMP")
        assert dcgm_score > 0
    
    def test_extract_key_concepts(self):
        """Test concept extraction from user questions."""
        from core.chat_with_prometheus import extract_key_concepts
        
        # Test intent detection
        concepts = extract_key_concepts("How many pods are running?")
        assert concepts["intent_type"] == "count"
        
        concepts = extract_key_concepts("What is the current CPU usage?")
        assert concepts["intent_type"] == "current_value"
        
        concepts = extract_key_concepts("Show me the average memory usage")
        assert concepts["intent_type"] == "average"
        
        # Test measurement detection
        concepts = extract_key_concepts("What's the GPU temperature?")
        assert "temperature" in concepts["measurements"]
        # Note: GPU is detected via semantic scoring, not always in measurements
        
        # Test component detection
        concepts = extract_key_concepts("How are the pods doing?")
        assert "pod" in concepts["components"]


class TestMetricRanking:
    """Test metric ranking and selection functions."""
    
    def test_rank_metrics_by_relevance(self):
        """Test metric ranking algorithm."""
        from core.chat_with_prometheus import rank_metrics_by_relevance
        
        test_metrics = [
            "cpu_usage_total",
            "DCGM_FI_DEV_GPU_TEMP", 
            "kube_pod_status_phase",
            "memory_bytes_total",
            "random_metric"
        ]
        
        # GPU question should rank GPU metrics higher
        ranked = rank_metrics_by_relevance("gpu temperature", test_metrics)
        assert isinstance(ranked, list)
        assert len(ranked) > 0
        # GPU metric should be first
        assert "DCGM_FI_DEV_GPU_TEMP" in ranked[:2]
        
        # Pod question should rank pod metrics higher
        ranked = rank_metrics_by_relevance("pod status", test_metrics)
        assert "kube_pod_status_phase" in ranked[:2]
    
    def test_select_best_metric_for_question(self):
        """Test best metric selection."""
        from core.chat_with_prometheus import select_best_metric_for_question
        
        test_metrics = ["cpu_usage", "DCGM_FI_DEV_GPU_TEMP", "memory_total"]
        
        # Should return the best match
        best = select_best_metric_for_question("gpu temperature", test_metrics)
        assert best == "DCGM_FI_DEV_GPU_TEMP"
        
        # Should handle empty list
        best = select_best_metric_for_question("anything", [])
        assert best == ""


class TestQueryGeneration:
    """Test PromQL query generation functions."""
    
    def test_generate_query_examples(self):
        """Test PromQL query example generation."""
        from core.chat_with_prometheus import generate_query_examples
        
        # Counter metric
        examples = generate_query_examples("requests_total", {"type": "counter"})
        assert isinstance(examples, list)
        assert len(examples) > 0
        assert any("rate(" in ex for ex in examples)
        
        # Gauge metric
        examples = generate_query_examples("cpu_usage", {"type": "gauge"})
        assert any("avg(" in ex for ex in examples)
        
        # Histogram metric
        examples = generate_query_examples("latency_bucket", {"type": "histogram"})
        assert any("histogram_quantile(" in ex for ex in examples)
    
    def test_generate_metadata_driven_promql(self):
        """Test metadata-driven PromQL generation."""
        from core.chat_with_prometheus import generate_metadata_driven_promql
        
        metric_analysis = {
            "name": "cpu_usage_percent",
            "metadata": {"type": "gauge"}
        }
        concepts = {"intent_type": "current_value", "measurements": set()}
        
        query = generate_metadata_driven_promql(metric_analysis, concepts)
        assert isinstance(query, str)
        assert "cpu_usage_percent" in query
    
    def test_suggest_related_queries(self):
        """Test query suggestion functionality."""
        from core.chat_with_prometheus import suggest_related_queries
        
        # With base metric
        suggestions = suggest_related_queries("usage", "cpu_utilization")
        assert isinstance(suggestions, list)
        assert len(suggestions) > 0
        assert any("cpu_utilization" in s for s in suggestions)
        
        # Without base metric (intent-based)
        suggestions = suggest_related_queries("performance monitoring")
        assert isinstance(suggestions, list)
        assert len(suggestions) > 0


class TestPrometheusIntegration:
    """Test Prometheus integration functions (with mocking)."""
    
    @patch('core.chat_with_prometheus.make_prometheus_request')
    def test_search_metrics_by_pattern(self, mock_request):
        """Test metric search functionality."""
        from core.chat_with_prometheus import search_metrics_by_pattern
        
        # Mock Prometheus response
        mock_request.side_effect = [
            {"data": ["metric1", "metric2", "gpu_temp"]},  # Metric names
            {"data": {"metric1": [{"type": "gauge", "help": "Test metric"}]}},  # Metadata
            {"data": {"metric2": [{"type": "counter", "help": "Another metric"}]}},
            {"data": {"gpu_temp": [{"type": "gauge", "help": "GPU temperature"}]}},
        ]
        
        result = search_metrics_by_pattern("gpu", 5)
        
        assert isinstance(result, dict)
        assert "total_found" in result
        assert "metrics" in result
        assert result["pattern"] == "gpu"
        assert result["limit"] == 5
    
    @patch('core.chat_with_prometheus.make_prometheus_request')
    def test_get_metric_metadata(self, mock_request):
        """Test metric metadata retrieval."""
        from core.chat_with_prometheus import get_metric_metadata
        
        # Mock responses
        mock_request.side_effect = [
            {"data": {"test_metric": [{"type": "gauge", "help": "Test metric", "unit": "bytes"}]}},
            {"data": ["instance", "job", "namespace"]},
            {"data": ["host1", "host2"]},  # instance values
            {"data": ["job1", "job2"]},    # job values
            {"data": ["ns1", "ns2"]},      # namespace values
        ]
        
        result = get_metric_metadata("test_metric")
        
        assert isinstance(result, dict)
        assert "metric_name" in result
        assert "metadata" in result
        assert "available_labels" in result
        assert "sample_label_values" in result
        assert "query_examples" in result
    
    @patch('core.chat_with_prometheus.make_prometheus_request')
    def test_execute_promql_query_instant(self, mock_request):
        """Test instant PromQL query execution."""
        from core.chat_with_prometheus import execute_promql_query
        
        # Mock instant query response
        mock_request.return_value = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {"metric": {"__name__": "up", "job": "test"}, "value": [1234567890, "1"]}
                ]
            }
        }
        
        result = execute_promql_query("up")
        
        assert isinstance(result, dict)
        assert result["status"] == "success"
        assert result["result_type"] == "vector"
        assert len(result["results"]) == 1
        
        # Should use instant query endpoint
        mock_request.assert_called_with("/api/v1/query", {"query": "up"})
    
    @patch('core.chat_with_prometheus.make_prometheus_request')
    def test_execute_promql_query_range(self, mock_request):
        """Test range PromQL query execution."""
        from core.chat_with_prometheus import execute_promql_query
        
        # Mock range query response
        mock_request.return_value = {
            "status": "success", 
            "data": {
                "resultType": "matrix",
                "result": []
            }
        }
        
        result = execute_promql_query("up", "2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z")
        
        assert isinstance(result, dict)
        assert result["status"] == "success"
        
        # Should use range query endpoint
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == "/api/v1/query_range"


class TestErrorHandling:
    """Test error handling in core functions."""
    
    def test_get_metric_metadata_not_found(self):
        """Test handling of non-existent metrics."""
        from core.chat_with_prometheus import get_metric_metadata
        
        with patch('core.chat_with_prometheus.make_prometheus_request') as mock_request:
            mock_request.return_value = {"data": {}}  # No metric found
            
            with pytest.raises(ValueError, match="not found"):
                get_metric_metadata("nonexistent_metric")
    
    def test_find_best_metric_no_candidates(self):
        """Test handling when no metrics are found."""
        from core.chat_with_prometheus import find_best_metric_with_metadata
        
        with patch('core.chat_with_prometheus.make_prometheus_request') as mock_request:
            mock_request.return_value = {"data": []}  # No metrics available
            
            with pytest.raises(ValueError, match="No relevant metrics found"):
                find_best_metric_with_metadata("test question")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
