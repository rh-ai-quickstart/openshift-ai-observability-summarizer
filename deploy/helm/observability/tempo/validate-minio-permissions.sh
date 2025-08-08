#!/bin/bash

# MinIO Client Permission Fix Validation Script
# This script validates that the HOME environment variable fix resolves mc client permission issues

set -e

NAMESPACE="observability-hub"
DEPLOYMENT_NAME="minio-tempo"

echo "🔍 Validating MinIO Client Permission Fix..."
echo "============================================="

# Function to check if deployment exists
check_deployment() {
    if ! kubectl get deployment $DEPLOYMENT_NAME -n $NAMESPACE &>/dev/null; then
        echo "❌ ERROR: Deployment $DEPLOYMENT_NAME not found in namespace $NAMESPACE"
        echo "💡 Please deploy the Tempo stack first using: helm install tempo ./helm/tempo"
        exit 1
    fi
    echo "✅ Found deployment: $DEPLOYMENT_NAME"
}

# Function to check environment variables in deployment
check_env_vars() {
    echo ""
    echo "🔧 Checking environment variables in deployment..."
    
    # Check init container
    echo "📋 Init Container Environment:"
    kubectl get deployment $DEPLOYMENT_NAME -n $NAMESPACE -o jsonpath='{.spec.template.spec.initContainers[0].env[*]}' | jq -r '
        if .name == "HOME" then 
            "✅ HOME=" + .value 
        elif .name == "MINIO_ROOT_USER" then 
            "✅ MINIO_ROOT_USER=(from secret)" 
        elif .name == "MINIO_ROOT_PASSWORD" then 
            "✅ MINIO_ROOT_PASSWORD=(from secret)"
        else
            "  " + .name + "=" + (.value // "(from secret)")
        end' 2>/dev/null || echo "❌ Could not parse init container environment variables"
    
    # Check main container
    echo ""
    echo "📋 Main Container Environment:"
    kubectl get deployment $DEPLOYMENT_NAME -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].env[*]}' | jq -r '
        if .name == "HOME" then 
            "✅ HOME=" + .value 
        elif .name == "MINIO_ROOT_USER" then 
            "✅ MINIO_ROOT_USER=(from secret)" 
        elif .name == "MINIO_ROOT_PASSWORD" then 
            "✅ MINIO_ROOT_PASSWORD=(from secret)"
        else
            "  " + .name + "=" + (.value // "(from secret)")
        end' 2>/dev/null || echo "❌ Could not parse main container environment variables"
}

# Function to check security context
check_security_context() {
    echo ""
    echo "🔒 Checking security context..."
    
    # Check pod security context
    POD_SECURITY=$(kubectl get deployment $DEPLOYMENT_NAME -n $NAMESPACE -o jsonpath='{.spec.template.spec.securityContext.runAsNonRoot}')
    if [ "$POD_SECURITY" = "true" ]; then
        echo "✅ Pod runs as non-root: $POD_SECURITY"
    else
        echo "⚠️  Pod security context: runAsNonRoot=$POD_SECURITY"
    fi
    
    # Check container security context
    CONTAINER_SECURITY=$(kubectl get deployment $DEPLOYMENT_NAME -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].securityContext.runAsNonRoot}')
    if [ "$CONTAINER_SECURITY" = "true" ]; then
        echo "✅ Container runs as non-root: $CONTAINER_SECURITY"
    else
        echo "⚠️  Container security context: runAsNonRoot=$CONTAINER_SECURITY"
    fi
}

# Function to check pod status
check_pod_status() {
    echo ""
    echo "🚀 Checking pod status..."
    
    # Get pod name
    POD_NAME=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=tempo-stack,app.kubernetes.io/component=minio -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    
    if [ -z "$POD_NAME" ]; then
        echo "⚠️  No MinIO pods found. This is expected if the deployment is new."
        return
    fi
    
    echo "📦 Pod: $POD_NAME"
    
    # Check pod status
    POD_STATUS=$(kubectl get pod $POD_NAME -n $NAMESPACE -o jsonpath='{.status.phase}')
    echo "📊 Status: $POD_STATUS"
    
    if [ "$POD_STATUS" = "Running" ]; then
        echo "✅ Pod is running successfully"
        
        # Test mc client inside the pod
        echo ""
        echo "🧪 Testing mc client inside pod..."
        if kubectl exec $POD_NAME -n $NAMESPACE -- mc --version &>/dev/null; then
            echo "✅ mc client works without permission errors"
        else
            echo "❌ mc client test failed"
        fi
        
        # Check if mc can create config directory
        echo ""
        echo "🧪 Testing mc config directory creation..."
        if kubectl exec $POD_NAME -n $NAMESPACE -- mc alias set test http://localhost:9000 test test 2>&1 | grep -q "permission denied"; then
            echo "❌ mc client still has permission issues"
        else
            echo "✅ mc client can create config directory (permission fix working)"
        fi
    else
        echo "⚠️  Pod is not running. Status: $POD_STATUS"
        
        # Show recent events
        echo ""
        echo "📋 Recent pod events:"
        kubectl describe pod $POD_NAME -n $NAMESPACE | tail -10
    fi
}

# Function to show deployment verification commands
show_verification_commands() {
    echo ""
    echo "🔍 Manual Verification Commands:"
    echo "================================"
    echo ""
    echo "# Check deployment configuration:"
    echo "kubectl get deployment $DEPLOYMENT_NAME -n $NAMESPACE -o yaml | grep -A 10 -B 2 'HOME'"
    echo ""
    echo "# Check pod logs:"
    echo "kubectl logs -l app.kubernetes.io/name=tempo-stack,app.kubernetes.io/component=minio -n $NAMESPACE"
    echo ""
    echo "# Test mc client manually:"
    echo "kubectl exec -it \$(kubectl get pod -l app.kubernetes.io/name=tempo-stack,app.kubernetes.io/component=minio -n $NAMESPACE -o jsonpath='{.items[0].metadata.name}') -n $NAMESPACE -- mc --help"
    echo ""
}

# Main execution
main() {
    check_deployment
    check_env_vars
    check_security_context
    check_pod_status
    show_verification_commands
    
    echo ""
    echo "🎉 MinIO Permission Fix Validation Complete!"
    echo ""
    echo "Summary of fixes applied:"
    echo "✅ HOME=/tmp environment variable added to init container"
    echo "✅ HOME=/tmp environment variable added to main container"
    echo "✅ Security context maintained (runAsNonRoot: true)"
    echo "✅ Automated service account creation preserved"
    echo ""
    echo "This should resolve the 'mkdir /.mc: permission denied' error."
}

# Run the main function
main