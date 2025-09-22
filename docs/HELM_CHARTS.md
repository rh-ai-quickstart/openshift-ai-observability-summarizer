# Helm Charts Image Management

## Overview

This directory contains Helm charts for deploying the AI Observability Summarizer. Both image repositories and versions are centralized in the Makefile using Helm's `--set` option.

## Image Management

### How It Works

1. **Repository and version defined in Makefile**: 
   - `VERSION ?= <automatically-updated>` (updated on each successful PR merge to `dev`/`main`)
   - `METRICS_API_IMAGE = $(REGISTRY)/$(ORG)/$(IMAGE_PREFIX)-metrics-api`
   - `METRICS_UI_IMAGE = $(REGISTRY)/$(ORG)/$(IMAGE_PREFIX)-metrics-ui`
   - `METRICS_ALERTING_IMAGE = $(REGISTRY)/$(ORG)/$(IMAGE_PREFIX)-metrics-alerting`
   - `MCP_SERVER_IMAGE = $(REGISTRY)/$(ORG)/$(IMAGE_PREFIX)-mcp-server`

   **Note**: The observability charts (MinIO, Tempo, OTEL Collector) and RAG charts use external images and are not automatically updated by the CI/CD pipeline. Only the application charts (metrics-api, ui, mcp-server, alerting) are automatically versioned.

2. **Helm commands use `--set` for both repository and tag**:
   - `--set image.repository=$(METRICS_API_IMAGE)`
   - `--set image.tag=$(VERSION)`

3. **Values override defaults**: Helm automatically overrides values.yaml defaults
4. **No file generation needed**: Direct helm command execution

### Automated Version Management

The `VERSION` variable in the Makefile is **automatically updated** by the GitHub Actions CI/CD pipeline on every successful PR merge to `dev` or `main` branches using semantic versioning.

**Manual Override**: You can still override the version for local development:
```bash
VERSION=1.2.3 make install NAMESPACE=my-namespace
```

📖 **[GitHub Actions Documentation](GITHUB_ACTIONS.md)** - Complete details about automated version management, semantic versioning rules, and CI/CD workflows.

## Usage

### Deploy with Default Version
```bash
make install NAMESPACE=my-namespace
```

### Deploy with Custom Version
```bash
VERSION=1.0.0 make install NAMESPACE=my-namespace
```

### Configure UI Log Level

The UI chart supports configuring the Python log level via `env.PYTHON_LOG_LEVEL` (DEBUG, INFO, WARNING, ERROR). This is passed to the container as the `PYTHON_LOG_LEVEL` environment variable and picked up by the UI to initialize structured logging.

Example:
```bash
helm upgrade --install aiobs-ui deploy/helm/ui \
  --namespace my-namespace \
  --create-namespace \
  --set env.PYTHON_LOG_LEVEL=DEBUG
```

Notes:
- You can also set the default in `deploy/helm/ui/values.yaml` under `env.PYTHON_LOG_LEVEL`.

## File Structure

```
deploy/helm/
├── alerting/
│   ├── Chart.yaml
│   └── values.yaml            # Default values (edit this)
├── mcp-server/
│   ├── Chart.yaml
│   └── values.yaml            # Default values (edit this)
├── metrics-api/
│   ├── Chart.yaml
│   └── values.yaml            # Default values (edit this)
├── ui/
│   ├── Chart.yaml
│   └── values.yaml            # Default values (edit this)
├── rag/
│   ├── Chart.yaml
│   └── values.yaml            # RAG components (llama-stack, llm-service)
├── minio/
│   ├── Chart.yaml
│   └── values.yaml            # MinIO object storage for traces
├── observability/
│   ├── tempo/
│   │   ├── Chart.yaml
│   │   └── values.yaml        # TempoStack for trace storage
│   └── otel-collector/
│       ├── Chart.yaml
│       └── values.yaml        # OpenTelemetry Collector
```

## Important Notes

- **Edit `values.yaml`** files directly to change default values
- **Version changes** should be made in the Makefile `VERSION` variable
- **Helm `--set`** automatically overrides values.yaml defaults
- **No template system** - simple and straightforward approach

## How Helm Override Works

```bash
# Helm command with --set
helm upgrade --install my-release ./chart \
  --set image.tag=1.0.0

# This overrides any image.tag value in values.yaml
# If values.yaml has image.tag: 0.1.2, it becomes 1.0.0
```

## Observability Charts

The observability stack includes three main Helm charts:

### **MinIO Chart** (`deploy/helm/minio/`)
- **Purpose**: S3-compatible object storage for trace data persistence
- **Namespace**: `observability-hub` (hardcoded)
- **Dependencies**: Uses external MinIO chart from `https://rh-ai-quickstart.github.io/ai-architecture-charts`
- **Features**: StatefulSet deployment with dynamic multi-bucket creation (tempo, loki)

### **Tempo Chart** (`deploy/helm/observability/tempo/`)
- **Purpose**: Distributed tracing backend for storing and querying traces
- **Namespace**: `observability-hub` (hardcoded)
- **Dependencies**: Uses TempoStack operator for deployment
- **Features**: Multitenant trace storage with OpenShift integration

### **OpenTelemetry Collector Chart** (`deploy/helm/observability/otel-collector/`)
- **Purpose**: Collects, processes, and forwards traces to Tempo
- **Namespace**: `observability-hub` (hardcoded)
- **Dependencies**: Uses OpenTelemetry Collector Helm chart
- **Features**: Trace collection, processing, and forwarding

## Benefits of This Approach

- **Simpler**: No template files or generation needed
- **Standard**: Uses Helm's built-in override mechanism
- **Flexible**: Can override any value, not just version
- **Maintainable**: Less complex than template systems
- **Debugging**: Easy to see what values are being used
