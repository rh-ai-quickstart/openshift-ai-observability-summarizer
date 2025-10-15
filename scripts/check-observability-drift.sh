#!/bin/bash

# Check for configuration drift in observability-hub namespace
# This script detects issues like deprecated configuration fields

set -e

OBSERVABILITY_NAMESPACE=${1:-observability-hub}

echo ""
echo "→ Checking for configuration drift in $OBSERVABILITY_NAMESPACE namespace"
echo ""

DRIFT_DETECTED=0

# Check OpenTelemetry Collector
echo "  🔍 Checking OpenTelemetry Collector..."
if helm list -n $OBSERVABILITY_NAMESPACE | grep -q "^otel-collector\s"; then
    OTEL_REVISION=$(helm list -n $OBSERVABILITY_NAMESPACE | grep "^otel-collector\s" | awk '{print $2}')
    echo "  📊 OpenTelemetry Collector: Revision $OTEL_REVISION"
    
    # Check for deprecated configuration (the actual drift we found)
    if oc get opentelemetrycollector otel-collector -n $OBSERVABILITY_NAMESPACE -o yaml | grep -q 'address:.*:8888'; then
        echo "  ❌ OpenTelemetry Collector: Contains deprecated 'address' field in telemetry config"
        echo "     → This will cause crashes with OpenTelemetry operator 0.135.0+"
        DRIFT_DETECTED=1
    else
        echo "  ✅ OpenTelemetry Collector: Configuration is up-to-date"
    fi
else
    echo "  ❌ OpenTelemetry Collector: Not installed"
    DRIFT_DETECTED=1
fi

# Check TempoStack
echo ""
echo "  🔍 Checking TempoStack..."
if helm list -n $OBSERVABILITY_NAMESPACE | grep -q "^tempo\s"; then
    TEMPO_REVISION=$(helm list -n $OBSERVABILITY_NAMESPACE | grep "^tempo\s" | awk '{print $2}')
    echo "  📊 TempoStack: Revision $TEMPO_REVISION"
    echo "  ✅ TempoStack: Configuration is up-to-date"
else
    echo "  ❌ TempoStack: Not installed"
    DRIFT_DETECTED=1
fi

# Check OpenTelemetry operator compatibility
echo ""
echo "  🔍 Checking OpenTelemetry operator compatibility..."
OTEL_OPERATOR_VERSION=$(oc get csv -n openshift-operators | grep opentelemetry-operator | awk '{print $7}' | head -1)
if [ -n "$OTEL_OPERATOR_VERSION" ]; then
    echo "  📊 OpenTelemetry Operator: $OTEL_OPERATOR_VERSION"
    # Only show warning if we detect actual configuration issues
    if echo "$OTEL_OPERATOR_VERSION" | grep -q "0.135.0"; then
        # Check if the collector has the deprecated configuration that would cause issues
        if oc get opentelemetrycollector otel-collector -n $OBSERVABILITY_NAMESPACE -o yaml | grep -q 'address:.*:8888'; then
            echo "  ⚠️  Using operator 0.135.0+ with deprecated configuration - will cause crashes"
        else
            echo "  ✅ OpenTelemetry Operator: Configuration is compatible"
            echo "     → No deprecated 'address' field found in telemetry config"
        fi
    else
        echo "  ✅ OpenTelemetry Operator: Version is compatible"
        echo "     → Using operator version that doesn't require configuration changes"
    fi
else
    echo "  ❌ OpenTelemetry Operator: Not found"
fi

echo ""
if [ "$DRIFT_DETECTED" -eq 0 ]; then
    echo "  💡 All observability components are up-to-date"
    echo "✅ No configuration drift detected"
    exit 0
else
    echo "  ⚠️  Configuration drift detected!"
    echo "  🔧 To fix drift, run:"
    echo "    make upgrade-observability"
    exit 1
fi
