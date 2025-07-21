import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from metric_ui.mcp.mcp import (
    detect_anomalies,
    describe_trend,
    compute_health_score,
    _clean_llm_summary_string,
    calculate_metric_stats,
    _validate_and_extract_response
)


class TestDetectAnomalies:
    """Test anomaly detection logic - core statistical analysis"""
    
    def test_empty_dataframe_returns_no_data(self):
        """Empty DataFrame should return 'No data'"""
        df = pd.DataFrame()
        result = detect_anomalies(df, "Test Metric")
        assert result == "No data"
    
    def test_spike_detection(self):
        """Detect metrics that spike above 90th percentile"""
        # Create data with clear spike at the end
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 50] 
        df = pd.DataFrame({"value": values})
        
        result = detect_anomalies(df, "CPU Usage")
        assert "⚠️ CPU Usage spike" in result
        assert "latest=50.00" in result
        assert ">90th pct" in result
    
    def test_low_value_detection(self):
        """Detect values below mean - standard deviation"""
        # Create data where latest value is unusually low
        values = [10, 10, 10, 10, 10, 10, 10, 10, 10, 2]
        df = pd.DataFrame({"value": values})
        
        result = detect_anomalies(df, "Request Rate")
        assert "⚠️ Request Rate unusually low" in result
        assert "latest=2.00" in result
        assert "mean=9.20" in result
    
    def test_stable_metric(self):
        """Stable metrics should return stable status"""
        values = [5, 5.1, 4.9, 5.2, 4.8, 5.0, 5.1, 4.9, 5.0, 5.0]
        df = pd.DataFrame({"value": values})
        
        result = detect_anomalies(df, "Memory Usage")
        assert "Memory Usage stable" in result
        assert "latest=5.00" in result


class TestDescribeTrend:
    """Test trend analysis using linear regression"""
    
    def test_empty_dataframe(self):
        """Empty DataFrame should return 'not enough data'"""
        df = pd.DataFrame()
        assert describe_trend(df) == "not enough data"
    
    def test_single_datapoint(self):
        """Single data point should return 'not enough data'"""
        df = pd.DataFrame({
            "timestamp": [datetime.now()],
            "value": [10]
        })
        assert describe_trend(df) == "not enough data"
    
    def test_increasing_trend(self):
        """Strong upward trend should be detected"""
        timestamps = [datetime.now() + timedelta(minutes=i) for i in range(10)]
        values = [i * 2 for i in range(10)]  # Clear increasing pattern
        df = pd.DataFrame({"timestamp": timestamps, "value": values})
        
        assert describe_trend(df) == "increasing"
    
    def test_decreasing_trend(self):
        """Strong downward trend should be detected"""
        timestamps = [datetime.now() + timedelta(minutes=i) for i in range(10)]
        values = [20 - i * 2 for i in range(10)]  # Clear decreasing pattern
        df = pd.DataFrame({"timestamp": timestamps, "value": values})
        
        assert describe_trend(df) == "decreasing"
    
    def test_stable_trend(self):
        """Small changes should be classified as stable"""
        timestamps = [datetime.now() + timedelta(minutes=i) for i in range(10)]
        values = [10 + 0.001 * i for i in range(10)]  # Very slight increase
        df = pd.DataFrame({"timestamp": timestamps, "value": values})
        
        assert describe_trend(df) == "stable"
    
    def test_flat_trend_identical_timestamps(self):
        """Identical timestamps should return 'flat'"""
        same_time = datetime.now()
        df = pd.DataFrame({
            "timestamp": [same_time, same_time, same_time],
            "value": [10, 11, 12]
        })
        assert describe_trend(df) == "flat"


class TestComputeHealthScore:
    """Test health scoring algorithm"""
    
    def test_healthy_system_zero_score(self):
        """Healthy metrics should result in score of 0"""
        metric_dfs = {
            "P95 Latency (s)": pd.DataFrame({"value": [0.5, 0.6, 0.7]}),  # Good latency
            "GPU Usage (%)": pd.DataFrame({"value": [80, 85, 90]}),        # Good GPU usage
            "Requests Running": pd.DataFrame({"value": [2, 3, 4]})         # Reasonable load
        }
        
        score, reasons = compute_health_score(metric_dfs)
        assert score == 0
        assert len(reasons) == 0
    
    def test_high_latency_penalty(self):
        """High latency should reduce health score by 2"""
        metric_dfs = {
            "P95 Latency (s)": pd.DataFrame({"value": [3.0, 3.5, 4.0]}),  # High latency
        }
        
        score, reasons = compute_health_score(metric_dfs)
        assert score == -2
        assert len(reasons) == 1
        assert "High Latency" in reasons[0]
        assert "avg=3.50" in reasons[0]
    
    def test_low_gpu_utilization_penalty(self):
        """Low GPU usage should reduce health score by 1"""
        metric_dfs = {
            "GPU Usage (%)": pd.DataFrame({"value": [5, 6, 7]}),  # Low GPU usage
        }
        
        score, reasons = compute_health_score(metric_dfs)
        assert score == -1
        assert len(reasons) == 1
        assert "Low GPU Utilization" in reasons[0]
        assert "avg=6.00" in reasons[0]
    
    def test_too_many_requests_penalty(self):
        """High request load should reduce health score by 1"""
        metric_dfs = {
            "Requests Running": pd.DataFrame({"value": [15, 20, 25]}),  # Too many requests
        }
        
        score, reasons = compute_health_score(metric_dfs)
        assert score == -1
        assert len(reasons) == 1
        assert "Too many requests" in reasons[0]
        assert "avg=20.00" in reasons[0]
    
    def test_multiple_issues_cumulative_penalty(self):
        """Multiple issues should result in cumulative penalties"""
        metric_dfs = {
            "P95 Latency (s)": pd.DataFrame({"value": [3.0, 3.5, 4.0]}),  # -2
            "GPU Usage (%)": pd.DataFrame({"value": [5, 6, 7]}),          # -1
            "Requests Running": pd.DataFrame({"value": [15, 20, 25]})     # -1
        }
        
        score, reasons = compute_health_score(metric_dfs)
        assert score == -4  # -2 + -1 + -1
        assert len(reasons) == 3
    
    def test_empty_dataframes_ignored(self):
        """Empty DataFrames should be ignored in health calculation"""
        metric_dfs = {
            "P95 Latency (s)": pd.DataFrame(),  # Empty - should be ignored
            "GPU Usage (%)": pd.DataFrame({"value": [80, 85, 90]}),  # Healthy
        }
        
        score, reasons = compute_health_score(metric_dfs)
        assert score == 0
        assert len(reasons) == 0


class TestCalculateMetricStats:
    """Test statistical calculations on metric data"""
    
    def test_empty_data_returns_none(self):
        """Empty data should return None values"""
        assert calculate_metric_stats([]) == (None, None)
        assert calculate_metric_stats(None) == (None, None)
    
    def test_valid_data_calculation(self):
        """Should correctly calculate average and max"""
        data = [
            {"value": 10, "timestamp": "2023-01-01T00:00:00Z"},
            {"value": 20, "timestamp": "2023-01-01T00:01:00Z"},
            {"value": 30, "timestamp": "2023-01-01T00:02:00Z"}
        ]
        
        avg, max_val = calculate_metric_stats(data)
        assert avg == 20.0  # (10 + 20 + 30) / 3
        assert max_val == 30.0
    
    def test_single_value_data(self):
        """Single data point should work correctly"""
        data = [{"value": 42, "timestamp": "2023-01-01T00:00:00Z"}]
        
        avg, max_val = calculate_metric_stats(data)
        assert avg == 42.0
        assert max_val == 42.0
    
    def test_malformed_data_returns_none(self):
        """Malformed data should return None safely"""
        malformed_data = [{"timestamp": "2023-01-01T00:00:00Z"}]  # Missing 'value' key
        
        avg, max_val = calculate_metric_stats(malformed_data)
        assert avg is None
        assert max_val is None


class TestValidateAndExtractResponse:
    """Test LLM response validation and extraction"""
    
    def test_external_openai_response(self):
        """Should extract content from OpenAI-style responses"""
        response_json = {
            "choices": [
                {
                    "message": {
                        "content": "This is the response content"
                    }
                }
            ]
        }
        
        result = _validate_and_extract_response(response_json, is_external=True, provider="openai")
        assert result == "This is the response content"
    
    def test_external_google_response(self):
        """Should extract content from Google Gemini responses"""
        response_json = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "This is the Gemini response"
                            }
                        ]
                    }
                }
            ]
        }
        
        result = _validate_and_extract_response(response_json, is_external=True, provider="google")
        assert result == "This is the Gemini response"
    
    def test_local_model_response(self):
        """Should extract content from local model responses"""
        response_json = {
            "choices": [
                {
                    "text": "This is the local model response"
                }
            ]
        }
        
        result = _validate_and_extract_response(response_json, is_external=False)
        assert result == "This is the local model response"
    
    def test_invalid_response_raises_error(self):
        """Should raise ValueError for invalid responses"""
        invalid_response = {"invalid": "structure"}
        
        with pytest.raises(ValueError):
            _validate_and_extract_response(invalid_response, is_external=True)
    
    def test_missing_choices_raises_error(self):
        """Should raise error when choices are missing"""
        response_json = {"choices": []}
        
        with pytest.raises(ValueError):
            _validate_and_extract_response(response_json, is_external=True)


class TestCleanLlmSummaryString:
    """Test LLM response text cleaning"""
    
    def test_removes_non_printable_characters(self):
        """Should remove non-printable ASCII characters"""
        dirty_text = "Hello\x00\x01World🤖"
        clean_text = _clean_llm_summary_string(dirty_text)
        assert clean_text == "HelloWorld"
    
    def test_normalizes_whitespace(self):
        """Should normalize multiple spaces/newlines/tabs to single spaces"""
        messy_text = "Hello     World\n\n\nTest\t\t\tText"
        clean_text = _clean_llm_summary_string(messy_text)
        assert clean_text == "Hello World Test Text"
    
    def test_strips_whitespace(self):
        """Should strip leading and trailing whitespace"""
        padded_text = "   Hello World   "
        clean_text = _clean_llm_summary_string(padded_text)
        assert clean_text == "Hello World"
    
    def test_empty_string(self):
        """Should handle empty and whitespace-only strings"""
        assert _clean_llm_summary_string("") == ""
        assert _clean_llm_summary_string("   \n\t   ") == ""