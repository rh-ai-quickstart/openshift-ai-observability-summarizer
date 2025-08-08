# OpenTelemetry Collector Helm Chart

This Helm chart deploys an OpenTelemetry Collector for comprehensive application observability and distributed tracing in a Kubernetes cluster.

## Overview

This chart provides:
- Centralized OpenTelemetry Collector deployment for telemetry processing
- OTLP endpoints for receiving traces from applications
- Integration with Tempo for distributed tracing storage
- RBAC configuration for secure trace export
- Configurable resource limits and observability settings

## Prerequisites

- Kubernetes 1.19+
- Helm 3.2.0+
- OpenTelemetry Operator installed in the cluster
- Tempo operator and TempoStack instance (for trace export)

## Installation

### Basic Installation

```bash
helm install otel-collector ./otel-collector \
  --namespace observability-hub \
  --create-namespace
```

### Installation with Custom Values

```bash
helm install otel-collector ./otel-collector \
  --namespace observability-hub \
  --create-namespace \
  --values custom-values.yaml
```

## Configuration

### Key Configuration Areas

#### Global Settings

```yaml
global:
  namespace: observability-hub  # Target namespace
```

#### Main Collector

```yaml
collector:
  enabled: true
  name: "otel-collector"
  mode: deployment  # deployment, daemonset, sidecar, statefulset
  replicas: 1
  resources:
    limits:
      cpu: 500m
      memory: 512Mi
    requests:
      cpu: 100m
      memory: 128Mi
```

#### Tempo Integration

```yaml
tempo:
  gateway:
    endpoint: "tempo-tempostack-gateway"
    port: 8080
    path: "/api/traces/v1/dev"
    protocol: "https"
    namespace: "observability-hub"
  auth:
    orgID: "dev"
    useServiceAccountToken: true
```

### RBAC Configuration

```yaml
rbac:
  create: true
  clusterRole:
    name: "tempostack-traces-write"
    rules:
      - apiGroups:
          - 'tempo.grafana.com'
        resources:
          - dev
        resourceNames:
          - traces
        verbs:
          - 'create'
```

## Usage

### Configuring Applications to Send Traces

The OpenTelemetry Collector exposes OTLP endpoints that your applications can send traces to:

- **OTLP gRPC**: `otel-collector-collector:4317`
- **OTLP HTTP**: `otel-collector-collector:4318`

#### Python Application Example

```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

# Configure the tracer
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)

# Configure OTLP exporter to send to collector
otlp_exporter = OTLPSpanExporter(
    endpoint="http://otel-collector-collector.observability-hub.svc.cluster.local:4318/v1/traces",
    headers={},
)

# Add span processor
span_processor = BatchSpanProcessor(otlp_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)

# Auto-instrument popular libraries
RequestsInstrumentor().instrument()

# Create custom spans
def my_function():
    with tracer.start_as_current_span("my-operation"):
        # Your application logic here
        pass
```

#### Environment Variables for Applications

For applications running in the same cluster, you can configure OpenTelemetry using environment variables:

```yaml
apiVersion: v1
kind: Deployment
metadata:
  name: my-python-app
spec:
  template:
    spec:
      containers:
      - name: app
        image: my-app:latest
        env:
        - name: OTEL_EXPORTER_OTLP_ENDPOINT
          value: "http://otel-collector-collector.observability-hub.svc.cluster.local:4318"
        - name: OTEL_EXPORTER_OTLP_PROTOCOL
          value: "http/protobuf"
        - name: OTEL_SERVICE_NAME
          value: "my-python-service"
```

## Customization Examples

### Custom Namespace

```yaml
global:
  namespace: my-observability-namespace
```

### Custom Tempo Endpoint

```yaml
tempo:
  gateway:
    endpoint: "my-tempo-gateway"
    port: 8080
    namespace: "my-tempo-namespace"
```

### Resource Limits

```yaml
collector:
  resources:
    limits:
      cpu: 1000m
      memory: 1Gi
    requests:
      cpu: 200m
      memory: 256Mi
```

### Custom Service Configuration

```yaml
collector:
  config:
    processors:
      batch:
        send_batch_size: 200
        timeout: 2s
      memory_limiter:
        check_interval: 10s
        limit_percentage: 90
```

## Upgrading

```bash
helm upgrade otel-collector ./otel-collector \
  --namespace observability-hub \
  --values custom-values.yaml
```

## Uninstalling

```bash
helm uninstall otel-collector --namespace observability-hub
```

## Troubleshooting

### Common Issues

1. **RBAC Permission Errors**: Ensure the Tempo TempoStack is deployed and accessible
2. **Traces Not Appearing**: Check that applications are configured with correct collector endpoints
3. **Connection Refused**: Verify the collector service is running and accessible

### Debugging Commands

```bash
# Check collector status
kubectl get opentelemetrycollector -n observability-hub

# View collector logs
kubectl logs -n observability-hub deployment/otel-collector-collector

# Check RBAC
kubectl auth can-i create dev --as=system:serviceaccount:observability-hub:otel-collector

# Test connectivity from a pod
kubectl run test-trace --rm -i --tty --image=curlimages/curl -- \
  curl -v http://otel-collector-collector.observability-hub.svc.cluster.local:4318/v1/traces
```

### Trace Testing

Test the collector with a sample trace:

```bash
kubectl run test-trace --rm -i --tty --image=curlimages/curl -- \
  curl -X POST http://otel-collector-collector.observability-hub.svc.cluster.local:4318/v1/traces \
  -H "Content-Type: application/json" \
  -d '{
    "resourceSpans": [{
      "resource": {
        "attributes": [{
          "key": "service.name",
          "value": {"stringValue": "test-service"}
        }]
      },
      "instrumentationLibrarySpans": [{
        "spans": [{
          "traceId": "12345678901234567890123456789012",
          "spanId": "1234567890123456",
          "name": "test-span",
          "kind": 1,
          "startTimeUnixNano": "1640995200000000000",
          "endTimeUnixNano": "1640995201000000000"
        }]
      }]
    }]
  }'
```

## Values Reference

For a complete list of configurable values, see the [values.yaml](./values.yaml) file.

Key configurable sections:
- `global`: Global settings like namespace
- `collector`: Main collector configuration
- `tempo`: Tempo integration settings
- `rbac`: RBAC and permissions
- `serviceAccount`: Service account configuration

## License

This chart is licensed under the Apache License 2.0.