"""
OpenShift AI Observability - Core Business Logic

This package contains shared business logic that can be used by:
- FastAPI service (src/api/)
- Streamlit UI (src/ui/)
- MCP server (src/mcp-server/)

Modules:
- metrics: Prometheus/Thanos data collection and processing
- llm_client: LLM interactions and prompt building
- models: Pydantic data models (framework-agnostic)
- reports: HTML/PDF/Markdown report generation
"""

__version__ = "0.1.0" 