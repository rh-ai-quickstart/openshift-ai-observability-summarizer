# AI Observability MCP Server

Model Context Protocol (MCP) server providing AI-powered observability tools for vLLM models in OpenShift environments.

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- OpenShift cluster access
- Virtual environment

### Installation & Setup

```bash
# 1. Install MCP server
cd src/mcp_server
pip install -r requirements.txt

# 2. Run locally
PYTHONPATH=src uvicorn mcp_server.api:app --host 0.0.0.0 --port 8080

# 3. Health check
curl http://127.0.0.1:8080/health
```

### Deployment (Docker)

```bash
cd src
docker build -f mcp_server/Dockerfile -t obs-mcp-server:local .
docker run --rm -p 8080:8080 obs-mcp-server:local
```

## Endpoints
- `/health`: readiness/liveness
- `/mcp`: MCP HTTP transport



