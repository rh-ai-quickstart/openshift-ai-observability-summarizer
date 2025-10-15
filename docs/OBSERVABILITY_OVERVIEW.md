# Observability Stack Overview

## Overview

The OpenShift AI Observability Summarizer includes a comprehensive observability stack that
provides distributed tracing capabilities for monitoring AI applications and OpenShift workloads.

This document provides a complete overview of the observability components, their relationships, and how they work together.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Observability Stack                      │
├─────────────────────────────────────────────────────────────────┤
│  Application Namespace (e.g., test)                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   Python Apps   │  │   Python Apps   │  │   Python Apps   │  │
│  │      (ui)       │  │  (mcp-server)   │  │   (alerting)    │  │
│  │                 │  │                 │  │                 │  │
│  │  ┌───────────┐  │  │  ┌───────────┐  │  │  ┌───────────┐  │  │
│  │  │OTEL Init  │  │  │  │OTEL Init  │  │  │  │OTEL Init  │  │  │
│  │  │Container  │  │  │  │Container  │  │  │  │Container  │  │  │
│  └──┴───────────┴──┴──┴──┴───────────┴──┴──┴──┴───────────┴──┴──┘
│           │                    │                    │           │
│           └────────────────────┼────────────────────┘           │
│                                │                                │
│                                ▼                                │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              OpenTelemetry Collector                        ││
│  │  (otel-collector-collector.observability-hub.svc)           ││
│  └─────────────────────────────────────────────────────────────┘│
│                                │                                │
│                                ▼                                │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    TempoStack                               ││
│  │  (tempo-tempostack-gateway.observability-hub.svc)           ││
│  └─────────────────────────────────────────────────────────────┘│
│                                │                                │
│                                ▼                                │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                      MinIO                                  ││
│  │  (minio-observability-storage.observability-hub.svc)        ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. **MinIO Object Storage**
- **Purpose**: S3-compatible object storage for trace data and log data persistence
- **Namespace**: `observability-hub`
- **Service**: `minio-observability-storage`
- **Features**:
  - StatefulSet deployment with persistent storage
  - Dynamic multi-bucket creation (tempo, loki)
  - S3-compatible API for Tempo integration
- **Configuration**: `deploy/helm/minio/`

### 2. **TempoStack (Distributed Tracing Backend)**
- **Purpose**: Multitenant trace storage and analysis
- **Namespace**: `observability-hub`
- **Components**:
  - `tempo-tempostack-gateway`: Trace ingestion endpoint
  - `tempo-tempostack-distributor`: Trace distribution
  - `tempo-tempostack-ingester`: Trace storage
  - `tempo-tempostack-querier`: Trace querying
  - `tempo-tempostack-query-frontend`: Query optimization
  - `tempo-tempostack-compactor`: Trace compaction
- **Configuration**: `deploy/helm/observability/tempo/`

### 3. **OpenTelemetry Collector**
- **Purpose**: Collects, processes, and forwards traces to Tempo
- **Namespace**: `observability-hub`
- **Service**: `otel-collector-collector`
- **Features**:
  - Receives traces from instrumented applications
  - Processes and enriches trace data
  - Forwards traces to Tempo for storage
- **Configuration**: `deploy/helm/observability/otel-collector/`

### 4. **OpenTelemetry Auto-Instrumentation**
- **Purpose**: Automatic Python application tracing
- **Namespace**: Application namespace (e.g., `test`)
- **Components**:
  - `Instrumentation` resource: Defines instrumentation configuration
  - Init containers: Inject OpenTelemetry libraries
  - Environment variables: Configure tracing behavior
- **Configuration**: `deploy/helm/observability/otel-collector/scripts/instrumentation.yaml`

## Data Flow

1. **Application Startup**:
   - Python applications start with OpenTelemetry init containers
   - Init containers inject tracing libraries and environment variables
   - Applications begin generating traces automatically

2. **Trace Generation**:
   - Applications generate traces for HTTP requests, database calls, etc.
   - Traces include spans with timing, metadata, and context information
   - Traces are sent to OpenTelemetry Collector via OTLP protocol

3. **Trace Processing**:
   - OpenTelemetry Collector receives traces on port 4318
   - Collector processes and enriches trace data
   - Collector forwards traces to Tempo gateway

4. **Trace Storage**:
   - Tempo gateway receives traces and distributes them
   - Tempo ingester stores traces in MinIO object storage
   - Tempo compactor optimizes storage and removes old traces

5. **Trace Querying**:
   - Tempo querier provides trace search and retrieval
   - Tempo query frontend optimizes complex queries
   - Traces can be viewed in OpenShift console or Grafana

## Installation Order

The observability stack must be installed in the correct order to ensure proper functionality:

```bash
# 1. Install MinIO storage first
make install-minio

# 2. Install TempoStack and OpenTelemetry Collector
make install-observability

# 3. Setup auto-instrumentation for application namespace
make setup-tracing NAMESPACE=your-namespace

# Or install everything at once (recommended)
make install-observability-stack NAMESPACE=your-namespace
```

## Configuration

### Environment Variables

Applications receive these OpenTelemetry environment variables:

```yaml
- name: OTEL_SERVICE_NAME
  value: <service-name>  # ui, mcp-server, alerting
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: http://otel-collector-collector.observability-hub.svc.cluster.local:4318
- name: OTEL_TRACES_EXPORTER
  value: otlp
- name: OTEL_PYTHON_PLATFORM
  value: glibc
- name: PYTHONPATH
  value: /otel-auto-instrumentation-python/opentelemetry/instrumentation/auto_instrumentation:/otel-auto-instrumentation-python
```

### Service Endpoints

- **OpenTelemetry Collector**: `http://otel-collector-collector.observability-hub.svc.cluster.local:4318`
- **Tempo Gateway**: `http://tempo-tempostack-gateway.observability-hub.svc.cluster.local:3200`
- **MinIO**: `http://minio-observability-storage.observability-hub.svc.cluster.local:9000`

## Verification

### Check Installation Status

```bash
# Check all observability components
oc get pods -n observability-hub

# Check instrumentation in application namespace
oc get instrumentation -n your-namespace
oc get namespace your-namespace -o yaml | grep instrumentation

# Check application pods have init containers
oc get pod <pod-name> -n your-namespace -o yaml | grep -A 20 "initContainers:"
```

### Verify Trace Generation

```bash
# Check OpenTelemetry Collector logs
oc logs -n observability-hub deployment/otel-collector-collector --tail=20

# Look for trace processing indicators:
# - "spans": X - Shows traces being processed
# - "resource spans": 1 - Shows trace resources being created

# Check Tempo gateway logs
oc logs -n observability-hub deployment/tempo-tempostack-gateway --tail=20

# Look for successful trace ingestion:
# - status=200 - Traces successfully stored
# - status=502 - Connection issues (needs troubleshooting)
```

### View Traces

1. **OpenShift Console**:
   - Navigate to **Observe > Traces**
   - Search for traces by service name or time range

2. **Grafana** (if available):
   - Configure Tempo as data source
   - Use trace ID or service name to search traces

## Updating Shared Observability Infrastructure

The observability infrastructure (OpenTelemetry collector, Tempo, MinIO) is deployed 
to the `observability-hub` namespace and shared by all application namespaces 
(main, dev, etc.).

### Important Notes:
- Deploying to application namespaces (main, dev) does NOT update observability-hub
- The Makefile skips reinstalling observability components if already present
- Manual patches to CRs will be overwritten by Helm operations
- Always update via Helm to ensure changes persist

### To Update Observability Components:
1. Make changes to Helm charts in `deploy/helm/observability/`
2. Run: `helm upgrade <component> ./deploy/helm/observability/<component> --namespace observability-hub`
3. Verify the update was successful

### Force Updating Observability Infrastructure:
```bash
# Force upgrade all observability components
make upgrade-observability

# Check for configuration drift
make check-observability-drift
```

### Configuration Drift Detection

The `check-observability-drift` target provides detailed analysis of observability components:

- **OpenTelemetry Collector**: Checks for deprecated configuration fields that cause crashes with operator 0.135.0+
- **TempoStack**: Verifies installation and revision status
- **OpenTelemetry Operator**: Validates compatibility and configuration format

Example output:
```
→ Checking for configuration drift in observability-hub namespace

  🔍 Checking OpenTelemetry Collector...
  📊 OpenTelemetry Collector: Revision observability-hub
  ✅ OpenTelemetry Collector: Configuration is up-to-date

  🔍 Checking TempoStack...
  📊 TempoStack: Revision observability-hub
  ✅ TempoStack: Configuration is up-to-date

  🔍 Checking OpenTelemetry operator compatibility...
  📊 OpenTelemetry Operator: 0.135.0-1
  ✅ OpenTelemetry Operator: Configuration is compatible
     → No deprecated 'address' field found in telemetry config

✅ No configuration drift detected
💡 All observability components are up-to-date
```

## Troubleshooting

### Common Issues

1. **No traces appearing**:
   - Check if instrumentation is applied: `oc get instrumentation -n your-namespace`
   - Verify namespace annotation: `oc get namespace your-namespace -o yaml | grep instrumentation`
   - Restart application deployments to pick up instrumentation

2. **Tempo gateway 502 errors**:
   - Check OpenTelemetry Collector is running: `oc get pods -n observability-hub | grep otel-collector`
   - Verify service connectivity: `oc get svc -n observability-hub | grep otel-collector`
   - Check Tempo gateway configuration

3. **Applications not instrumented**:
   - Ensure instrumentation is applied before application deployment
   - Check init containers are present in pod spec
   - Verify environment variables are set correctly

### Debug Commands

```bash
# Check all observability components
oc get all -n observability-hub

# Check instrumentation status
oc get instrumentation -n your-namespace

# Check application pod configuration
oc get pod <pod-name> -n your-namespace -o yaml | grep -A 10 -B 5 "OTEL_"

# Check OpenTelemetry Collector logs
oc logs -n observability-hub deployment/otel-collector-collector --tail=50

# Check Tempo components
oc get pods -n observability-hub | grep tempo
oc logs -n observability-hub deployment/tempo-tempostack-gateway --tail=20
```

## Makefile Targets

### Complete Stack Management
- `make install-observability-stack NAMESPACE=ns` - Install complete stack
- `make uninstall-observability-stack NAMESPACE=ns` - Uninstall complete stack

### Individual Component Management
- `make install-minio` - Install MinIO storage only
- `make uninstall-minio` - Uninstall MinIO storage only
- `make install-observability` - Install TempoStack + OTEL only
- `make uninstall-observability` - Uninstall TempoStack + OTEL only
- `make setup-tracing NAMESPACE=ns` - Enable auto-instrumentation
- `make remove-tracing NAMESPACE=ns` - Disable auto-instrumentation

### Observability Infrastructure Management
- `make upgrade-observability` - Force upgrade observability components (bypasses "already installed" checks)
- `make check-observability-drift` - Check for configuration drift and compatibility issues

### Shell Scripts
- `scripts/check-observability-drift.sh` - Standalone script for drift detection (can be run independently)

## Benefits

1. **Automatic Instrumentation**: No code changes required for basic tracing
2. **Comprehensive Coverage**: Traces all Python applications in the namespace
3. **Centralized Storage**: All traces stored in MinIO with Tempo for querying
4. **OpenShift Integration**: Native integration with OpenShift console
5. **Scalable Architecture**: Supports multiple namespaces and applications
6. **Easy Management**: Simple Makefile targets for installation and management

## References

- [OpenTelemetry Operator Documentation](https://github.com/open-telemetry/opentelemetry-operator)
- [Tempo Documentation](https://grafana.com/docs/tempo/)
- [OpenTelemetry Python Auto-instrumentation](https://opentelemetry.io/docs/instrumentation/python/automatic/)
