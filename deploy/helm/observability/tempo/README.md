# Tempo TempoStack Helm Chart

This directory contains the Helm chart for deploying a TempoStack instance that uses a shared MinIO storage backend. This chart is designed to work with the Tempo Operator and depends on the shared MinIO instance deployed by the main MinIO chart.

## Overview

This configuration includes:
- **TempoStack Instance**: Multitenant Tempo configuration
- **Shared MinIO Integration**: Uses the shared MinIO instance for trace storage
- **Storage Secrets**: Credentials and connection details for the shared MinIO
- **RBAC**: Cluster roles for trace access

## Prerequisites

1. **Tempo Operator**: Must be installed first using the tempo-operator Helm chart:
   ```bash
   helm install tempo-operator ../tempo-operator/
   ```

2. **Shared MinIO Instance**: The shared MinIO instance must be deployed first:
   ```bash
   # Deploy the shared MinIO instance
   make install-minio
   # OR
   helm install minio-observability-storage ../../minio/
   ```

3. **Namespace**: Ensure the `observability-hub` namespace exists:
   ```bash
   kubectl create namespace observability-hub
   ```

## Deployment

Deploy the TempoStack configuration using Helm:

```bash
helm install tempo-stack .
```

This will create:
- TempoStack instance configured for multitenancy with Gateway access
- Storage secrets that reference the shared MinIO instance
- Required RBAC permissions
- Integration with the existing MinIO deployment

⚠️ **Important Configuration Fix**: This chart resolves the gateway/Jaeger ingress conflict by using the recommended Gateway approach. See [`CONFIGURATION_FIX.md`](./CONFIGURATION_FIX.md) for details.

## Configuration Details

### Shared MinIO Storage
- **Deployment**: Uses the shared `minio-observability-storage` instance
- **Service**: `minio-observability-storage` ClusterIP service on port 9000
- **Credentials**: References the shared MinIO credentials
  - User: `admin` (default MinIO user)
  - Password: `minio123` (default MinIO password)
  - Bucket: `tempo` (created automatically via dynamic bucket creation)

### TempoStack Configuration
- **Name**: `tempostack`
- **Storage**: Uses shared MinIO storage (no local PVC)
- **Resources**: 10Gi memory, 5000m CPU limits
- **Multitenancy**: Enabled with OpenShift mode
- **Tenant**: `dev` tenant pre-configured
- **UI Access**: Gateway enabled, accessible via OpenShift Console (Observe -> Traces)

### RBAC
- **ClusterRole**: `tempostack-traces-reader` for trace access
- **Binding**: Allows all authenticated users to read traces

## Accessing Tempo

After deployment, access traces via the **OpenShift Console**:

1. Navigate to **Observe -> Traces** in the OpenShift console
2. Ensure the **COO UIPlugin** is installed (see observability documentation)

Alternative: Check for gateway services:
```bash
oc get services -n observability-hub -l app.kubernetes.io/component=gateway
```

**Note**: The legacy Jaeger Query UI route has been disabled in favor of the modern Gateway + COO UIPlugin approach.

## Security Considerations

⚠️ **Important**: The default MinIO credentials are for development/testing only. For production deployments:

1. Change the credentials in the shared MinIO chart (`deploy/helm/minio/`)
2. Update the corresponding values in the Tempo storage secrets
3. Consider using external S3-compatible storage instead of MinIO

## Customization

### Changing Storage Size
Edit the shared MinIO chart (`deploy/helm/minio/values.yaml`) to change the storage size:
```yaml
persistence:
  size: 20Gi  # Change as needed
```

### Adding More Tenants
Edit `tempo-multitenant.yaml` to add additional tenants:
```yaml
tenants:
  mode: openshift
  authentication:
    - tenantName: dev
      tenantId: "1610b0c3-c509-4592-a256-a1871353dbfa"
    - tenantName: prod
      tenantId: "2610b0c3-c509-4592-a256-a1871353dbfb"
```

### Resource Limits
Adjust resources in `tempo-multitenant.yaml`:
```yaml
resources:
  total:
    limits:
      memory: 20Gi  # Increase for higher throughput
      cpu: 8000m
```

## Troubleshooting

### Shared MinIO Not Available
Check if the shared MinIO instance is running:
```bash
kubectl get pods -n observability-hub | grep minio-observability-storage
kubectl get pvc -n observability-hub | grep minio
```

### TempoStack Not Ready
Check operator logs:
```bash
kubectl logs -n openshift-tempo-operator deployment/tempo-operator-controller
```

Check TempoStack status:
```bash
kubectl get tempostack tempostack -n observability-hub -o yaml
```

### Storage Secret Issues
Verify the MinIO secret is properly configured:
```bash
kubectl get secret minio-observability-storage -n observability-hub -o yaml
```

## Integration with Applications

To send traces to this Tempo instance, configure your applications to send traces to the gateway endpoint. The operator will create the necessary services and routes.

Example OpenTelemetry configuration:
```yaml
exporters:
  otlp:
    endpoint: "http://tempostack-gateway.observability-hub.svc.cluster.local:8080"