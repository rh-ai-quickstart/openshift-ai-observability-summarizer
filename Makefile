# Makefile for OpenShift AI Observability Summarizer
# Handles building and pushing container images for the application components and deployment on OpenShift

# NAMESPACE validation for deployment targets
ifeq ($(NAMESPACE),)
ifeq (,$(filter install-local depend install-ingestion-pipeline list-models% generate-model-config help build build-ui build-alerting build-mcp-server push push-ui push-alerting push-mcp-server clean config test check-observability-drift install-operators uninstall-operators check-operators install-cluster-observability-operator install-opentelemetry-operator install-tempo-operator uninstall-cluster-observability-operator uninstall-opentelemetry-operator uninstall-tempo-operator enable-tracing-ui disable-tracing-ui,$(MAKECMDGOALS)))
$(error NAMESPACE is not set)
endif
endif

MAKEFLAGS += --no-print-directory

# Default values
REGISTRY ?= quay.io
ORG ?= ecosystem-appeng
IMAGE_PREFIX ?= aiobs
VERSION ?= 0.14.3
PLATFORM ?= linux/amd64

# Container image names
METRICS_UI_IMAGE = $(REGISTRY)/$(ORG)/$(IMAGE_PREFIX)-metrics-ui
METRICS_ALERTING_IMAGE = $(REGISTRY)/$(ORG)/$(IMAGE_PREFIX)-metrics-alerting
MCP_SERVER_IMAGE = $(REGISTRY)/$(ORG)/$(IMAGE_PREFIX)-mcp-server


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
# MinIO configuration for observability storage (traces, logs, metrics)
MINIO_USER ?= admin
MINIO_PASSWORD ?= minio123
MINIO_HOST ?= minio
MINIO_PORT ?= 9000
# MinIO bucket configuration (comma-separated list)
MINIO_BUCKETS ?= tempo,loki

# HF_TOKEN is only required if LLM_URL is not set
HF_TOKEN ?= $(shell \
    if [ -n "$(LLM_URL)" ]; then \
        echo ""; \
    else \
        bash -c 'read -r -p "Enter Hugging Face Token: " HF_TOKEN; echo $$HF_TOKEN'; \
    fi \
)

RAG_CHART := rag
MINIO_CHART := minio-observability-storage
MINIO_CHART_PATH := minio
METRICS_UI_RELEASE_NAME ?= ui
METRICS_UI_CHART_PATH ?= ui
MCP_SERVER_RELEASE_NAME ?= mcp-server
MCP_SERVER_CHART_PATH ?= mcp-server
TOLERATIONS_TEMPLATE=[{"key":"$(1)","effect":"NoSchedule","operator":"Exists"}]
GEN_MODEL_CONFIG_PREFIX = /tmp/gen_model_config

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
MINIO_NAMESPACE ?= observability-hub

# LLM URL processing constants
DEFAULT_LLM_PORT_AND_PATH := :8080/v1

OPERATOR_MANAGER_SCRIPT := scripts/operator-manager.sh

# Helm argument templates

helm_llm_service_args = \
    $(if $(LLM_URL),,--set llm-service.secret.hf_token=$(HF_TOKEN)) \
    $(if $(DEVICE),--set llm-service.device='$(DEVICE)',) \
    $(if $(LLM),--set global.models.$(LLM).enabled=true,) \
    $(if $(SAFETY),--set global.models.$(SAFETY).enabled=true,) \
    $(if $(LLM_TOLERATION),--set-json global.models.$(LLM).tolerations='$(call TOLERATIONS_TEMPLATE,$(LLM_TOLERATION))',) \
    $(if $(SAFETY_TOLERATION),--set-json global.models.$(SAFETY).tolerations='$(call TOLERATIONS_TEMPLATE,$(SAFETY_TOLERATION))',) \
    $(if $(RAW_DEPLOYMENT),--set llm-service.rawDeploymentMode=$(RAW_DEPLOYMENT),)

# Process LLM_URL to add default port and /v1 if port is missing
define process_llm_url
$(if $(LLM_URL),$(shell \
    if echo "$(LLM_URL)" | grep -q ":[0-9]"; then \
        echo "$(LLM_URL)"; \
    else \
        echo "$(LLM_URL)$(DEFAULT_LLM_PORT_AND_PATH)"; \
    fi \
),)
endef

helm_llama_stack_args = \
    $(if $(LLM),--set global.models.$(LLM).enabled=true,) \
    $(if $(SAFETY),--set global.models.$(SAFETY).enabled=true,) \
    $(if $(LLM_URL),--set global.models.$(LLM).url='$(call process_llm_url)',) \
    $(if $(SAFETY_URL),--set global.models.$(SAFETY).url='$(SAFETY_URL)',) \
    $(if $(LLM_API_TOKEN),--set global.models.$(LLM).apiToken='$(LLM_API_TOKEN)',) \
    $(if $(SAFETY_API_TOKEN),--set global.models.$(SAFETY).apiToken='$(SAFETY_API_TOKEN)',) \
    $(if $(LLAMA_STACK_ENV),--set-json llama-stack.secrets='$(LLAMA_STACK_ENV)',) \
    $(if $(RAW_DEPLOYMENT),--set llama-stack.rawDeploymentMode=$(RAW_DEPLOYMENT),)

helm_pgvector_args = \
    --set pgvector.secret.user=$(POSTGRES_USER) \
    --set pgvector.secret.password=$(POSTGRES_PASSWORD) \
    --set pgvector.secret.dbname=$(POSTGRES_DBNAME)

helm_minio_args = \
    --set minio.secret.user=$(MINIO_USER) \
    --set minio.secret.password=$(MINIO_PASSWORD) \
    --set minio.secret.host=$(MINIO_HOST) \
    --set-string minio.secret.port=$(MINIO_PORT) \
    --set-json minio.buckets='[$(shell echo "$(MINIO_BUCKETS)" | sed 's/,/","/g' | sed 's/^/"/' | sed 's/$$/"/')]'

helm_tempo_args = \
    --set minio.s3.accessKeyId=$(MINIO_USER) \
    --set minio.s3.accessKeySecret=$(MINIO_PASSWORD) \
    --set minio.s3.bucket=tempo

.PHONY: help
help:
	@echo "OpenShift AI Observability Summarizer - Build & Deploy"
	@echo ""
	@echo "Available targets:"
	@echo ""
	@echo "Build & Push:"
	@echo "  build              - Build all container images"
	@echo "  build-ui           - Build Streamlit UI (metric-ui)"
	@echo "  build-alerting     - Build Alerting Service (metric-alerting)"
	@echo "  build-mcp-server   - Build MCP Server (mcp-server)"
	@echo "  push               - Push all container images to registry"
	@echo "  push-ui            - Push metric-ui image"
	@echo "  push-alerting      - Push metric-alerting image"
	@echo "  push-mcp-server    - Push mcp-server image"
	@echo ""
	@echo "Deployment:"
	@echo "  install            - Deploy to OpenShift using Helm"
	@echo "  install-with-alerts - Deploy with alerting enabled"
	@echo "  install-local      - Set up local development environment"
	@echo "  install-rag        - Install RAG backend services only"
	@echo "  install-metric-ui  - Install UI only"
	@echo "  install-mcp-server - Install MCP server only"
	@echo "  uninstall          - Uninstall from OpenShift"
	@echo "  status             - Check deployment status"
	@echo "  list-models        - List available models"
	@echo "  generate-model-config - Generate JSON config for specified LLM using template"
	@echo "  install-ingestion-pipeline - Install extra ingestion pipelines"
	@echo ""
	@echo "Observability Stack:"
	@echo "  install-observability-stack - Install complete observability stack (MinIO + TempoStack + OTEL + tracing + drift check)"
	@echo "  uninstall-observability-stack - Uninstall complete observability stack (tracing + TempoStack + OTEL + MinIO)"
	@echo ""
	@echo "Operators:"
	@echo "  install-operators - Install all mandatory operators (observability, otel, tempo)"
	@echo "  install-cluster-observability-operator - Install Cluster Observability Operator (observability)"
	@echo "  install-opentelemetry-operator - Install OpenTelemetry Operator (otel)"
	@echo "  install-tempo-operator - Install Tempo Operator (tempo)"
	@echo "  uninstall-operators - Uninstall all mandatory operators (with confirmation)"
	@echo "  uninstall-cluster-observability-operator - Uninstall Cluster Observability Operator only"
	@echo "  uninstall-opentelemetry-operator - Uninstall OpenTelemetry Operator only"
	@echo "  uninstall-tempo-operator - Uninstall Tempo Operator only"
	@echo "  check-operators - Check status of all mandatory operators"
	@echo ""
	@echo "Individual Components:"
	@echo "  install-observability - Install TempoStack and OTEL Collector only"
	@echo "  uninstall-observability - Uninstall TempoStack and OTEL Collector only"
	@echo "  upgrade-observability - Force upgrade observability components (even if already installed)"
	@echo "  check-observability-drift - Check for configuration drift in observability-hub"
	@echo "  setup-tracing - Enable auto-instrumentation for tracing in target namespace (idempotent)"
	@echo "  remove-tracing - Disable auto-instrumentation for tracing in target namespace"
	@echo "  enable-tracing-ui - Enable 'Observe → Traces' menu in OpenShift Console"
	@echo "  disable-tracing-ui - Disable 'Observe → Traces' menu in OpenShift Console"
	@echo "  install-minio - Install MinIO observability storage backend only"
	@echo "  uninstall-minio - Uninstall MinIO observability storage backend only"
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
	@echo "  VERSION            - Image version (default: $(VERSION))"
	@echo "  PLATFORM           - Target platform (default: linux/amd64)"
	@echo "  BUILD_TOOL         - Build tool: docker or podman (auto-detected)"
	@echo "  NAMESPACE          - OpenShift namespace for deployment"
	@echo "  HF_TOKEN           - Hugging Face Token (will prompt if not provided and LLM_URL not set)"
	@echo "  DEVICE             - Deploy models on cpu or gpu (default)"
	@echo "  LLM                - Model id (eg. llama-3-2-3b-instruct)"
	@echo "  LLM_URL            - Use existing model URL (auto-adds :8080/v1 if no port specified)"
	@echo "  SAFETY             - Safety model id"
	@echo "  ALERTS             - Set to TRUE to install alerting with main deployment"
	@echo "  SLACK_WEBHOOK_URL  - Slack Webhook URL for alerting (will prompt if not provided)"
	@echo "  MINIO_USER         - MinIO username for observability storage (default: admin)"
	@echo "  MINIO_PASSWORD     - MinIO password for observability storage (default: minio123)"
	@echo "  MINIO_BUCKETS      - Comma-separated list of MinIO buckets to create (default: tempo,loki)"
	@echo "  UNINSTALL_OBSERVABILITY - Set to 'true' to uninstall observability stack during uninstall"
	@echo "  UNINSTALL_OPERATORS     - Set to 'true' to uninstall operators during uninstall"
	@echo ""

.PHONY: build
build: build-ui build-alerting build-mcp-server
	@echo "✅ All container images built successfully"

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

.PHONY: build-mcp-server
build-mcp-server:
	@echo "🔨 Building MCP Server (mcp-server)..."
	@$(BUILD_TOOL) buildx build --platform $(PLATFORM) \
		-f src/mcp_server/Dockerfile \
		-t $(MCP_SERVER_IMAGE):$(VERSION) \
		src
	@echo "✅ mcp-server image built: $(MCP_SERVER_IMAGE):$(VERSION)"

.PHONY: push
push: push-ui push-alerting push-mcp-server
	@echo "✅ All container images pushed successfully"

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

.PHONY: push-mcp-server
push-mcp-server:
	@echo "📤 Pushing mcp-server image..."
	@$(BUILD_TOOL) push $(MCP_SERVER_IMAGE):$(VERSION)
	@echo "✅ mcp-server image pushed"



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
	@echo "Updating Helm dependencies (for $(RAG_CHART))..."
	@cd deploy/helm && helm dependency update $(RAG_CHART) || exit 1

	@echo "Updating Helm dependencies (for $(MINIO_CHART))..."
	@cd deploy/helm && helm dependency update $(MINIO_CHART_PATH) || exit 1


.PHONY: install-metric-ui
install-metric-ui: namespace
	@echo "Deploying Metric UI"
	@cd deploy/helm && helm upgrade --install $(METRICS_UI_RELEASE_NAME) $(METRICS_UI_CHART_PATH) -n $(NAMESPACE) \
		--set image.repository=$(METRICS_UI_IMAGE) \
		--set image.tag=$(VERSION)

.PHONY: install-mcp-server
install-mcp-server: namespace
	@echo "Deploying MCP Server"
	@echo "Generating model configuration for MCP Server (LLM=$(LLM))"
	@$(MAKE) generate-model-config LLM=$(LLM)
	@echo "  → [$(GEN_MODEL_CONFIG_PREFIX).output] contains the model config generation output"
	@echo "Checking ClusterRole grafana-prometheus-reader for MCP..."
	@if oc get clusterrole grafana-prometheus-reader > /dev/null 2>&1; then \
		echo "ClusterRole exists. Deploying without creating Grafana role..."; \
		cd deploy/helm && helm upgrade --install $(MCP_SERVER_RELEASE_NAME) $(MCP_SERVER_CHART_PATH) -n $(NAMESPACE) \
			--set image.repository=$(MCP_SERVER_IMAGE) \
			--set image.tag=$(VERSION) \
			--set rbac.createGrafanaRole=false \
			$(if $(MCP_SERVER_ROUTE_HOST),--set route.host='$(MCP_SERVER_ROUTE_HOST)',) \
			$(if $(LLAMA_STACK_URL),--set llm.url='$(LLAMA_STACK_URL)',) \
			-f $(GEN_MODEL_CONFIG_PREFIX)-for_helm.yaml; \
	else \
		echo "ClusterRole does not exist. Deploying and creating Grafana role..."; \
		cd deploy/helm && helm upgrade --install $(MCP_SERVER_RELEASE_NAME) $(MCP_SERVER_CHART_PATH) -n $(NAMESPACE) \
			--set image.repository=$(MCP_SERVER_IMAGE) \
			--set image.tag=$(VERSION) \
			--set rbac.createGrafanaRole=true \
			$(if $(MCP_SERVER_ROUTE_HOST),--set route.host='$(MCP_SERVER_ROUTE_HOST)',) \
			$(if $(LLAMA_STACK_URL),--set llm.url='$(LLAMA_STACK_URL)',) \
			-f $(GEN_MODEL_CONFIG_PREFIX)-for_helm.yaml; \
	fi

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
install: namespace depend validate-llm install-operators install-observability-stack install-rag install-metric-ui install-mcp-server delete-jobs
	@if [ "$(ALERTS)" = "TRUE" ]; then \
		echo "ALERTS flag is set to TRUE. Installing alerting..."; \
		$(MAKE) install-alerts NAMESPACE=$(NAMESPACE); \
	fi
	@echo "Installation complete."

.PHONY: install-with-alerts
install-with-alerts:
	@if [ -z "$(NAMESPACE)" ]; then \
		echo "❌ Error: NAMESPACE is required for deployment"; \
		echo "Usage: make install-with-alerts NAMESPACE=your-namespace"; \
		exit 1; \
	fi
	@echo "🚀 Deploying to OpenShift namespace: $(NAMESPACE) with alerting"
	@$(MAKE) namespace depend validate-llm install-observability-stack install-rag install-metric-ui install-mcp-server delete-jobs install-alerts NAMESPACE=$(NAMESPACE)
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
	@echo "Removing pgvector PVCs from $(NAMESPACE)"
	- @oc delete pvc -n $(NAMESPACE) -l app.kubernetes.io/name=pgvector ||:
	@if helm list -n $(NAMESPACE) -q | grep -q "^$(ALERTING_RELEASE_NAME)$$"; then \
		echo "→ Detected alerting chart $(ALERTING_RELEASE_NAME). Uninstalling alerting..."; \
		$(MAKE) uninstall-alerts NAMESPACE=$(NAMESPACE); \
	fi

	@echo "Uninstalling $(METRICS_UI_RELEASE_NAME) helm chart"
	- @helm -n $(NAMESPACE) uninstall $(METRICS_UI_RELEASE_NAME) --ignore-not-found
	@echo "Uninstalling $(MCP_SERVER_RELEASE_NAME) helm chart (if installed)"
	- @helm -n $(NAMESPACE) uninstall $(MCP_SERVER_RELEASE_NAME) --ignore-not-found

	@echo ""
	@echo "Checking if observability stack should be uninstalled..."
	@$(MAKE) uninstall-observability-stack NAMESPACE=$(NAMESPACE) || true

	@echo ""
	@echo "Checking if operators should be uninstalled..."
	@$(MAKE) uninstall-operators || true

	@echo "\nRemaining resources in namespace $(NAMESPACE):"
	@echo " → Pods..."
	@oc get pods -n $(NAMESPACE) || true
	@echo " → Services..."
	@oc get svc -n $(NAMESPACE) || true
	@echo " → Routes..."
	@oc get routes -n $(NAMESPACE) || true
	@echo " → Secrets..."
	@oc get secrets -n $(NAMESPACE) | grep huggingface-secret || true
	@echo " → Pvcs..."
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
	@if [ -z "$(NAMESPACE)" ]; then \
		echo "❌ Error: NAMESPACE parameter is required"; \
		echo "Usage: make install-local NAMESPACE=your-namespace"; \
		echo "Optional: make install-local NAMESPACE=default-ns MODEL_NAMESPACE=model-ns"; \
		exit 1; \
	fi
	@echo "📋 Using namespace: $(NAMESPACE)"
	@if [ -n "$(MODEL_NAMESPACE)" ]; then echo "📋 Using model namespace: $(MODEL_NAMESPACE)"; fi
	@bash -c '\
		uv sync && \
		chmod +x ./scripts/local-dev.sh && \
		if [ -n "$(MODEL_NAMESPACE)" ]; then \
			./scripts/local-dev.sh -n $(NAMESPACE) -m $(MODEL_NAMESPACE); \
		else \
			./scripts/local-dev.sh -n $(NAMESPACE); \
		fi && \
		echo "✅ Local development environment setup completed" \
	'

.PHONY: clean
clean:
	@echo "🧹 Cleaning up local images..."
	@ERRORS=0; \
	if ! $(BUILD_TOOL) rmi $(METRICS_UI_IMAGE):$(VERSION) 2>/dev/null; then \
		echo "⚠️  Could not remove $(METRICS_UI_IMAGE):$(VERSION) (may not exist)"; \
		ERRORS=$$((ERRORS + 1)); \
	fi; \
	if ! $(BUILD_TOOL) rmi $(METRICS_ALERTING_IMAGE):$(VERSION) 2>/dev/null; then \
		echo "⚠️  Could not remove $(METRICS_ALERTING_IMAGE):$(VERSION) (may not exist)"; \
		ERRORS=$$((ERRORS + 1)); \
	fi; \
	if ! $(BUILD_TOOL) rmi $(MCP_SERVER_IMAGE):$(VERSION) 2>/dev/null; then \
		echo "⚠️  Could not remove $(MCP_SERVER_IMAGE):$(VERSION) (may not exist)"; \
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

.PHONY: build-deploy-mcp-server
build-deploy-mcp-server: build-mcp-server push-mcp-server install-mcp-server
	@echo "✅ Build, push, and deploy mcp-server completed"

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
	@echo "  Metric UI Image: $(METRICS_UI_IMAGE):$(VERSION)"
	@echo "  Metric Alerting Image: $(METRICS_ALERTING_IMAGE):$(VERSION)"
	@echo "  MCP Server Image: $(MCP_SERVER_IMAGE):$(VERSION)"

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
	@cd deploy/helm && helm upgrade --install $(ALERTING_RELEASE_NAME) ./alerting --namespace $(NAMESPACE) \
		--set image.repository=$(METRICS_ALERTING_IMAGE) \
		--set image.tag=$(VERSION)
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
	@bash -c 'source scripts/generate-model-config.sh && generate_model_config "$(LLM)" --helm-format' > $(GEN_MODEL_CONFIG_PREFIX).output 2>&1

# Validate that LLM variable is set and non-empty
.PHONY: validate-llm
validate-llm:
	@if [ -z "$(LLM)" ]; then \
		echo "\n❌ Error: LLM variable is not set or empty. Please set LLM=<model_name>"; \
		exit 1; \
	fi

.PHONY: install-observability
install-observability:
	@echo "→ Checking if OpenTelemetry Collector and Tempo already exist in namespace $(OBSERVABILITY_NAMESPACE)"
	@if helm list -n $(OBSERVABILITY_NAMESPACE) 2>/dev/null | grep -q "^tempo\s"; then \
		echo "  → TempoStack already installed, skipping..."; \
	else \
		echo "Installing TempoStack in namespace $(OBSERVABILITY_NAMESPACE)"; \
		cd deploy/helm && helm upgrade --install tempo ./observability/tempo \
			--namespace $(OBSERVABILITY_NAMESPACE) \
			--create-namespace \
			--set global.namespace=$(OBSERVABILITY_NAMESPACE) \
			$(helm_tempo_args); \
	fi

	@if helm list -n $(OBSERVABILITY_NAMESPACE) 2>/dev/null | grep -q "^otel-collector\s"; then \
		echo "  → OpenTelemetry Collector already installed, skipping..."; \
	else \
		echo "Installing Open Telemetry Collector in namespace $(OBSERVABILITY_NAMESPACE)"; \
		cd deploy/helm && helm upgrade --install otel-collector ./observability/otel-collector \
			--namespace $(OBSERVABILITY_NAMESPACE) \
			--create-namespace \
			--set global.namespace=$(OBSERVABILITY_NAMESPACE); \
	fi

.PHONY: install-observability-stack
install-observability-stack: install-minio setup-tracing install-observability check-observability-drift enable-tracing-ui

.PHONY: setup-tracing
setup-tracing: namespace
	@echo "→ Setting up auto-instrumentation for tracing in namespace $(NAMESPACE)"
	@if oc get instrumentation python-instrumentation -n $(NAMESPACE) >/dev/null 2>&1; then \
		echo "  → Instrumentation already exists in namespace $(NAMESPACE), skipping..."; \
	else \
		echo "  → Applying instrumentation configuration to namespace $(NAMESPACE)"; \
		cd deploy/helm && oc apply -f $(INSTRUMENTATION_PATH) -n $(NAMESPACE); \
	fi
	@oc annotate namespace $(NAMESPACE) instrumentation.opentelemetry.io/inject-python="true" --overwrite

.PHONY: remove-tracing
remove-tracing: namespace
	@echo "Removing auto-instrumentation for tracing in namespace $(NAMESPACE)"
	@oc delete instrumentation python-instrumentation -n $(NAMESPACE)
	@oc annotate namespace $(NAMESPACE) instrumentation.opentelemetry.io/inject-python- --overwrite

.PHONY: enable-tracing-ui
enable-tracing-ui:
	@echo "→ Enabling distributed-tracing console plugin for Observe → Traces menu"
	@if oc get console.operator.openshift.io cluster -o jsonpath='{.spec.plugins}' 2>/dev/null | grep -q "distributed-tracing-console-plugin"; then \
		echo "  → Console plugin already enabled"; \
	else \
		echo "  → Enabling console plugin..."; \
		oc patch console.operator.openshift.io cluster --type=json -p='[{"op": "add", "path": "/spec/plugins/-", "value": "distributed-tracing-console-plugin"}]' 2>/dev/null && \
		echo "  → Console plugin enabled. The OpenShift Console will refresh automatically." || \
		echo "  → Note: Console plugin enablement requires cluster-admin permissions. You may need to run this manually."; \
	fi

.PHONY: disable-tracing-ui
disable-tracing-ui:
	@echo "→ Disabling distributed-tracing console plugin for Observe → Traces menu"
	@if oc get console.operator.openshift.io cluster -o jsonpath='{.spec.plugins}' 2>/dev/null | grep -q "distributed-tracing-console-plugin"; then \
		PLUGIN_INDEX=$$(oc get console.operator.openshift.io cluster -o json | jq '.spec.plugins | to_entries | .[] | select(.value=="distributed-tracing-console-plugin") | .key'); \
		if [ -n "$$PLUGIN_INDEX" ]; then \
			oc patch console.operator.openshift.io cluster --type=json -p="[{\"op\": \"remove\", \"path\": \"/spec/plugins/$$PLUGIN_INDEX\"}]" 2>/dev/null && \
			echo "  → Console plugin disabled. The OpenShift Console will refresh automatically." || \
			echo "  → Note: Console plugin disabling requires cluster-admin permissions. You may need to run this manually."; \
		else \
			echo "  → Could not find plugin index"; \
		fi \
	else \
		echo "  → Console plugin is not enabled"; \
	fi

.PHONY: uninstall-observability
uninstall-observability:
	@echo "Uninstalling TempoStack and Otel Collector in namespace $(OBSERVABILITY_NAMESPACE)"
	@helm uninstall tempo -n $(OBSERVABILITY_NAMESPACE)
	@helm uninstall otel-collector -n $(OBSERVABILITY_NAMESPACE)

	@echo "Removing TempoStack PVCs from $(OBSERVABILITY_NAMESPACE)"
	- @oc delete pvc -n $(OBSERVABILITY_NAMESPACE) -l app.kubernetes.io/name=tempo --timeout=30s ||:

.PHONY: uninstall-observability-stack
uninstall-observability-stack:
	@if [ "$(UNINSTALL_OBSERVABILITY)" = "true" ]; then \
		echo "🗑️  Uninstalling observability stack (includes tracing and MinIO)"; \
		echo ""; \
		echo "⚠️  WARNING: This will remove the following components:"; \
		echo "  → Auto-instrumentation for tracing in namespace $(NAMESPACE)"; \
		echo "  → TempoStack and OTEL Collector in namespace $(OBSERVABILITY_NAMESPACE)"; \
		echo "  → MinIO observability storage in namespace $(MINIO_NAMESPACE)"; \
		echo "  → Distributed Tracing Console Plugin (Observe → Traces menu)"; \
		echo ""; \
		echo "This infrastructure is shared by multiple applications."; \
		echo ""; \
		$(MAKE) remove-tracing NAMESPACE=$(NAMESPACE); \
		$(MAKE) uninstall-observability; \
		$(MAKE) uninstall-minio; \
		$(MAKE) disable-tracing-ui; \
		echo ""; \
		echo "✅ Observability stack uninstallation completed!"; \
	else \
		echo "❌ WARNING: UNINSTALL_OBSERVABILITY is not set to 'true'"; \
		echo "   Skipping removal of shared observability infrastructure to protect other teams."; \
		echo "   This infrastructure (TempoStack, OTel Collector) is shared by multiple applications."; \
		echo ""; \
		echo "   To remove observability infrastructure, run:"; \
		echo "     → make uninstall NAMESPACE=$(NAMESPACE) UNINSTALL_OBSERVABILITY=true"; \
		echo ""; \
		echo "   Or remove components individually:"; \
		echo "     → make uninstall-observability-stack NAMESPACE=$(NAMESPACE) UNINSTALL_OBSERVABILITY=true"; \
	fi

.PHONY: upgrade-observability
upgrade-observability:
	@echo "→ Force upgrading OpenTelemetry Collector and Tempo in namespace $(OBSERVABILITY_NAMESPACE)"
	@echo "  This will update the configuration even if already installed"
	cd deploy/helm && helm upgrade --install tempo ./observability/tempo \
		--namespace $(OBSERVABILITY_NAMESPACE) \
		--create-namespace \
		--set global.namespace=$(OBSERVABILITY_NAMESPACE) \
		$(helm_tempo_args)
	cd deploy/helm && helm upgrade --install otel-collector ./observability/otel-collector \
		--namespace $(OBSERVABILITY_NAMESPACE) \
		--create-namespace \
		--set global.namespace=$(OBSERVABILITY_NAMESPACE)
	@echo "✅ Observability components upgraded successfully"

.PHONY: check-observability-drift
check-observability-drift:
	@scripts/check-observability-drift.sh $(OBSERVABILITY_NAMESPACE)


.PHONY: install-minio
install-minio:
	@$(eval MINIO_ARGS := $(call helm_minio_args))

	@echo "→ Checking if $(MINIO_CHART) already exists in namespace $(MINIO_NAMESPACE)"
	@if helm list -n $(MINIO_NAMESPACE) 2>/dev/null | grep -q "^$(MINIO_CHART)\s"; then \
		echo "  → $(MINIO_CHART) already installed, skipping..."; \
	else \
		echo "Installing $(MINIO_CHART) helm chart"; \
		cd deploy/helm && helm -n $(MINIO_NAMESPACE) upgrade --install $(MINIO_CHART) $(MINIO_CHART_PATH) \
		--atomic --timeout 5m \
		$(MINIO_ARGS); \
		echo "$(MINIO_CHART) installed successfully"; \
	fi
	@echo "→ Cleaning up broken upstream routes (pointing to non-existent 'minio' service)"
	- @oc delete route minio-api minio-webui -n $(MINIO_NAMESPACE) --ignore-not-found ||:
	@echo "  → Broken upstream routes cleaned up"


.PHONY: uninstall-minio
uninstall-minio:
	@echo "Uninstalling $(MINIO_CHART) in namespace $(MINIO_NAMESPACE)"
	@helm -n $(MINIO_NAMESPACE) uninstall $(MINIO_CHART) --ignore-not-found

	@echo "Removing minio PVCs from $(MINIO_NAMESPACE)"
	- @oc delete pvc -n $(MINIO_NAMESPACE) -l app.kubernetes.io/name=$(MINIO_CHART) --timeout=30s ||:

# -- Operator Installation targets --

# Install Cluster Observability Operator
.PHONY: install-cluster-observability-operator
install-cluster-observability-operator:
	@echo ""
	@$(OPERATOR_MANAGER_SCRIPT) -i observability -n openshift-cluster-observability-operator

# Install OpenTelemetry Operator
.PHONY: install-opentelemetry-operator
install-opentelemetry-operator:
	@echo ""
	@$(OPERATOR_MANAGER_SCRIPT) -i otel -n openshift-opentelemetry-operator

# Install Tempo Operator
.PHONY: install-tempo-operator
install-tempo-operator:
	@echo ""
	@$(OPERATOR_MANAGER_SCRIPT) -i tempo -n openshift-tempo-operator

# Install all three mandatory operators for Tempo and OpenTelemetry Collector
.PHONY: install-operators
install-operators: install-cluster-observability-operator install-opentelemetry-operator install-tempo-operator

# Uninstall Cluster Observability Operator
.PHONY: uninstall-cluster-observability-operator
uninstall-cluster-observability-operator:
	@$(OPERATOR_MANAGER_SCRIPT) -u observability -n openshift-cluster-observability-operator

# Uninstall OpenTelemetry Operator
.PHONY: uninstall-opentelemetry-operator
uninstall-opentelemetry-operator:
	@$(OPERATOR_MANAGER_SCRIPT) -u otel -n openshift-opentelemetry-operator

# Uninstall Tempo Operator
.PHONY: uninstall-tempo-operator
uninstall-tempo-operator:
	@$(OPERATOR_MANAGER_SCRIPT) -u tempo -n openshift-tempo-operator

# Uninstall all three operators
.PHONY: uninstall-operators
uninstall-operators:
	@if [ "$(UNINSTALL_OPERATORS)" = "true" ]; then \
		echo "🗑️  Uninstalling operators for Tempo and OpenTelemetry Collector..."; \
		echo ""; \
		echo "⚠️  WARNING: This will remove the following operators:"; \
		echo "  → Cluster Observability Operator"; \
		echo "  → Red Hat build of OpenTelemetry Operator"; \
		echo "  → Tempo Operator"; \
		echo ""; \
		echo "This may affect other applications using these operators."; \
		echo ""; \
		$(MAKE) uninstall-cluster-observability-operator; \
		$(MAKE) uninstall-opentelemetry-operator; \
		$(MAKE) uninstall-tempo-operator; \
		echo ""; \
		echo "✅ All operators uninstallation completed!"; \
	else \
		echo "❌ WARNING: UNINSTALL_OPERATORS is not set to 'true'"; \
		echo "   Skipping removal of operators to protect other applications."; \
		echo "   These operators are cluster-scoped and shared by multiple applications."; \
		echo ""; \
		echo "   To remove operators, run:"; \
		echo "     → make uninstall NAMESPACE=$(NAMESPACE) UNINSTALL_OPERATORS=true"; \
		echo ""; \
		echo "   Or remove components individually:"; \
		echo "     → make uninstall-operators UNINSTALL_OPERATORS=true"; \
	fi


# Check operator status
.PHONY: check-operators
check-operators:
	@echo "📊 Checking operator status for Tempo and OpenTelemetry Collector..."
	@echo ""
	@printf "🔍 Cluster Observability Operator: " && $(OPERATOR_MANAGER_SCRIPT) -c observability
	@printf "🔍 OpenTelemetry Operator: " && $(OPERATOR_MANAGER_SCRIPT) -c otel
	@printf "🔍 Tempo Operator: " && $(OPERATOR_MANAGER_SCRIPT) -c tempo
