"""
Configuration management for OpenShift AI Observability

Centralizes all environment variables and configuration settings
that are shared across FastAPI, Streamlit UI, and MCP servers.
"""

import os
import json
import logging
from typing import Dict, Any
from common.pylogger import get_python_logger

# Initialize structured logger once - other modules should use logging.getLogger(__name__)
get_python_logger()

logger = logging.getLogger(__name__)


def load_model_config() -> Dict[str, Any]:
    """Load unified model configuration from environment."""
    try:
        model_config_str = os.getenv("MODEL_CONFIG", "{}")
        return json.loads(model_config_str)
    except Exception as e:
        logger.warning("Could not parse MODEL_CONFIG: %s", e)
        return {}


def load_thanos_token() -> str:
    """Load Thanos token from file or environment variable."""
    token_input = os.getenv(
        "THANOS_TOKEN", "/var/run/secrets/kubernetes.io/serviceaccount/token"
    )
    if os.path.exists(token_input):
        with open(token_input, "r") as f:
            return f.read().strip()
    else:
        return token_input


def get_ca_verify_setting():
    """Get SSL certificate verification setting."""
    ca_bundle_path = "/etc/pki/ca-trust/extracted/pem/ca-bundle.crt"
    return ca_bundle_path if os.path.exists(ca_bundle_path) else True


# Main configuration settings
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
LLAMA_STACK_URL = os.getenv("LLAMA_STACK_URL", "http://localhost:8321/v1/openai/v1")
LLM_API_TOKEN = os.getenv("LLM_API_TOKEN", "")

# Load complex configurations
MODEL_CONFIG = load_model_config()
THANOS_TOKEN = load_thanos_token()
VERIFY_SSL = get_ca_verify_setting() 

# Common constants
# Chat scope values used across the codebase
CHAT_SCOPE_FLEET_WIDE = "fleet_wide"
FLEET_WIDE_DISPLAY = "Fleet-wide"

# Time range constraints
# Maximum time range allowed for analysis (in days)
MAX_TIME_RANGE_DAYS: int = int(os.getenv("MAX_TIME_RANGE_DAYS", "90"))

# Default time range when none is provided (in days)
DEFAULT_TIME_RANGE_DAYS: int = int(os.getenv("DEFAULT_TIME_RANGE_DAYS", "90"))