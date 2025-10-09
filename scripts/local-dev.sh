#!/bin/bash

# AI Observability Metric Summarizer - Local Development Script

# Source common utilities
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Configuration
PROMETHEUS_NAMESPACE="openshift-monitoring"
OBSERVABILITY_NAMESPACE="observability-hub"
THANOS_PORT=9090
TEMPO_PORT=8082
LLAMASTACK_PORT=8321
LLAMA_MODEL_PORT=8080
UI_PORT=8501
MCP_PORT=${MCP_PORT:-8085}

echo -e "${BLUE}🚀 AI Observability Metric Summarizer - Local Development Setup${NC}"
echo "=============================================================="

# Function to display usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -n/-N NAMESPACE              Default namespace for pods (required)"
    echo "  -m/-M NAMESPACE              Llama Model namespace (optional, use if model is in different namespace)"
    echo "  -c/-C CONFIG                 Model config source: 'local' or 'cluster' (default: local)"
    echo "  -l/-L LLM_MODEL              LLM model to generate config for (default: llama-3.2-3b-instruct, only used with -c local)"
    echo ""
    echo "Examples:"
    echo "  $0 -n default-ns                       # Use local config with default LLM (llama-3.2-3b-instruct)"
    echo "  $0 -N default-ns                       # Same as above (uppercase option)"
    echo "  $0 -n default-ns -m model-ns           # Model in different namespace, use default LLM"
    echo "  $0 -n default-ns -c cluster            # Use cluster model config instead of local"
    echo "  $0 -n default-ns -l llama-3.2-1b-instruct  # Generate config for llama-3.2-1b-instruct"
    echo "  $0 -n default-ns -l llama-3.1-8b-instruct  # Generate config for llama-3.1-8b-instruct"
}

# Function to parse command line arguments
parse_args() {
    # Check if no arguments provided
    if [ $# -eq 0 ]; then
        usage
        exit 2
    fi

    DEFAULT_NAMESPACE=""
    LLAMA_MODEL_NAMESPACE=""
    MODEL_CONFIG_SOURCE="local"  # Default to local
    LLM_MODEL=$(get_default_model)  # Optional LLM model for config generation

    # Parse standard arguments using getopts
    while getopts "n:N:m:M:c:C:l:L:h" opt; do
        case $opt in
            n|N) DEFAULT_NAMESPACE="$OPTARG"
                 ;;
            m|M) LLAMA_MODEL_NAMESPACE="$OPTARG"
                 ;;
            c|C) MODEL_CONFIG_SOURCE="$OPTARG"
                 ;;
            l|L) LLM_MODEL="$OPTARG"
                 ;;
            h) usage
               exit 0
               ;;
            *) echo -e "${RED}❌ INVALID option: [$OPTARG]${NC}"
               usage
               exit 1
               ;;
        esac
    done

    # Validate arguments
    if [ -z "$DEFAULT_NAMESPACE" ]; then
        echo -e "${RED}❌ Default namespace is required. Please specify using -n or -N${NC}"
        usage
        exit 1
    fi

    # Validate model config source
    if [[ "$MODEL_CONFIG_SOURCE" != "local" && "$MODEL_CONFIG_SOURCE" != "cluster" ]]; then
        echo -e "${RED}❌ Invalid model config source: $MODEL_CONFIG_SOURCE${NC}"
        echo -e "${YELLOW}   Valid options: 'local' or 'cluster'${NC}"
        usage
        exit 1
    fi

    # Set llama model namespace to default if not provided
    if [ -z "$LLAMA_MODEL_NAMESPACE" ]; then
        LLAMA_MODEL_NAMESPACE="$DEFAULT_NAMESPACE"
    fi
}

# Function to cleanup on exit
cleanup() {
    # Prevent multiple cleanup calls
    if [ "$CLEANUP_DONE" = "true" ]; then
        return
    fi
    CLEANUP_DONE=true

    echo -e "\n${YELLOW}🧹 Cleaning up services and port-forwards...${NC}"
    ensure_port_free "$MCP_PORT"
    ensure_port_free "$TEMPO_PORT"
    pkill -f "oc port-forward" || true
    pkill -f "mcp_server.main" || true
    pkill -f "streamlit run ui.py" || true

    # Deactivate virtual environment if it was activated
    if [ -n "$VIRTUAL_ENV" ]; then
        echo -e "${BLUE}🐍 Deactivating virtual environment...${NC}"
        deactivate
    fi

    echo -e "${GREEN}✅ Cleanup complete${NC}"
}

# Function to check prerequisites and activate virtual environment
check_prerequisites() {
    echo -e "${BLUE}🔍 Checking prerequisites...${NC}"

    # Check for virtual environment and activate it
    if [ -f ".venv/bin/activate" ]; then
        echo -e "${BLUE}🐍 Activating Python virtual environment...${NC}"
        source .venv/bin/activate
        echo -e "${GREEN}✅ Virtual environment activated${NC}"
    else
        echo -e "${YELLOW}⚠️  Virtual environment (.venv) not found${NC}"
        echo -e "${YELLOW}   Please create virtual environment by following README or DEV_GUIDE${NC}"
        exit 1
    fi

    check_tool_exists "oc"
    check_openshift_login

    echo -e "${GREEN}✅ Prerequisites check passed${NC}"
}

# Helper function to create port-forward command
create_port_forward() {
    local resource_name="$1"
    local local_port="$2"
    local remote_port="$3"
    local namespace="$4"
    local description="$5"
    local emoji="$6"

    # Check if resource name is found
    if [ -z "$resource_name" ]; then
        echo -e "${YELLOW}⚠️  $description resource NOT found in $namespace namespace. Exiting...${NC}"
        exit 1
    fi
    
    # Create port-forward
    oc port-forward "$resource_name" "$local_port:$remote_port" -n "$namespace" >/dev/null 2>&1 &
    echo -e "${GREEN}✅ Found $description: $emoji (resource: $resource_name, namespace: $namespace) available at: http://localhost:$local_port${NC}"
}

# Function to find and start port forwards
start_port_forwards() {
    echo -e "${BLUE}🔍 Finding pods and starting port-forwards...${NC}"

    THANOS_POD=$(oc get pods -n "$PROMETHEUS_NAMESPACE" -o name -l 'app.kubernetes.io/component=query-layer,app.kubernetes.io/instance=thanos-querier' | head -1)
    create_port_forward "$THANOS_POD" "$THANOS_PORT" "9090" "$PROMETHEUS_NAMESPACE" "Thanos" "📊"
    
    # Find LlamaStack pod
    LLAMASTACK_SERVICE=$(oc get services -n "$DEFAULT_NAMESPACE" -o name -l 'app.kubernetes.io/instance=rag, app.kubernetes.io/name=llamastack')
    create_port_forward "$LLAMASTACK_SERVICE" "$LLAMASTACK_PORT" "8321" "$DEFAULT_NAMESPACE" "LlamaStack" "🦙"
    
    # Find Llama Model service
    LLAMA_MODEL_SERVICE=$(oc get services -n "$LLAMA_MODEL_NAMESPACE" -o name -l "serving.kserve.io/inferenceservice=$LLM_MODEL, component=predictor")
    create_port_forward "$LLAMA_MODEL_SERVICE" "$LLAMA_MODEL_PORT" "8080" "$LLAMA_MODEL_NAMESPACE" "Llama Model" "🤖"
    
    # Find Tempo gateway service
    TEMPO_SERVICE=$(oc get services -n "$OBSERVABILITY_NAMESPACE" -o name -l 'app.kubernetes.io/name=tempo,app.kubernetes.io/component=gateway')
    create_port_forward "$TEMPO_SERVICE" "$TEMPO_PORT" "8080" "$OBSERVABILITY_NAMESPACE" "Tempo" "🔍"

    sleep 3  # Give port-forwards time to establish
}

# Ensure a TCP port is free by terminating any process listening on it
ensure_port_free() {
    local port=$1
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Port $port is in use. Attempting to free it...${NC}"
        # Try graceful termination first
        lsof -nP -iTCP:"$port" -sTCP:LISTEN -t | xargs -r kill || true
        sleep 1
        # Force kill if still listening
        if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
            lsof -nP -iTCP:"$port" -sTCP:LISTEN -t | xargs -r kill -9 || true
        fi
        if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
            echo -e "${RED}❌ Could not free port $port. Please free it and retry.${NC}"
            exit 1
        fi
        echo -e "${GREEN}✅ Port $port is now free${NC}"
    fi
}

# This function sets "MODEL_CONFIG" environment variable from cluster deployment or dynamically generated config
set_model_config() {
    if [ "$MODEL_CONFIG_SOURCE" = "local" ]; then
        # Generate model config dynamically (LLM_MODEL is optional, will use default if not specified)
        # Script is already sourced in main(), just call the function
        if generate_model_config "$LLM_MODEL"; then
            return 0
        else
            echo -e "${RED}❌ Failed to generate MODEL_CONFIG${NC}"
            exit 1
        fi
    else
        # Use cluster config
        echo -e "${BLUE}🔧 Setting up MODEL_CONFIG from cluster...${NC}"
        local MCP_SERVER_APP="mcp-server-app"
        MCP_SERVER_APP_DEPLOYMENT=$(oc get deploy $MCP_SERVER_APP -n "$DEFAULT_NAMESPACE" 2>/dev/null)
        if [ -n "$MCP_SERVER_APP_DEPLOYMENT" ]; then
            echo -e "${YELLOW}✅ Found [$MCP_SERVER_APP] deployment:\n$MCP_SERVER_APP_DEPLOYMENT${NC}"
            export $(oc set env deployment/$MCP_SERVER_APP --list  -n "$DEFAULT_NAMESPACE" | grep MODEL_CONFIG)
            if [ -n "$MODEL_CONFIG" ]; then
              echo -e "${GREEN}✅ CLUSTER MODEL_CONFIG set successfully${NC}"
              echo -e "${BLUE}   Available models: $(echo "$MODEL_CONFIG" | jq -r 'keys | join(", ")')${NC}"
            else
              echo -e "${RED}❌ Unable to set MODEL_CONFIG environment variable. It is required to run the UI locally.${NC}"
              exit 1
            fi
        else
            echo -e "${RED}❌ $MCP_SERVER_APP deployment not found. It is required to set MODEL_CONFIG.${NC}"
            exit 1
        fi
    fi
}

# Function to start local services
start_local_services() {
    echo -e "${BLUE}🏃 Starting local services...${NC}"
    
    # Get service account token
    TOKEN=$(oc whoami -t)
    
    # Set environment variables
    export PROMETHEUS_URL="http://localhost:$THANOS_PORT"
    export TEMPO_URL="https://localhost:$TEMPO_PORT"
    export TEMPO_TENANT_ID="dev"
    export TEMPO_TOKEN="$TOKEN"
    export LLAMA_STACK_URL="http://localhost:$LLAMASTACK_PORT/v1/openai/v1"
    export THANOS_TOKEN="$TOKEN"
    export MCP_URL="http://localhost:$MCP_PORT"
    export PROM_URL="$PROMETHEUS_URL"
    # Set log level (override with PYTHON_LOG_LEVEL=DEBUG for more verbose logging)
    export PYTHON_LOG_LEVEL="${PYTHON_LOG_LEVEL:-INFO}"

    # SSL verification settings for Tempo HTTPS
    export VERIFY_SSL=false
    export PYTHONHTTPSVERIFY=0

    # macOS weasyprint support
    export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_FALLBACK_LIBRARY_PATH"

    set_model_config

    # Start MCP server (HTTP transport)
    echo -e "${BLUE}🧩 Starting MCP Server (HTTP)...${NC}"
    ensure_port_free "$MCP_PORT"
    (cd src && \
      MCP_TRANSPORT_PROTOCOL=http \
      MODEL_CONFIG="$MODEL_CONFIG" \
      PROMETHEUS_URL="$PROMETHEUS_URL" \
      TEMPO_URL="$TEMPO_URL" \
      TEMPO_TENANT_ID="$TEMPO_TENANT_ID" \
      TEMPO_TOKEN="$TEMPO_TOKEN" \
      LLAMA_STACK_URL="$LLAMA_STACK_URL" \
      THANOS_TOKEN="$THANOS_TOKEN" \
      VERIFY_SSL="$VERIFY_SSL" \
      PYTHON_LOG_LEVEL="$PYTHON_LOG_LEVEL" \
      python3 -m mcp_server.main > /tmp/summarizer-mcp-server.log 2>&1) &
    MCP_SRV_PID=$!

    # Wait for MCP server to start
    sleep 3

    # Test MCP server health
    if curl -s --connect-timeout 5 "http://localhost:$MCP_PORT/health" | grep -q '"status"'; then
        echo -e "${GREEN}✅ MCP Server started successfully on port $MCP_PORT${NC}"
    else
        echo -e "${RED}❌ MCP Server failed to start${NC}"
        exit 1
    fi
    
    # Start Streamlit UI
    echo -e "${BLUE}🎨 Starting Streamlit UI...${NC}"
    (cd src/ui && \
      MCP_SERVER_URL="http://localhost:$MCP_PORT" \
      PYTHON_LOG_LEVEL="$PYTHON_LOG_LEVEL" \
      streamlit run ui.py --server.port $UI_PORT --server.address 0.0.0.0 --server.headless true > /tmp/summarizer-ui.log 2>&1) &
    UI_PID=$!
    
    # Wait for UI to start
    sleep 5
    
    # Show log file locations for debugging
    echo -e "${GREEN}📋 Log files for debugging (all in /tmp):${NC}"
    echo -e "   🔧 MCP Server: /tmp/summarizer-mcp-server.log"
    echo -e "   🎨 Streamlit UI: /tmp/summarizer-ui.log"
    echo -e "   📊 Metrics API: /tmp/summarizer-metrics-api.log"
    echo -e "   💡 To see live UI logs: tail -f /tmp/summarizer-ui.log"
    echo -e "   💡 To see all logs: tail -f /tmp/summarizer-*.log"

    echo -e "${GREEN}✅ All services started successfully!${NC}"
}

# Main execution
main() {
    # Source the shared script once (for model config generation and default model)
    source scripts/generate-model-config.sh

    parse_args "$@"
    check_prerequisites

    # Set cleanup trap only after successful prerequisite checks
    trap cleanup EXIT INT TERM

    echo ""
    echo -e "${BLUE}--------------------------------${NC}"
    echo -e "${BLUE}Configuration being used for setup:${NC}"
    echo -e "${BLUE}  DEFAULT_NAMESPACE: $DEFAULT_NAMESPACE${NC}"
    echo -e "${BLUE}  LLAMA_MODEL_NAMESPACE: $LLAMA_MODEL_NAMESPACE${NC}"
    echo -e "${BLUE}  MODEL_CONFIG_SOURCE: $MODEL_CONFIG_SOURCE${NC}"
    echo -e "${BLUE}  LLM_MODEL: $LLM_MODEL${NC}"
    echo -e "${BLUE}--------------------------------${NC}\n"

    start_port_forwards
    start_local_services
    
    echo -e "\n${GREEN}🎉 Setup complete! All services are running.${NC}"
    echo -e "\n${BLUE}📋 Services Available:${NC}"
    echo -e "   ${YELLOW}🎨 Streamlit UI: http://localhost:$UI_PORT${NC}"
    echo -e "   ${YELLOW}🧩 MCP Server (health): $MCP_URL/health${NC}"
    echo -e "   ${YELLOW}🧩 MCP HTTP Endpoint: $MCP_URL/mcp${NC}"
    echo -e "   ${YELLOW}📊 Prometheus: $PROMETHEUS_URL${NC}"
    echo -e "   ${YELLOW}🔍 TempoStack: $TEMPO_URL${NC}"
    echo -e "   ${YELLOW}🦙 LlamaStack: $LLAMA_STACK_URL${NC}"
    echo -e "   ${YELLOW}🤖 Llama Model: http://localhost:$LLAMA_MODEL_PORT${NC}"
    
    echo -e "\n${GREEN}🎯 Ready to use! Open your browser to http://localhost:$UI_PORT${NC}"
    echo -e "\n${YELLOW}📝 Note: Keep this terminal open to maintain all services${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop all services and cleanup${NC}"
    
    # Keep script running
    wait
}

# Run main function
main "$@"