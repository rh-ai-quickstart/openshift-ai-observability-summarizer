# Tempo TempoStack Helm Chart

This directory contains the Helm chart for deploying a TempoStack instance with MinIO storage. This chart is designed to work with the Tempo Operator installed via the `../tempo-operator/` Helm chart.

## Overview

This configuration includes:
- **MinIO Deployment**: S3-compatible storage backend for Tempo traces
- **TempoStack Instance**: Multitenant Tempo configuration
- **Storage Secrets**: Credentials and connection details for MinIO
- **RBAC**: Cluster roles for trace access

## Prerequisites

1. **Tempo Operator**: Must be installed first using the tempo-operator Helm chart:
   ```bash
   helm install tempo-operator ../tempo-operator/
   ```

2. **Namespace**: Ensure the `observability-hub` namespace exists:
   ```bash
   kubectl create namespace observability-hub
   ```

## Deployment

Deploy the TempoStack and MinIO configuration using Helm:

```bash
helm install tempo-stack .
```

This will create:
- MinIO deployment with persistent storage (12Gi)
- MinIO service and credentials
- TempoStack instance configured for multitenancy with Gateway access
- Required RBAC permissions

⚠️ **Important Configuration Fix**: This chart resolves the gateway/Jaeger ingress conflict by using the recommended Gateway approach. See [`CONFIGURATION_FIX.md`](./CONFIGURATION_FIX.md) for details.

## Configuration Details

### MinIO Storage
- **Deployment**: `minio-tempo` with 12Gi PVC
- **Service**: ClusterIP service on port 9000
- **Credentials**: Default test credentials (change for production)
  - User: `tempo`
  - Password: `supersecret`
  - Bucket: `tempo`

### TempoStack Configuration
- **Name**: `tempostack`
- **Storage**: 15Gi for trace data
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

1. Change the credentials in `minio-user-creds.yaml`
2. Update the corresponding values in `minio-secret-tempo.yaml`
3. Consider using external S3-compatible storage instead of MinIO

## Customization

### Changing Storage Size
Edit `minio-tempo-pvc.yaml` to change the MinIO storage size:
```yaml
resources:
  requests:
    storage: 20Gi  # Change as needed
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

### MinIO Pod Not Starting
Check PVC availability:
```bash
kubectl get pvc minio-tempo -n observability-hub
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
kubectl get secret minio-tempo -n observability-hub -o yaml
```

## Integration with Applications

To send traces to this Tempo instance, configure your applications to send traces to the gateway endpoint. The operator will create the necessary services and routes.

Example OpenTelemetry configuration:
```yaml
exporters:
  otlp:
    endpoint: "http://tempostack-gateway.observability-hub.svc.cluster.local:8080"