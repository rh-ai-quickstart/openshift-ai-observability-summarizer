# DEV_GUIDE.md - OpenShift AI Observability Summarizer

> **Comprehensive Development Guide for Human Developers & AI Assistants**  
> This file provides complete guidance for working with the AI Observability Summarizer project, combining development patterns, architecture, and comprehensive instructions for both **human developers** and **AI coding assistants**.

## 🚀 Project Overview

The **OpenShift AI Observability Summarizer** is an open source, CNCF-style project that provides advanced monitoring and automated summarization of AI model and OpenShift cluster metrics. It generates AI-powered insights and reports from Prometheus/Thanos metrics data.

### Key Capabilities
- **vLLM Monitoring**: GPU usage, latency, request volume analysis
- **OpenShift Fleet Monitoring**: Cluster-wide and namespace-scoped metrics
- **AI-Powered Insights**: LLM-based metric summarization and analysis
- **Report Generation**: HTML, PDF, and Markdown exports
- **Alerting & Notifications**: AI-powered alerts with Slack integration
- **Distributed Tracing**: OpenTelemetry and Tempo integration

## 📁 Project Structure

```
summarizer/
├── src/                    # Main source code
│   ├── api/               # FastAPI metrics API
│   │   ├── metrics_api.py # Main API endpoints
│   │   └── report_assets/ # Report generation assets
│   ├── core/              # Core business logic
│   │   ├── config.py      # Configuration management
│   │   ├── llm_client.py  # LLM communication
│   │   ├── metrics.py     # Metrics discovery & fetching
│   │   ├── analysis.py    # Statistical analysis
│   │   ├── reports.py     # Report generation
│   │   ├── promql_service.py # PromQL generation
│   │   └── thanos_service.py # Thanos integration
│   ├── ui/                # Streamlit UI
│   │   └── ui.py         # Multi-dashboard interface
│   └── alerting/          # Alerting service
│       └── alert_receiver.py # Alert handling
├── deploy/helm/           # Helm charts for deployment
├── tests/                 # Test suite
├── scripts/               # Development and deployment scripts
└── docs/                  # Documentation
```

## 🔧 Development Setup

### Prerequisites
- Python 3.11+
- `uv` package manager
- OpenShift CLI (`oc`)
- `helm` v3.x
- `yq` (YAML processor)
- Docker or Podman


### Local Development
```bash
# Set up port-forwarding to cluster services
LLM_NAMESPACE=<TARGET_NAMESPACE> make install-local

# This runs ./scripts/local-dev.sh which sets up:
# - Port-forwarding to Llamastack (8000:8000)
# - Port-forwarding to llm-service (8001:8001)  
# - Port-forwarding to Thanos (9090:9090)

# Example:
LLM_NAMESPACE=test make install-local
```

**Note**: The `LLM_NAMESPACE` environment variable is used by the `./scripts/local-dev.sh` script to:
- Set up port-forwarding to the correct namespace
- Configure the local development environment
- Ensure all services are accessible from your local machine

## 🏗️ Architecture & Data Flow

### Core Components
1. **Metrics API** (`src/api/metrics_api.py`): FastAPI backend serving metrics analysis and chat endpoints
2. **UI** (`src/ui/ui.py`): Streamlit multi-dashboard frontend
3. **Core Logic** (`src/core/`): Business logic modules for metrics processing and LLM integration
4. **Alerting** (`src/alerting/`): Alert handling and Slack notifications
5. **Helm Charts** (`deploy/helm/`): OpenShift deployment configuration

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

## 🧪 Testing

### Test Commands
```bash
# Run all tests with coverage
uv run pytest -v --cov=src --cov-report=html --cov-report=term

# Run specific test categories
uv run pytest -v tests/mcp/           # MCP tests
uv run pytest -v tests/core/          # Core logic tests
uv run pytest -v tests/alerting/      # Alerting tests
uv run pytest -v tests/api/           # API tests

# Run specific test file
uv run pytest -v tests/mcp/test_api_endpoints.py

# View coverage report
open htmlcov/index.html
```

### Test Structure
- **`tests/mcp/`** - Metric Collection & Processing tests
- **`tests/core/`** - Core business logic tests
- **`tests/alerting/`** - Alerting service tests
- **`tests/api/`** - API endpoint tests

### Testing Strategy
- **Unit Tests**: Core business logic in `tests/core/`
- **Integration Tests**: API endpoints in `tests/mcp/`
- **Alert Tests**: Alerting functionality in `tests/alerting/`
- **Coverage**: Configured to exclude UI components and report assets

## 🚀 Building & Deployment

### Container Images
```bash
# Build all components
make build

# Build individual components
make build-metrics-api    # FastAPI backend
make build-ui            # Streamlit UI
make build-alerting      # Alerting service

# Build with custom tag
make build TAG=v1.0.0
```

### Deployment
```bash
# Deploy to OpenShift
make install NAMESPACE=your-namespace

# Deploy with alerting
make install-with-alerts NAMESPACE=your-namespace

# Deploy with specific LLM model
make install NAMESPACE=your-namespace LLM=llama-3-2-3b-instruct

# Deploy with GPU tolerations
make install NAMESPACE=your-namespace \
  LLM=llama-3-2-3b-instruct \
  LLM_TOLERATION="nvidia.com/gpu"

# Deploy with safety models
make install NAMESPACE=your-namespace \
  LLM=llama-3-2-3b-instruct \
  SAFETY=llama-guard-3-8b
```

### Management
```bash
# Check deployment status
make status NAMESPACE=your-namespace

# Uninstall
make uninstall NAMESPACE=your-namespace

# List available models
make list-models
```

## ⚙️ Configuration

### Environment Variables
- `PROMETHEUS_URL`: Thanos/Prometheus endpoint (default: http://localhost:9090)
- `LLAMA_STACK_URL`: LLM backend URL (default: http://localhost:8321/v1/openai/v1)
- `LLM_API_TOKEN`: API token for LLM service
- `MODEL_CONFIG`: JSON configuration for available models
- `THANOS_TOKEN`: Authentication token (default: reads from service account)
- `SLACK_WEBHOOK_URL`: Slack webhook for alerting notifications

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

### Available Models
```bash
# List available models for deployment
make list-models
```
Common models include:
- `llama-3-2-3b-instruct` (default)
- `llama-3-1-8b-instruct`
- `llama-3-3-70b-instruct`
- `llama-guard-3-8b` (safety model)

## 🔍 Common Development Patterns

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

## 🚀 Development Workflows

### 1. Feature Development
```bash
# 1. Set up local environment
LLM_NAMESPACE=<TARGET_NAMESPACE> make install-local

# 2. Make changes to source code

# 3. Run tests
make test

# 4. Build and test locally
make build
```

### 2. Bug Fixing
```bash
# 1. Setup local environment
LLM_NAMESPACE=<TARGET_NAMESPACE> make install-local

# 2. Activate virtual environment
uv sync --group dev
source .venv/bin/activate

# 3. Run specific test
uv run pytest -v tests/core/test_specific_feature.py

# 4. Debug with coverage
uv run pytest -v --cov=src --cov-report=term-missing
```

### 3. Deployment Testing
```bash
# 1. Build images
make build TAG=test-$(date +%s)

# 2. Deploy to test namespace
make install NAMESPACE=test-namespace

# 3. Verify deployment
make status NAMESPACE=test-namespace

# 4. Test functionality
# Access UI via OpenShift route

# 5. Cleanup
make uninstall NAMESPACE=test-namespace
```

## 📊 Monitoring & Debugging

### Setup Namespace
```bash
export LLM_NAMESPACE=<TARGET_NAMESPACE>
```

### Port Forwarding
```bash
# Manual port-forwarding (if make install-local fails)
oc port-forward svc/llama-stack 8000:8000 -n $LLM_NAMESPACE &
oc port-forward svc/llm-service 8001:8001 -n $LLM_NAMESPACE &
oc port-forward svc/thanos-query 9090:9090 -n $LLM_NAMESPACE &
```

### Logs
```bash
# View pod logs
oc logs -f deployment/metrics-api -n $LLM_NAMESPACE
oc logs -f deployment/metric-ui -n $LLM_NAMESPACE
oc logs -f deployment/metric-alerting -n $LLM_NAMESPACE
```

### Metrics
```bash

# Access Prometheus metrics
oc port-forward svc/metrics-api 8000:8000 -n $LLM_NAMESPACE
# Then visit http://localhost:8000/metrics
```

## 🛠️ Useful Makefile Targets

### Development
- `LLM_NAMESPACE=<namespace> make install-local` - Set up local development environment
- `make test` - Run unit tests with coverage
- `make clean` - Clean up local images

### Building
- `make build` - Build all container images
- `make build-metrics-api` - Build FastAPI backend
- `make build-ui` - Build Streamlit UI
- `make build-alerting` - Build alerting service

### Deployment
- `make install` - Deploy to OpenShift
- `make install-with-alerts` - Deploy with alerting
- `make status` - Check deployment status
- `make uninstall` - Remove deployment

### Configuration
- `make config` - Show current configuration
- `make list-models` - List available LLM models
- `make help` - Show all available targets

## 🔧 Troubleshooting

### Common Issues

#### Port Forwarding Fails
```bash
# Check if pods are running
oc get pods -n $LLM_NAMESPACE

# Restart port-forwarding
LLM_NAMESPACE=<TARGET_NAMESPACE> make install-local
```

#### Tests Fail
```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Reinstall dependencies
uv sync --group dev --reinstall

# Run tests with verbose output
uv run pytest -v --tb=short
```

#### Build Fails
```bash
# Check Docker/Podman is running
docker ps

# Clean and rebuild
make clean
make build
```

#### Deployment Issues
```bash
# Check namespace exists
oc get namespace $LLM_NAMESPACE

# Check Helm releases
helm list -n $LLM_NAMESPACE

# View deployment events
oc get events -n $LLM_NAMESPACE --sort-by='.lastTimestamp'
```

## 🔒 Security Considerations
- Service account tokens are read from mounted volumes
- SSL verification uses cluster CA bundle when available
- No secrets should be logged or committed to repository
- API endpoints use proper authentication and authorization

## 🔐 Credential Management

### Required Credentials
- **Quay Registry**: Username and password for container image pushing
- **OpenShift**: Server URL and authentication token
- **Hugging Face**: API token for model access

### Retrieving Credentials

#### Quay Registry Access
- **Search for**: `Appeng Quay ecosystem-appeng+aiobs kubernetes secret and token` in Bitwarden
  - **Required fields**: Username and Password
- **Purpose**: Pushing container images to Quay registry

#### OpenShift Access
- **For GitHub Actions workflows**: Run `./scripts/ocp-setup.sh -s -n <namespace>` to generate the required token
- **Manual setup**: Access your password manager and search for:
  - `openshift-ai-observability-summarizer ai-kickstart (aiobs)` for OCP server user/password
  - **Required fields**: Username and Password
- **Purpose**: Deploying to OpenShift clusters

#### Hugging Face Access
- User your personal "Hugging Face" token (_read token is sufficient_)
- **Purpose**: Accessing AI models and datasets

### Security Best Practices
- Never commit credentials to source code
- Use GitHub repository secrets for CI/CD
- Rotate credentials regularly
- Limit credential scope to minimum required permissions

## 📚 Additional Resources

- **README.md** - Comprehensive project overview and setup
- **docs/GITHUB_ACTIONS.md** - CI/CD workflow documentation
- **docs/SEMANTIC_VERSIONING.md** - Version management guidelines

## 🎯 Quick Reference

### File Locations
- **Main API**: `src/api/metrics_api.py`
- **Core Logic**: `src/core/llm_summary_service.py`
- **UI**: `src/ui/ui.py`
- **Tests**: `tests/`
- **Helm Charts**: `deploy/helm/`

### Key Commands
- **Local Dev**: `LLM_NAMESPACE=<namespace> make install-local`
- **Tests**: `uv run pytest -v`
- **Build**: `make build`
- **Deploy**: `make install NAMESPACE=ns`
- **Status**: `make status NAMESPACE=ns`

### Environment Variables
- `LLM_NAMESPACE` - Target OpenShift namespace
- `REGISTRY` - Container registry (default: quay.io)
- `VERSION` - Image version (default: 0.1.2)
- `LLM` - LLM model ID for deployment
- `PROMETHEUS_URL` - Metrics endpoint
- `LLAMA_STACK_URL` - LLM backend URL

---

**💡 Tip**: Use `make help` to see all available Makefile targets and their descriptions.
