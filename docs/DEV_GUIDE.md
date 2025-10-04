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
│   ├── mcp_server/        # Model Context Protocol server
│   │   ├── api.py         # MCP API implementation
│   │   ├── main.py        # HTTP server entrypoint
│   │   ├── stdio_server.py # STDIO server for AI assistants
│   │   ├── tools/         # MCP tools (observability_tools.py)
│   │   └── integrations/  # AI assistant integration configs
│   └── alerting/          # Alerting service
│       └── alert_receiver.py # Alert handling
├── deploy/helm/           # Helm charts for deployment
│   ├── mcp-server/        # MCP server Helm chart
│   ├── ui/                # UI Helm chart
│   └── rag/               # RAG components (llama-stack, llm-service)
├── tests/                 # Test suite
│   ├── mcp/               # MCP server tests
│   ├── core/              # Core logic tests
│   └── alerting/          # Alerting tests
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

### macOS: WeasyPrint for local PDF reports (optional)
WeasyPrint is used for generating PDF reports. Containers and CI handle dependencies automatically via `uv`, but for local macOS development you may need a system install:

```bash
brew install weasyprint
weasyprint --version

# If WeasyPrint cannot find libraries at runtime, set:
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_FALLBACK_LIBRARY_PATH
```


### Local Development
```bash
# Set up port-forwarding to cluster services (default LLM: llama-3.2-3b-instruct)
./scripts/local-dev.sh -n <DEFAULT_NAMESPACE>

# With specific LLM model (optional)
./scripts/local-dev.sh -n <DEFAULT_NAMESPACE> -l llama-3.1-8b-instruct

# If model is in different namespace:
./scripts/local-dev.sh -n <DEFAULT_NAMESPACE> -m <MODEL_NAMESPACE>

# Use cluster config instead of generating new one:
./scripts/local-dev.sh -n <DEFAULT_NAMESPACE> -c cluster

# This script sets up:
# - Virtual environment activation (.venv)
# - MODEL_CONFIG generation (merges base models + specified LLM)
# - Port-forwarding to Llamastack (localhost:8321)
# - Port-forwarding to Model service (localhost:8080)
# - Port-forwarding to Thanos (localhost:9090)
# - MCP Server (localhost:8085)
# - Streamlit UI (localhost:8501)

# Examples:
./scripts/local-dev.sh -n default-ns                      # Default LLM
./scripts/local-dev.sh -n default-ns -l llama-3.1-8b-instruct  # Custom LLM
./scripts/local-dev.sh -n default-ns -m model-ns          # Model in different namespace
./scripts/local-dev.sh -n default-ns -c cluster           # Use cluster config
```

**Note**: The script automatically:
- Activates Python virtual environment if `.venv` exists
- Generates MODEL_CONFIG by merging base external models (OpenAI, Google, Anthropic) with your specified LLM
- Uses service-based port forwarding for better reliability
- Supports separate namespaces for different services

## 🏗️ Architecture & Data Flow

### Core Components
1. **MCP Server** (`src/mcp_server/`): Model Context Protocol server for metrics analysis, report generation, and AI assistant integration
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
make build-ui            # Streamlit UI
make build-alerting      # Alerting service
make build-mcp-server    # MCP server

# Build with custom tag
make build TAG=v1.0.0
```

### Deployment
```bash
# Deploy to OpenShift (deploys default model)
make install NAMESPACE=your-namespace

# Deploy with alerting (deploys default model)
make install-with-alerts NAMESPACE=your-namespace

# Deploy with specific LLM model
make install NAMESPACE=your-namespace LLM=llama-3-2-1b-instruct

# Deploy with GPU tolerations (deploys default model)
make install NAMESPACE=your-namespace LLM_TOLERATION="nvidia.com/gpu"

# Deploy with safety models (deploys default model)
make install NAMESPACE=your-namespace SAFETY=llama-guard-3-8b

# Use existing model (specify LLM_URL as model service URL)
# Note: When LLM_URL is provided, HF_TOKEN will not be prompted since no new model deployment is needed

# URL with port (no processing applied):
make install NAMESPACE=your-namespace \
  LLM_URL=http://llama-3-2-3b-instruct-predictor.dev.svc.cluster.local:8080/v1

# URL without port (automatically adds :8080/v1):
make install NAMESPACE=your-namespace \
  LLM_URL=http://llama-3-2-3b-instruct-predictor.dev.svc.cluster.local

# Deploy individual components
make install-mcp-server NAMESPACE=your-namespace    # MCP server only
make install-metric-ui NAMESPACE=your-namespace     # UI only
```

### Observability Stack Management

The project includes a comprehensive observability stack with flexible deployment options:

#### **Complete Observability Stack**
```bash
# Install complete observability stack (MinIO + TempoStack + OTEL + tracing)
# Note: NAMESPACE is required for tracing setup
make install-observability-stack NAMESPACE=your-namespace

# Uninstall complete observability stack
# Note: NAMESPACE is required for tracing removal
make uninstall-observability-stack NAMESPACE=your-namespace
```

#### **Individual Observability Components**
```bash
# Install individual components
make install-minio                                           # MinIO storage only (uses observability-hub namespace)
make install-observability                                   # TempoStack + OTEL only (uses observability-hub namespace)
make setup-tracing NAMESPACE=your-namespace                 # Auto-instrumentation only (requires NAMESPACE)

# Uninstall individual components
make uninstall-minio                                         # MinIO storage only (uses observability-hub namespace)
make uninstall-observability                                 # TempoStack + OTEL only (uses observability-hub namespace)
make remove-tracing NAMESPACE=your-namespace                 # Auto-instrumentation only (requires NAMESPACE)
```

#### **NAMESPACE Requirements**
- **`install-observability-stack` / `uninstall-observability-stack`**: Require NAMESPACE for tracing components
- **`install-minio` / `uninstall-minio`**: Use hardcoded `observability-hub` namespace
- **`install-observability` / `uninstall-observability`**: Use hardcoded `observability-hub` namespace  
- **`setup-tracing` / `remove-tracing`**: Require NAMESPACE parameter

#### **MinIO Chart Simplification**
The MinIO chart has been simplified to use a single template file (`minio-simple.yaml`) that:
- Deploys MinIO as a StatefulSet with built-in bucket creation
- Uses MinIO's native `mc` client for bucket and user management
- Eliminates the need for separate initialization jobs
- Reduces complexity from 7 template files to 2 (including helpers)
- Provides more reliable and maintainable MinIO deployment

#### **Observability Stack Features**
- **MinIO**: S3-compatible object storage for trace data and log data persistence
- **TempoStack**: Multitenant trace storage and analysis with OpenShift integration
- **OpenTelemetry Collector**: Distributed tracing collection and forwarding
- **Auto-instrumentation**: Automatic Python application tracing setup
- **Dependency Management**: Proper installation/uninstallation order with dependency chains

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
- `LLM_URL`: Use existing model URL (skips HF_TOKEN prompt and model deployment)
- `HF_TOKEN`: Hugging Face token (auto-prompted only when LLM_URL is not set)
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

### Model Configuration Generation

**Location**: `scripts/generate-model-config.sh`

**Purpose**: Single source of truth for dynamically generating model configurations. Used by both Makefile (OpenShift deployment) and local-dev.sh (local development).

**Architecture**:
```
generate-model-config.sh
├── Used by Makefile (with --helm-format flag)
│   └── Generates: JSON + Helm YAML values file
└── Used by local-dev.sh (without flag)
    └── Generates: JSON only
```

**How it works**:
1. **Template Substitution**: Reads `deploy/helm/default-model.json.template` and substitutes:
   - `$MODEL_ID` → Full model path (e.g., `meta-llama/Llama-3.2-3B-Instruct`)
   - `$MODEL_NAME` → Service name (e.g., `llama-3-2-3b-instruct`)

2. **JSON Merging**: Merges the LLM-specific config with base external models from `deploy/helm/model-config.json`:
   ```bash
   jq -s '.[0] * .[1]' new_model_config.json model-config.json > final_config.json
   ```

3. **Export**: Sets `MODEL_CONFIG` environment variable for use by services

**Parameters**:
- **LLM model name** (optional): Model identifier (default: `llama-3-2-3b-instruct`)
- **`--helm-format` flag** (optional): Generate Helm values YAML file in addition to JSON

**Output Files** (in `/tmp`):
- `gen_model_config-list_models_output.txt` - Available models from Helm chart
- `gen_model_config-final_config.json` - Merged JSON configuration
- `gen_model_config-for_helm.yaml` - Helm values format (only with `--helm-format`)

**Usage Examples**:
```bash
# Direct usage (for debugging/testing)
source scripts/generate-model-config.sh
generate_model_config                                    # Use default model
generate_model_config "llama-3.1-8b-instruct"           # Specific model, JSON only
generate_model_config "llama-3.2-3b-instruct" --helm-format  # JSON + Helm YAML

# Automatic usage via Makefile
make install NAMESPACE=your-ns LLM=llama-3.1-8b-instruct
# → Calls: generate_model_config "llama-3.1-8b-instruct" --helm-format

# Automatic usage via local-dev.sh
./scripts/local-dev.sh -n your-ns -l llama-3.1-8b-instruct
# → Calls: generate_model_config "llama-3.1-8b-instruct" (no --helm-format)
```

**Example: Config Merging Process**:
```bash
# 1. Template (default-model.json.template)
{
  "$MODEL_ID": {
    "external": false,
    "requiresApiKey": false,
    "serviceName": "$MODEL_NAME"
  }
}

# 2. After substitution (new_model_config.json)
{
  "meta-llama/Llama-3.2-3B-Instruct": {
    "external": false,
    "requiresApiKey": false,
    "serviceName": "llama-3-2-3b-instruct"
  }
}

# 3. Base config (model-config.json)
{
  "openai/gpt-4o-mini": { ... },
  "google/gemini-2.5-flash": { ... },
  "anthropic/claude-sonnet-4-20250514": { ... }
}

# 4. Final merged config (final_config.json)
{
  "meta-llama/Llama-3.2-3B-Instruct": { ... },  # ← LLM-specific
  "openai/gpt-4o-mini": { ... },                 # ← Base external models
  "google/gemini-2.5-flash": { ... },
  "anthropic/claude-sonnet-4-20250514": { ... }
}
```

## 🔍 Common Development Patterns

### Adding New Metrics
1. Update metric discovery functions in `src/core/metrics.py`
2. Add PromQL queries for the new metrics
3. Update UI components to display the metrics
4. Add corresponding tests

### Adding New MCP Tools
1. Define request/response models in `src/core/models.py`
2. Implement business logic in appropriate `src/core/` module
3. Add MCP tool in `src/mcp_server/tools/`
4. Add corresponding tests

### Error Handling
- API endpoints use HTTPException for user-facing errors
- Internal errors are logged with stack traces
- LLM API key errors return specific user-friendly messages

## 🚀 Development Workflows

### 1. Feature Development
```bash
# 1. Set up local environment
./scripts/local-dev.sh -n <DEFAULT_NAMESPACE>

# 2. Make changes to source code

# 3. Run tests
make test

# 4. Build and test locally
make build
```

### 2. Bug Fixing
```bash
# 1. Setup local environment
./scripts/local-dev.sh -n <DEFAULT_NAMESPACE>

# 2. Activate virtual environment (for testing)
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
# Use the script with appropriate namespace parameters
./scripts/local-dev.sh -n <DEFAULT_NAMESPACE>
# or with separate model namespace:
./scripts/local-dev.sh -n <DEFAULT_NAMESPACE> -m <MODEL_NAMESPACE>
```

### Port Forwarding
```bash
# Manual port-forwarding (if script fails)

# Thanos querier (pod-based, use head -1 since multiple pods may exist)
THANOS_POD=$(oc get pods -n openshift-monitoring -o name -l 'app.kubernetes.io/component=query-layer,app.kubernetes.io/instance=thanos-querier' | head -1)
oc port-forward $THANOS_POD 9090:9090 -n openshift-monitoring &

# LlamaStack (service-based)
LLAMASTACK_SERVICE=$(oc get services -n <DEFAULT_NAMESPACE> -o name -l 'app.kubernetes.io/instance=rag, app.kubernetes.io/name=llamastack')
oc port-forward $LLAMASTACK_SERVICE 8321:8321 -n <DEFAULT_NAMESPACE> &

# Llama Model service (service-based)
LLAMA_MODEL_SERVICE=$(oc get services -n <MODEL_NAMESPACE> -o name -l 'app=isvc.llama-3-2-3b-instruct-predictor')
oc port-forward $LLAMA_MODEL_SERVICE 8080:8080 -n <MODEL_NAMESPACE> &

# Tempo gateway (service-based)
TEMPO_SERVICE=$(oc get services -n observability-hub -o name -l 'app.kubernetes.io/name=tempo,app.kubernetes.io/component=gateway')
oc port-forward $TEMPO_SERVICE 8082:8080 -n observability-hub &
```

**Note**:
- Thanos uses pod-based forwarding with `head -1` because multiple thanos-querier pods may exist
- Other services use service-based forwarding for better reliability
- Replace `<DEFAULT_NAMESPACE>` and `<MODEL_NAMESPACE>` with your actual namespaces

### Logs
```bash
# View pod logs (replace with your actual namespace)
oc logs -f deployment/metric-ui -n <DEFAULT_NAMESPACE>
oc logs -f deployment/mcp-server -n <DEFAULT_NAMESPACE>
oc logs -f deployment/metric-alerting -n <DEFAULT_NAMESPACE>
```

### Metrics
```bash
# Access MCP server health/metrics
oc port-forward svc/mcp-server 8085:8085 -n <DEFAULT_NAMESPACE>
# Then visit http://localhost:8085/health
```

## 🛠️ Useful Makefile Targets

### Development
- `./scripts/local-dev.sh -n <namespace>` - Set up local development environment
- `make test` - Run unit tests with coverage
- `make clean` - Clean up local images

### Building
- `make build` - Build all container images
- `make build-ui` - Build Streamlit UI
- `make build-alerting` - Build alerting service
- `make build-mcp-server` - Build MCP server

### Deployment
- `make install` - Deploy to OpenShift
- `make install-with-alerts` - Deploy with alerting
- `make install-mcp-server` - Deploy MCP server only
- `make install-metric-ui` - Deploy UI only
- `make status` - Check deployment status
- `make uninstall` - Remove deployment

### Observability Stack
- `make install-observability-stack` - Install complete observability stack
- `make uninstall-observability-stack` - Uninstall complete observability stack
- `make install-minio` - Install MinIO storage only
- `make uninstall-minio` - Uninstall MinIO storage only
- `make install-observability` - Install TempoStack + OTEL only
- `make uninstall-observability` - Uninstall TempoStack + OTEL only
- `make setup-tracing` - Enable auto-instrumentation
- `make remove-tracing` - Disable auto-instrumentation

### Configuration
- `make config` - Show current configuration
- `make list-models` - List available LLM models
- `make help` - Show all available targets

## 🔧 Troubleshooting

### Common Issues

#### Port Forwarding Fails
```bash
# Check if pods are running
oc get pods -n <DEFAULT_NAMESPACE>

# Restart port-forwarding
./scripts/local-dev.sh -n <DEFAULT_NAMESPACE>
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
oc get namespace <DEFAULT_NAMESPACE>

# Check Helm releases
helm list -n <DEFAULT_NAMESPACE>

# View deployment events
oc get events -n <DEFAULT_NAMESPACE> --sort-by='.lastTimestamp'
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
- **MCP Server**: `src/mcp_server/main.py`
- **Core Logic**: `src/core/llm_summary_service.py`
- **UI**: `src/ui/ui.py`
- **Tests**: `tests/`
- **Helm Charts**: `deploy/helm/`

### Key Commands
- **Local Dev**: `./scripts/local-dev.sh -n <namespace>`
- **Tests**: `uv run pytest -v`
- **Build**: `make build`
- **Deploy**: `make install NAMESPACE=ns`
- **Status**: `make status NAMESPACE=ns`

### Environment Variables
- `REGISTRY` - Container registry (default: quay.io)
- `VERSION` - Image version (default: 0.1.2)
- `LLM` - LLM model ID for deployment
- `PROMETHEUS_URL` - Metrics endpoint
- `LLAMA_STACK_URL` - LLM backend URL

---

**💡 Tip**: Use `make help` to see all available Makefile targets and their descriptions.
