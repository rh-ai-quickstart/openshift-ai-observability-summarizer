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

readonly OBSERVABILITY_CRDS="monitoring.rhobs perses.dev observability.openshift.io"
readonly OTEL_CRDS="opentelemetry.io"
readonly TEMPO_CRDS="tempo.grafana.com"

# Function to display usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -c/-C OPERATOR_NAME          Check if operator is installed"
    echo "  -i/-I OPERATOR_NAME          Install operator (simple names supported)"
    echo "  -u/-U OPERATOR_NAME          Uninstall operator (simple names supported)"
    echo "  -f/-F YAML_FILE              YAML file for operator install/uninstall (optional)"
    echo "  -n/-N NAMESPACE              Namespace for operator install/uninstall (REQUIRED)"
    echo "  -d/-D                        Debug mode"
    echo "  -h, --help                   Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 -c observability              # Check Cluster Observability Operator"
    echo "  $0 -i observability -n openshift-cluster-observability-operator  # Install Cluster Observability Operator"
    echo "  $0 -u observability -n openshift-cluster-observability-operator  # Uninstall Cluster Observability Operator"
    echo "  $0 -i otel -n openshift-opentelemetry-operator  # Install OpenTelemetry Operator"
    echo "  $0 -u otel -n openshift-opentelemetry-operator  # Uninstall OpenTelemetry Operator"
    echo "  $0 -i tempo -n openshift-tempo-operator  # Install Tempo Operator"
    echo "  $0 -u tempo -n openshift-tempo-operator  # Uninstall Tempo Operator"
    echo "  $0 -i tempo -n custom-namespace  # Install Tempo Operator in custom namespace"
    echo "  $0 -u tempo -n custom-namespace  # Uninstall Tempo Operator in custom namespace"
    echo "  $0 -i custom-operator -n custom-namespace -f custom.yaml  # Install with custom YAML in custom namespace"
    echo "  $0 -u custom-operator -n custom-namespace -f custom.yaml  # Uninstall with custom YAML in custom namespace"
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
    local OPERATOR_FULL_NAME=""
    local YAML_FILE=""
    local ACTION=""
    local NAMESPACE=""

    # Parse standard arguments using getopts
    while getopts "c:C:i:I:u:U:f:F:n:N:dD:hH" opt; do
        case $opt in
            c|C) ACTION="$OPERATOR_ACTION_CHECK"
                 OPERATOR_NAME="$OPTARG"
                 OPERATOR_FULL_NAME=$(get_operator_full_name "$OPERATOR_NAME") || exit 1
                 ;;
            i|I) ACTION="$OPERATOR_ACTION_INSTALL"
                 OPERATOR_NAME="$OPTARG"
                 ;;
            u|U) ACTION="$OPERATOR_ACTION_UNINSTALL"
                 OPERATOR_NAME="$OPTARG"
                 ;;
            f|F) YAML_FILE="$OPTARG"
                 ;;
            n|N) NAMESPACE="$OPTARG"
                 ;;
            d|D) DEBUG="true"
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


    # Determine operator details if YAML file not provided
    if [ -z "$YAML_FILE" ]; then
        [[ "$DEBUG" == "true" ]] && echo -e "${BLUE} **** 📋 Auto-detecting operator and YAML file for: $OPERATOR_NAME${NC}"
        OPERATOR_NAME=$(get_operator_full_name "$OPERATOR_NAME") || exit 1
        YAML_FILE=$(get_operator_yaml "$OPERATOR_NAME") || exit 1
        [[ "$DEBUG" == "true" ]] && echo -e "${BLUE}📋 Auto-detected operator: $OPERATOR_NAME${NC}"
        [[ "$DEBUG" == "true" ]] && echo -e "${BLUE}📋 Auto-detected YAML file: $YAML_FILE${NC}"
    fi

    # Check if operator is installed
    local is_installed=false
    check_operator "$OPERATOR_NAME" && is_installed=true

    # Execute check/install/uninstall action based on operator status
    case "$ACTION" in
        "$OPERATOR_ACTION_CHECK")
            if [ "$is_installed" = true ]; then
              if [ "$DEBUG" == "true" ]; then
                echo -e "${GREEN}✅ Operator $OPERATOR_NAME is installed${NC}"
              else
                echo -e "${GREEN}✅ Installed${NC}"
              fi
            else
              if [ "$DEBUG" == "true" ]; then
                echo -e "${RED}❌ Operator $OPERATOR_NAME is not installed${NC}"
              else
                echo -e "${RED}❌ Not installed${NC}"
              fi
            fi
            exit 0
            ;;
        "$OPERATOR_ACTION_INSTALL")
            validate_namespace "$OPERATOR_ACTION_INSTALL"
            if [ "$is_installed" = true ]; then
                echo -e "${GREEN}✅ $OPERATOR_NAME already installed${NC}"
                exit 0
            fi
            install_operator "$OPERATOR_NAME" "$YAML_FILE" "$NAMESPACE"
            ;;
        "$OPERATOR_ACTION_UNINSTALL")
            validate_namespace "$OPERATOR_ACTION_UNINSTALL"
            if [ "$is_installed" = false ]; then
                echo -e "${YELLOW}⚠️  Operator $OPERATOR_NAME is not installed${NC}"
                exit 0
            fi
            uninstall_operator "$OPERATOR_NAME" "$YAML_FILE" "$NAMESPACE"
            ;;
    esac
}

# Function to validate namespace for install/uninstall operations
validate_namespace() {
    local action="$1"

    if [ -z "$NAMESPACE" ]; then
        echo -e "${RED}❌ Namespace is required for install/uninstall operations${NC}"
        echo -e "${YELLOW}   Please specify namespace with -n NAMESPACE${NC}"
        # usage
        exit 1
    fi

    if [ "$action" = "$OPERATOR_ACTION_INSTALL" ]; then
        # For install: namespace will be created by the YAML if it doesn't exist
        [[ "$DEBUG" == "true" ]] && echo -e "${BLUE}  📋 Installing in namespace: $NAMESPACE${NC}"
    elif [ "$action" = "$OPERATOR_ACTION_UNINSTALL" ]; then
        # For uninstall: namespace must exist
        if ! oc get namespace "$NAMESPACE" >/dev/null 2>&1; then
            echo -e "${RED}❌ Namespace '$NAMESPACE' does not exist${NC}"
            echo -e "${YELLOW}   Cannot uninstall from non-existent namespace${NC}"
            exit 1
        else
            [[ "$DEBUG" == "true" ]] && echo -e "${BLUE}  📋 Using namespace: $NAMESPACE${NC}"
        fi
    fi
}

# Function to check if an operator exists
check_operator() {
    local operator_name="$1"
    [[ "$DEBUG" == "true" ]] && echo -e "${BLUE}📋 Checking operator: $operator_name${NC}"    
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
        "$OPERATOR_OBSERVABILITY"|"$OPERATOR_OBSERVABILITY_ALT"|"$FULL_NAME_OBSERVABILITY")
            echo "$FULL_NAME_OBSERVABILITY"
            ;;
        "$OPERATOR_OTEL"|"$OPERATOR_OTEL_ALT")
            echo "$FULL_NAME_OTEL"
            ;;
        "$OPERATOR_TEMPO"|"$FULL_NAME_TEMPO")
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
        "$OPERATOR_OBSERVABILITY"|"$OPERATOR_OBSERVABILITY_ALT"|"$FULL_NAME_OBSERVABILITY")
            echo "$YAML_OBSERVABILITY"
            ;;
        "$OPERATOR_OTEL"|"$OPERATOR_OTEL_ALT"|"$FULL_NAME_OTEL")
            echo "$YAML_OTEL"
            ;;
        "$OPERATOR_TEMPO"|"$FULL_NAME_TEMPO")
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

# Function to get CRD patterns for an operator
get_operator_crds() {
    local operator_name="$1"

    case "$operator_name" in
        "$FULL_NAME_OBSERVABILITY")
            echo "$OBSERVABILITY_CRDS"
            ;;
        "$FULL_NAME_OTEL")
            echo "$OTEL_CRDS"
            ;;
        "$FULL_NAME_TEMPO")
            echo "$TEMPO_CRDS"
            ;;
        *)
            echo ""
            ;;
    esac
}

# Function to delete an operator
uninstall_operator() {
    local operator_name="$1"
    local yaml_file="$2"
    local namespace="$3"
    local yaml_path=$(get_yaml_path "$yaml_file")

    echo -e "${YELLOW}🗑️  Uninstalling $operator_name (using YAML file: $yaml_path)...${NC}"

    # Namespace validation is already done by validate_namespace function

    # Get the subscription name from YAML to find the specific CSV
    local subscription_name=$(grep -A2 "kind: Subscription" "$yaml_path" | grep "name:" | awk '{print $2}')
    echo -e "${BLUE}  📋 Found subscription: $subscription_name${NC}"

    # Get the CSV name from subscription status BEFORE deleting subscription
    # Example CSVs: cluster-observability-operator.v1.2.2, opentelemetry-operator.v0.135.0-1, tempo-operator.v0.18.0-1
    local csv_name=$(oc get subscription "$subscription_name" -n "$namespace" -o jsonpath='{.status.installedCSV}' 2>/dev/null)

    echo -e "${BLUE}  📋 Step 1: Deleting Subscription and OperatorGroup...${NC}"
    echo -e "${BLUE}     → This prevents OLM from recreating the operator${NC}"
    # Delete subscription FIRST to prevent OLM from recreating the operator
    # We use individual resource deletion instead of 'oc delete -f' to preserve the namespace
    oc delete subscription,operatorgroup --all -n "$namespace" --ignore-not-found=true

    echo -e "${BLUE}  📋 Step 2: Deleting ClusterServiceVersion (CSV)...${NC}"
    if [ -n "$csv_name" ] && [ "$csv_name" != "null" ]; then
        echo -e "${BLUE}     → Deleting CSV: $csv_name${NC}"
        oc delete csv "$csv_name" -n "$namespace" --ignore-not-found=true
    else
        echo -e "${YELLOW}     ⚠️  No CSV found for subscription $subscription_name${NC}"
        echo -e "${BLUE}     → You can manually delete CSVs by running:${NC}"
        echo -e "${BLUE}       oc delete csv -n $namespace --all --ignore-not-found=true${NC}"
    fi

    echo -e "${BLUE}  📋 Step 3: Deleting CRDs to prevent operator resurrection...${NC}"
    # Get CRD patterns for this operator
    local crd_patterns=$(get_operator_crds "$operator_name")
    if [ -n "$crd_patterns" ]; then
        for pattern in $crd_patterns; do
            echo -e "${BLUE}     → Finding CRDs matching pattern: $pattern${NC}"
            local crds=$(oc get crd -o name | grep "$pattern" | cut -d'/' -f2)
            if [ -n "$crds" ]; then
                echo -e "${BLUE}     → Deleting CRDs: $crds${NC}"
                echo "$crds" | xargs -r oc delete crd --ignore-not-found=true
            else
                echo -e "${YELLOW}     ⚠️  No CRDs found matching pattern: $pattern${NC}"
            fi
        done
    else
        echo -e "${YELLOW}  ⚠️  No CRD patterns defined for operator $operator_name${NC}"
        echo -e "${YELLOW}  ⚠️  You may need to manually delete CRDs to fully remove the operator${NC}"
    fi

    echo -e "${BLUE}  📋 Step 4: Deleting operator resource: $operator_name${NC}"
    # Delete the operator resource directly
    oc delete operator "$operator_name" --ignore-not-found=true --wait=false

    # Wait for OLM to clean up the operator resource (max 2 minutes)
    echo -e "${BLUE}     → Waiting for OLM to clean up operator resource...${NC}"
    local wait_attempts=24  # 2 minutes with 5-second intervals
    local wait_count=0
    while [ $wait_count -lt $wait_attempts ]; do
        if ! oc get operator "$operator_name" >/dev/null 2>&1; then
            echo -e "${GREEN}     ✅ Operator resource removed${NC}"
            break
        fi
        wait_count=$((wait_count + 1))
        if [ $wait_count -lt $wait_attempts ]; then
            sleep 5
        fi
    done

    if [ $wait_count -eq $wait_attempts ]; then
        echo -e "${YELLOW}     ⚠️  Operator resource still exists after 2 minutes${NC}"
        echo -e "${YELLOW}     ⚠️  OLM will eventually clean it up (can take 30-60 minutes)${NC}"
        echo -e "${YELLOW}     ⚠️  The operator is functionally removed (no pods/deployments running)${NC}"
    fi

    echo -e "${GREEN}✅ $operator_name deletion completed!${NC}"
    echo -e "${BLUE}  ℹ️  Note: Namespace '$namespace' was preserved${NC}"
}

# Function to install an operator
install_operator() {
    local operator_name="$1"
    local yaml_file="$2"
    local namespace="$3"
    echo -e "${BLUE}📦 → Installing $operator_name...${NC}"

    local yaml_path=$(get_yaml_path "$yaml_file")

    # Namespace creation is handled by validate_namespace function

    # Use envsubst to substitute the NAMESPACE variable
    # Note: We use 'oc create' instead of 'oc apply' because the YAML uses 'generateName' for OperatorGroup
    # which is only supported by 'create'. We add --save-config to enable future kubectl apply operations.
    # Suppress "AlreadyExists" errors for namespaces since uninstall preserves them by design.
    export NAMESPACE="$namespace"
    envsubst < "$yaml_path" | oc create --save-config -f - 2>&1 | grep -v "namespaces.*already exists" || true

    echo -e "${GREEN}  ✅ $operator_name installation initiated${NC}"

    # Wait for operator to be installed (operator resource exists)
    echo -e "${BLUE}  ⏳ Waiting for operator resource to be created...${NC}"

    local max_attempts=60  # 10 minutes with 10-second intervals
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if check_operator "$operator_name"; then
            echo -e "${GREEN}  ✅ Operator resource created${NC}"
            break
        fi

        attempt=$((attempt + 1))
        if [ $attempt -lt $max_attempts ]; then
            echo -e "${BLUE}  ⏳ Attempt $attempt/$max_attempts - waiting 10 seconds...${NC}"
            sleep 10
        fi
    done

    if [ $attempt -eq $max_attempts ]; then
        echo -e "${RED}  ❌ Operator resource was not created after 10 minutes${NC}"
        exit 1
    fi

    # Get the subscription name to check CSV status
    local subscription_name=$(grep -A2 "kind: Subscription" "$yaml_path" | grep "name:" | awk '{print $2}')

    # Wait for CSV to reach Succeeded phase
    echo -e "${BLUE}  ⏳ Waiting for CSV to reach Succeeded phase...${NC}"
    attempt=0
    max_attempts=60  # 10 minutes

    while [ $attempt -lt $max_attempts ]; do
        local csv_phase=$(oc get subscription "$subscription_name" -n "$namespace" -o jsonpath='{.status.installedCSV}' 2>/dev/null)
        if [ -n "$csv_phase" ] && [ "$csv_phase" != "null" ]; then
            local phase=$(oc get csv "$csv_phase" -n "$namespace" -o jsonpath='{.status.phase}' 2>/dev/null)
            if [ "$phase" = "Succeeded" ]; then
                echo -e "${GREEN}  ✅ CSV $csv_phase is in Succeeded phase${NC}"
                break
            fi
            echo -e "${BLUE}  ⏳ CSV phase: $phase (attempt $attempt/$max_attempts)${NC}"
        else
            echo -e "${BLUE}  ⏳ Waiting for CSV to be created (attempt $attempt/$max_attempts)${NC}"
        fi

        attempt=$((attempt + 1))
        if [ $attempt -lt $max_attempts ]; then
            sleep 10
        fi
    done

    if [ $attempt -eq $max_attempts ]; then
        echo -e "${RED}  ❌ CSV did not reach Succeeded phase after 10 minutes${NC}"
        exit 1
    fi

    # Wait for CRDs to be created
    local crd_patterns=$(get_operator_crds "$operator_name")
    if [ -n "$crd_patterns" ]; then
        echo -e "${BLUE}  ⏳ Waiting for CRDs to be created...${NC}"
        attempt=0
        max_attempts=30  # 5 minutes with 10-second intervals

        local all_crds_created=false
        while [ $attempt -lt $max_attempts ]; do
            all_crds_created=true
            for pattern in $crd_patterns; do
                local crds=$(oc get crd -o name 2>/dev/null | grep "$pattern" || true)
                if [ -z "$crds" ]; then
                    echo -e "${BLUE}  ⏳ Waiting for CRDs matching pattern: $pattern (attempt $attempt/$max_attempts)${NC}"
                    all_crds_created=false
                    break
                fi
            done

            if [ "$all_crds_created" = true ]; then
                echo -e "${GREEN}  ✅ All CRDs created successfully${NC}"
                break
            fi

            attempt=$((attempt + 1))
            if [ $attempt -lt $max_attempts ]; then
                sleep 10
            fi
        done

        if [ $attempt -eq $max_attempts ]; then
            echo -e "${RED}  ❌ CRDs were not created after 5 minutes${NC}"
            exit 1
        fi
    fi

    echo -e "${GREEN}✅ $operator_name installation completed and fully ready!${NC}"
}



# Main execution
main() {
    [[ "$DEBUG" == "true" ]] && echo -e "${BLUE}🚀 OpenShift Operator Management${NC}"
    [[ "$DEBUG" == "true" ]] && echo "=================================="
    
    check_openshift_prerequisites

    # Check if envsubst is installed (required for variable substitution)
    check_tool_exists "envsubst"

    parse_args "$@"
}

# Run main function
main "$@"