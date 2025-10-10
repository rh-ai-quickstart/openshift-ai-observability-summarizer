#!/bin/bash

# Common utilities for OpenShift operator management scripts

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Debug mode (global variable)
DEBUG="false"

# Function to check if a tool exists
check_tool_exists() {
    local tool="$1"
    if ! command -v "$tool" &> /dev/null; then
        echo -e "${RED}❌ $tool is required but not installed${NC}"
        exit 1
    fi
}

# Function to check if a file exists
check_file() {
    local file="$1"
    local description="$2"
    if [ ! -f "$file" ]; then
        echo -e "${RED}❌ $description file not found: $file${NC}"
        exit 1
    fi
}

# Function to check if logged in to OpenShift cluster
check_openshift_login() {
    if ! oc whoami &> /dev/null; then
        echo -e "${RED}❌ Not logged in to OpenShift cluster${NC}"
        echo -e "${YELLOW}   Please run: oc login${NC}"
        exit 1
    fi
}

# Function to check OpenShift CLI and login status
check_openshift_prerequisites() {
    [[ "$DEBUG" == "true" ]] && echo -e "${BLUE}🔍 Checking prerequisites...${NC}"
    
    # Check if oc CLI is installed
    check_tool_exists "oc"
    
    # Check if logged in to OpenShift cluster
    check_openshift_login
    
    [[ "$DEBUG" == "true" ]] && echo -e "${GREEN}✅ Prerequisites check passed${NC}"
}
