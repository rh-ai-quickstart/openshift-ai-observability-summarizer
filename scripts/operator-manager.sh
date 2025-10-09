#!/bin/bash

# OpenShift Operator Management Script
# Handles installation and checking of OpenShift operators

# Source common utilities
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Function to display usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -c/-C OPERATOR_NAME          Check if operator is installed"
    echo "  -i/-I OPERATOR_NAME          Install operator (simple names supported)"
    echo "  -d/-D OPERATOR_NAME          Delete/uninstall operator (simple names supported)"
    echo "  -f/-F YAML_FILE              YAML file for operator installation (optional)"
    echo "  -h, --help                   Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 -c observability          # Check Cluster Observability Operator"
    echo "  $0 -i observability          # Install Cluster Observability Operator"
    echo "  $0 -d observability          # Delete Cluster Observability Operator"
    echo "  $0 -i otel                   # Install OpenTelemetry Operator"
    echo "  $0 -d otel                    # Delete OpenTelemetry Operator"
    echo "  $0 -i tempo                  # Install Tempo Operator"
    echo "  $0 -d tempo                   # Delete Tempo Operator"
    echo "  $0 -i custom-operator -f custom.yaml  # Install with custom YAML"
    echo ""
    echo "Available operators (simple names):"
    echo "  observability - Cluster Observability Operator"
    echo "  otel          - Red Hat build of OpenTelemetry Operator"
    echo "  tempo         - Tempo Operator"
}

# Function to parse command line arguments
parse_args() {
    # Check if no arguments provided
    if [ $# -eq 0 ]; then
        usage
        exit 2
    fi

    # Initialize variables
    OPERATOR_NAME=""
    YAML_FILE=""
    ACTION=""

    # Parse standard arguments using getopts
    while getopts "c:C:i:I:d:D:f:F:hH" opt; do
        case $opt in
            c|C) ACTION="check"
                 OPERATOR_NAME="$OPTARG"
                 ;;
            i|I) ACTION="install"
                 OPERATOR_NAME="$OPTARG"
                 ;;
            d|D) ACTION="delete"
                 OPERATOR_NAME="$OPTARG"
                 ;;
            f|F) YAML_FILE="$OPTARG"
                 ;;
            h|H) usage
               exit 0
               ;;
        esac
    done

    # Validate arguments
    if [ -z "$ACTION" ]; then
        echo -e "${RED}❌ No action specified. Please use -c to check or -i to install${NC}"
        usage
        exit 1
    fi

    if [ -z "$OPERATOR_NAME" ]; then
        echo -e "${RED}❌ Operator name is required${NC}"
        usage
        exit 1
    fi

    # For install action, determine operator details if not provided
    if [ "$ACTION" = "install" ] && [ -z "$YAML_FILE" ]; then
        OPERATOR_DETAILS=$(get_operator_details "$OPERATOR_NAME")
        if [ -n "$OPERATOR_DETAILS" ]; then
            # Split the result: operator_name|yaml_file
            OPERATOR_NAME=$(echo "$OPERATOR_DETAILS" | cut -d'|' -f1)
            YAML_FILE=$(echo "$OPERATOR_DETAILS" | cut -d'|' -f2)
            echo -e "${BLUE}📋 Auto-detected operator: $OPERATOR_NAME${NC}"
            echo -e "${BLUE}📋 Auto-detected YAML file: $YAML_FILE${NC}"
        else
            echo -e "${RED}❌ Unknown operator: $OPERATOR_NAME${NC}"
            echo -e "${YELLOW}   Available operators: observability, otel, tempo${NC}"
            echo -e "${YELLOW}   Or specify full operator name with -f flag${NC}"
            usage
            exit 1
        fi
    fi

    # For check action, also determine operator details if needed
    if [ "$ACTION" = "check" ]; then
        OPERATOR_DETAILS=$(get_operator_details "$OPERATOR_NAME")
        if [ -n "$OPERATOR_DETAILS" ]; then
            # Split the result: operator_name|yaml_file
            OPERATOR_NAME=$(echo "$OPERATOR_DETAILS" | cut -d'|' -f1)
            echo -e "${BLUE}📋 Checking operator: $OPERATOR_NAME${NC}"
        fi
    fi

    # Execute the action
    case "$ACTION" in
        "check")
            if check_operator "$OPERATOR_NAME"; then
                echo -e "${GREEN}✅ Operator $OPERATOR_NAME is installed${NC}"
                exit 0
            else
                echo -e "${RED}❌ Operator $OPERATOR_NAME is not installed${NC}"
                exit 1
            fi
            ;;
        "install")
            install_operator "$OPERATOR_NAME" "$YAML_FILE"
            ;;
        "delete")
            delete_operator "$OPERATOR_NAME"
            ;;
    esac
}

# Function to check if an operator exists
check_operator() {
    local operator_name="$1"
    if oc get operator "$operator_name" >/dev/null 2>&1; then
        return 0  # Operator exists
    else
        return 1  # Operator does not exist
    fi
}

# Function to get operator details from simple name
get_operator_details() {
    local operator_name="$1"

    case "$operator_name" in
        "observability"|"cluster-observability")
            echo "cluster-observability-operator.openshift-cluster-observability|cluster-observability.yaml"
            ;;
        "otel"|"opentelemetry")
            echo "opentelemetry-product.openshift-opentelemetry-operator|opentelemetry.yaml"
            ;;
        "tempo")
            echo "tempo-product.openshift-tempo-operator|tempo.yaml"
            ;;
        *)
            echo ""
            ;;
    esac
}

# Function to delete an operator
delete_operator() {
    local operator_name="$1"
    
    echo -e "${YELLOW}🗑️  Deleting $operator_name...${NC}"
    
    # Get operator details for namespace and subscription name
    local operator_details=$(get_operator_details "$operator_name")
    if [ -z "$operator_details" ]; then
        echo -e "${RED}❌ Unknown operator: $operator_name${NC}"
        echo -e "${YELLOW}   Available operators: observability, otel, tempo${NC}"
        return 1
    fi
    
    # Extract YAML file from operator details
    local yaml_file=$(echo "$operator_details" | cut -d'|' -f2)
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local yaml_path="$script_dir/operators/$yaml_file"
    
    # Check if operator exists first using the full name
    local full_operator_name=$(echo "$operator_details" | cut -d'|' -f1)
    if ! check_operator "$full_operator_name"; then
        echo -e "${YELLOW}  ⚠️  Operator $operator_name is not installed${NC}"
        return 0
    fi
    
    echo -e "${BLUE}  📋 Deleting operator using YAML: $yaml_file${NC}"
    
    # Use the same YAML file to delete the resources
    oc delete -f "$yaml_path" 2>/dev/null || true
    
    # Also delete the operator resource directly
    echo -e "${BLUE}  📋 Deleting operator resource: $full_operator_name${NC}"
    oc delete operator "$full_operator_name" 2>/dev/null || true
    
    echo -e "${GREEN}✅ $operator_name deletion completed!${NC}"
}

# Function to install an operator
install_operator() {
    local operator_name="$1"
    local yaml_file="$2"
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local yaml_path="$script_dir/operators/$yaml_file"

    # Validate YAML file exists
    if [ ! -f "$yaml_path" ]; then
        echo -e "${RED}❌ Error: YAML file not found: $yaml_path${NC}"
        exit 1
    fi

    echo -e "${BLUE}📦 Installing $operator_name...${NC}"

    # Check if operator is already installed
    if check_operator "$operator_name"; then
        echo -e "${GREEN}  ✅ $operator_name already installed${NC}"
        return 0
    fi

    echo -e "${YELLOW}  📦 Installing $operator_name...${NC}"

    # Apply the subscription
    oc apply -f "$yaml_path"

    echo -e "${GREEN}  ✅ $operator_name installation initiated${NC}"

    # Wait for operator to be installed
    echo -e "${BLUE}  ⏳ Waiting for operator to be ready...${NC}"
    
    local max_attempts=60  # 10 minutes with 10-second intervals
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if check_operator "$operator_name"; then
            echo -e "${GREEN}  ✅ $operator_name is ready${NC}"
            break
        fi
        
        attempt=$((attempt + 1))
        if [ $attempt -lt $max_attempts ]; then
            echo -e "${BLUE}  ⏳ Attempt $attempt/$max_attempts - waiting 10 seconds...${NC}"
            sleep 10
        fi
    done
    
    if [ $attempt -eq $max_attempts ]; then
        echo -e "${YELLOW}  ⚠️  $operator_name may still be installing${NC}"
    fi

    echo -e "${GREEN}✅ $operator_name installation completed!${NC}"
}



# Main execution
main() {
    echo -e "${BLUE}🚀 OpenShift Operator Management${NC}"
    echo "=================================="
    
    check_openshift_prerequisites
    parse_args "$@"
}

# Run main function
main "$@"