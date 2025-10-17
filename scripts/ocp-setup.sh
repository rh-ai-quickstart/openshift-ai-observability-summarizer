#!/bin/bash

# OpenShift Service Account Setup Script
# Sets up GitHub Actions service account with required permissions

# Source common utilities
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Configuration
SERVICE_ACCOUNT_NAME="github-actions"
TOKEN_SECRET_NAME="github-actions-token"

echo -e "${BLUE}🚀 OpenShift Service Account Setup for GitHub Actions${NC}"
echo "=================================================================="

# Function to display usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -n/-N NAMESPACE              Target namespace (required)"
    echo "  -s/-S                        Perform initial setup (create SA and grant permissions)"
    echo "  -t/-T                        Extract token only"
    echo "  -h                           Display this help message"
    echo ""
    echo "Examples:"
    echo "  $0 -s -n my-namespace           # Initial setup (lowercase)"
    echo "  $0 -T -N my-namespace           # Extract token only (uppercase)"
    echo "  $0 -S -T -n my-namespace        # Setup and extract token (mixed case)"
}


# Function to check prerequisites
check_prerequisites() {
    echo -e "${BLUE}🔍 Checking prerequisites...${NC}"
    
    # Check dependencies
    check_tool_exists "oc"
    check_tool_exists "envsubst"
    
    # Check OpenShift login
    check_openshift_login
    
    # Check if required files exist
    check_file "$SCRIPT_DIR/ocp_config/github-actions-rbac.yml" "RBAC"
    check_file "$SCRIPT_DIR/ocp_config/sa_token_secret.yml" "Token secret"
    
    echo -e "${GREEN}✅ Prerequisites check passed${NC}"
    echo -e "${GREEN}   Logged in as: $(oc whoami)${NC}"
    echo -e "${GREEN}   Target namespace: $NAMESPACE${NC}"
}

# Function to create and setup service account
setup_service_account() {
    echo -e "${BLUE}🔧 Setting up service account...${NC}"
    
    # 1. Create namespace if it doesn't exist
    if ! oc get namespace "$NAMESPACE" &> /dev/null; then
        echo -e "${YELLOW}⚠️  Namespace $NAMESPACE doesn't exist, creating it...${NC}"
        oc create namespace "$NAMESPACE"
        echo -e "${GREEN}✅ Created namespace: $NAMESPACE${NC}"
    fi
    
    # 2. Create service account
    if oc get serviceaccount "$SERVICE_ACCOUNT_NAME" -n "$NAMESPACE" &> /dev/null; then
        echo -e "${YELLOW}⚠️  Service account $SERVICE_ACCOUNT_NAME already exists${NC}"
    else
        echo -e "${BLUE}   Creating service account: $SERVICE_ACCOUNT_NAME${NC}"
        oc create serviceaccount "$SERVICE_ACCOUNT_NAME" -n "$NAMESPACE"
        echo -e "${GREEN}✅ Created service account: $SERVICE_ACCOUNT_NAME${NC}"
    fi
    
    # 3. Grant edit role in namespace
    echo -e "${BLUE}   Granting edit role to service account...${NC}"
    oc adm policy add-role-to-user edit -z "$SERVICE_ACCOUNT_NAME" -n "$NAMESPACE"
    echo -e "${GREEN}✅ Granted edit role to $SERVICE_ACCOUNT_NAME in $NAMESPACE${NC}"
    
    # 4. Create token secret using the template file
    echo -e "${BLUE}   Creating token secret...${NC}"
    if oc get secret "$TOKEN_SECRET_NAME" -n "$NAMESPACE" &> /dev/null; then
        echo -e "${YELLOW}⚠️  Token secret already exists, recreating...${NC}"
        oc delete secret "$TOKEN_SECRET_NAME" -n "$NAMESPACE"
    fi
    
    # Apply token secret with namespace substitution
    NAMESPACE="$NAMESPACE" envsubst < "$SCRIPT_DIR/ocp_config/sa_token_secret.yml" | oc apply -f -
    echo -e "${GREEN}✅ Created token secret: $TOKEN_SECRET_NAME${NC}"
    
    # 5. Apply cluster-level RBAC permissions using the RBAC file
    echo -e "${BLUE}   Applying cluster-level RBAC permissions...${NC}"
    NAMESPACE="$NAMESPACE" envsubst < "$SCRIPT_DIR/ocp_config/github-actions-rbac.yml" | oc apply -f -
    echo -e "${GREEN}✅ Applied cluster-level RBAC permissions${NC}"
    
    echo -e "${GREEN}🎉 Service account setup completed successfully!${NC}"
}

# Function to extract token
extract_token() {
    echo -e "${BLUE}🔑 Extracting service account token...${NC}"
    
    # Wait for token to be available
    echo -e "${BLUE}   Waiting for token to be generated...${NC}"
    local retries=0
    local max_retries=30
    
    while [ $retries -lt $max_retries ]; do
        if oc get secret "$TOKEN_SECRET_NAME" -n "$NAMESPACE" &> /dev/null; then
            TOKEN_DATA=$(oc get secret "$TOKEN_SECRET_NAME" -o jsonpath='{.data.token}' -n "$NAMESPACE" 2>/dev/null)
            if [ -n "$TOKEN_DATA" ]; then
                break
            fi
        fi
        
        echo -e "${YELLOW}   Waiting for token... (attempt $((retries + 1))/$max_retries)${NC}"
        sleep 2
        retries=$((retries + 1))
    done
    
    if [ $retries -eq $max_retries ]; then
        echo -e "${RED}❌ Timeout waiting for token to be generated${NC}"
        exit 1
    fi
    
    # Extract and decode token
    OCP_TOKEN=$(echo "$TOKEN_DATA" | base64 --decode)
    
    if [ -n "$OCP_TOKEN" ]; then
        echo -e "${GREEN}✅ Token extracted successfully${NC}"
        echo ""
        echo -e "${BLUE}📋 GitHub Secrets Configuration:${NC}"
        echo "=================================="
        echo -e "${YELLOW}OPENSHIFT_SERVER:${NC} $(oc whoami --show-server)"
        echo -e "${YELLOW}OPENSHIFT_TOKEN:${NC} $OCP_TOKEN"
        echo ""
        echo -e "${BLUE}💡 Add these to your GitHub repository secrets:${NC}"
        echo "   Settings → Secrets and variables → Actions → Repository secrets"
    else
        echo -e "${RED}❌ Failed to extract token${NC}"
        exit 1
    fi
}

# Function to cleanup on exit
cleanup() {
    local exit_code=$?
    # Don't show "Script failed" for usage display (exit code 2)
    if [ $exit_code -ne 0 ] && [ $exit_code -ne 2 ]; then
        echo -e "\n${RED}❌ Script failed${NC}"
    fi
}
trap cleanup EXIT

# Parse command line arguments
NAMESPACE=""
SETUP=false
EXTRACT_TOKEN=false

while getopts "n:N:sStTh" opt; do
    case $opt in
        n|N)
            NAMESPACE="$OPTARG"
            ;;
        s|S)
            SETUP=true
            ;;
        t|T)
            EXTRACT_TOKEN=true
            ;;
        h)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}❌ INVALID option: [$OPTARG]${NC}"
            usage
            exit 1
            ;;
    esac
done

# Check if no arguments provided
if [ $# -eq 0 ]; then
    usage
    exit 2
fi

# Validate arguments
if [ -z "$NAMESPACE" ]; then
    echo -e "${RED}❌ Namespace is required. Please specify using -n or -N${NC}"
    usage
    exit 1
fi

if [ "$SETUP" = false ] && [ "$EXTRACT_TOKEN" = false ]; then
    echo -e "${RED}❌ Must specify either -s/-S (setup), -t/-T (token), or both${NC}"
    usage
    exit 1
fi

# Main execution
check_prerequisites

if [ "$SETUP" = true ]; then
    setup_service_account
fi

if [ "$EXTRACT_TOKEN" = true ]; then
    extract_token
fi

echo -e "${GREEN}🎉 Script completed successfully!${NC}"