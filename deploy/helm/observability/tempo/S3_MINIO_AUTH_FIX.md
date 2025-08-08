# Tempo S3/MinIO Authentication Fix

## Problem Solved

**Original Error:**
```
level=error ts=2025-06-12T22:07:37.823246477Z caller=main.go:124 msg="error running Tempo" err="failed to init module services: error initialising module: store: failed to create store: unexpected error from ListObjects on tempo: The Access Key Id you provided does not exist in our records."
```

## Root Cause Analysis

The issue was a **credential mismatch between Tempo and MinIO**:

### What Tempo Expected:
- **Access Key ID:** `tempo` 
- **Secret Access Key:** `supersecret`
- **S3 Endpoint:** `http://minio-tempo-svc.observability-hub.svc.cluster.local:9000`
- **Bucket:** `tempo`

### What MinIO Had:
- **Root User:** `admin` with password `minio123`
- **Service Accounts:** None (this was the problem!)
- **Result:** Access key `tempo` didn't exist

## Solution Applied

### 1. Immediate Fix (Manual)
Created the missing service account in MinIO:
```bash
kubectl exec -n observability-hub minio-tempo-<pod-id> -- \
  mc admin user svcacct add myminio admin \
  --access-key tempo \
  --secret-key supersecret
```

### 2. Verification Steps
```bash
# Verify service account creation
kubectl exec -n observability-hub minio-tempo-<pod-id> -- \
  mc admin user svcacct list myminio admin

# Test credentials work
kubectl exec -n observability-hub minio-tempo-<pod-id> -- \
  mc alias set tempoaccess http://localhost:9000 tempo supersecret

# Verify bucket access  
kubectl exec -n observability-hub minio-tempo-<pod-id> -- \
  mc ls tempoaccess/tempo
```

### 3. Restart Affected Pods
```bash
kubectl delete pods \
  tempo-tempostack-compactor-<id> \
  tempo-tempostack-ingester-0 \
  tempo-tempostack-querier-<id> \
  tempo-tempostack-query-frontend-<id> \
  -n observability-hub
```

## Long-term Prevention

### Option A: Automated Service Account Creation (Recommended)

Update the MinIO deployment to automatically create the service account:

```yaml
# In minio-deployment.yaml, add an init container or post-start hook
initContainers:
- name: create-service-account
  image: quay.io/minio/mc:latest
  command:
    - /bin/sh
    - -c
    - |
      # Wait for MinIO to be ready
      until mc alias set myminio http://localhost:9000 admin minio123; do
        echo "Waiting for MinIO to be ready..."
        sleep 5
      done
      
      # Create service account if it doesn't exist
      if ! mc admin user svcacct list myminio admin | grep -q "tempo"; then
        mc admin user svcacct add myminio admin --access-key tempo --secret-key supersecret
        echo "Service account 'tempo' created successfully"
      else
        echo "Service account 'tempo' already exists"
      fi
  env:
    - name: MINIO_ROOT_USER
      valueFrom:
        secretKeyRef:
          name: minio-user-creds
          key: MINIO_ROOT_USER
    - name: MINIO_ROOT_PASSWORD
      valueFrom:
        secretKeyRef:
          name: minio-user-creds
          key: MINIO_ROOT_PASSWORD
```

### Option B: Use Root Credentials Directly

Update Tempo secret to use MinIO root credentials:

```yaml
# In values.yaml, change:
minio:
  s3:
    accessKeyId: admin
    accessKeySecret: minio123
    bucket: tempo
```

**Note:** Option A is recommended for production as it follows the principle of least privilege.

## Credential Flow Diagram

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   TempoStack    │    │   Secret        │    │     MinIO       │
│                 │    │   minio-tempo   │    │                 │
│ Needs:          │───▶│                 │───▶│ Must Have:      │
│ • Access Key    │    │ access_key_id:  │    │ • Service Acct  │
│ • Secret        │    │   "tempo"       │    │   with same     │
│ • Endpoint      │    │ access_key_sec: │    │   credentials   │
│ • Bucket        │    │   "supersecret" │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Verification Commands

### Check TempoStack Status
```bash
kubectl get tempostack -n observability-hub
kubectl describe tempostack tempostack -n observability-hub
```

### Check All Tempo Pods
```bash
kubectl get pods -n observability-hub | grep tempo
```

### Check Specific Pod Logs
```bash
kubectl logs tempo-tempostack-compactor-<id> -n observability-hub --tail=20
```

### Test MinIO Connectivity
```bash
kubectl exec -n observability-hub minio-tempo-<pod-id> -- \
  mc ls tempoaccess/tempo
```

## Status After Fix

✅ **All Tempo pods are Running (1/1)**  
✅ **TempoStack status: Ready = True**  
✅ **No more S3 authentication errors**  
✅ **MinIO service account created with correct credentials**  
✅ **Tempo bucket accessible**  

## Security Considerations

1. **Production Deployment:**
   - Change default credentials in `values.yaml`
   - Use external S3-compatible storage instead of embedded MinIO
   - Enable TLS for S3 connections

2. **Credential Management:**
   - Store credentials in external secret management systems
   - Rotate access keys regularly
   - Use IAM roles where possible (for cloud S3)

## Related Files

- `llama-stack-observability/helm/tempo/values.yaml` - Tempo configuration
- `llama-stack-observability/helm/tempo/templates/minio-secrets.yaml` - Credential secrets
- `llama-stack-observability/helm/tempo/templates/minio-deployment.yaml` - MinIO deployment
- `llama-stack-observability/helm/tempo/templates/tempostack.yaml` - TempoStack configuration

## Implementation Status

✅ **Option A (Automated Service Account Creation) - IMPLEMENTED**
- Init container added to `minio-deployment.yaml`
- Automatically creates service account on deployment
- Uses values from `values.yaml` for credentials
- Ensures service account exists before MinIO starts

## MinIO Client Permission Fix

### Problem: mc client permission denied error
When running as non-root user (security best practice), the mc client tries to create config directory at `/.mc` which fails with permission denied.

**Error:**
```
mkdir /.mc: permission denied
```

### Solution: HOME environment variable
Added `HOME=/tmp` environment variable to both init container and main container to provide mc client with a writable directory for its configuration.

**Implementation:**
```yaml
env:
  - name: HOME
    value: "/tmp"
  - name: MINIO_ROOT_USER
    valueFrom:
      secretKeyRef:
        name: minio-user-creds
        key: MINIO_ROOT_USER
  # ... other environment variables
```

✅ **HOME environment variable fix - IMPLEMENTED**
- Added to init container (create-service-account)
- Added to main container (minio-tempo)
- Maintains security context with runAsNonRoot: true
- Allows mc client to create config in writable /tmp directory

## Next Steps

1. ~~Consider implementing Option A for permanent fix~~ ✅ **COMPLETED**
2. ~~Fix mc client permission errors~~ ✅ **COMPLETED**
3. Test trace ingestion and visualization
4. Monitor for any additional authentication issues
5. Plan migration to external S3 for production