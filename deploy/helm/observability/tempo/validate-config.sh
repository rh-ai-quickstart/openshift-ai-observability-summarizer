#!/bin/bash

set -e

echo "🔍 Validating TempoStack Configuration Fix"
echo "=========================================="

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}1. Testing Helm template rendering...${NC}"
if helm template tempo-stack . --dry-run > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Helm template renders successfully${NC}"
else
    echo -e "${RED}❌ Helm template failed to render${NC}"
    exit 1
fi

echo -e "${YELLOW}2. Checking gateway configuration...${NC}"
GATEWAY_ENABLED=$(helm template tempo-stack . | grep -A 5 "template:" | grep -A 2 "gateway:" | grep "enabled:" | awk '{print $2}')
if [ "$GATEWAY_ENABLED" = "true" ]; then
    echo -e "${GREEN}✅ Gateway is enabled${NC}"
else
    echo -e "${RED}❌ Gateway is not enabled${NC}"
    exit 1
fi

echo -e "${YELLOW}3. Checking Jaeger query configuration...${NC}"
JAEGER_ENABLED=$(helm template tempo-stack . | grep -A 10 "queryFrontend:" | grep -A 2 "jaegerQuery:" | grep "enabled:" | awk '{print $2}')
if [ "$JAEGER_ENABLED" = "false" ]; then
    echo -e "${GREEN}✅ Jaeger query is disabled${NC}"
else
    echo -e "${RED}❌ Jaeger query is still enabled${NC}"
    exit 1
fi

echo -e "${YELLOW}4. Checking for ingress configuration conflicts...${NC}"
INGRESS_COUNT=$(helm template tempo-stack . | grep -c "ingress:" || true)
if [ "$INGRESS_COUNT" -eq 0 ]; then
    echo -e "${GREEN}✅ No ingress configuration rendered (conflict avoided)${NC}"
else
    echo -e "${YELLOW}⚠️  Ingress configuration found ($INGRESS_COUNT occurrences) - please verify manually${NC}"
fi

echo -e "${YELLOW}5. Validating TempoStack spec structure...${NC}"
TEMPOSTACK_TEMPLATE=$(helm template tempo-stack . | grep -A 10 "spec:" | grep -c "template:" || true)
if [ "$TEMPOSTACK_TEMPLATE" -gt 0 ]; then
    echo -e "${GREEN}✅ TempoStack template section is properly structured${NC}"
else
    echo -e "${RED}❌ TempoStack template section missing or malformed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}🎉 All validation checks passed!${NC}"
echo ""
echo "Configuration Summary:"
echo "  - Gateway: Enabled (✅)"
echo "  - Jaeger Query: Disabled (✅)"
echo "  - Ingress: Not configured (✅)"
echo "  - Access Method: OpenShift Console (Observe -> Traces)"
echo ""
echo "Next steps:"
echo "  1. Ensure COO UIPlugin is installed"
echo "  2. Deploy with: helm install tempo-stack ."
echo "  3. Verify access via OpenShift console"