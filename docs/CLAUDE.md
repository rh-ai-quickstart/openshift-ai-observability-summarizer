# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the OpenShift AI Observability Summarizer - an open source project that provides advanced monitoring and automated summarization of AI model and OpenShift cluster metrics. The system generates AI-powered insights and reports from Prometheus/Thanos metrics data.

## Development Commands

### Python Environment Setup
```bash
# Install uv for dependency management
# See: https://github.com/astral-sh/uv

# Sync dependencies
uv sync --group dev

# Activate virtual environment
source .venv/bin/activate
```

### Build and Push Images
```bash
# Build all container images
make build

# Build individual components
make build-metrics-api    # FastAPI backend
make build-ui            # Streamlit UI
make build-alerting      # Alerting service

# Push to registry
make push

# Build and push workflow
make build-and-push
```

### Testing
```bash
# Run all tests with coverage
make test
# OR
uv run pytest -v --cov=src --cov-report=html --cov-report=term

# Run specific test modules
uv run pytest -v tests/mcp/
uv run pytest -v tests/core/
```

### Local Development
```bash
# Set up local development with port-forwarding
make install-local
# OR manually
export LLM_NAMESPACE=<namespace>
./scripts/local-dev.sh
```

### Deployment
```bash
# Deploy to OpenShift
make install NAMESPACE=your-namespace

# Deploy with specific model
make install NAMESPACE=your-namespace LLM=llama-3-2-3b-instruct

# Deploy with alerting
make install NAMESPACE=your-namespace ALERTS=TRUE

# Uninstall
make uninstall NAMESPACE=your-namespace
```

## Architecture

### Core Components
- **src/api/metrics_api.py**: FastAPI backend serving metrics analysis and chat endpoints
- **src/ui/ui.py**: Streamlit multi-dashboard frontend
- **src/core/**: Business logic modules
  - `config.py`: Configuration management and environment variables
  - `llm_client.py`: LLM communication and prompt building
  - `metrics.py`: Metrics discovery and fetching from Prometheus/Thanos
  - `analysis.py`: Statistical analysis and anomaly detection
  - `reports.py`: Report generation utilities
  - `promql_service.py`: PromQL query generation from natural language
  - `thanos_service.py`: Thanos querying and data processing
- **src/alerting/**: Alert handling and Slack notifications
- **deploy/helm/**: Helm charts for OpenShift deployment

### Data Flow
1. **Natural Language Question** → PromQL generation via LLM
2. **PromQL Queries** → Thanos/Prometheus for metrics data
3. **Metrics Data** → Statistical analysis and anomaly detection
4. **Analysis Results** → LLM summarization
5. **Summary** → Report generation (HTML/PDF/Markdown)

### Key Services Integration
- **Prometheus/Thanos**: Metrics storage and querying
- **vLLM**: Model serving with /metrics endpoint
- **DCGM**: GPU monitoring metrics
- **Llama Stack**: LLM inference backend
- **OpenTelemetry/Tempo**: Distributed tracing

## Configuration

### Environment Variables
- `PROMETHEUS_URL`: Thanos/Prometheus endpoint (default: http://localhost:9090)
- `LLAMA_STACK_URL`: LLM backend URL (default: http://localhost:8321/v1/openai/v1)
- `LLM_API_TOKEN`: API token for LLM service
- `MODEL_CONFIG`: JSON configuration for available models
- `THANOS_TOKEN`: Authentication token (default: reads from service account)

### Model Configuration
Models are configured via `MODEL_CONFIG` environment variable as JSON:
```json
{
  "model-name": {
    "external": false,
    "url": "http://service:port",
    "apiToken": "token"
  }
}
```

## Testing Strategy

- **Unit Tests**: Core business logic in `tests/core/`
- **Integration Tests**: API endpoints in `tests/mcp/`
- **Alert Tests**: Alerting functionality in `tests/alerting/`
- **Coverage**: Configured to exclude UI components and report assets

## Common Development Patterns

### Adding New Metrics
1. Update metric discovery functions in `src/core/metrics.py`
2. Add PromQL queries for the new metrics
3. Update UI components to display the metrics
4. Add corresponding tests

### Adding New LLM Endpoints
1. Define request/response models in `src/core/models.py`
2. Implement business logic in appropriate `src/core/` module
3. Add FastAPI endpoint in `src/api/metrics_api.py`
4. Add corresponding tests

### Error Handling
- API endpoints use HTTPException for user-facing errors
- Internal errors are logged with stack traces
- LLM API key errors return specific user-friendly messages

## Security Considerations
- Service account tokens are read from mounted volumes
- SSL verification uses cluster CA bundle when available
- No secrets should be logged or committed to repository