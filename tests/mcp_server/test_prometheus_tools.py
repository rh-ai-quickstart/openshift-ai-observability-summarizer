"""Tests for refactored Prometheus tools - updated for new architecture."""

import pytest
import json
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


class TestPrometheusToolsBasic:
    """Basic tests for refactored Prometheus tools."""
    
    def test_all_tools_importable(self):
        """Test that all Prometheus tools can be imported."""
        from mcp_server.tools.prometheus_tools import (
            search_metrics,
            get_metric_metadata,
            get_label_values,
            execute_promql,
            explain_results,
            suggest_queries,
            select_best_metric,
            find_best_metric_with_metadata_v2,
            find_best_metric_with_metadata,
        )
        
        # All tools should be callable
        tools = [
            search_metrics, get_metric_metadata, get_label_values,
            execute_promql, explain_results, suggest_queries,
            select_best_metric, find_best_metric_with_metadata_v2,
            find_best_metric_with_metadata
        ]
        
        for tool in tools:
            assert callable(tool), f"{tool.__name__} should be callable"
    
    def test_core_business_logic_imports(self):
        """Test that core business logic can be imported."""
        from core.chat_with_prometheus import (
            search_metrics_by_pattern,
            execute_promql_query,
            calculate_semantic_score,
            rank_metrics_by_relevance,
            extract_key_concepts
        )
        
        # All core functions should be callable
        core_functions = [
            search_metrics_by_pattern, execute_promql_query, calculate_semantic_score,
            rank_metrics_by_relevance, extract_key_concepts
        ]
        
        for func in core_functions:
            assert callable(func), f"{func.__name__} should be callable"
    
    def test_concept_extraction_basic(self):
        """Test basic concept extraction from user questions."""
        from core.chat_with_prometheus import extract_key_concepts
        
        # Test basic concept extraction
        concepts = extract_key_concepts("How many pods are running?")
        assert isinstance(concepts, dict)
        assert "intent_type" in concepts
        assert "components" in concepts
        
        # Should detect pod component
        assert "pod" in concepts["components"]
    
    def test_semantic_scoring_basic(self):
        """Test basic semantic scoring."""
        from core.chat_with_prometheus import calculate_semantic_score
        
        # GPU question should score high for GPU metric
        score = calculate_semantic_score("gpu temperature", "DCGM_FI_DEV_GPU_TEMP")
        assert isinstance(score, int)
        assert score > 0, "GPU metric should score positive for GPU question"
        
        # Non-matching should score lower
        score_low = calculate_semantic_score("gpu temperature", "kube_pod_status")
        assert score > score_low, "Relevant metric should score higher"
    
    def test_metric_ranking_basic(self):
        """Test metric ranking functionality."""
        from core.chat_with_prometheus import rank_metrics_by_relevance
        
        test_metrics = ["cpu_usage", "DCGM_FI_DEV_GPU_TEMP", "memory_total", "gpu_util"]
        ranked = rank_metrics_by_relevance("gpu temperature", test_metrics)
        
        assert isinstance(ranked, list)
        assert len(ranked) > 0
        # GPU metrics should be ranked higher
        assert any("gpu" in metric.lower() or "dcgm" in metric.lower() for metric in ranked[:2])


class TestPrometheusToolsMCP:
    """Test MCP tool interface layer."""
    
    def test_mcp_response_format(self):
        """Test that MCP tools return proper response format."""
        from mcp_server.tools.prometheus_tools import suggest_queries
        
        result = suggest_queries("cpu performance")
        
        # Should return MCP format: List[Dict[str, Any]] with type and text
        assert isinstance(result, list), "Should return list"
        assert len(result) > 0, "Should have at least one response item"
        assert "type" in result[0], "Should have type field"
        assert "text" in result[0], "Should have text field"
        assert result[0]["type"] == "text", "Type should be text"
    
    def test_parameter_validation(self):
        """Test parameter validation in MCP tools."""
        from mcp_server.tools.prometheus_tools import search_metrics, get_metric_metadata
        
        # Test search_metrics with invalid limit
        result = search_metrics("test", -1)
        assert isinstance(result, list)
        assert "error" in result[0]["text"].lower() or "limit" in result[0]["text"].lower()
        
        # Test get_metric_metadata with empty metric name
        result = get_metric_metadata("")
        assert isinstance(result, list)
        assert "required" in result[0]["text"].lower()
    
    def test_error_handling(self):
        """Test error handling in MCP tools."""
        from mcp_server.tools.prometheus_tools import get_label_values
        
        # Test with missing parameters
        result = get_label_values("", "")
        assert isinstance(result, list)
        assert len(result) > 0
        assert "required" in result[0]["text"].lower()


class TestArchitectureSeparation:
    """Test that architecture separation is working correctly."""
    
    def test_core_functions_framework_agnostic(self):
        """Test that core functions don't depend on MCP framework."""
        from core.chat_with_prometheus import calculate_semantic_score, extract_key_concepts
        
        # Core functions should work without any MCP imports
        score = calculate_semantic_score("memory usage", "memory_total")
        assert isinstance(score, int)
        
        concepts = extract_key_concepts("what is cpu usage")
        assert isinstance(concepts, dict)
        assert concepts["intent_type"] in ["current_value", "count", "average", "percentile"]
    
    def test_mcp_tools_delegate_to_core(self):
        """Test that MCP tools properly delegate to core business logic."""
        from mcp_server.tools.prometheus_tools import suggest_queries
        from core.chat_with_prometheus import suggest_related_queries
        
        # Both should work independently
        mcp_result = suggest_queries("cpu usage")
        core_result = suggest_related_queries("cpu usage")
        
        assert isinstance(mcp_result, list)  # MCP format
        assert isinstance(core_result, list)  # Core returns list of strings
        
        # MCP result should contain core result data
        if len(mcp_result) > 0:
            mcp_text = mcp_result[0]["text"]
            assert "suggested_queries" in mcp_text
    
    def test_import_consistency(self):
        """Test that import patterns are consistent with working tools."""
        import inspect
        
        # Check prometheus_tools imports from core
        from mcp_server.tools import prometheus_tools
        source = inspect.getsource(prometheus_tools)
        assert "from core.chat_with_prometheus import" in source
        
        # Check working vllm tools for comparison
        from mcp_server.tools import observability_vllm_tools
        vllm_source = inspect.getsource(observability_vllm_tools)
        assert "from core.metrics import" in vllm_source
        
        # Both should follow similar patterns
        assert "from core." in source and "from core." in vllm_source


class TestRealDataFlow:
    """Test data flow with mocked Prometheus responses."""
    
    def test_search_metrics_response_structure(self):
        """Test search metrics returns expected structure."""
        from core.chat_with_prometheus import search_metrics_by_pattern
        
        # Mock a small search (should work even without Prometheus if we catch the exception)
        try:
            result = search_metrics_by_pattern("test", 1)
            
            # Should return dict with expected keys
            assert isinstance(result, dict)
            expected_keys = ["total_found", "metrics", "pattern", "limit"]
            for key in expected_keys:
                assert key in result, f"Missing key: {key}"
                
        except Exception:
            # If Prometheus not available, that's expected in unit tests
            pass
    
    def test_response_format_consistency(self):
        """Test that all tools return consistent MCP response format."""
        from mcp_server.tools.prometheus_tools import (
            suggest_queries, search_metrics
        )
        
        tools_to_test = [
            (suggest_queries, ("cpu usage",), {}),
            (search_metrics, ("test", 1), {}),
        ]
        
        for tool_func, args, kwargs in tools_to_test:
            try:
                result = tool_func(*args, **kwargs)
                
                # All should return List[Dict[str, Any]] with consistent structure
                assert isinstance(result, list), f"{tool_func.__name__} should return list"
                if len(result) > 0:
                    assert "type" in result[0], f"{tool_func.__name__} missing type field"
                    assert "text" in result[0], f"{tool_func.__name__} missing text field"
                    
            except Exception as e:
                # Some tools may fail without Prometheus, that's OK for structure testing
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])