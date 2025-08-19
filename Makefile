# Makefile for OpenShift AI Observability Summarizer
# Handles building and pushing container images for the application components and deployment on OpenShift

# NAMESPACE validation for deployment targets
ifeq ($(NAMESPACE),)
ifeq (,$(filter install-local depend install-ingestion-pipeline list-models% generate-model-config help build build-metrics-api build-ui build-alerting push push-metrics-api push-ui push-alerting install-observability uninstall-observability clean config test,$(MAKECMDGOALS)))
$(error NAMESPACE is not set)
endif
endif

MAKEFLAGS += --no-print-directory

# Default values
REGISTRY ?= quay.io
ORG ?= ecosystem-appeng
IMAGE_PREFIX ?= aiobs
VERSION ?= 0.1.2
PLATFORM ?= linux/amd64

# Container image names
METRICS_API_IMAGE = $(REGISTRY)/$(ORG)/$(IMAGE_PREFIX)-metrics-api
METRICS_UI_IMAGE = $(REGISTRY)/$(ORG)/$(IMAGE_PREFIX)-metrics-ui
METRICS_ALERTING_IMAGE = $(REGISTRY)/$(ORG)/$(IMAGE_PREFIX)-metrics-alerting


# Build tools
DOCKER ?= docker
PODMAN ?= podman
BUILD_TOOL ?= $(DOCKER)

# Detect if podman is available and prefer it
ifeq ($(shell which podman 2>/dev/null),)
    BUILD_TOOL := $(DOCKER)
else
    BUILD_TOOL := $(PODMAN)
endif

# Deployment configuration
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
# Load model configuration from separate JSON file
MODEL_CONFIG_JSON := $(shell cat deploy/helm/model-config.json | jq -c .)

# Variable to hold the dynamically generated model configuration
DYNAMIC_MODEL_CONFIG_JSON :=

# Extract only non-external models for deployment
LLM := llama-3-2-3b-instruct
LLM_JSON := $(shell echo '["$(LLM_JSON)"]')

# Alerting configuration
SLACK_WEBHOOK_URL ?= $(shell bash -c 'read -r -p "Enter SLACK_WEBHOOK_URL: " SLACK_URL; echo $$SLACK_URL')
ALERTING_RELEASE_NAME ?= alerting

# Observability configuration
OBSERVABILITY_NAMESPACE ?= observability-hub # currently hard-coded in instrumentation.yaml
INSTRUMENTATION_PATH ?= observability/otel-collector/scripts/instrumentation.yaml

# Helm argument templates

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

.PHONY: help
help:
	@echo "OpenShift AI Observability Summarizer - Build & Deploy"
	@echo ""
	@echo "Available targets:"
	@echo ""
	@echo "Build & Push:"
	@echo "  build              - Build all container images"
	@echo "  build-metrics-api  - Build FastAPI backend (metrics-api)"
	@echo "  build-ui           - Build Streamlit UI (metric-ui)"
	@echo "  build-alerting     - Build Alerting Service (metric-alerting)"
	@echo "  push               - Push all container images to registry"
	@echo "  push-metrics-api   - Push metrics-api image"
	@echo "  push-ui            - Push metric-ui image"
	@echo "  push-alerting      - Push metric-alerting image"
	@echo ""
	@echo "Deployment:"
	@echo "  install            - Deploy to OpenShift using Helm"
	@echo "  install-with-alerts - Deploy with alerting enabled"
	@echo "  install-local      - Set up local development environment"
	@echo "  install-rag        - Install RAG backend services only"
	@echo "  install-metric-mcp - Install metrics API only"
	@echo "  install-metric-ui  - Install UI only"
	@echo "  uninstall          - Uninstall from OpenShift"
	@echo "  status             - Check deployment status"
	@echo "  list-models        - List available models"
	@echo "  generate-model-config - Generate JSON config for specified LLM using template"
	@echo "  install-ingestion-pipeline - Install extra ingestion pipelines"
	@echo ""
	@echo "Tracing:"
	@echo "  install-observability - Install TempoStack and OpenTelemetry Collector for tracing"
	@echo "  setup-tracing - Enable auto-instrumentation for tracing in target namespace"
	@echo "  remove-tracing - Disable auto-instrumentation for tracing in target namespace"
	@echo "  uninstall-observability - Uninstall observability components (Tempo and OTEL Collector)"
	@echo ""
	@echo "Alerting:"
	@echo "  install-alerts     - Install alerting Helm chart"
	@echo "  uninstall-alerts   - Uninstall alerting and related resources"
	@echo "  patch-config       - Enable Alertmanager and configure cross-project alerting"
	@echo "  revert-config      - Remove namespace from cross-project alerting configuration"
	@echo "  create-secret      - Create/update Kubernetes Secret with Slack Webhook URL"
	@echo ""
	@echo "Utilities:"
	@echo "  clean              - Clean up local images"
	@echo "  config             - Show current configuration"
	@echo ""
	@echo "Tests:"
	@echo "  test               - Run unit tests with coverage"
	@echo ""
	@echo "Configuration (set via environment variables):"
	@echo "  REGISTRY           - Container registry (default: quay.io)"
	@echo "  ORG                - Account or org name (default: ecosystem-appeng)"
	@echo "  IMAGE_PREFIX       - Image prefix (default: aiobs)"
	@echo "  VERSION            - Image version (default: 0.1.0)"
	@echo "  PLATFORM           - Target platform (default: linux/amd64)"
	@echo "  BUILD_TOOL         - Build tool: docker or podman (auto-detected)"
	@echo "  NAMESPACE          - OpenShift namespace for deployment"
	@echo "  HF_TOKEN           - Hugging Face Token (will prompt if not provided)"
	@echo "  DEVICE             - Deploy models on cpu or gpu (default)"
	@echo "  LLM                - Model id (eg. llama-3-2-3b-instruct)"
	@echo "  SAFETY             - Safety model id"
	@echo "  ALERTS             - Set to TRUE to install alerting with main deployment"
	@echo "  SLACK_WEBHOOK_URL  - Slack Webhook URL for alerting (will prompt if not provided)"
	@echo ""

.PHONY: build
build: build-metrics-api build-ui build-alerting
	@echo "✅ All container images built successfully"

.PHONY: build-metrics-api
build-metrics-api:
	@echo "🔨 Building FastAPI Backend (metrics-api)..."
	@cd src && $(BUILD_TOOL) buildx build --platform $(PLATFORM) \
		-f api/Dockerfile \
		-t $(METRICS_API_IMAGE):$(VERSION) \
		.
	@echo "✅ metrics-api image built: $(METRICS_API_IMAGE):$(VERSION)"

.PHONY: build-ui
build-ui:
	@echo "🔨 Building Streamlit UI (metric-ui)..."
	@$(BUILD_TOOL) buildx build --platform $(PLATFORM) \
		-f src/ui/Dockerfile \
		-t $(METRICS_UI_IMAGE):$(VERSION) \
		src
	@echo "✅ metrics-ui image built: $(METRICS_UI_IMAGE):$(VERSION)"

.PHONY: build-alerting
build-alerting:
	@echo "🔨 Building Alerting Service (metric-alerting)..."
	@$(BUILD_TOOL) buildx build --platform $(PLATFORM) \
		-f src/alerting/Dockerfile \
		-t $(METRICS_ALERTING_IMAGE):$(VERSION) \
		src
	@echo "✅ metrics-alerting image built: $(METRICS_ALERTING_IMAGE):$(VERSION)"

.PHONY: push
push: push-metrics-api push-ui push-alerting
	@echo "✅ All container images pushed successfully"



.PHONY: push-metrics-api
push-metrics-api:
	@echo "📤 Pushing metrics-api image..."
	@$(BUILD_TOOL) push $(METRICS_API_IMAGE):$(VERSION)
	@echo "✅ metrics-api image pushed"

.PHONY: push-ui
push-ui:
	@echo "📤 Pushing metric-ui image..."
	@$(BUILD_TOOL) push $(METRICS_UI_IMAGE):$(VERSION)
	@echo "✅ metric-ui image pushed"

.PHONY: push-alerting
push-alerting:
	@echo "📤 Pushing metric-alerting image..."
	@$(BUILD_TOOL) push $(METRICS_ALERTING_IMAGE):$(VERSION)
	@echo "✅ metric-alerting image pushed"



# Create namespace and deploy
.PHONY: namespace
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
	@cd deploy/helm && helm dependency update $(RAG_CHART) || exit 1


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
		cd deploy/helm && helm upgrade --install $(METRIC_MCP_RELEASE_NAME) $(METRIC_MCP_CHART_PATH) -n $(NAMESPACE) \
			--set rbac.createGrafanaRole=false \
			--set-json listModels.modelId.enabledModelIds='$(LLM_JSON)' \
			-f $(GEN_MODEL_CONFIG_PREFIX)-for_helm.yaml; \
	else \
		echo "ClusterRole does not exist. Deploying and creating Grafana role..."; \
		cd deploy/helm && helm upgrade --install $(METRIC_MCP_RELEASE_NAME) $(METRIC_MCP_CHART_PATH) -n $(NAMESPACE) \
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
	@cd deploy/helm && helm upgrade --install $(METRIC_UI_RELEASE_NAME) $(METRIC_UI_CHART_PATH) -n $(NAMESPACE)

.PHONY: install-rag
install-rag: namespace
	@$(eval LLM_SERVICE_ARGS := $(call helm_llm_service_args))
	@$(eval LLAMA_STACK_ARGS := $(call helm_llama_stack_args))
	@$(eval PGVECTOR_ARGS := $(call helm_pgvector_args))
	@echo "Installing $(RAG_CHART) helm chart (backend services only)"
	@cd deploy/helm && helm -n $(NAMESPACE) upgrade --install $(RAG_CHART) $(RAG_CHART) \
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
	@echo "Installing OpenTelemetry Collector and Tempo..."
	@$(MAKE) install-observability
	@$(MAKE) setup-tracing NAMESPACE=$(NAMESPACE)
	@echo "Installation complete."

.PHONY: install-with-alerts
install-with-alerts:
	@if [ -z "$(NAMESPACE)" ]; then \
		echo "❌ Error: NAMESPACE is required for deployment"; \
		echo "Usage: make install-with-alerts NAMESPACE=your-namespace"; \
		exit 1; \
	fi
	@echo "🚀 Deploying to OpenShift namespace: $(NAMESPACE) with alerting"
	@$(MAKE) namespace depend validate-llm install-rag install-metric-mcp install-metric-ui delete-jobs install-alerts NAMESPACE=$(NAMESPACE)
	@echo "✅ Deployment with alerting completed"

# Delete all jobs in the namespace
.PHONY: delete-jobs
delete-jobs:
	@echo "Deleting all jobs in namespace $(NAMESPACE)"
	@oc delete jobs -n $(NAMESPACE) --all ||:
	@echo "Job deletion completed"

# Check deployment status
.PHONY: status
status:
	@if [ -z "$(NAMESPACE)" ]; then \
		echo "❌ Error: NAMESPACE is required for status check"; \
		echo "Usage: make status NAMESPACE=your-namespace"; \
		exit 1; \
	fi
	@echo "📊 Checking deployment status in namespace: $(NAMESPACE)"
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


.PHONY: uninstall
uninstall:
	@if [ -z "$(NAMESPACE)" ]; then \
		echo "❌ Error: NAMESPACE is required for uninstallation"; \
		echo "Usage: make uninstall NAMESPACE=your-namespace"; \
		exit 1; \
	fi
	@echo "🔍 Checking OpenShift credentials..."
	@if ! oc whoami >/dev/null 2>&1; then \
		echo "❌ Error: Not logged in to OpenShift or credentials have expired"; \
		echo "   Please run: oc login"; \
		exit 1; \
	fi
	@echo "✅ OpenShift credentials are valid"
	@echo "🗑️  Uninstalling from OpenShift namespace: $(NAMESPACE)"
	@echo "Uninstalling $(RAG_CHART) helm chart"
	- @helm -n $(NAMESPACE) uninstall $(RAG_CHART) --ignore-not-found
	@echo "Removing pgvector and minio PVCs from $(NAMESPACE)"
	- @oc get pvc -n $(NAMESPACE) -o custom-columns=NAME:.metadata.name | grep -E '^(pg|minio)-data' | xargs -I {} oc delete pvc -n $(NAMESPACE) {} ||:
	@if helm list -n $(NAMESPACE) -q | grep -q "^$(ALERTING_RELEASE_NAME)$$"; then \
		echo "→ Detected alerting chart $(ALERTING_RELEASE_NAME). Uninstalling alerting..."; \
		$(MAKE) uninstall-alerts NAMESPACE=$(NAMESPACE); \
	fi
	@echo "Deleting remaining pods in namespace $(NAMESPACE)"
	- @oc delete pods -n $(NAMESPACE) --all
	@echo "Uninstalling $(METRIC_UI_RELEASE_NAME) helm chart"
	- @helm -n $(NAMESPACE) uninstall $(METRIC_UI_RELEASE_NAME)
	@echo "Uninstalling $(METRIC_MCP_RELEASE_NAME) helm chart"
	- @helm -n $(NAMESPACE) uninstall $(METRIC_MCP_RELEASE_NAME)
	@echo "Removing tracing instrumentation from namespace $(NAMESPACE)"
	- @$(MAKE) remove-tracing NAMESPACE=$(NAMESPACE) || true
	@echo "Uninstalling observability stack"
	- @$(MAKE) uninstall-observability || true
	@echo "Checking for any remaining resources in namespace $(NAMESPACE)..."
	@echo "If you want to completely remove the namespace, run: oc delete project $(NAMESPACE)"
	@echo "Remaining resources in namespace $(NAMESPACE):"
	@echo "Listing pods..."
	@oc get pods -n $(NAMESPACE) || true
	@echo "Listing services..."
	@oc get svc -n $(NAMESPACE) || true
	@echo "Listing routes..."
	@oc get routes -n $(NAMESPACE) || true
	@echo "Listing secrets..."
	@oc get secrets -n $(NAMESPACE) | grep huggingface-secret || true
	@echo "Listing pvcs..."
	@oc get pvc -n $(NAMESPACE) || true
	@echo "✅ Uninstallation completed"

# Install extra ingestion pipelines
.PHONY: install-ingestion-pipeline
install-ingestion-pipeline:
	@if [ -z "$(CUSTOM_INGESTION_PIPELINE_NAME)" ] || [ -z "$(CUSTOM_INGESTION_PIPELINE_VALUES)" ]; then \
		echo "❌ Error: CUSTOM_INGESTION_PIPELINE_NAME and CUSTOM_INGESTION_PIPELINE_VALUES must be set"; \
		echo "Usage: make install-ingestion-pipeline CUSTOM_INGESTION_PIPELINE_NAME=my-pipeline CUSTOM_INGESTION_PIPELINE_VALUES=/path/to/values.yaml"; \
		exit 1; \
	fi
	@echo "Installing extra ingestion pipeline: $(CUSTOM_INGESTION_PIPELINE_NAME)"
	@cd deploy/helm && helm -n $(NAMESPACE) install $(CUSTOM_INGESTION_PIPELINE_NAME) rag/charts/ingestion-pipeline-0.1.0.tgz -f $(CUSTOM_INGESTION_PIPELINE_VALUES)

# List available models
.PHONY: list-models
list-models: depend
	@echo "📋 Available models for deployment:"
	@cd deploy/helm && helm template dummy-release $(RAG_CHART) --set llm-service._debugListModels=true | grep ^model:

.PHONY: install-local
install-local:
	@echo "🚀 Setting up local development environment..."
	@bash -c '\
		uv sync && \
		chmod +x ./scripts/local-dev.sh && \
		source .venv/bin/activate && ./scripts/local-dev.sh && \
		echo "✅ Local development environment setup completed" \
	'

.PHONY: clean
clean:
	@echo "🧹 Cleaning up local images..."
	@ERRORS=0; \
	if ! $(BUILD_TOOL) rmi $(METRICS_API_IMAGE):$(VERSION) 2>/dev/null; then \
		echo "⚠️  Could not remove $(METRICS_API_IMAGE):$(VERSION) (may not exist)"; \
		ERRORS=$$((ERRORS + 1)); \
	fi; \
	if ! $(BUILD_TOOL) rmi $(METRICS_UI_IMAGE):$(VERSION) 2>/dev/null; then \
		echo "⚠️  Could not remove $(METRICS_UI_IMAGE):$(VERSION) (may not exist)"; \
		ERRORS=$$((ERRORS + 1)); \
	fi; \
	if ! $(BUILD_TOOL) rmi $(METRICS_ALERTING_IMAGE):$(VERSION) 2>/dev/null; then \
		echo "⚠️  Could not remove $(METRICS_ALERTING_IMAGE):$(VERSION) (may not exist)"; \
		ERRORS=$$((ERRORS + 1)); \
	fi; \
	if [ $$ERRORS -eq 0 ]; then \
		echo "✅ All images cleaned successfully"; \
	else \
		echo "⚠️  Cleanup completed with $$ERRORS warning(s)"; \
	fi

# Run tests
.PHONY: test
test:	
	@echo "🧪 Running tests with coverage..."
	@uv sync --group test
	@uv run pytest -v --cov=src --cov-report=html --cov-report=term

# Convenience targets for common workflows
.PHONY: build-and-push
build-and-push: build push
	@echo "✅ Build and push workflow completed"

.PHONY: build-deploy
build-deploy: build push install
	@echo "✅ Build, push, and deploy workflow completed"

.PHONY: build-deploy-alerts
build-deploy-alerts: build push install-with-alerts
	@echo "✅ Build, push, and deploy with alerting workflow completed"

# Show current configuration
.PHONY: config
config:
	@echo "🔧 Current Build Configuration:"
	@echo "  Registry: $(REGISTRY)"
	@echo "  Org: $(ORG)"
	@echo "  Image Prefix: $(IMAGE_PREFIX)"
	@echo "  Version: $(VERSION)"
	@echo "  Platform: $(PLATFORM)"
	@echo "  Build Tool: $(BUILD_TOOL)"
	@echo "  Metrics API Image: $(METRICS_API_IMAGE):$(VERSION)"
	@echo "  Metric UI Image: $(METRICS_UI_IMAGE):$(VERSION)"
	@echo "  Metric Alerting Image: $(METRICS_ALERTING_IMAGE):$(VERSION)"

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
	@cd deploy/helm && helm upgrade --install $(ALERTING_RELEASE_NAME) ./alerting --namespace $(NAMESPACE)
	@echo "Alerting Helm chart deployment complete."

.PHONY: uninstall-alerts
uninstall-alerts: revert-config
	@echo "Uninstalling Helm chart $(ALERTING_RELEASE_NAME) from namespace $(NAMESPACE)"
	@cd deploy/helm && helm uninstall $(ALERTING_RELEASE_NAME) --namespace $(NAMESPACE)
	@echo "Deleting secret 'alerts-secrets' in namespace $(NAMESPACE)"
	@oc delete secret alerts-secrets -n $(NAMESPACE) || true
	@echo "Alerting cleanup complete for namespace $(NAMESPACE)."

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
	sed "s|\$$MODEL_ID|$$MODEL_ID|g; s|\$$MODEL_NAME|$$MODEL_NAME|g" deploy/helm/default-model.json.template > $(GEN_MODEL_CONFIG_PREFIX)-new_model_config.json; \
	echo "  → Merging with existing MODEL_CONFIG_JSON..."; \
	echo "✅ Final merged configuration is saved in $(GEN_MODEL_CONFIG_PREFIX)-final_config.json"; \
	jq -s '.[0] * .[1]' $(GEN_MODEL_CONFIG_PREFIX)-new_model_config.json deploy/helm/model-config.json > $(GEN_MODEL_CONFIG_PREFIX)-final_config.json; \
	rm -f $(GEN_MODEL_CONFIG_PREFIX)-new_model_config.json

# Validate that LLM variable is set and non-empty
.PHONY: validate-llm
validate-llm:
	@if [ -z "$(LLM)" ]; then \
		echo "\n❌ Error: LLM variable is not set or empty. Please set LLM=<model_name>"; \
		exit 1; \
	fi

.PHONY: install-observability
install-observability:
	@echo "Installing TempoStack and MinIO in namespace $(OBSERVABILITY_NAMESPACE)"
	@cd deploy/helm && helm upgrade --install tempo ./observability/tempo \
		--namespace $(OBSERVABILITY_NAMESPACE) \
		--create-namespace \
		--set global.namespace=$(OBSERVABILITY_NAMESPACE)

	@echo "Installing Open Telemetry Collector in namespace $(OBSERVABILITY_NAMESPACE)"
	@cd deploy/helm && helm upgrade --install otel-collector ./observability/otel-collector \
		--namespace $(OBSERVABILITY_NAMESPACE) \
		--create-namespace \
		--set global.namespace=$(OBSERVABILITY_NAMESPACE)

.PHONY: setup-tracing
setup-tracing: namespace
	@echo "Setting up auto-instrumentation for tracing in namespace $(NAMESPACE)"
	@cd deploy/helm && oc apply -f $(INSTRUMENTATION_PATH) -n $(NAMESPACE)
	@oc annotate namespace $(NAMESPACE) instrumentation.opentelemetry.io/inject-python="true" --overwrite

.PHONY: remove-tracing
remove-tracing: namespace
	@echo "Removing auto-instrumentation for tracing in namespace $(NAMESPACE)"
	@oc delete instrumentation python-instrumentation -n $(NAMESPACE)
	@oc annotate namespace $(NAMESPACE) instrumentation.opentelemetry.io/inject-python- --overwrite

.PHONY: uninstall-observability
uninstall-observability:
	@echo "Uninstalling TempoStack and MinIO and Otel Collector in namespace $(OBSERVABILITY_NAMESPACE)"
	@helm uninstall tempo -n $(OBSERVABILITY_NAMESPACE)
	@helm uninstall otel-collector -n $(OBSERVABILITY_NAMESPACE)
