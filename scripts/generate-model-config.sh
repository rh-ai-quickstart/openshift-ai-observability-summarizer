#!/bin/bash

# AI Observability Metric Summarizer - Local Development Script

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color


check_tool_exists() {
  local tool="$1"
  if ! command -v "$tool" &> /dev/null; then
    echo -e "${RED}❌ $tool is required but not installed${NC}"
    exit 1
  fi
}

# Get the default LLM model name
get_default_model() {
  echo "llama-3-2-3b-instruct"
}

# This function generates MODEL_CONFIG by merging LLM-specific config with base config
# Used by both Makefile's generate-model-config target and local-dev.sh
# Usage: generate_model_config "llama-3.1-8b-instruct" [--helm-format]
generate_model_config() {
  local DEFAULT_MODEL=$(get_default_model)
  local LLM="${1:-$DEFAULT_MODEL}"
  local CREATE_HELM_FILE=false
  local GEN_MODEL_CONFIG_PREFIX="/tmp/gen_model_config"
  local RAG_CHART="rag"

  # Check for --helm-format flag
  if [ "$2" = "--helm-format" ]; then
    CREATE_HELM_FILE=true
  fi

  echo -e "${BLUE}🔧 Generating MODEL_CONFIG...${NC}"
  echo -e "${BLUE}   LLM: $LLM${NC}"
  if [ "$CREATE_HELM_FILE" = true ]; then
    echo -e "${BLUE}   Helm format: enabled${NC}"
  fi

  # Check if jq is available
  check_tool_exists "jq"

  # Check if helm is available
  check_tool_exists "helm"

  echo -e "${BLUE}   → Running list-models to find available models...${NC}"
  # Run helm template to get available models
  cd deploy/helm && helm template dummy-release "$RAG_CHART" --set llm-service._debugListModels=true 2>/dev/null | grep "^model:" > "${GEN_MODEL_CONFIG_PREFIX}-list_models_output.txt"
  cd - > /dev/null

  if [ ! -s "${GEN_MODEL_CONFIG_PREFIX}-list_models_output.txt" ]; then
      echo -e "${RED}❌ Failed to get list of available models${NC}"
      return 1
  fi

  echo -e "${BLUE}     → list-models output saved to ${GEN_MODEL_CONFIG_PREFIX}-list_models_output.txt${NC}"

  # Find the model line matching the LLM
  echo -e "${BLUE}     → Searching for model: $LLM${NC}"
  MODEL_LINE=$(grep "model: $LLM (" "${GEN_MODEL_CONFIG_PREFIX}-list_models_output.txt" || echo "")

  if [ -z "$MODEL_LINE" ]; then
      echo -e "${RED}❌ Error: Model '$LLM' not found in available models${NC}"
      echo -e "${YELLOW}→ Available models:${NC}"
      cat "${GEN_MODEL_CONFIG_PREFIX}-list_models_output.txt"
      return 1
  fi

  echo -e "${BLUE}     → Found MODEL_LINE: $MODEL_LINE${NC}"

  # Extract MODEL_NAME and MODEL_ID
  echo -e "${BLUE}   → Extracting MODEL_NAME and MODEL_ID from MODEL_LINE${NC}"
  MODEL_NAME=$(echo "$MODEL_LINE" | sed 's/model: \([^(]*\)(.*)/\1/' | tr -d '[:space:]')
  MODEL_ID=$(echo "$MODEL_LINE" | sed 's/model: [^(]*(\([^)]*\))/\1/' | tr -d '[:space:]')

  echo -e "${BLUE}     → Extracted MODEL_NAME: $MODEL_NAME, MODEL_ID: $MODEL_ID${NC}"

  # Generate new model config from template
  echo -e "${BLUE}   → Generating JSON configuration from template...${NC}"
  if [ ! -f "deploy/helm/default-model.json.template" ]; then
      echo -e "${RED}❌ Template file not found: deploy/helm/default-model.json.template${NC}"
      return 1
  fi

  sed "s|\$MODEL_ID|$MODEL_ID|g; s|\$MODEL_NAME|$MODEL_NAME|g" deploy/helm/default-model.json.template > "${GEN_MODEL_CONFIG_PREFIX}-new_model_config.json"

  # Merge with base model config
  echo -e "${BLUE}     → Merging with existing model-config.json...${NC}"
  if [ ! -f "deploy/helm/model-config.json" ]; then
      echo -e "${RED}❌ Base config file not found: deploy/helm/model-config.json${NC}"
      return 1
  fi

  jq -s '.[0] * .[1]' "${GEN_MODEL_CONFIG_PREFIX}-new_model_config.json" deploy/helm/model-config.json > "${GEN_MODEL_CONFIG_PREFIX}-final_config.json"

  if [ $? -ne 0 ]; then
      echo -e "${RED}❌ Failed to merge configurations${NC}"
      return 1
  fi

  # Load the final config into MODEL_CONFIG
  export MODEL_CONFIG=$(cat "${GEN_MODEL_CONFIG_PREFIX}-final_config.json")

  if [ -z "$MODEL_CONFIG" ]; then
      echo -e "${RED}❌ Failed to load final configuration${NC}"
      return 1
  fi

  echo -e "${GREEN}  ✅ MODEL_CONFIG generated successfully${NC}"
  echo -e "${GREEN}     Final merged configuration saved in ${GEN_MODEL_CONFIG_PREFIX}-final_config.json${NC}"
  echo -e "${BLUE}     → Available models: $(echo "$MODEL_CONFIG" | jq -r 'keys | join(", ")')${NC}"

  # Generate Helm-formatted YAML file only if requested (for Makefile usage)
  if [ "$CREATE_HELM_FILE" = true ]; then
    echo -e "${BLUE}  → Creating Helm values file...${NC}"
    (echo "modelConfig:"; cat "${GEN_MODEL_CONFIG_PREFIX}-final_config.json" | sed 's/^/  /') > "${GEN_MODEL_CONFIG_PREFIX}-for_helm.yaml"
    echo -e "${GREEN}   Helm values file created: ${GEN_MODEL_CONFIG_PREFIX}-for_helm.yaml${NC}"
  fi

  # Cleanup intermediate file
  rm -f "${GEN_MODEL_CONFIG_PREFIX}-new_model_config.json"

  return 0
}
