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

## Operator Requirements

The observability stack depends on three OpenShift operators that must be installed before deploying the stack. These operators are cluster-scoped and managed by the OpenShift Operator Lifecycle Manager (OLM).

### 1. **Cluster Observability Operator**
- **Purpose**: Provides core observability capabilities and monitoring primitives
- **Operator Name**: `cluster-observability-operator`
- **Namespace**: `openshift-cluster-observability-operator`
- **CRDs Provided**:
  - `monitoring.rhobs/*`: Monitoring configurations
  - `perses.dev/*`: Perses dashboard definitions
  - `observability.openshift.io/*`: UIPlugin for OpenShift Console integration
- **Channel**: `stable`
- **Source**: `redhat-operators`
- **Configuration**: `scripts/operators/cluster-observability.yaml`

### 2. **Red Hat build of OpenTelemetry Operator**
- **Purpose**: Manages OpenTelemetry Collector and auto-instrumentation resources
- **Operator Name**: `opentelemetry-product`
- **Namespace**: `openshift-opentelemetry-operator`
- **CRDs Provided**:
  - `opentelemetrycollectors.opentelemetry.io`: Collector deployments
  - `instrumentations.opentelemetry.io`: Auto-instrumentation configs
- **Channel**: `stable`
- **Source**: `redhat-operators`
- **Version**: v0.135.0+ (supports new configuration format)
- **Configuration**: `scripts/operators/opentelemetry.yaml`

### 3. **Tempo Operator**
- **Purpose**: Manages TempoStack distributed tracing backend
- **Operator Name**: `tempo-product`
- **Namespace**: `openshift-tempo-operator`
- **CRDs Provided**:
  - `tempostacks.tempo.grafana.com`: Tempo deployments
  - `tempomonolithics.tempo.grafana.com`: Single-instance Tempo
- **Channel**: `stable`
- **Source**: `redhat-operators`
- **Version**: v0.18.0+ (supports OTLP endpoints, Jaeger Query API removed)
- **Configuration**: `scripts/operators/tempo.yaml`

### Operator Installation Workflow

The operator installation process includes robust validation to ensure operators are fully ready before proceeding:

1. **Subscription Creation**: Operator subscription is created in the target namespace
2. **CSV Wait**: Waits up to 10 minutes for ClusterServiceVersion (CSV) to reach "Succeeded" phase
3. **CRD Validation**: Waits up to 5 minutes for all expected CRDs to be created
4. **Readiness Confirmation**: Only proceeds when operators are fully functional

This three-phase validation prevents race conditions where resources are created before CRDs exist.

### Manual Operator Management

```bash
# Install all three operators (automatically installed with 'make install')
make install-operators

# Check operator status
make check-operators

# Uninstall individual operators
make uninstall-cluster-observability-operator
make uninstall-opentelemetry-operator
make uninstall-tempo-operator

# Uninstall all operators (requires confirmation)
make uninstall-operators UNINSTALL_OPERATORS=true
```

**Important Notes**:
- Operators are cluster-scoped and shared across all namespaces
- Uninstalling operators will delete all associated CRDs and custom resources
- The `UNINSTALL_OPERATORS=true` flag is required to prevent accidental removal
- Operators are automatically installed during `make install`
- Operators are NOT automatically removed during `make uninstall` (requires explicit flag)

## Components

### 1. **MinIO Object Storage**
- **Purpose**: S3-compatible object storage for trace data and log data persistence
- **Namespace**: `observability-hub`
- **Service**: `minio-observability-storage`
- **Features**:
  - StatefulSet deployment with persistent storage
  - Dynamic multi-bucket creation (tempo, loki)
  - S3-compatible API for Tempo integration
  - Automatic security context assignment (OpenShift SCC compliant)
- **Configuration**: `deploy/helm/minio/`

### 2. **TempoStack (Distributed Tracing Backend)**
- **Purpose**: Multitenant trace storage and analysis (managed by Tempo Operator)
- **Namespace**: `observability-hub`
- **Components**:
  - `tempo-tempostack-gateway`: Query API endpoint
  - `tempo-tempostack-distributor`: Trace distribution and OTLP ingestion (port 4318)
  - `tempo-tempostack-ingester`: Trace storage
  - `tempo-tempostack-querier`: Trace querying
  - `tempo-tempostack-query-frontend`: Query optimization
  - `tempo-tempostack-compactor`: Trace compaction
- **Configuration**: `deploy/helm/observability/tempo/`
- **Version Compatibility**: v0.18.0+ (OTLP native, Jaeger Query API removed)

### 3. **OpenTelemetry Collector**
- **Purpose**: Collects, processes, and forwards traces to Tempo (managed by OpenTelemetry Operator)
- **Namespace**: `observability-hub`
- **Service**: `otel-collector-collector`
- **Features**:
  - Receives traces from instrumented applications
  - Processes and enriches trace data
  - Forwards traces to Tempo distributor via OTLP/HTTP on port 4318
  - mTLS encryption using OpenShift service CA
- **Configuration**: `deploy/helm/observability/otel-collector/`

### 4. **OpenTelemetry Auto-Instrumentation**
- **Purpose**: Automatic Python application tracing (managed by OpenTelemetry Operator)
- **Namespace**: Application namespace (e.g., `test`)
- **Components**:
  - `Instrumentation` resource: Defines instrumentation configuration
  - Init containers: Inject OpenTelemetry libraries
  - Environment variables: Configure tracing behavior
- **Configuration**: `deploy/helm/observability/otel-collector/scripts/instrumentation.yaml`

### 5. **OpenShift Console UIPlugin**
- **Purpose**: Enables "Observe → Traces" menu in OpenShift Console (requires Cluster Observability Operator)
- **Namespace**: `observability-hub`
- **Resource Type**: `UIPlugin` (observability.openshift.io/v1alpha1)
- **Features**:
  - Native OpenShift Console integration
  - Trace search and visualization
  - 30-second query timeout
- **Configuration**: `deploy/helm/observability/tempo/templates/uiplugin.yaml`

## Data Flow

### 1. **Operator Setup** (One-time, cluster-wide)
   - Install Cluster Observability Operator (provides UIPlugin CRD)
   - Install OpenTelemetry Operator (provides Collector and Instrumentation CRDs)
   - Install Tempo Operator (provides TempoStack CRD)
   - Wait for CSVs to reach "Succeeded" phase
   - Validate all CRDs are created

### 2. **Infrastructure Deployment** (Per observability-hub namespace)
   - Deploy MinIO for persistent trace storage
   - Deploy TempoStack (creates distributor, ingester, querier, etc.)
   - Deploy OpenTelemetry Collector (configured to forward to Tempo distributor)
   - Deploy UIPlugin resource (enables "Observe → Traces" menu)

### 3. **Application Instrumentation** (Per application namespace)
   - Apply Instrumentation resource to application namespace
   - Annotate namespace with `instrumentation.opentelemetry.io/inject-python=true`
   - Application pods start with OpenTelemetry init containers
   - Init containers inject tracing libraries and environment variables
   - Applications begin generating traces automatically

### 4. **Trace Generation** (Runtime)
   - Applications generate traces for HTTP requests, database calls, etc.
   - Traces include spans with timing, metadata, and context information
   - Traces are sent to OpenTelemetry Collector via OTLP/HTTP protocol

### 5. **Trace Processing** (Runtime)
   - OpenTelemetry Collector receives traces on port 4318
   - Collector processes and enriches trace data
   - Collector forwards traces to Tempo distributor via OTLP/HTTP with mTLS

### 6. **Trace Storage** (Runtime)
   - Tempo distributor receives traces and distributes them
   - Tempo ingester stores traces in MinIO object storage
   - Tempo compactor optimizes storage and removes old traces

### 7. **Trace Querying** (User-initiated)
   - Tempo querier provides trace search and retrieval
   - Tempo query frontend optimizes complex queries
   - Traces viewed via OpenShift Console ("Observe → Traces") or Grafana

## Installation Order

The observability stack must be installed in the correct order to ensure proper functionality:

```bash
# 1. Install required operators (cluster-scoped, one-time setup)
make install-operators

# 2. Install MinIO storage backend
make install-minio

# 3. Install TempoStack and OpenTelemetry Collector
make install-observability

# 4. Setup auto-instrumentation for application namespace
make setup-tracing NAMESPACE=your-namespace

# 5. Enable OpenShift Console "Observe → Traces" menu
make enable-tracing-ui

# Or install everything at once (recommended)
# This includes operators, MinIO, observability components, and tracing setup
make install NAMESPACE=your-namespace LLM=llama-3-2-3b-instruct
```

**Notes**:
- `make install` automatically includes `install-operators` and `install-observability-stack`
- Operators only need to be installed once per cluster
- MinIO, TempoStack, and OpenTelemetry Collector are shared across application namespaces
- Each application namespace needs its own `setup-tracing` configuration

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
- **Tempo Distributor** (OTLP ingestion): `https://tempo-tempostack-distributor.observability-hub.svc.cluster.local:4318`
- **Tempo Gateway** (Query API): `http://tempo-tempostack-gateway.observability-hub.svc.cluster.local:3200`
- **MinIO**: `http://minio-observability-storage.observability-hub.svc.cluster.local:9000`

**Important**: Since Tempo Operator v0.18.0, the Jaeger Query API has been removed. Traces must be ingested via OTLP endpoints only. The OpenTelemetry Collector forwards traces directly to the Tempo distributor endpoint using OTLP/HTTP with mTLS encryption.

## Verification

### Check Operator Installation

```bash
# Check all operator status
make check-operators

# Check individual operator CSVs
oc get csv -n openshift-cluster-observability-operator
oc get csv -n openshift-opentelemetry-operator
oc get csv -n openshift-tempo-operator

# Verify CRDs are installed
oc get crd | grep -E "tempo.grafana.com|opentelemetry.io|observability.openshift.io"
```

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

## Tempo Operator v0.18.0 Upgrade

The observability stack has been updated to use Tempo Operator v0.18.0, which includes breaking changes:

### Breaking Changes
- **Jaeger Query API Removed**: Tempo no longer supports Jaeger Query endpoints
- **OTLP Only**: All trace ingestion must use native OTLP endpoints
- **Endpoint Change**: OpenTelemetry Collector now forwards to Tempo distributor (port 4318) instead of gateway

### Migration Impact
- **OpenTelemetry Collector Configuration**: Updated to use `tempo-tempostack-distributor:4318` endpoint
- **mTLS Encryption**: All trace traffic now uses mTLS with OpenShift service CA certificates
- **UIPlugin Restored**: OpenShift Console "Observe → Traces" menu functionality restored
- **No Application Changes**: Applications continue using OTLP without modification

### Verification After Upgrade
```bash
# Check Tempo distributor is receiving traces
oc logs -n observability-hub deployment/tempo-tempostack-distributor --tail=20

# Verify OTel Collector is forwarding to distributor
oc logs -n observability-hub deployment/otel-collector-collector --tail=20 | grep distributor

# Check for successful trace ingestion (status=200)
oc logs -n observability-hub deployment/tempo-tempostack-distributor | grep "POST /otlp/v1/traces"
```

## Updating Shared Observability Infrastructure

The observability infrastructure (OpenTelemetry collector, Tempo, MinIO) is deployed
to the `observability-hub` namespace and shared by all application namespaces
(main, dev, etc.).

### Important Notes:
- Deploying to application namespaces (main, dev) does NOT update observability-hub
- The Makefile skips reinstalling observability components if already present
- Manual patches to CRs will be overwritten by Helm operations
- Always update via Helm to ensure changes persist
- Operators are cluster-scoped and shared across all namespaces

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

1. **Operator installation fails or hangs**:
   - Check CSV status: `oc get csv -n <operator-namespace>`
   - Look for CSV phase: "Succeeded" is expected, "Installing" or "Failed" indicates issues
   - Check operator pod logs: `oc logs -n <operator-namespace> deployment/<operator-name>`
   - Verify CRDs are created: `oc get crd | grep <crd-pattern>`

2. **"Resource mapping not found" for Instrumentation or TempoStack**:
   - This indicates operators are not fully ready
   - Wait for CSV to reach "Succeeded" phase
   - Verify CRDs exist: `oc get crd instrumentations.opentelemetry.io`
   - The installation process automatically waits for operator readiness

3. **No traces appearing**:
   - Check if instrumentation is applied: `oc get instrumentation -n your-namespace`
   - Verify namespace annotation: `oc get namespace your-namespace -o yaml | grep instrumentation`
   - Restart application deployments to pick up instrumentation
   - Check OpenTelemetry Collector logs for trace receipt

4. **Tempo distributor connection errors**:
   - Check OpenTelemetry Collector is running: `oc get pods -n observability-hub | grep otel-collector`
   - Verify Tempo distributor is available: `oc get pods -n observability-hub | grep tempo-tempostack-distributor`
   - Check service connectivity: `oc get svc -n observability-hub | grep tempo-tempostack-distributor`
   - Verify mTLS certificates are mounted correctly

5. **Applications not instrumented**:
   - Ensure OpenTelemetry Operator is installed and ready
   - Ensure instrumentation is applied before application deployment
   - Check init containers are present in pod spec
   - Verify environment variables are set correctly
   - Check for operator errors: `oc get events -n your-namespace | grep Instrumentation`

6. **"Observe → Traces" menu not appearing in OpenShift Console**:
   - Verify UIPlugin is deployed: `oc get uiplugin -n observability-hub`
   - Check Cluster Observability Operator is installed
   - Enable the console plugin: `make enable-tracing-ui`
   - Verify console plugin is enabled: `oc get console.operator.openshift.io cluster -o jsonpath='{.spec.plugins}'`

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
- `make install NAMESPACE=ns LLM=model-name` - Install complete stack (operators + observability + application)
- `make uninstall NAMESPACE=ns` - Uninstall application and namespace-scoped resources (protected uninstall)
- `make uninstall NAMESPACE=ns UNINSTALL_OBSERVABILITY=true UNINSTALL_OPERATORS=true` - Full uninstall including shared resources

### Operator Management
- `make install-operators` - Install all three operators (cluster-scoped, one-time)
- `make check-operators` - Check status of all operators
- `make install-cluster-observability-operator` - Install Cluster Observability Operator only
- `make install-opentelemetry-operator` - Install OpenTelemetry Operator only
- `make install-tempo-operator` - Install Tempo Operator only
- `make uninstall-operators UNINSTALL_OPERATORS=true` - Uninstall all operators (requires flag)
- `make uninstall-cluster-observability-operator` - Uninstall Cluster Observability Operator only
- `make uninstall-opentelemetry-operator` - Uninstall OpenTelemetry Operator only
- `make uninstall-tempo-operator` - Uninstall Tempo Operator only

### Observability Stack Management
- `make install-observability-stack NAMESPACE=ns` - Install MinIO + TempoStack + OTEL + tracing
- `make uninstall-observability-stack NAMESPACE=ns UNINSTALL_OBSERVABILITY=true` - Uninstall observability stack (requires flag)

### Individual Component Management
- `make install-minio` - Install MinIO storage only
- `make uninstall-minio` - Uninstall MinIO storage only
- `make install-observability` - Install TempoStack + OTEL only
- `make uninstall-observability` - Uninstall TempoStack + OTEL only
- `make setup-tracing NAMESPACE=ns` - Enable auto-instrumentation
- `make remove-tracing NAMESPACE=ns` - Disable auto-instrumentation
- `make enable-tracing-ui` - Enable "Observe → Traces" console menu
- `make disable-tracing-ui` - Disable "Observe → Traces" console menu

### Observability Infrastructure Management
- `make upgrade-observability` - Force upgrade observability components (bypasses "already installed" checks)
- `make check-observability-drift` - Check for configuration drift and compatibility issues

### Shell Scripts
- `scripts/operator-manager.sh` - Operator lifecycle management (install/uninstall/check with CSV and CRD validation)
- `scripts/check-observability-drift.sh` - Standalone script for drift detection (can be run independently)

## Benefits

1. **Automated Operator Management**: Operators are automatically installed with CSV and CRD validation
2. **Automatic Instrumentation**: No code changes required for basic tracing
3. **Comprehensive Coverage**: Traces all Python applications in the namespace
4. **Centralized Storage**: All traces stored in MinIO with Tempo for querying
5. **OpenShift Integration**: Native integration with OpenShift console ("Observe → Traces" menu)
6. **Scalable Architecture**: Supports multiple namespaces and applications
7. **Protected Uninstall**: Conditional flags prevent accidental removal of shared resources
8. **Easy Management**: Simple Makefile targets for installation and management
9. **Version Compatibility**: Tempo v0.18.0+ with OTLP endpoints and mTLS encryption
10. **Robust Validation**: Three-phase operator readiness checks prevent race conditions

## References

- [OpenTelemetry Operator Documentation](https://github.com/open-telemetry/opentelemetry-operator)
- [Tempo Documentation](https://grafana.com/docs/tempo/)
- [OpenTelemetry Python Auto-instrumentation](https://opentelemetry.io/docs/instrumentation/python/automatic/)
