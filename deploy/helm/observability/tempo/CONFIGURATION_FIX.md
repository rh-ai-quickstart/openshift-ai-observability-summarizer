# TempoStack Gateway vs Jaeger Ingress Configuration Fix

## Problem Description

The Helm installation was failing with this error:
```
Error: INSTALLATION FAILED: 1 error occurred:
        * admission webhook "vtempostack.tempo.grafana.com" denied the request: TempoStack.tempo.grafana.com "tempostack" is invalid: spec.template.gateway.enabled: Invalid value: true: cannot enable gateway and jaeger query ingress at the same time, please use the Jaeger UI from the gateway
```

## Root Cause

The TempoStack configuration had both:
1. `gateway.enabled: true` 
2. `jaegerQuery.enabled: true` with `ingress.type: route`

This is not allowed because these are mutually exclusive access methods for the Tempo tracing UI.

## Solution Applied

### Configuration Changes

**File: `values.yaml`**
- Changed `jaegerQuery.enabled` from `true` to `false`
- Commented out the `ingress` configuration section
- Kept `gateway.enabled: true`

**File: `templates/tempostack.yaml`**
- Added conditional templating to only render ingress configuration when it's defined
- This prevents template rendering errors when ingress config is commented out

### Why Gateway is the Better Choice

1. **Red Hat Recommendation**: According to the observability documentation, "The Jaeger frontend feature of TempoStack is no longer supported by Red Hat. This has been replaced by the COO UIPlugin."

2. **Modern Architecture**: The Gateway approach integrates with the Cluster Observability Operator (COO) UIPlugin, providing a native OpenShift console experience.

3. **Unified Access**: Traces are accessible directly from the OpenShift console at `Observe -> Traces`.

4. **Maintenance**: Gateway-based access is the current and future-supported approach.

## Access Methods After Fix

### Primary: OpenShift Console (Recommended)
- Access traces via OpenShift console: `Observe -> Traces`
- Requires the COO UIPlugin to be installed (see tracing-ui-plugin.yaml)
- Native integration with OpenShift RBAC and authentication

### Alternative: Grafana Integration
- Configure Grafana with Tempo datasource
- Use Grafana dashboards for trace visualization
- Example configuration available in `grafana/instance-with-prom-tempo-ds/`

## Deployment Instructions

1. **Install COO UIPlugin** (if not already done):
   ```bash
   oc apply -f llama-stack-observability/observability/tracing-ui-plugin.yaml
   ```

2. **Deploy TempoStack with fixed configuration**:
   ```bash
   helm install tempo-stack ./tempo
   ```

3. **Verify deployment**:
   ```bash
   kubectl get tempostack -n observability-hub
   kubectl describe tempostack tempostack -n observability-hub
   ```

## Configuration Options

### If you need Jaeger UI specifically:
If you absolutely need the legacy Jaeger UI, you must disable the gateway:

```yaml
template:
  gateway:
    enabled: false
  queryFrontend:
    jaegerQuery:
      enabled: true
      ingress:
        type: route
```

**Note**: This is not recommended for production OpenShift environments.

### For custom ingress requirements:
If you need custom ingress (e.g., external LoadBalancer), consider using the gateway with custom ingress controllers or service mesh integration.

## Architecture Alignment

This fix aligns with the overall observability architecture where:
- **Metrics**: Collected via PodMonitor/ServiceMonitor → User Workload Monitoring Prometheus
- **Traces**: Collected via OpenTelemetry Collector → Tempo → Gateway → COO UIPlugin
- **Visualization**: OpenShift Console + Optional Grafana

## Testing the Fix

1. **Verify TempoStack is ready**:
   ```bash
   kubectl get tempostack tempostack -n observability-hub -o yaml
   ```

2. **Check that traces are accessible**:
   - Navigate to OpenShift Console → Observe → Traces
   - Should show the Tempo tracing interface

3. **Test trace ingestion**:
   - Deploy a test workload with OpenTelemetry instrumentation
   - Verify traces appear in the UI

## Troubleshooting

If you encounter issues:

1. **Check TempoStack status**:
   ```bash
   kubectl describe tempostack tempostack -n observability-hub
   ```

2. **Verify MinIO storage**:
   ```bash
   kubectl get pods,pvc,svc -n observability-hub -l app.kubernetes.io/name=minio-tempo
   ```

3. **Check COO UIPlugin**:
   ```bash
   kubectl get uiplugin
   ```

## Security Considerations

- Gateway approach integrates with OpenShift RBAC
- MinIO credentials should be changed for production (see values.yaml)
- Consider external S3 storage for production deployments
- TLS should be enabled for production environments