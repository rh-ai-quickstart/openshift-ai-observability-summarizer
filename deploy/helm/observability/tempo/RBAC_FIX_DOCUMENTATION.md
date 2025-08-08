# RBAC Fix Documentation for OTEL Collector Tempo Integration

## Problem Description

When deploying OTEL Collector in the `observability-hub` namespace to send traces to Tempo, authentication failures occurred with the error:
```json
{"error":"failed to find token","errorType":"observatorium-api","status":"error"}
```

## Root Cause

The OTEL Collector service account in the `observability-hub` namespace lacked the necessary RBAC permissions to read/write traces to the Tempo TempoStack. The original RBAC bindings in `rbac2.yaml` were only configured for the `llama-serve` namespace.

## Fix Applied

Added the missing ClusterRoleBinding in `templates/rbac2.yaml`:

```yaml
# Additional binding for OTEL collector in observability-hub namespace
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: tempostack-traces-reader-grafana
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: tempostack-traces-reader
subjects:
- kind: ServiceAccount
  name: otel-collector
  namespace: observability-hub
```

## Verification Steps

1. **Check RBAC permissions:**
   ```bash
   kubectl get clusterrolebinding tempostack-traces-reader-grafana -o yaml
   ```

2. **Test authentication:**
   ```bash
   kubectl exec otel-collector-collector-<pod-id> -n observability-hub -- \
     curl -k -s -H "Authorization: Bearer $(kubectl exec otel-collector-collector-<pod-id> -n observability-hub -- cat /var/run/secrets/kubernetes.io/serviceaccount/token)" \
     -H "X-Scope-OrgID: dev" \
     https://tempo-tempostack-gateway.observability-hub.svc.cluster.local:8080/api/traces/v1/dev
   ```

3. **Send test trace:**
   ```bash
   kubectl exec otel-collector-collector-<pod-id> -n observability-hub -- \
     curl -X POST http://localhost:4318/v1/traces \
     -H "Content-Type: application/json" \
     -d '{"resourceSpans":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"test-service"}}]},"scopeSpans":[{"spans":[{"traceId":"12345678901234567890123456789012","spanId":"1234567890123456","name":"test-span","startTimeUnixNano":"1609459200000000000","endTimeUnixNano":"1609459201000000000","kind":"SPAN_KIND_SERVER"}]}]}]}'
   ```

4. **Check OTEL Collector logs:**
   ```bash
   kubectl logs otel-collector-collector-<pod-id> -n observability-hub --tail=20
   ```

## Deployment Notes

- This fix is now included in the Helm template and will be applied automatically when deploying the Tempo chart
- The RBAC binding allows the OTEL Collector to authenticate properly with the Tempo gateway
- Both read and write permissions are granted for comprehensive trace handling

## Related Files

- `templates/rbac2.yaml` - Contains the RBAC fix
- `templates/rbac.yaml` - Original RBAC configuration
- OTEL Collector configuration handles the bearer token authentication via the `bearertokenauth` extension

## Troubleshooting

If authentication issues persist:

1. Verify service account exists: `kubectl get sa otel-collector -n observability-hub`
2. Check ClusterRoleBindings: `kubectl get clusterrolebinding | grep tempo`
3. Restart OTEL Collector: `kubectl rollout restart deployment/otel-collector-collector -n observability-hub`
4. Check Tempo gateway logs: `kubectl logs tempo-tempostack-gateway-<pod-id> -n observability-hub`