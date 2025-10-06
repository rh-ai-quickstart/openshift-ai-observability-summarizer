"""Tests for Tempo MCP tools."""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import src.mcp_server.tools.tempo as tempo_tools


def _texts(result):
    """Extract text content from MCP tool results."""
    return [part.get("text") for part in result]


class TestQueryTempoTool:
    """Test query_tempo_tool function."""

    @patch("src.mcp_server.tools.tempo.mcp_tools.TempoQueryTool")
    def test_query_tempo_tool_success(self, mock_tempo_class):
        """Test successful trace query."""
        # Mock the TempoQueryTool instance
        mock_tempo = MagicMock()
        mock_tempo_class.return_value = mock_tempo
        
        # Mock successful query response as a coroutine
        async def mock_query_traces(*args, **kwargs):
            return {
                "success": True,
                "query": "service.name=ui",
                "time_range": "2024-01-01T00:00:00Z to 2024-01-01T23:59:59Z",
                "total": 2,
                "traces": [
                    {
                        "traceID": "abc123",
                        "rootServiceName": "ui",
                        "durationMs": 1500,
                        "spanCount": 5
                    },
                    {
                        "traceID": "def456", 
                        "rootServiceName": "api",
                        "durationMs": 800,
                        "spanCount": 3
                    }
                ]
            }
        
        mock_tempo.query_traces = mock_query_traces

        # Since the function is async, we need to run it in an event loop
        import asyncio
        result = asyncio.run(tempo_tools.query_tempo_tool(
            query="service.name=ui",
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-01T23:59:59Z",
            limit=20
        ))

        # Verify the result structure
        assert isinstance(result, list)
        assert len(result) == 1
        assert "text" in result[0]
        
        text = result[0]["text"]
        assert "abc123" in text
        assert "ui" in text
        assert "1500" in text

    @patch("src.mcp_server.tools.tempo.mcp_tools.TempoQueryTool")
    def test_query_tempo_tool_no_traces(self, mock_tempo_class):
        """Test query with no traces found."""
        mock_tempo = MagicMock()
        mock_tempo_class.return_value = mock_tempo
        
        async def mock_query_traces(*args, **kwargs):
            return {
                "success": True,
                "query": "service.name=nonexistent",
                "time_range": "2024-01-01T00:00:00Z to 2024-01-01T23:59:59Z",
                "total": 0,
                "traces": []
            }
        
        mock_tempo.query_traces = mock_query_traces

        import asyncio
        result = asyncio.run(tempo_tools.query_tempo_tool(
            query="service.name=nonexistent",
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-01T23:59:59Z",
            limit=20
        ))

        assert isinstance(result, list)
        assert len(result) == 1
        text = result[0]["text"]
        assert "No traces found" in text or "0 traces" in text

    @patch("src.mcp_server.tools.tempo.mcp_tools.TempoQueryTool")
    def test_query_tempo_tool_error(self, mock_tempo_class):
        """Test query with error response."""
        mock_tempo = MagicMock()
        mock_tempo_class.return_value = mock_tempo
        
        async def mock_query_traces(*args, **kwargs):
            return {
                "success": False,
                "query": "service.name=ui",
                "error": "Connection failed"
            }
        
        mock_tempo.query_traces = mock_query_traces

        import asyncio
        result = asyncio.run(tempo_tools.query_tempo_tool(
            query="service.name=ui",
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-01T23:59:59Z",
            limit=20
        ))

        assert isinstance(result, list)
        assert len(result) == 1
        text = result[0]["text"]
        assert "Connection failed" in text


class TestGetTraceDetailsTool:
    """Test get_trace_details_tool function."""

    @patch("src.mcp_server.tools.tempo.mcp_tools.TempoQueryTool")
    def test_get_trace_details_success(self, mock_tempo_class):
        """Test successful trace details retrieval."""
        mock_tempo = MagicMock()
        mock_tempo_class.return_value = mock_tempo
        
        # Mock successful trace details response as a coroutine
        async def mock_get_trace_details(*args, **kwargs):
            return {
                "success": True,
                "trace": {
                    "traceID": "abc123",
                    "spans": [
                        {
                            "spanID": "span1",
                            "operationName": "GET /api/users",
                            "startTime": 1640995200000000,
                            "duration": 500000,
                            "process": {
                                "serviceName": "ui"
                            }
                        }
                    ]
                }
            }
        
        mock_tempo.get_trace_details = mock_get_trace_details

        import asyncio
        result = asyncio.run(tempo_tools.get_trace_details_tool("abc123"))

        assert isinstance(result, list)
        assert len(result) == 1
        text = result[0]["text"]
        assert "abc123" in text
        assert "GET /api/users" in text
        assert "ui" in text

    @patch("src.mcp_server.tools.tempo.mcp_tools.TempoQueryTool")
    def test_get_trace_details_error(self, mock_tempo_class):
        """Test trace details with error response."""
        mock_tempo = MagicMock()
        mock_tempo_class.return_value = mock_tempo
        
        async def mock_get_trace_details(*args, **kwargs):
            return {
                "success": False,
                "error": "Trace not found"
            }
        
        mock_tempo.get_trace_details = mock_get_trace_details

        import asyncio
        result = asyncio.run(tempo_tools.get_trace_details_tool("nonexistent"))

        assert isinstance(result, list)
        assert len(result) == 1
        text = result[0]["text"]
        assert "Trace not found" in text


class TestChatTempoTool:
    """Test chat_tempo_tool function."""

    @patch("src.mcp_server.tools.tempo.mcp_tools.TempoQueryTool")
    def test_chat_tempo_tool_success(self, mock_tempo_class):
        """Test successful conversational trace analysis."""
        mock_tempo = MagicMock()
        mock_tempo_class.return_value = mock_tempo
        
        # Mock successful query response as a coroutine
        async def mock_query_traces(*args, **kwargs):
            return {
                "success": True,
                "traces": [
                    {
                        "traceID": "abc123",
                        "rootServiceName": "ui",
                        "durationMs": 1500,
                        "spanCount": 5
                    }
                ]
            }
        
        mock_tempo.query_traces = mock_query_traces

        import asyncio
        result = asyncio.run(tempo_tools.chat_tempo_tool("Show me traces from ui service"))

        assert isinstance(result, list)
        assert len(result) == 1
        text = result[0]["text"]
        assert "Tempo Chat Analysis" in text
        assert "abc123" in text
        assert "ui" in text

    @patch("src.mcp_server.tools.tempo.mcp_tools.TempoQueryTool")
    def test_chat_tempo_tool_no_traces(self, mock_tempo_class):
        """Test conversational analysis with no traces."""
        mock_tempo = MagicMock()
        mock_tempo_class.return_value = mock_tempo
        
        async def mock_query_traces(*args, **kwargs):
            return {
                "success": True,
                "traces": []
            }
        
        mock_tempo.query_traces = mock_query_traces

        import asyncio
        result = asyncio.run(tempo_tools.chat_tempo_tool("Show me slow traces"))

        assert isinstance(result, list)
        assert len(result) == 1
        text = result[0]["text"]
        assert "No traces found" in text or "0 traces" in text

    @patch("src.mcp_server.tools.tempo.mcp_tools.TempoQueryTool")
    def test_chat_tempo_tool_error(self, mock_tempo_class):
        """Test conversational analysis with error."""
        mock_tempo = MagicMock()
        mock_tempo_class.return_value = mock_tempo
        
        async def mock_query_traces(*args, **kwargs):
            return {
                "success": False,
                "error": "Service unavailable"
            }
        
        mock_tempo.query_traces = mock_query_traces

        import asyncio
        result = asyncio.run(tempo_tools.chat_tempo_tool("Show me traces from last hour"))

        assert isinstance(result, list)
        assert len(result) == 1
        text = result[0]["text"]
        assert "Service unavailable" in text


class TestUtilityFunctions:
    """Test utility functions."""

    def test_extract_time_range_from_question(self):
        """Test time range extraction from natural language questions."""
        from src.mcp_server.tools.tempo import extract_time_range_from_question
        
        test_cases = [
            ("Show me traces from the last 24 hours", "last 24h"),
            ("Find traces from last week", "last 7d"),
            ("Show me traces from yesterday", "last 24h"),
            ("Get traces from the last 2 hours", "last 2h"),
            ("Show me traces from last month", "last 30d"),
            ("Find traces from the last 6 hours", "last 6h")
        ]
        
        for question, expected_range in test_cases:
            result = extract_time_range_from_question(question)
            assert result == expected_range


class TestTempoQueryToolClass:
    """Test TempoQueryTool class methods."""

    @patch("httpx.AsyncClient")
    def test_tempo_query_tool_initialization(self, mock_client):
        """Test TempoQueryTool initialization with environment variables."""
        with patch.dict("os.environ", {
            "TEMPO_URL": "https://tempo.example.com:8080",
            "TEMPO_TENANT_ID": "test-tenant"
        }):
            from src.mcp_server.tools.tempo import TempoQueryTool
            tool = TempoQueryTool()
            
            assert tool.tempo_url == "https://tempo.example.com:8080"
            assert tool.tenant_id == "test-tenant"
            assert tool.namespace == "observability-hub"

    @patch("httpx.AsyncClient")
    def test_tempo_query_tool_default_config(self, mock_client):
        """Test TempoQueryTool with default configuration."""
        from src.mcp_server.tools.tempo import TempoQueryTool
        tool = TempoQueryTool()
        
        assert tool.tempo_url == "https://tempo-tempostack-gateway.observability-hub.svc.cluster.local:8080"
        assert tool.tenant_id == "dev"
        assert tool.namespace == "observability-hub"

    @patch("httpx.AsyncClient")
    def test_get_available_services_success(self, mock_client):
        """Test successful service discovery."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": ["ui", "api", "database"]
        }
        
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        
        from src.mcp_server.tools.tempo import TempoQueryTool
        tool = TempoQueryTool()
        
        import asyncio
        services = asyncio.run(tool.get_available_services())
        
        assert services == ["ui", "api", "database"]

    @patch("httpx.AsyncClient")
    def test_get_available_services_error(self, mock_client):
        """Test service discovery with error response."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        
        from src.mcp_server.tools.tempo import TempoQueryTool
        tool = TempoQueryTool()
        
        import asyncio
        services = asyncio.run(tool.get_available_services())
        
        assert services == []