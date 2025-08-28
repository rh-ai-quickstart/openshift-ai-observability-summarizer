from unittest.mock import patch

from fastapi.testclient import TestClient


class _DummyASGIApp:
    def __init__(self):
        # Minimal callable to satisfy FastAPI(lifespan=...)
        async def _lifespan(app):  # type: ignore[no-redef]
            yield

        self.lifespan = _lifespan


class _DummyMCP:
    def http_app(self, path: str):  # noqa: ARG002 - path unused in dummy
        return _DummyASGIApp()


class _DummyServer:
    def __init__(self):
        self.mcp = _DummyMCP()


def _import_api_with_dummy_server():
    with patch("mcp_server.mcp.ObservabilityMCPServer", _DummyServer):
        import importlib
        import mcp_server.api as api_module

        importlib.reload(api_module)
        return api_module


def test_app_health_structure_and_defaults():
    api = _import_api_with_dummy_server()
    client = TestClient(api.app)

    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    for key in ["status", "service", "transport_protocol", "mcp_endpoint"]:
        assert key in data
    assert data["service"] == "observability-mcp-server"
    assert resp.headers["content-type"].startswith("application/json")


def test_health_protocol_switch_runtime():
    api = _import_api_with_dummy_server()
    client = TestClient(api.app)

    for proto in ["http", "sse", "streamable-http"]:
        with patch.object(api.settings, "MCP_TRANSPORT_PROTOCOL", proto):
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["transport_protocol"] == proto


