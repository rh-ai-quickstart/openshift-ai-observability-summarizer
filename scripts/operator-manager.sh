#!/bin/bash

# OpenShift Operator Management Script
# Handles installation/uninstallation and checking of OpenShift operators

# Source common utilities
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Operator name constants
readonly OPERATOR_OBSERVABILITY="observability"
readonly OPERATOR_OBSERVABILITY_ALT="cluster-observability"
readonly OPERATOR_OTEL="otel"
readonly OPERATOR_OTEL_ALT="opentelemetry"
readonly OPERATOR_TEMPO="tempo"

# Full operator names (subscription.namespace format)
readonly FULL_NAME_OBSERVABILITY="cluster-observability-operator.openshift-cluster-observability"
readonly FULL_NAME_OTEL="opentelemetry-product.openshift-opentelemetry-operator"
readonly FULL_NAME_TEMPO="tempo-product.openshift-tempo-operator"

# YAML file names
readonly YAML_OBSERVABILITY="cluster-observability.yaml"
readonly YAML_OTEL="opentelemetry.yaml"
readonly YAML_TEMPO="tempo.yaml"


readonly OPERATOR_ACTION_CHECK="check"
readonly OPERATOR_ACTION_INSTALL="install"
readonly OPERATOR_ACTION_UNINSTALL="uninstall"

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
    local OPERATOR_NAME=""
    local YAML_FILE=""
    local ACTION=""

    # Parse standard arguments using getopts
    while getopts "c:C:i:I:d:D:f:F:hH" opt; do
        case $opt in
            c|C) ACTION="$OPERATOR_ACTION_CHECK"
                 OPERATOR_NAME="$OPTARG"
                 OPERATOR_NAME=$(get_operator_full_name "$OPERATOR_NAME") || exit 1
                 ;;
            i|I) ACTION="$OPERATOR_ACTION_INSTALL"
                 OPERATOR_NAME="$OPTARG"
                 ;;
            d|D) ACTION="$OPERATOR_ACTION_UNINSTALL"
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

    # For install/uninstall actions, determine operator details if YAML file not provided
    if [ -z "$YAML_FILE" ] && { [ "$ACTION" = "$OPERATOR_ACTION_INSTALL" ] || [ "$ACTION" = "$OPERATOR_ACTION_UNINSTALL" ]; }; then
        OPERATOR_NAME=$(get_operator_full_name "$OPERATOR_NAME") || exit 1
        YAML_FILE=$(get_operator_yaml "$OPERATOR_NAME") || exit 1
        echo -e "${BLUE}📋 Auto-detected operator: $OPERATOR_NAME${NC}"
        echo -e "${BLUE}📋 Auto-detected YAML file: $YAML_FILE${NC}"
    fi

    # Check if operator is installed
    local is_installed=false
    check_operator "$OPERATOR_NAME" && is_installed=true

    # Execute check/install/uninstall action based on operator status
    case "$ACTION" in
        "$OPERATOR_ACTION_CHECK")
            if [ "$is_installed" = true ]; then
                echo -e "${GREEN}✅ Operator $OPERATOR_NAME is installed${NC}"
            else
                echo -e "${RED}❌ Operator $OPERATOR_NAME is not installed${NC}"
            fi
            exit 0
            ;;
        "$OPERATOR_ACTION_INSTALL")
            if [ "$is_installed" = true ]; then
                echo -e "${GREEN}✅ $OPERATOR_NAME already installed${NC}"
                exit 0
            fi
            install_operator "$OPERATOR_NAME" "$YAML_FILE"
            ;;
        "$OPERATOR_ACTION_UNINSTALL")
            if [ "$is_installed" = false ]; then
                echo -e "${YELLOW}⚠️  Operator $OPERATOR_NAME is not installed${NC}"
                exit 0
            fi
            uninstall_operator "$OPERATOR_NAME" "$YAML_FILE"
            ;;
    esac
}

# Function to check if an operator exists
check_operator() {
    local operator_name="$1"
    echo -e "${BLUE}📋 Checking operator: $operator_name${NC}"    
    if oc get operator "$operator_name" >/dev/null 2>&1; then
        return 0  # Operator exists
    else
        return 1  # Operator does not exist
    fi
}

# Function to get full operator name from simple name
get_operator_full_name() {
    local operator_name="$1"

    case "$operator_name" in
        "$OPERATOR_OBSERVABILITY"|"$OPERATOR_OBSERVABILITY_ALT")
            echo "$FULL_NAME_OBSERVABILITY"
            ;;
        "$OPERATOR_OTEL"|"$OPERATOR_OTEL_ALT")
            echo "$FULL_NAME_OTEL"
            ;;
        "$OPERATOR_TEMPO")
            echo "$FULL_NAME_TEMPO"
            ;;
        *)
            echo -e "${RED}❌ Unknown operator: $operator_name${NC}" >&2
            echo -e "${YELLOW}   Available operators: observability, otel, tempo${NC}" >&2
            exit 1
            ;;
    esac
}

# Function to get YAML file name from simple operator name
get_operator_yaml() {
    local operator_name="$1"

    case "$operator_name" in
        "$OPERATOR_OBSERVABILITY"|"$OPERATOR_OBSERVABILITY_ALT")
            echo "$YAML_OBSERVABILITY"
            ;;
        "$OPERATOR_OTEL"|"$OPERATOR_OTEL_ALT")
            echo "$YAML_OTEL"
            ;;
        "$OPERATOR_TEMPO")
            echo "$YAML_TEMPO"
            ;;
        *)
            echo -e "${RED}❌ Unknown operator: $operator_name${NC}" >&2
            echo -e "${YELLOW}   Available operators: observability, otel, tempo${NC}" >&2
            exit 1
            ;;
    esac
}

# Function to get full YAML path and validate it exists
get_yaml_path() {
    local yaml_file="$1"
    local yaml_path="$SCRIPT_DIR/operators/$yaml_file"

    if [ ! -f "$yaml_path" ]; then
        echo -e "${RED}❌ Error: YAML file not found: $yaml_path${NC}" >&2
        exit 1
    fi

    echo "$yaml_path"
}

# Function to delete an operator
uninstall_operator() {
    local operator_name="$1"
    local yaml_file="$2"

    echo -e "${YELLOW}🗑️  Uninstalling $operator_name...${NC}"

    local yaml_path=$(get_yaml_path "$yaml_file")

    # Get the subscription name from YAML
    local subscription_name=$(grep -A2 "kind: Subscription" "$yaml_path" | grep "name:" | awk '{print $2}')

    # Get the actual namespace where the operator is installed by querying the subscription
    local namespace=$(oc get subscription -A -o json | jq -r ".items[] | select(.metadata.name==\"$subscription_name\") | .metadata.namespace")

    if [ -z "$namespace" ]; then
        echo -e "${RED}❌ Could not determine namespace for operator $operator_name${NC}"
        return 1
    fi

    echo -e "${BLUE}  📋 Detected namespace: $namespace${NC}"

    echo -e "${BLUE}  📋 Step 1: Deleting ClusterServiceVersion (CSV)...${NC}"
    # Delete all CSVs in the operator namespace
    # This is critical - without deleting the CSV, the operator will be reinstalled
    oc delete csv -n "$namespace" --all --ignore-not-found=true

    echo -e "${BLUE}  📋 Step 2: Deleting Subscription and OperatorGroup...${NC}"
    # Delete subscription and operatorgroup but NOT the namespace
    # We use individual resource deletion instead of 'oc delete -f' to preserve the namespace
    oc delete subscription,operatorgroup --all -n "$namespace" --ignore-not-found=true

    echo -e "${BLUE}  📋 Step 3: Deleting operator resource: $operator_name${NC}"
    # Delete the operator resource directly
    oc delete operator "$operator_name" --ignore-not-found=true

    echo -e "${GREEN}✅ $operator_name deletion completed!${NC}"
    echo -e "${BLUE}  ℹ️  Note: Namespace '$namespace' was preserved${NC}"
}

# Function to install an operator
install_operator() {
    local operator_name="$1"
    local yaml_file="$2"

    echo -e "${BLUE}📦 Installing $operator_name...${NC}"

    local yaml_path=$(get_yaml_path "$yaml_file")

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