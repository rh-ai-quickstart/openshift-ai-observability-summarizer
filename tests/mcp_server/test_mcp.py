import types
import sys
from unittest.mock import Mock

import pytest


class _DummyMCP:
    def __init__(self, name: str):  # noqa: ARG002 - name not used
        self.tool_calls = 0

    def tool(self):
        def _decorator(func):
            self.tool_calls += 1
            return func

        return _decorator


def _make_dummy_fastmcp_module():
    mod = types.ModuleType("fastmcp")

    class DummyFastMCP:  # noqa: D401 - simple dummy
        """Dummy FastMCP that returns a minimal MCP object."""

        def __init__(self, name: str):  # noqa: ARG002 - name not used
            self._mcp = _DummyMCP(name)

        def __call__(self, *args, **kwargs):  # pragma: no cover - not used
            return self._mcp

        def __getattr__(self, item):  # forward attributes to MCP instance
            return getattr(self._mcp, item)

    mod.FastMCP = DummyFastMCP
    return mod


def _make_dummy_tools_module():
    tools_mod = types.ModuleType("mcp_server.tools.observability_tools")

    def list_models():  # noqa: D401 - dummy
        """dummy"""

    def list_namespaces():  # noqa: D401 - dummy
        """dummy"""

    def get_model_config():  # noqa: D401 - dummy
        """dummy"""

    def analyze_vllm(*args, **kwargs):  # noqa: D401 - dummy
        """dummy"""

    tools_mod.list_models = list_models
    tools_mod.list_namespaces = list_namespaces
    tools_mod.get_model_config = get_model_config
    tools_mod.analyze_vllm = analyze_vllm
    return tools_mod


def test_observability_mcp_server_registers_four_tools_and_reconfigures(monkeypatch):
    # Arrange: inject dummy fastmcp and dummy tools to avoid heavy deps
    monkeypatch.setitem(sys.modules, "fastmcp", _make_dummy_fastmcp_module())
    monkeypatch.setitem(
        sys.modules, "mcp_server.tools.observability_tools", _make_dummy_tools_module()
    )

    import importlib
    import mcp_server.mcp as mcp_mod

    importlib.reload(mcp_mod)

    mock_reconfigure = Mock()
    mock_get_logger = Mock()
    monkeypatch.setattr(mcp_mod, "force_reconfigure_all_loggers", mock_reconfigure)
    monkeypatch.setattr(mcp_mod, "get_python_logger", mock_get_logger)

    # Act
    server = mcp_mod.ObservabilityMCPServer()

    # Assert
    assert hasattr(server, "mcp")
    # Our DummyFastMCP proxies to _DummyMCP instance with tool_calls counter
    assert getattr(server.mcp, "tool_calls", 0) == 4
    mock_get_logger.assert_called_once()
    mock_reconfigure.assert_called_once()


def test_observability_mcp_server_init_failure_propagates(monkeypatch):
    # Arrange: make FastMCP raise during construction
    failing_fastmcp = types.ModuleType("fastmcp")

    class FailingFastMCP:  # noqa: D401 - dummy
        """Raises on init."""

        def __init__(self, *args, **kwargs):  # noqa: D401 - dummy
            raise RuntimeError("boom")

    failing_fastmcp.FastMCP = FailingFastMCP
    monkeypatch.setitem(sys.modules, "fastmcp", failing_fastmcp)

    import importlib
    import mcp_server.mcp as mcp_mod

    importlib.reload(mcp_mod)

    # Act & Assert
    with pytest.raises(RuntimeError, match="boom"):
        mcp_mod.ObservabilityMCPServer()


