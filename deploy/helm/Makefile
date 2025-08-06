# Makefile for RAG Deployment
# Replaces the original deploy.sh script with additional uninstall functionality
ifeq ($(NAMESPACE),)
ifeq (,$(filter depend install-ingestion-pipeline list-models% generate-model-config help,$(MAKECMDGOALS)))
$(error NAMESPACE is not set)
endif
endif

MAKEFLAGS += --no-print-directory

# Default values
POSTGRES_USER ?= postgres
POSTGRES_PASSWORD ?= rag_password
POSTGRES_DBNAME ?= rag_blueprint
HF_TOKEN ?= $(shell bash -c 'read -r -p "Enter Hugging Face Token: " HF_TOKEN; echo $$HF_TOKEN')
RAG_CHART := rag
METRIC_MCP_RELEASE_NAME ?= metrics-api
METRIC_MCP_CHART_PATH ?= metrics-api
METRIC_UI_RELEASE_NAME ?= ui
METRIC_UI_CHART_PATH ?= ui
TOLERATIONS_TEMPLATE=[{"key":"$(1)","effect":"NoSchedule","operator":"Exists"}]
GEN_MODEL_CONFIG_PREFIX = "/tmp/gen_model_config"

# Unified model configuration map
# Contains all model details: external/internal, API key requirements, service mappings
# Load model configuration from separate JSON file
MODEL_CONFIG_JSON := $(shell cat model-config.json | jq -c .)

# Variable to hold the dynamically generated model configuration
DYNAMIC_MODEL_CONFIG_JSON :=

# Extract only non-external models for deployment
LLM := llama-3-2-3b-instruct
LLM_JSON := $(shell echo '["$(LLM_JSON)"]')

# If using extra tools that require API Keys set the LLAMA_STACK_ENV variable with key, value pairs
# LLAMA_STACK_ENV ?= {Key1: "Value1", Key2: "Value2" etc.}

#ingestion pipeline configuration
SOURCE ?= S3
EMBEDDING_MODEL ?= all-MiniLM-L6-v2
INGESTION_PIPELINE_NAME ?= demo-rag-vector-db
INGESTION_PIPELINE_VERSION ?= 1.0
ACCESS_KEY_ID ?= $(MINIO_USER)
SECRET_ACCESS_KEY ?= $(MINIO_PASSWORD)
BUCKET_NAME ?= documents
ENDPOINT_URL ?= http://minio:9000
REGION ?= us-east-1
# PDF file path variable for upload-pdf target
PDF_DIR = ../../notebooks
S3_TEMPLATE={"access_key_id":"$(1)","secret_access_key":"$(2)","bucket_name":"$(3)","endpoint_url":"$(4)","region":"$(5)"}

# CUSTOM VALUES (full path) FOR EXTRA INGESTION PIPELINE
# CUSTOM_INGESTION_PIPELINE_VALUES = ~/my-values.yaml
# CUSTOM_INGESTION_PIPELINE_NAME ?= my-pipeline

# Alerting configuration
SLACK_WEBHOOK_URL ?= $(shell bash -c 'read -r -p "Enter SLACK_WEBHOOK_URL: " SLACK_URL; echo $$SLACK_URL')
ALERTING_RELEASE_NAME ?= alerting

helm_llm_service_args = \
    --set llm-service.secret.hf_token=$(HF_TOKEN) \
    $(if $(DEVICE),--set llm-service.device='$(DEVICE)',) \
    $(if $(LLM),--set global.models.$(LLM).enabled=true,) \
    $(if $(SAFETY),--set global.models.$(SAFETY).enabled=true,) \
    $(if $(LLM_TOLERATION),--set-json global.models.$(LLM).tolerations='$(call TOLERATIONS_TEMPLATE,$(LLM_TOLERATION))',) \
    $(if $(SAFETY_TOLERATION),--set-json global.models.$(SAFETY).tolerations='$(call TOLERATIONS_TEMPLATE,$(SAFETY_TOLERATION))',) \
    $(if $(RAW_DEPLOYMENT),--set llm-service.rawDeploymentMode=$(RAW_DEPLOYMENT),)

helm_llama_stack_args = \
    $(if $(LLM),--set global.models.$(LLM).enabled=true,) \
    $(if $(SAFETY),--set global.models.$(SAFETY).enabled=true,) \
    $(if $(LLM_URL),--set global.models.$(LLM).url='$(LLM_URL)',) \
    $(if $(SAFETY_URL),--set global.models.$(SAFETY).url='$(SAFETY_URL)',) \
    $(if $(LLM_API_TOKEN),--set global.models.$(LLM).apiToken='$(LLM_API_TOKEN)',) \
    $(if $(SAFETY_API_TOKEN),--set global.models.$(SAFETY).apiToken='$(SAFETY_API_TOKEN)',) \
    $(if $(LLAMA_STACK_ENV),--set-json llama-stack.secrets='$(LLAMA_STACK_ENV)',) \
    $(if $(RAW_DEPLOYMENT),--set llama-stack.rawDeploymentMode=$(RAW_DEPLOYMENT),)

helm_pgvector_args = \
    --set pgvector.secret.user=$(POSTGRES_USER) \
    --set pgvector.secret.password=$(POSTGRES_PASSWORD) \
    --set pgvector.secret.dbname=$(POSTGRES_DBNAME)

# Default target
# Validate that LLM variable is set and non-empty
.PHONY: validate-llm
validate-llm:
	@if [ -z "$(LLM)" ]; then \
		echo "\n❌ Error: LLM variable is not set or empty. Please set LLM=<model_name>"; \
		exit 1; \
	fi

.PHONY: help
help:
	@echo "Available targets:"
	@echo "  list-models   - List available models"
	@echo "  generate-model-config - Generate JSON config for specified LLM using template"
	@echo "  install       - Install backend services only (llm-service, llama-stack, pgvector)"
	@echo "  install-ingestion-pipeline - Install extra ingestion pipelines (must be on the same namespace as the RAG deployment)"
	@echo "  uninstall     - Uninstall the RAG deployment and clean up resources"
	@echo "  status        - Check status of the deployment"
	@echo "  patch-config  - Enable Alertmanager and configure cross-project alerting"
	@echo "  revert-config - Remove namespace from cross-project alerting configuration"
	@echo "  create-secret - Create/update Kubernetes Secret with Slack Webhook URL"
	@echo "  install-alerts - Install alerting Helm chart"
	@echo "  uninstall-alerts - Uninstall alerting and related resources"
	@echo ""
	@echo "Configuration options (set via environment variables or make arguments):"
	@echo "  NAMESPACE                - Target namespace (default: llama-stack-rag)"
	@echo "  HF_TOKEN                 - Hugging Face Token (will prompt if not provided)"
	@echo "  DEVICE                	  - Deploy models on cpu or gpu (default)"
	@echo "  {SAFETY,LLM}             - Model id as defined in values (eg. llama-3-2-1b-instruct)"
	@echo "  {SAFETY,LLM}_URL         - Model URL"
	@echo "  {SAFETY,LLM}_API_TOKEN   - Model API token for remote models"
	@echo "  {SAFETY,LLM}_TOLERATION  - Model pod toleration"
	@echo "  ALERTS                   - Set to TRUE to install alerting with main deployment"
	@echo "  CUSTOM_INGESTION_PIPELINE_VALUES - Custom ingestion pipeline values (full path)"
	@echo "  CUSTOM_INGESTION_PIPELINE_NAME   - Custom ingestion pipeline name"
	@echo "  LLAMA_STACK_ENV          - List of environment variables for llama-stack (eg. {TAVILY_SEARCH_API_KEY: \"<Your Tavily Search API Key here>\"})"


# Create namespace and deploy
namespace:
	@if oc get namespace $(NAMESPACE) > /dev/null 2>&1; then \
		echo "✅ Namespace $(NAMESPACE) exists."; \
	else \
		echo "Namespace $(NAMESPACE) not found. Creating one!"; \
		oc create namespace $(NAMESPACE); \
		echo "✅ Namespace $(NAMESPACE) created..."; \
	fi

	@echo "Setting [$(NAMESPACE)] as default namespace..."
	@oc project $(NAMESPACE) > /dev/null


.PHONY: depend
depend:
	@echo "Updating Helm dependencies..."
	@helm dependency update $(RAG_CHART) || exit 1


.PHONY: list-models
list-models: depend
	@helm template dummy-release $(RAG_CHART) --set llm-service._debugListModels=true | grep ^model:


.PHONY: install-metric-mcp
install-metric-mcp: namespace
	@echo "Installing MCP by generating dynamic model configuration for $(LLM)"
	@$(MAKE) generate-model-config LLM=$(LLM) > /dev/null 2>&1

	# TODO (SG): Do we need to get the URL for the model - it's already set earlier in the script
	@echo "Getting URL for model: $(LLM)"
	@TMP_LLM_URL=$$(oc get inferenceservice $(LLM) -n $(NAMESPACE) -o jsonpath='{.status.url}'); \
	echo "Detected TMP_LLM_URL for $(LLM): $$TMP_LLM_URL"

	@echo "Checking ClusterRole grafana-prometheus-reader..."
	@(echo "modelConfig:"; cat $(GEN_MODEL_CONFIG_PREFIX)-final_config.json | sed 's/^/  /') > $(GEN_MODEL_CONFIG_PREFIX)-for_helm.yaml; \
	if oc get clusterrole grafana-prometheus-reader > /dev/null 2>&1; then \
		echo "ClusterRole exists. Deploying without creating Grafana role..."; \
		helm upgrade --install $(METRIC_MCP_RELEASE_NAME) $(METRIC_MCP_CHART_PATH) -n $(NAMESPACE) \
			--set rbac.createGrafanaRole=false \
			--set-json listModels.modelId.enabledModelIds='$(LLM_JSON)' \
			-f $(GEN_MODEL_CONFIG_PREFIX)-for_helm.yaml; \
	else \
		echo "ClusterRole does not exist. Deploying and creating Grafana role..."; \
		helm upgrade --install $(METRIC_MCP_RELEASE_NAME) $(METRIC_MCP_CHART_PATH) -n $(NAMESPACE) \
			--set rbac.createGrafanaRole=true \
			--set-json listModels.modelId.enabledModelIds='$(LLM_JSON)' \
			-f $(GEN_MODEL_CONFIG_PREFIX)-for_helm.yaml; \
	fi

	@echo "Files used for Metric MCP deployment:"
	@echo "  - $(GEN_MODEL_CONFIG_PREFIX)-for_helm.yaml"
	@echo "  - $(GEN_MODEL_CONFIG_PREFIX)-final_config.json"
	@echo "  - $(GEN_MODEL_CONFIG_PREFIX)-list_models_output.txt"
	

.PHONY: install-metric-ui
install-metric-ui: namespace
	@echo "Deploying Metric UI"
	helm upgrade --install $(METRIC_UI_RELEASE_NAME) $(METRIC_UI_CHART_PATH) -n $(NAMESPACE)

.PHONY: install-rag
install-rag: namespace
	@$(eval LLM_SERVICE_ARGS := $(call helm_llm_service_args))
	@$(eval LLAMA_STACK_ARGS := $(call helm_llama_stack_args))
	@$(eval PGVECTOR_ARGS := $(call helm_pgvector_args))
	@echo "Installing $(RAG_CHART) helm chart (backend services only)"
	@helm -n $(NAMESPACE) upgrade --install $(RAG_CHART) $(RAG_CHART) \
	--atomic --timeout 25m \
	$(LLM_SERVICE_ARGS) \
	$(LLAMA_STACK_ARGS) \
	$(PGVECTOR_ARGS)
	@echo "Waiting for model services to deploy. It will take around 10-15 minutes depending on the size of the model..."
	@oc wait -n $(NAMESPACE) --for=condition=Ready --timeout=60m inferenceservice --all ||:
	@echo "$(RAG_CHART) installed successfully"

.PHONY: install
install: namespace depend validate-llm install-rag install-metric-mcp install-metric-ui delete-jobs
	@if [ "$(ALERTS)" = "TRUE" ]; then \
		echo "ALERTS flag is set to TRUE. Installing alerting..."; \
		$(MAKE) install-alerts NAMESPACE=$(NAMESPACE); \
	fi
	@echo "Installation complete."

# Uninstall the deployment and clean up
.PHONY: uninstall
uninstall:
	@echo "→ Uninstalling $(RAG_CHART) helm chart"
	@helm -n $(NAMESPACE) uninstall $(RAG_CHART) --ignore-not-found
	@echo "\n→ Removing pgvector and minio PVCs from $(NAMESPACE)"
	@oc get pvc -n $(NAMESPACE) -o custom-columns=NAME:.metadata.name | grep -E '^(pg|minio)-data' | xargs -I {} oc delete pvc -n $(NAMESPACE) {} ||:
	@if helm list -n $(NAMESPACE) -q | grep -q "^$(ALERTING_RELEASE_NAME)$$"; then \
		echo "\n→ Detected alerting chart $(ALERTING_RELEASE_NAME). Uninstalling alerting..."; \
		$(MAKE) uninstall-alerts NAMESPACE=$(NAMESPACE); \
	fi
	@echo "\n→ Deleting remaining pods in namespace $(NAMESPACE)"
	@oc delete pods -n $(NAMESPACE) --all

	@echo "\n→ Uninstalling $(METRIC_UI_RELEASE_NAME) helm chart"
	@helm -n $(NAMESPACE) uninstall $(METRIC_UI_RELEASE_NAME) --ignore-not-found
	@echo "\n→ Uninstalling $(METRIC_MCP_RELEASE_NAME) helm chart"
	@helm -n $(NAMESPACE) uninstall $(METRIC_MCP_RELEASE_NAME) --ignore-not-found

	@echo "\nChecking for any remaining resources in namespace $(NAMESPACE)..."
	@$(MAKE) status

	@echo "\nIf you want to completely remove the namespace, run: oc delete project $(NAMESPACE)"
	@echo "Remaining resources in namespace $(NAMESPACE):"

# Install extra ingestion pipelines
.PHONY: install-ingestion-pipeline
install-ingestion-pipeline:
	helm -n $(NAMESPACE) install $(CUSTOM_INGESTION_PIPELINE_NAME) rag/charts/ingestion-pipeline-0.1.0.tgz -f $(CUSTOM_INGESTION_PIPELINE_VALUES)

# -- Alerting targets --

# Patches the user-workload-monitoring ConfigMap by enabling Alertmanager and adding namespace to namespacesWithoutLabelEnforcement
.PHONY: patch-config
patch-config: namespace
	@echo "Patching user-workload-monitoring-config ConfigMap..."
	@CURRENT_CONFIG=$$(oc get configmap user-workload-monitoring-config \
		-n openshift-user-workload-monitoring \
		-o jsonpath='{.data.config\.yaml}'); \
	if [ -z "$$CURRENT_CONFIG" ]; then \
		CURRENT_CONFIG="{}"; \
	fi; \
	EXISTING_NAMESPACES=$$(echo "$$CURRENT_CONFIG" | yq eval '.namespacesWithoutLabelEnforcement[]' - 2>/dev/null | paste -sd, -); \
	if [ -n "$$EXISTING_NAMESPACES" ]; then \
		if echo "$$EXISTING_NAMESPACES" | grep -q "$(NAMESPACE)"; then \
			NAMESPACE_ARRAY="[\"$$(echo "$$EXISTING_NAMESPACES" | sed 's/,/", "/g')\"]"; \
		else \
			NAMESPACE_ARRAY="[\"$$(echo "$$EXISTING_NAMESPACES" | sed 's/,/", "/g')\", \"$(NAMESPACE)\"]"; \
		fi; \
	else \
		NAMESPACE_ARRAY="[\"$(NAMESPACE)\"]"; \
	fi; \
	BASE_CONFIG=$$(echo "$$CURRENT_CONFIG" | \
		yq eval '. as $$item ireduce ({}; . * $$item) | \
		.alertmanager = (.alertmanager // {}) | \
		.alertmanager.enabled = true | \
		.alertmanager.enableAlertmanagerConfig = true | \
		del(.namespacesWithoutLabelEnforcement)' -); \
	NEW_CONFIG="$$BASE_CONFIG"$$'\n'"namespacesWithoutLabelEnforcement: $$NAMESPACE_ARRAY"; \
	oc patch configmap user-workload-monitoring-config \
		-n openshift-user-workload-monitoring \
		--type merge \
		-p "$$(echo '{"data":{"config.yaml":""}}' | jq --arg config "$$NEW_CONFIG" '.data."config.yaml" = $$config')"
	@echo "ConfigMap patched successfully. Alertmanager enabled and cross-project alerting set up for namespace $(NAMESPACE)."

# Revert patched user-workload-monitoring ConfigMap by removing namespace from namespacesWithoutLabelEnforcement
.PHONY: revert-config
revert-config: namespace
	@echo "Reverting user-workload-monitoring-config ConfigMap..."
	@CURRENT_CONFIG=$$(oc get configmap user-workload-monitoring-config \
		-n openshift-user-workload-monitoring \
		-o jsonpath='{.data.config\.yaml}'); \
	if [ -z "$$CURRENT_CONFIG" ]; then \
		echo "ConfigMap not found or empty. Nothing to revert."; \
		exit 0; \
	fi; \
	EXISTING_NAMESPACES=$$(echo "$$CURRENT_CONFIG" | yq eval '.namespacesWithoutLabelEnforcement[]' - 2>/dev/null | paste -sd, -); \
	if [ -z "$$EXISTING_NAMESPACES" ]; then \
		echo "No namespaces found in namespacesWithoutLabelEnforcement. Nothing to revert."; \
		exit 0; \
	fi; \
	if ! echo "$$EXISTING_NAMESPACES" | grep -q "$(NAMESPACE)"; then \
		echo "Namespace $(NAMESPACE) not found in namespacesWithoutLabelEnforcement. Nothing to revert."; \
		exit 0; \
	fi; \
	FILTERED_NAMESPACES=$$(echo "$$EXISTING_NAMESPACES" | tr ',' '\n' | grep -v "^$(NAMESPACE)$$" | paste -sd, -); \
	if [ -z "$$FILTERED_NAMESPACES" ]; then \
		BASE_CONFIG=$$(echo "$$CURRENT_CONFIG" | \
			yq eval '. as $$item ireduce ({}; . * $$item) | \
			del(.namespacesWithoutLabelEnforcement)' -); \
		NEW_CONFIG="$$BASE_CONFIG"; \
	else \
		NAMESPACE_ARRAY="[\"$$(echo "$$FILTERED_NAMESPACES" | sed 's/,/", "/g')\"]"; \
		BASE_CONFIG=$$(echo "$$CURRENT_CONFIG" | \
			yq eval '. as $$item ireduce ({}; . * $$item) | \
			del(.namespacesWithoutLabelEnforcement)' -); \
		NEW_CONFIG="$$BASE_CONFIG"$$'\n'"namespacesWithoutLabelEnforcement: $$NAMESPACE_ARRAY"; \
	fi; \
	oc patch configmap user-workload-monitoring-config \
		-n openshift-user-workload-monitoring \
		--type merge \
		-p "$$(echo '{"data":{"config.yaml":""}}' | jq --arg config "$$NEW_CONFIG" '.data."config.yaml" = $$config')"
	@echo "ConfigMap reverted successfully. Namespace $(NAMESPACE) removed from namespacesWithoutLabelEnforcement."

# Request Slack URL from user and create/update a Kubernetes Secret
.PHONY: create-secret
create-secret: namespace
	@echo "Creating/Updating 'alerts-secrets' with Slack Webhook URL in namespace $(NAMESPACE)..."
	@oc create secret generic alerts-secrets \
		--from-literal=slack-webhook-url='$(SLACK_WEBHOOK_URL)' \
		--namespace $(NAMESPACE) \
		--dry-run=client -o yaml | oc apply -f -
	@echo "Secret 'alerts-secrets' created/updated in namespace $(NAMESPACE)."

.PHONY: install-alerts
install-alerts: patch-config create-secret 
	@echo "Installing/Upgrading Helm chart $(ALERTING_RELEASE_NAME) in namespace $(NAMESPACE)..."
	@helm upgrade --install $(ALERTING_RELEASE_NAME) ./alerting --namespace $(NAMESPACE)
	@echo "Alerting Helm chart deployment complete."

.PHONY: uninstall-alerts
uninstall-alerts: revert-config
	@echo "Uninstalling Helm chart $(ALERTING_RELEASE_NAME) from namespace $(NAMESPACE)"
	@helm uninstall $(ALERTING_RELEASE_NAME) --namespace $(NAMESPACE)
	@echo "Deleting secret 'alerts-secrets' in namespace $(NAMESPACE)"
	@oc delete secret alerts-secrets -n $(NAMESPACE) || true
	@echo "Alerting cleanup complete for namespace $(NAMESPACE)."

# Delete all jobs in the namespace
.PHONY: delete-jobs
delete-jobs:
	@echo "Deleting all jobs in namespace $(NAMESPACE)"
	@oc delete jobs -n $(NAMESPACE) --all ||:
	@echo "Job deletion completed"

# Generate model configuration JSON for the specified LLM
.PHONY: generate-model-config
generate-model-config: validate-llm
	@echo "→ Generating model configuration for LLM: $(LLM)"

	@echo "  → Running list-models to find available models..."; \
	$(MAKE) list-models > $(GEN_MODEL_CONFIG_PREFIX)-list_models_output.txt 2>&1; \
	echo "  → list-models output saved to $(GEN_MODEL_CONFIG_PREFIX)-list_models_output.txt"; \
	MODEL_LINE=$$(grep "model: $(LLM) (" $(GEN_MODEL_CONFIG_PREFIX)-list_models_output.txt); \
	echo "  → Searching for model: $(LLM)"; \
	if [ -z "$$MODEL_LINE" ]; then \
		echo "\n❌ Error: Model '$(LLM)' not found in available models"; \
		echo "\n→ Available models:"; \
		cat $(GEN_MODEL_CONFIG_PREFIX)-list_models_output.txt; \
		exit 1; \
	fi; \
	echo "  → Found MODEL_LINE: $$MODEL_LINE"; \
	echo "  → Trying to extract MODEL_NAME and MODEL_ID from MODEL_LINE"; \
	MODEL_NAME=$$(echo "$$MODEL_LINE" | sed 's/model: \([^(]*\)(.*)/\1/' | tr -d '[:space:]'); \
	MODEL_ID=$$(echo "$$MODEL_LINE" | sed 's/model: [^(]*(\([^)]*\))/\1/' | tr -d '[:space:]'); \
	echo "  → Extracted MODEL_NAME: $$MODEL_NAME, MODEL_ID: $$MODEL_ID"; \
	echo "→ Generating JSON configuration..."; \
	sed "s|\$$MODEL_ID|$$MODEL_ID|g; s|\$$MODEL_NAME|$$MODEL_NAME|g" default-model.json.template > $(GEN_MODEL_CONFIG_PREFIX)-new_model_config.json; \
	echo "  → Merging with existing MODEL_CONFIG_JSON..."; \
	echo "✅ Final merged configuration is saved in $(GEN_MODEL_CONFIG_PREFIX)-final_config.json"; \
	jq -s '.[0] * .[1]' $(GEN_MODEL_CONFIG_PREFIX)-new_model_config.json model-config.json > $(GEN_MODEL_CONFIG_PREFIX)-final_config.json; \
	rm -f $(GEN_MODEL_CONFIG_PREFIX)-new_model_config.json


# Check deployment status
.PHONY: status
status:
	@echo "\nListing pods..."
	@oc get pods -n $(NAMESPACE) || true

	@echo "\nListing services..."
	@oc get svc -n $(NAMESPACE) || true

	@echo "\nListing routes..."
	@oc get routes -n $(NAMESPACE) || true

	@echo "\nListing secrets..."
	@oc get secrets -n $(NAMESPACE) | grep huggingface-secret || true

	@echo "\nListing pvcs..."
	@oc get pvc -n $(NAMESPACE) || true
