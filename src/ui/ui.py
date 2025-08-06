# main_page.py - AI Observability Metric Summarizer (vLLM + OpenShift)
import streamlit as st
import requests
from datetime import datetime
import pandas as pd
import os
import streamlit.components.v1 as components
import base64
import matplotlib.pyplot as plt
import io
import time

# --- Config ---
API_URL = os.getenv("METRICS_API_URL", "http://localhost:8000")
PROM_URL = os.getenv("PROM_URL", "http://localhost:9090")

# --- Page Setup ---
st.set_page_config(page_title="AI Metric Tools", layout="wide")
st.markdown(
    """
<style>
    html, body, [class*="css"] { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto; }
    h1, h2, h3 { font-weight: 600; color: #1c1c1e; letter-spacing: -0.5px; }
    .stMetric { border-radius: 12px; background-color: #f9f9f9; padding: 1em; box-shadow: 0 2px 8px rgba(0,0,0,0.05); color: #1c1c1e !important; }
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"] { color: #1c1c1e !important; font-weight: 600; }
    .block-container { padding-top: 2rem; }
    .stButton>button { border-radius: 8px; padding: 0.5em 1.2em; font-size: 1em; }
    footer, header { visibility: hidden; }
</style>
""",
    unsafe_allow_html=True,
)

# --- Page Selector ---
st.sidebar.title("Navigation")
page = st.sidebar.radio(
    "Go to:", ["vLLM Metric Summarizer", "Chat with Prometheus", "OpenShift Metrics"]
)


# --- Shared Utilities ---
@st.cache_data(ttl=300)
def get_models():
    """Fetch available models from API"""
    try:
        res = requests.get(f"{API_URL}/models")
        return res.json()
    except Exception as e:
        st.sidebar.error(f"Error fetching models: {e}")
        return []


@st.cache_data(ttl=300)
def get_namespaces():
    """Fetch available namespaces from API"""
    try:
        res = requests.get(f"{API_URL}/namespaces")
        namespace_data = res.json()
        # Extract just the namespace names for the dropdown
        if isinstance(namespace_data, list) and len(namespace_data) > 0:
            if isinstance(namespace_data[0], dict) and 'name' in namespace_data[0]:
                # New format with name/displayName objects
                return [ns['name'] for ns in namespace_data]
            else:
                # Old format with just strings
                return namespace_data
        return []
    except Exception as e:
        st.sidebar.error(f"Error fetching namespaces: {e}")
        return []


@st.cache_data(ttl=300)
def get_multi_models():
    """Fetch available summarization models from API"""
    try:
        res = requests.get(f"{API_URL}/multi_models")
        return res.json()
    except Exception as e:
        st.sidebar.error(f"Error fetching multi models: {e}")
        return []


@st.cache_data(ttl=300)
def get_model_config():
    """Fetch model configuration from API"""
    try:
        res = requests.get(f"{API_URL}/model_config")
        if res.status_code == 200:
            return res.json()
        else:
            st.sidebar.error(f"API returned status {res.status_code}")
            return {}
    except Exception as e:
        st.sidebar.error(f"Error fetching model config: {e}")
        return {}


@st.cache_data(ttl=300)
def get_openshift_metric_groups():
    """Fetch available OpenShift metric groups from API"""
    try:
        res = requests.get(f"{API_URL}/openshift-metric-groups")
        return res.json()
    except Exception as e:
        st.sidebar.error(f"Error fetching metric groups: {e}")
        return []


@st.cache_data(ttl=300)
def get_openshift_namespace_metric_groups():
    """Fetch available OpenShift namespace-specific metric groups from API"""
    try:
        res = requests.get(f"{API_URL}/openshift-namespace-metric-groups")
        return res.json()
    except Exception as e:
        st.sidebar.error(f"Error fetching namespace metric groups: {e}")
        return []


@st.cache_data(ttl=300)
def get_openshift_namespaces():
    """Fetch available OpenShift namespaces from API"""
    try:
        res = requests.get(f"{API_URL}/openshift-namespaces")
        return res.json()
    except Exception as e:
        st.sidebar.error(f"Error fetching OpenShift namespaces: {e}")
        return ["default"]


@st.cache_data(ttl=300)
def get_vllm_metrics():
    """Fetch available vLLM metrics dynamically from API"""
    try:
        res = requests.get(f"{API_URL}/vllm-metrics")
        return res.json()
    except Exception as e:
        st.sidebar.error(f"Error fetching vLLM metrics: {e}")
        return {}


@st.cache_data(ttl=300)
def get_gpu_info():
    """Fetch GPU information from API"""
    try:
        res = requests.get(f"{API_URL}/gpu-info")
        return res.json()
    except Exception as e:
        st.sidebar.error(f"Error fetching GPU info: {e}")
        return {
            "total_gpus": 0,
            "vendors": [],
            "models": [],
            "temperatures": [],
            "power_usage": [],
        }


@st.cache_data(ttl=300)
def get_deployment_info(model_name):
    """Get deployment information for a model/namespace"""
    try:
        if "|" in model_name:
            namespace, actual_model = model_name.split("|", 1)
            namespace = namespace.strip()
            actual_model = actual_model.strip()
        else:
            return {"is_new_deployment": False, "deployment_date": None, "message": None}
        
        # Try to get deployment info from the backend
        res = requests.get(f"{API_URL}/deployment-info?namespace={namespace}&model={actual_model}")
        if res.status_code == 200:
            return res.json()
        else:
            # Fallback: assume it's a new deployment if we can't get info
            return {
                "is_new_deployment": True,
                "deployment_date": datetime.now().strftime("%Y-%m-%d"),
                "message": f"This appears to be a new deployment in namespace '{namespace}'. Metrics may take some time to appear."
            }
    except Exception as e:
        return {"is_new_deployment": False, "deployment_date": None, "message": None}


def check_if_new_deployment(calculated_metrics, model_name):
    """Check if this appears to be a new deployment with no data"""
    if not calculated_metrics:
        return True
    
    # Check if all metrics are None/empty
    all_empty = True
    for metric_name, data in calculated_metrics.items():
        if data and data.get("avg") is not None and data.get("count", 0) > 0:
            all_empty = False
            break
    
    return all_empty


def display_new_deployment_info(model_name):
    """Display helpful information for new deployments"""
    deployment_info = get_deployment_info(model_name)
    
    if deployment_info.get("is_new_deployment", False):
        deployment_date = deployment_info.get("deployment_date")
        message = deployment_info.get("message")
        
        if deployment_date:
            st.info(
                f"🚀 **New Deployment Detected** | Deployed: {deployment_date}\n\n"
                f"This model was recently deployed and metrics may not be available yet. "
                f"Metrics typically start appearing within 5-10 minutes after the first request is processed."
            )
        elif message:
            st.info(f"🚀 **New Deployment** | {message}")
        else:
            if "|" in model_name:
                namespace = model_name.split("|")[0].strip()
                st.info(
                    f"🚀 **New Deployment Detected** | Namespace: {namespace}\n\n"
                    f"This appears to be a newly deployed model. Metrics will appear once the model starts processing requests."
                )


def model_requires_api_key(model_id, model_config):
    """Check if a model requires an API key based on unified configuration"""
    if not isinstance(model_config, dict):
        return False
    
    model_info = model_config.get(model_id, {})
    if not isinstance(model_info, dict):
        return False
    
    # Check for both requiresApiKey and external fields
    return model_info.get("requiresApiKey", False) or model_info.get("external", False)


def clear_session_state():
    """Clear session state on errors"""
    # Clear vLLM-specific session state
    for key in [
        "summary",
        "prompt",
        "metric_data",
        "model_name",
        "analysis_params",
        "analysis_performed",
    ]:
        if key in st.session_state:
            del st.session_state[key]

    # Clear OpenShift-specific session state
    openshift_keys = [
        "openshift_prompt",
        "openshift_summary",
        "openshift_metric_category",
        "openshift_scope",
        "openshift_namespace",
        "openshift_metric_data",
        "openshift_analysis_type",
    ]
    for key in openshift_keys:
        if key in st.session_state:
            del st.session_state[key]


def handle_http_error(response, context):
    """Handle HTTP errors and display appropriate messages"""
    if response.status_code == 401:
        st.error("❌ Unauthorized. Please check your API Key.")
    elif response.status_code == 403:
        st.error("❌ Forbidden. Please check your API Key.")
    elif response.status_code == 500:
        st.error("❌ Please check your API Key or try again later.")
    else:
        st.error(f"❌ {context}: {response.status_code} - {response.text}")


def trigger_download(
    file_content: bytes, filename: str, mime_type: str = "application/octet-stream"
):

    b64 = base64.b64encode(file_content).decode()

    dl_link = f"""
    <html>
    <body>
    <script>
    const link = document.createElement('a');
    link.href = "data:{mime_type};base64,{b64}";
    link.download = "{filename}";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    </script>
    </body>
    </html>
    """

    components.html(dl_link, height=0, width=0)


def get_metrics_data_and_list():
    """Get metrics data and list to avoid code duplication"""
    metric_data = st.session_state.get("metric_data", {})
    metrics = [
        "GPU Temperature (°C)",
        "GPU Power Usage (Watts)",
        "P95 Latency (s)",
        "GPU Usage (%)",
        "GPU Memory Usage (GB)",
        "Output Tokens Created",
    ]
    return metric_data, metrics


def get_calculated_metrics_from_mcp(metric_data):
    """Get calculated metrics from MCP backend"""
    try:
        response = requests.post(
            f"{API_URL}/calculate-metrics", json={"metrics_data": metric_data}
        )
        response.raise_for_status()
        return response.json()["calculated_metrics"]
    except Exception as e:
        st.error(f"Error getting calculated metrics from MCP: {e}")
        return {}


def process_chart_data(metric_data, chart_metrics=None):
    """Process metrics data for chart generation"""
    if chart_metrics is None:
        chart_metrics = ["GPU Usage (%)", "P95 Latency (s)"]

    dfs = []
    for label in chart_metrics:
        raw_data = metric_data.get(label, [])
        if raw_data:
            try:
                timestamps = [datetime.fromisoformat(p["timestamp"]) for p in raw_data]
                values = [p["value"] for p in raw_data]
                df = pd.DataFrame({label: values}, index=timestamps)
                dfs.append(df)
            except Exception:
                pass
    return dfs


def create_trend_chart_image(metric_data, chart_metrics=None):
    """Create trend chart image for reports"""
    dfs = process_chart_data(metric_data, chart_metrics)
    if not dfs:
        return None

    try:
        chart_df = pd.concat(dfs, axis=1).fillna(0)
        fig, ax = plt.subplots(figsize=(8, 4))
        chart_df.plot(ax=ax)
        ax.set_title("Trend Over Time")
        ax.set_xlabel("Timestamp")
        ax.set_ylabel("Value")
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")
    except Exception:
        return None


def generate_report_and_download(report_format: str):
    try:
        analysis_params = st.session_state["analysis_params"]

        # Check if this is OpenShift analysis or vLLM analysis
        if "openshift_summary" in st.session_state:
            # OpenShift analysis data
            metric_data = st.session_state.get("openshift_metric_data", {})
            health_prompt = st.session_state.get("openshift_prompt", "")
            llm_summary = st.session_state.get("openshift_summary", "")

            # Use OpenShift-specific model name format
            model_name = f"OpenShift-{analysis_params.get('scope', 'cluster')}-{analysis_params.get('metric_category', 'analysis')}"

            # Create trend chart for OpenShift metrics
            trend_chart_image_b64 = create_trend_chart_image(metric_data)

            payload = {
                "model_name": model_name,
                "start_ts": analysis_params["start_ts"],
                "end_ts": analysis_params["end_ts"],
                "summarize_model_id": analysis_params["summarize_model_id"],
                "format": report_format,
                "api_key": analysis_params.get("api_key"),
                "health_prompt": health_prompt,
                "llm_summary": llm_summary,
                "metrics_data": metric_data,
            }
            filename = f"openshift_metrics_report.{report_format.lower()}"

        else:
            # vLLM analysis data (original logic)
            metric_data, metrics = get_metrics_data_and_list()

            # Filter metrics_data to only include the metrics shown in dashboard
            filtered_metrics_data = {}
            for metric_name in metrics:
                if metric_name in metric_data:
                    filtered_metrics_data[metric_name] = metric_data[metric_name]

            trend_chart_image_b64 = create_trend_chart_image(filtered_metrics_data)

            payload = {
                "model_name": analysis_params["model_name"],
                "start_ts": analysis_params["start_ts"],
                "end_ts": analysis_params["end_ts"],
                "summarize_model_id": analysis_params["summarize_model_id"],
                "format": report_format,
                "api_key": analysis_params["api_key"],
                "health_prompt": st.session_state["prompt"],
                "llm_summary": st.session_state["summary"],
                "metrics_data": filtered_metrics_data,
            }
            filename = f"vllm_metrics_report.{report_format.lower()}"

        if trend_chart_image_b64:
            payload["trend_chart_image"] = trend_chart_image_b64

        response = requests.post(
            f"{API_URL}/generate_report",
            json=payload,
        )
        response.raise_for_status()
        report_id = response.json()["report_id"]
        download_response = requests.get(f"{API_URL}/download_report/{report_id}")
        download_response.raise_for_status()
        mime_map = {
            "HTML": "text/html",
            "PDF": "application/pdf",
            "Markdown": "text/markdown",
        }
        mime_type = mime_map.get(report_format, "application/octet-stream")
        trigger_download(download_response.content, filename, mime_type)
    except requests.exceptions.HTTPError as http_err:
        st.error(f"HTTP error during report generation: {http_err}")
    except Exception as e:
        st.error(f"❌ Error during report generation: {e}")


# Page-specific sidebar configuration
if page == "OpenShift Metrics":
    # OpenShift-specific sidebar controls
    st.sidebar.markdown("### OpenShift Configuration")

    # Get OpenShift namespaces
    openshift_namespaces = get_openshift_namespaces()

    # 1. Analysis Scope Selection (Dropdown)
    scope_type = st.sidebar.selectbox(
        "Analysis Scope",
        ["Cluster-wide", "Namespace scoped"],
        help="Choose whether to analyze the entire cluster or a specific namespace",
        key="openshift_scope_selector",
    )

    # 2. Namespace Selection (Conditional - grayed out if cluster-wide)
    selected_openshift_namespace = None
    if scope_type == "Namespace scoped":
        selected_openshift_namespace = st.sidebar.selectbox(
            "Select Namespace",
            openshift_namespaces,
            help="Choose the namespace to analyze",
            key="openshift_namespace_selector",
        )
    else:
        # Show disabled dropdown for cluster-wide
        st.sidebar.selectbox(
            "Select Namespace",
            ["All Namespaces (Cluster-wide)"],
            disabled=True,
            help="Namespace selection is disabled for cluster-wide analysis",
            key="openshift_namespace_disabled",
        )

    # 3. Metric Categories Selection (Conditional based on scope)
    if scope_type == "Namespace scoped":
        # Get namespace-specific metric groups (excludes GPU & Accelerators)
        openshift_metric_groups = get_openshift_namespace_metric_groups()
        help_text = "Choose metric category to analyze for this namespace"
    else:
        # Get all metric groups (includes GPU & Accelerators)
        openshift_metric_groups = get_openshift_metric_groups()
        help_text = "Choose metric category to analyze across the entire cluster"

    selected_metric_category = st.sidebar.selectbox(
        "Metric Category",
        openshift_metric_groups,
        help=help_text,
        key="openshift_metric_category_selector",
    )

    st.sidebar.markdown("---")

    # Common elements for OpenShift page
    st.sidebar.markdown("### Select Timestamp Range")
    
    # Start time selection
    if "selected_start_date" not in st.session_state:
        st.session_state["selected_start_date"] = (datetime.now() - pd.Timedelta(hours=1)).date()
    if "selected_start_time" not in st.session_state:
        st.session_state["selected_start_time"] = (datetime.now() - pd.Timedelta(hours=1)).time()
    
    selected_start_date = st.sidebar.date_input(
        "Start Date", value=st.session_state["selected_start_date"], key="openshift_start_date_input"
    )
    selected_start_time = st.sidebar.time_input(
        "Start Time", value=st.session_state["selected_start_time"], key="openshift_start_time_input"
    )
    selected_start_datetime = datetime.combine(selected_start_date, selected_start_time)
    
    # End time selection
    if "selected_end_date" not in st.session_state:
        st.session_state["selected_end_date"] = datetime.now().date()
    if "selected_end_time" not in st.session_state:
        st.session_state["selected_end_time"] = datetime.now().time()
    
    selected_end_date = st.sidebar.date_input(
        "End Date", value=st.session_state["selected_end_date"], key="openshift_end_date_input"
    )
    selected_end_time = st.sidebar.time_input(
        "End Time", value=st.session_state["selected_end_time"], key="openshift_end_time_input"
    )
    selected_end_datetime = datetime.combine(selected_end_date, selected_end_time)
    
    # Validation
    now = datetime.now()
    if selected_start_datetime > now:
        st.sidebar.warning("Start time cannot be in the future.")
        st.stop()
    if selected_end_datetime > now:
        st.sidebar.warning("End time cannot be in the future.")
        st.stop()
    if selected_start_datetime >= selected_end_datetime:
        st.sidebar.warning("Start time must be before end time.")
        st.stop()
    
    selected_start = int(selected_start_datetime.timestamp())
    selected_end = int(selected_end_datetime.timestamp())
    
    # Show selected time range
    duration = selected_end_datetime - selected_start_datetime
    st.sidebar.info(f"📅 Time Range: {duration}")

    st.sidebar.markdown("---")

    # --- Select LLM ---
    st.sidebar.markdown("### Select LLM for summarization")

    # --- Multi-model support ---
    multi_model_list = get_multi_models()
    multi_model_name = st.sidebar.selectbox(
        "Select LLM for summarization",
        multi_model_list,
        key="openshift_multi_model_selector",
    )

    # --- Define model key requirements ---
    model_config = get_model_config()
    current_model_requires_api_key = model_requires_api_key(
        multi_model_name, model_config
    )

    # --- API Key Input ---
    api_key = st.sidebar.text_input(
        label="🔑 API Key",
        type="password",
        value=st.session_state.get("api_key", ""),
        help="Enter your API key if required by the selected model",
        disabled=not current_model_requires_api_key,
        key="openshift_api_key",
    )

    # Caption to show key requirement status
    if current_model_requires_api_key:
        st.sidebar.caption("⚠️ This model requires an API key.")
    else:
        st.sidebar.caption("✅ No API key is required for this model.")

    # Optional validation warning if required key is missing
    if current_model_requires_api_key and not api_key:
        st.sidebar.warning("🚫 Please enter an API key to use this model.")

    # Set default values for variables not used in OpenShift page
    selected_namespace = None
    model_name = None

elif page == "Chat with Prometheus":
    # Chat with Prometheus-specific sidebar controls
    st.sidebar.markdown("### Chat Scope")
    
    # Chat scope selection
    chat_scope = st.sidebar.radio(
        "Select Chat Scope",
        ["Namespace-specific", "Fleet-wide"],
        help="Choose whether to analyze a specific namespace or the entire cluster",
        key="chat_scope_selector"
    )
    
    # Namespace selection (conditional based on scope)
    if chat_scope == "Namespace-specific":
        namespaces = get_namespaces()
        selected_namespace = st.sidebar.selectbox(
            "Select Namespace", 
            namespaces, 
            key="chat_namespace_selector"
        )
    else:
        # Fleet-wide: show disabled dropdown
        selected_namespace = None
        st.sidebar.selectbox(
            "Select Namespace",
            ["All Namespaces (Fleet-wide)"],
            disabled=True,
            help="Namespace selection is disabled for fleet-wide analysis",
            key="chat_namespace_disabled",
        )
    
    # Model selection (always needed for some model-specific queries)
    model_list = get_models()
    if chat_scope == "Namespace-specific" and selected_namespace:
        # Filter models by selected namespace
        filtered_models = [
            model for model in model_list if model.startswith(f"{selected_namespace} | ")
        ]
        if filtered_models:
            model_name = st.sidebar.selectbox(
                "Select Model", filtered_models, key="chat_model_selector"
            )
        else:
            model_name = None
            st.sidebar.warning(f"No models found in namespace {selected_namespace}")
    else:
        # Fleet-wide: use first available model as default
        model_name = model_list[0] if model_list else None
    
    st.sidebar.markdown("---")
    
    # --- Select LLM ---
    st.sidebar.markdown("### Select LLM for summarization")

    # --- Multi-model support ---
    multi_model_list = get_multi_models()
    multi_model_name = st.sidebar.selectbox(
        "Select LLM for summarization",
        multi_model_list,
        key="chat_multi_model_selector",
    )

    # --- Define model key requirements ---
    model_config = get_model_config()
    current_model_requires_api_key = model_requires_api_key(
        multi_model_name, model_config
    )

    # --- API Key Input ---
    api_key = st.sidebar.text_input(
        label="🔑 API Key",
        type="password",
        value=st.session_state.get("api_key", ""),
        help="Enter your API key if required by the selected model",
        disabled=not current_model_requires_api_key,
        key="chat_api_key",
    )

    # Caption to show key requirement status
    if current_model_requires_api_key:
        st.sidebar.caption("⚠️ This model requires an API key.")
    else:
        st.sidebar.caption("✅ No API key is required for this model.")
    
    # Set default timestamp range (not displayed to user since we have dynamic parsing)
    now = datetime.now()
    selected_start = int((now - pd.Timedelta(hours=1)).timestamp())  # Default to 1 hour ago
    selected_end = int(now.timestamp())

else:
    # vLLM-specific sidebar controls (for vLLM pages)
    st.sidebar.markdown("### vLLM Configuration")

    model_list = get_models()
    namespaces = get_namespaces()

    # Add namespace selector in sidebar
    selected_namespace = st.sidebar.selectbox(
        "Select Namespace", namespaces, key="namespace_selector"
    )

    # Filter models by selected namespace
    if selected_namespace:
        filtered_models = [
            model for model in model_list if model.startswith(f"{selected_namespace} | ")
        ]
    else:
        filtered_models = model_list
    
    # Show debug info if no models found
    if not filtered_models and selected_namespace:
        st.sidebar.warning(f"No models found for namespace: {selected_namespace}")
        filtered_models = ["No models available"]
    
    model_name = st.sidebar.selectbox(
        "Select Model", 
        filtered_models if filtered_models else ["No models available"], 
        key="model_selector"
    )

    st.sidebar.markdown("### Select Timestamp Range")
    
    # Start time selection
    if "selected_start_date" not in st.session_state:
        st.session_state["selected_start_date"] = (datetime.now() - pd.Timedelta(hours=1)).date()
    if "selected_start_time" not in st.session_state:
        st.session_state["selected_start_time"] = (datetime.now() - pd.Timedelta(hours=1)).time()
    
    selected_start_date = st.sidebar.date_input(
        "Start Date", value=st.session_state["selected_start_date"], key="vllm_start_date_input"
    )
    selected_start_time = st.sidebar.time_input(
        "Start Time", value=st.session_state["selected_start_time"], key="vllm_start_time_input"
    )
    selected_start_datetime = datetime.combine(selected_start_date, selected_start_time)
    
    # End time selection
    if "selected_end_date" not in st.session_state:
        st.session_state["selected_end_date"] = datetime.now().date()
    if "selected_end_time" not in st.session_state:
        st.session_state["selected_end_time"] = datetime.now().time()
    
    selected_end_date = st.sidebar.date_input(
        "End Date", value=st.session_state["selected_end_date"], key="vllm_end_date_input"
    )
    selected_end_time = st.sidebar.time_input(
        "End Time", value=st.session_state["selected_end_time"], key="vllm_end_time_input"
    )
    selected_end_datetime = datetime.combine(selected_end_date, selected_end_time)
    
    # Validation
    now = datetime.now()
    if selected_start_datetime > now:
        st.sidebar.warning("Start time cannot be in the future.")
        st.stop()
    if selected_end_datetime > now:
        st.sidebar.warning("End time cannot be in the future.")
        st.stop()
    if selected_start_datetime >= selected_end_datetime:
        st.sidebar.warning("Start time must be before end time.")
        st.stop()
    
    selected_start = int(selected_start_datetime.timestamp())
    selected_end = int(selected_end_datetime.timestamp())
    
    # Show selected time range
    duration = selected_end_datetime - selected_start_datetime
    st.sidebar.info(f"📅 Time Range: {duration}")

    st.sidebar.markdown("---")

    # --- Select LLM ---
    st.sidebar.markdown("### Select LLM for summarization")

    # --- Multi-model support ---
    multi_model_list = get_multi_models()
    multi_model_name = st.sidebar.selectbox(
        "Select LLM for summarization",
        multi_model_list,
        key="vllm_multi_model_selector",
    )

    # --- Define model key requirements ---
    model_config = get_model_config()
    current_model_requires_api_key = model_requires_api_key(
        multi_model_name, model_config
    )

    # --- API Key Input ---
    api_key = st.sidebar.text_input(
        label="🔑 API Key",
        type="password",
        value=st.session_state.get("api_key", ""),
        help="Enter your API key if required by the selected model",
        disabled=not current_model_requires_api_key,
        key="default_api_key",
    )

    # Caption to show key requirement status
    if current_model_requires_api_key:
        st.sidebar.caption("⚠️ This model requires an API key.")
    else:
        st.sidebar.caption("✅ No API key is required for this model.")
    
    # Set chat_scope to None for non-chat pages
    chat_scope = None


# --- Report Generation ---
st.sidebar.markdown("---")
st.sidebar.markdown("### Download Report")

analysis_performed = st.session_state.get("analysis_performed", False)

if not analysis_performed:
    st.sidebar.warning("⚠️ Please analyze metrics first to generate a report.")

report_format = st.sidebar.selectbox(
    "Select Report Format",
    ["HTML", "PDF", "Markdown"],
    disabled=not analysis_performed,
    key="report_format_selector",
)

if analysis_performed:
    if "download_button_clicked" not in st.session_state:
        st.session_state.download_button_clicked = False

    if st.sidebar.button("📥 Download Report"):
        st.session_state.download_button_clicked = True

    # Move the spinner_placeholder definition AFTER the button
    spinner_placeholder = st.sidebar.empty()

    if st.session_state.download_button_clicked:
        with spinner_placeholder.container():
            with st.spinner("Downloading report..."):
                time.sleep(2)  # This line adds a 2-second delay
                generate_report_and_download(report_format)
        st.session_state.download_button_clicked = False

# --- 📊 vLLM Metric Summarizer Page ---
if page == "vLLM Metric Summarizer":
    st.markdown("<h1>vLLM Metric Summarizer</h1>", unsafe_allow_html=True)

    # --- Analyze Button ---
    if st.button("🔍 Analyze Metrics"):
        with st.spinner("Analyzing metrics..."):
            try:
                # Get parameters from sidebar
                params = {
                    "model_name": model_name,
                    "start_ts": selected_start,
                    "end_ts": selected_end,
                    "summarize_model_id": multi_model_name,
                    "api_key": api_key,
                }

                response = requests.post(f"{API_URL}/analyze", json=params)
                response.raise_for_status()
                result = response.json()

                # Store results in session state
                st.session_state["prompt"] = result["health_prompt"]
                st.session_state["summary"] = result["llm_summary"]
                st.session_state["model_name"] = params["model_name"]
                st.session_state["metric_data"] = result.get("metrics", {})
                st.session_state["analysis_params"] = (
                    params  # Store for report generation
                )
                st.session_state["analysis_performed"] = (
                    True  # Mark that analysis was performed
                )

                # Force rerun to update the UI state (enable download button and hide warning)
                st.rerun()

            except requests.exceptions.HTTPError as http_err:
                clear_session_state()
                handle_http_error(http_err.response, "Analysis failed")
            except Exception as e:
                clear_session_state()
                st.error(f"❌ Error during analysis: {e}")

    if "summary" in st.session_state:
        col1, col2 = st.columns([1.3, 1.7])
        with col1:
            st.markdown("### 🧠 Model Insights Summary")
            st.markdown(st.session_state["summary"])
            st.markdown("### 💬 Ask Assistant")
            question = st.text_input(
                "Ask a follow-up question", key="vllm_followup_question"
            )
            if st.button("Ask"):
                with st.spinner("Assistant is thinking..."):
                    try:
                        reply = requests.post(
                            f"{API_URL}/chat",
                            json={
                                "model_name": st.session_state["model_name"],
                                "summarize_model_id": multi_model_name,
                                "prompt_summary": st.session_state["prompt"],
                                "question": question,
                                "api_key": api_key,
                            },
                        )
                        reply.raise_for_status()
                        st.markdown("**Assistant's Response:**")
                        st.markdown(reply.json()["response"])
                    except requests.exceptions.HTTPError as http_err:
                        handle_http_error(http_err.response, "Chat failed")
                    except Exception as e:
                        st.error(f"❌ Chat failed: {e}")

        with col2:
            st.markdown("### 📊 Metric Dashboard")

            # Use the shared function to get metrics data
            metric_data, metrics = get_metrics_data_and_list()

            # Get calculated metrics from MCP
            calculated_metrics = get_calculated_metrics_from_mcp(metric_data)

            metric_data = st.session_state.get("metric_data", {})

            # Get dynamic vLLM metrics and prioritize useful ones for display
            available_vllm_metrics = get_vllm_metrics()

            if available_vllm_metrics:
                # Priority order for metrics to display (most useful first)
                priority_metrics = [
                    "GPU Temperature (°C)",
                    "GPU Power Usage (Watts)",
                    "P95 Latency (s)",
                    "GPU Usage (%)",
                    "Output Tokens Created",
                    "Prompt Tokens Created",
                    "Requests Running",
                    "Inference Time (s)",
                    "GPU Memory Usage (GB)",
                    "GPU Energy Consumption (Joules)",
                ]

                # Filter available metrics based on priority, excluding cache config
                metrics = []
                for priority_metric in priority_metrics:
                    if priority_metric in available_vllm_metrics:
                        metrics.append(priority_metric)
                        if len(metrics) >= 6:
                            break

                # If we don't have 6 metrics yet, add remaining ones (excluding cache config)
                if len(metrics) < 6:
                    for metric_name in available_vllm_metrics.keys():
                        if (
                            metric_name not in metrics
                            and "Cache Config" not in metric_name
                        ):
                            metrics.append(metric_name)
                            if len(metrics) >= 6:
                                break
            else:
                # Fallback with GPU-focused metrics
                metrics = [
                    "GPU Temperature (°C)",
                    "GPU Power Usage (Watts)",
                    "P95 Latency (s)",
                    "GPU Usage (%)",
                    "GPU Memory Usage (GB)",
                    "Output Tokens Created",
                ]

            # Check if this is a new deployment with no data
            is_new_deployment = check_if_new_deployment(calculated_metrics, model_name)
            
            # Display deployment info banner if new deployment detected
            if is_new_deployment:
                display_new_deployment_info(model_name)

            cols = st.columns(3)
            for i, label in enumerate(metrics):
                with cols[i % 3]:
                    if label in calculated_metrics:
                        calc_data = calculated_metrics[label]
                        if (
                            calc_data["avg"] is not None
                            and calc_data["max"] is not None
                        ):
                            avg_val = calc_data["avg"]
                            max_val = calc_data["max"]

                            # Enhanced unit formatting for vLLM metrics
                            if "Temperature" in label and "°C" in label:
                                value_display = f"{avg_val:.1f}°C"
                                delta_display = f"Max: {max_val:.1f}°C"
                            elif "Power Usage" in label and "Watts" in label:
                                value_display = f"{avg_val:.1f}W"
                                delta_display = f"Max: {max_val:.1f}W"
                            elif "Energy" in label and "Joules" in label:
                                if avg_val >= 1000:
                                    value_display = f"{avg_val/1000:.1f}kJ"
                                    delta_display = f"Max: {max_val/1000:.1f}kJ"
                                else:
                                    value_display = f"{avg_val:.0f}J"
                                    delta_display = f"Max: {max_val:.0f}J"
                            elif "Memory Usage" in label and "GB" in label:
                                value_display = f"{avg_val:.1f}GB"
                                delta_display = f"Max: {max_val:.1f}GB"
                            elif "Memory Usage" in label and "%" in label:
                                value_display = f"{avg_val:.1f}%"
                                delta_display = f"Max: {max_val:.1f}%"
                            elif "Usage" in label and "%" in label:
                                value_display = f"{avg_val:.1f}%"
                                delta_display = f"Max: {max_val:.1f}%"
                            elif "Utilization" in label and "%" in label:
                                value_display = f"{avg_val:.1f}%"
                                delta_display = f"Max: {max_val:.1f}%"
                            elif "Latency" in label:
                                if avg_val >= 1:
                                    value_display = f"{avg_val:.2f}s"
                                    delta_display = f"Max: {max_val:.2f}s"
                                else:
                                    value_display = f"{avg_val*1000:.0f}ms"
                                    delta_display = f"Max: {max_val*1000:.0f}ms"
                            elif "Tokens" in label:
                                if avg_val >= 1000000:
                                    value_display = f"{avg_val/1000000:.1f}M"
                                    delta_display = f"Max: {max_val/1000000:.1f}M"
                                elif avg_val >= 1000:
                                    value_display = f"{avg_val/1000:.1f}k"
                                    delta_display = f"Max: {max_val/1000:.1f}k"
                                else:
                                    value_display = f"{avg_val:.0f}"
                                    delta_display = f"Max: {max_val:.0f}"
                            elif "Time" in label:
                                if avg_val >= 1:
                                    value_display = f"{avg_val:.2f}s"
                                    delta_display = f"Max: {max_val:.2f}s"
                                else:
                                    value_display = f"{avg_val*1000:.0f}ms"
                                    delta_display = f"Max: {max_val*1000:.0f}ms"
                            elif "Requests" in label:
                                value_display = f"{avg_val:.0f}"
                                delta_display = f"Max: {max_val:.0f}"
                            else:
                                value_display = f"{avg_val:.2f}"
                                delta_display = f"Max: {max_val:.2f}"

                            # Clean up label for display
                            display_label = (
                                label.replace(" (°C)", "")
                                .replace(" (Watts)", "")
                                .replace(" (%)", "")
                                .replace(" (s)", "")
                                .replace(" (Joules)", "")
                            )

                            st.metric(
                                label=display_label,
                                value=value_display,
                                delta=delta_display,
                            )
                        else:
                            # Show deployment-aware message for no data
                            if is_new_deployment:
                                st.metric(label=label, value="🚀 New", delta="Awaiting data")
                            else:
                                st.metric(label=label, value="N/A", delta="No data")
                    else:
                        # Show deployment-aware message for no data
                        if is_new_deployment:
                            st.metric(label=label, value="🚀 New", delta="Awaiting data")
                        else:
                            st.metric(label=label, value="N/A", delta="No data")

            st.markdown("### 📈 Trend Over Time")
            dfs = process_chart_data(metric_data)
            if dfs:
                chart_df = pd.concat(dfs, axis=1).fillna(0)
                st.line_chart(chart_df)
            else:
                st.info("No data available to generate chart.")

# --- 🤖 Chat with Prometheus Page ---
elif page == "Chat with Prometheus":
    st.markdown("<h1>Chat with Prometheus</h1>", unsafe_allow_html=True)
    
    # Display current scope configuration
    if chat_scope == "Fleet-wide":
        st.markdown("🌐 **Fleet-wide analysis** - Querying metrics across all namespaces")
        st.markdown(
            "Ask questions like: `Total GPU usage across all namespaces?`, `Which namespace has highest latency?`, `What alerts were firing cluster-wide yesterday?` etc."
        )
    else:
        st.markdown(f"🏷️ **Namespace-specific analysis** - Currently selected namespace: **{selected_namespace}**")
        st.markdown(
            "Ask questions like: `What's the P95 latency in past 1 hour?`, `Is GPU usage stable in my namespace?`, `What alerts were firing in my namespace yesterday?` etc."
        )
    
    # Helpful hint about dynamic time parsing
    st.info(
        "💡 **Smart Time Parsing**: Just mention time naturally in your question! "
        "Examples: *'past 15 minutes'*, *'last 3 hours'*, *'yesterday'*, *'past 2 weeks'*"
    )

    # --- Chat history management ---
    if "messages" not in st.session_state:
        st.session_state.messages = []  # List to store chat messages

    # Display previous chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    user_question = st.chat_input("Your question")
    if user_question:
        st.session_state.messages.append({"role": "user", "content": user_question})
        with st.chat_message("user"):
            st.markdown(user_question)

        with st.spinner("Querying and summarizing..."):
            try:
                # Convert chat scope to backend format
                backend_chat_scope = "fleet_wide" if chat_scope == "Fleet-wide" else "namespace_specific"
                
                response = requests.post(
                    f"{API_URL}/chat-metrics",
                    json={
                        "model_name": model_name or "default",  # Provide default if None
                        "question": user_question,
                        "start_ts": selected_start,
                        "end_ts": selected_end,
                        "namespace": selected_namespace or "",  # Provide empty string if None
                        "summarize_model_id": multi_model_name,
                        "api_key": api_key,
                        "chat_scope": backend_chat_scope,
                    },
                )
                data = response.json()
                promql = data.get("promql", "")
                summary = data.get("summary", "")
                chat_scope_response = data.get("chat_scope", "namespace_specific")
                time_range = data.get("time_range", "")
                
                if not summary:
                    st.error("Error: Missing summary in response from AI.")
                else:
                    # Adding AI response to history ---
                    ai_response_content = ""
                    
                    # Show generated PromQL
                    if promql:
                        ai_response_content += (
                            "**Generated PromQL:**\n```promql\n" + promql + "\n```\n\n"
                        )
                    else:
                        ai_response_content += (
                            "_No direct PromQL generated for this question._\n\n"
                        )
                    
                    # Show AI Summary
                    ai_response_content += "**AI Summary:**\n\n" + summary
                    
                    # Show additional context if available
                    if time_range:
                        ai_response_content += f"\n\n📅 **Time Range:** {time_range}"
                    
                    scope_display = "Fleet-wide" if chat_scope_response == "fleet_wide" else "Namespace-specific"
                    ai_response_content += f"\n🔍 **Scope:** {scope_display}"

                    st.session_state.messages.append(
                        {"role": "assistant", "content": ai_response_content}
                    )
                    with st.chat_message("assistant"):
                        st.markdown(ai_response_content)

            except Exception as e:
                st.error(f"Error: {e}")


# --- 🔧 OpenShift Metrics Page ---
elif page == "OpenShift Metrics":
    st.markdown("<h1>OpenShift Metrics Dashboard</h1>", unsafe_allow_html=True)

    # Display current configuration
    scope_display = scope_type + (
        f" ({selected_openshift_namespace})" if selected_openshift_namespace else ""
    )
    category_display = selected_metric_category
    st.markdown(
        f"**Analysis Scope:** {scope_display} | **Category:** {category_display}"
    )

    # Fleet view indicator for cluster-wide
    if scope_type == "Cluster-wide":
        st.info(
            "🌐 **Fleet View**: Analyzing metrics across the entire OpenShift cluster"
        )

    # --- Analyze Button ---
    if st.button("🔍 Analyze OpenShift Metrics"):
        analysis_type = (
            "Fleet Analysis" if scope_type == "Cluster-wide" else "Namespace Analysis"
        )
        with st.spinner(f"Running {analysis_type}..."):
            try:
                # Get parameters for OpenShift analysis
                params = {
                    "metric_category": selected_metric_category,  # Specific category
                    "scope": scope_type.lower()
                    .replace("-", "_")
                    .replace(" ", "_"),  # "cluster_wide" or "namespace_scoped"
                    "namespace": selected_openshift_namespace,  # None for cluster-wide
                    "start_ts": selected_start,
                    "end_ts": selected_end,
                    "summarize_model_id": multi_model_name,
                    "api_key": api_key,
                }

                response = requests.post(f"{API_URL}/analyze-openshift", json=params)
                response.raise_for_status()
                result = response.json()

                # Store results in session state
                st.session_state["openshift_prompt"] = result["health_prompt"]
                st.session_state["openshift_summary"] = result["llm_summary"]
                st.session_state["openshift_metric_category"] = params[
                    "metric_category"
                ]
                st.session_state["openshift_scope"] = params["scope"]
                st.session_state["openshift_namespace"] = params["namespace"]
                st.session_state["openshift_metric_data"] = result.get("metrics", {})
                st.session_state["openshift_analysis_type"] = analysis_type

                # Store analysis parameters for report generation
                st.session_state["analysis_params"] = params

                # Enable download button for OpenShift analysis
                st.session_state["analysis_performed"] = True

                success_msg = f"✅ {analysis_type} completed successfully! Analyzed {len(result.get('metrics', {}))} metric types."
                st.success(success_msg)

                # Force rerun to update the UI state (enable download button)
                st.rerun()
            except requests.exceptions.HTTPError as http_err:
                clear_session_state()
                handle_http_error(http_err.response, f"{analysis_type} failed")
            except Exception as e:
                clear_session_state()
                st.error(f"❌ Error during {analysis_type}: {e}")

    # Display results if available
    if "openshift_summary" in st.session_state:
        col1, col2 = st.columns([1.3, 1.7])

        with col1:
            st.markdown("### OpenShift Insights Summary")
            st.markdown(st.session_state["openshift_summary"])

            st.markdown("### Ask About OpenShift")
            openshift_question = st.text_input(
                "Ask a question about OpenShift metrics", key="openshift_question"
            )
            if st.button("Ask OpenShift Assistant"):
                with st.spinner("OpenShift assistant is thinking..."):
                    try:
                        reply = requests.post(
                            f"{API_URL}/chat-openshift",
                            json={
                                "metric_category": st.session_state[
                                    "openshift_metric_category"
                                ],
                                "question": openshift_question,
                                "scope": st.session_state["openshift_scope"],
                                "namespace": st.session_state["openshift_namespace"],
                                "start_ts": selected_start,
                                "end_ts": selected_end,
                                "summarize_model_id": multi_model_name,
                                "api_key": api_key,
                            },
                        )
                        reply.raise_for_status()
                        response_data = reply.json()
                        st.markdown("**Assistant's Response:**")
                        st.markdown(response_data["summary"])
                        if response_data.get("promql"):
                            st.markdown("**Generated PromQL:**")
                            st.code(response_data["promql"], language="yaml")
                    except requests.exceptions.HTTPError as http_err:
                        handle_http_error(http_err.response, "OpenShift chat failed")
                    except Exception as e:
                        st.error(f"❌ OpenShift chat failed: {e}")

        with col2:
            # Determine dashboard title based on analysis type
            analysis_type = st.session_state.get("openshift_analysis_type", "Analysis")
            metric_category = st.session_state.get("openshift_metric_category", "")
            scope = st.session_state.get("openshift_scope", "cluster_wide")

            if analysis_type == "Fleet Analysis":
                st.markdown("### 🌐 OpenShift Fleet Dashboard")
            else:
                st.markdown("### 📊 OpenShift Metrics Dashboard")

            metric_data = st.session_state.get("openshift_metric_data", {})

            # Determine metrics to show based on category selection and scope
            scope = st.session_state.get("openshift_scope", "cluster_wide")

            if scope == "namespace_scoped":
                # Show namespace-specific metrics that actually have data
                if metric_category == "Fleet Overview":
                    metrics_to_show = [
                        "Pods Running",
                        "Pods Failed",
                        "Container CPU Usage",
                        "Container Memory Usage",
                        "Pod Restart Rate",
                        "Deployment Replicas Ready",
                    ]
                elif metric_category == "Workloads & Pods":
                    metrics_to_show = [
                        "Pods Running",
                        "Pods Pending",
                        "Pods Failed",
                        "Pod Restarts (Rate)",
                        "Container CPU Usage",
                        "Container Memory Usage",
                    ]
                elif metric_category == "Compute & Resources":
                    metrics_to_show = [
                        "Container CPU Throttling",
                        "Container Memory Failures",
                        "OOM Events",
                        "Container Processes",
                        "Container Threads",
                        "Container File Descriptors",
                    ]
                elif metric_category == "Storage & Networking":
                    metrics_to_show = [
                        "PV Claims Bound",
                        "PV Claims Pending",
                        "Container Network Receive",
                        "Container Network Transmit",
                        "Network Errors",
                        "Filesystem Usage",
                    ]
                elif metric_category == "Application Services":
                    metrics_to_show = [
                        "HTTP Request Rate",
                        "HTTP Error Rate (%)",
                        "Service Endpoints",
                        "Container Processes",
                        "Container File Descriptors",
                        "Container Threads",
                    ]
                else:
                    metrics_to_show = list(metric_data.keys())[:6]
            else:
                # Cluster-wide metrics (original)
                if metric_category == "Fleet Overview":
                    metrics_to_show = [
                        "Total Pods Running",
                        "Total Pods Failed",
                        "Cluster CPU Usage (%)",
                        "Cluster Memory Usage (%)",
                        "GPU Utilization (%)",
                        "GPU Temperature (°C)",
                    ]
                elif metric_category == "Workloads & Pods":
                    metrics_to_show = [
                        "Pods Running",
                        "Pods Pending",
                        "Pods Failed",
                        "Pod Restarts (Rate)",
                        "Container CPU Usage",
                        "Container Memory Usage",
                    ]
                elif metric_category == "GPU & Accelerators":
                    metrics_to_show = [
                        "GPU Temperature (°C)",
                        "GPU Power Usage (Watts)",
                        "GPU Utilization (%)",
                        "GPU Memory Usage (GB)",
                        "GPU Energy Consumption (Joules)",
                        "GPU Memory Temperature (°C)",
                    ]
                elif metric_category == "Storage & Networking":
                    metrics_to_show = [
                        "PV Available Space",
                        "PVC Bound",
                        "Storage I/O Rate",
                        "Network Receive Rate",
                        "Network Transmit Rate",
                        "Network Errors",
                    ]
                elif metric_category == "Application Services":
                    metrics_to_show = [
                        "HTTP Request Rate",
                        "HTTP Error Rate (%)",
                        "HTTP P95 Latency",
                        "Services Available",
                        "Ingress Request Rate",
                        "Load Balancer Backends",
                    ]
                else:
                    metrics_to_show = list(metric_data.keys())[:6]  # Fallback

            # Display metrics in a grid
            cols = st.columns(3)
            for i, label in enumerate(metrics_to_show):
                df = metric_data.get(label)
                if df:
                    try:
                        values = [point["value"] for point in df]
                        if values:
                            avg_val = sum(values) / len(values)
                            latest_val = values[-1]
                            with cols[i % 3]:
                                # Comprehensive unit formatting for OpenShift metrics
                                if "Power Usage" in label and "Watts" in label:
                                    value_display = f"{avg_val:.1f}W"
                                    delta_display = f"Latest: {latest_val:.1f}W"
                                elif "Temperature" in label and "°C" in label:
                                    value_display = f"{avg_val:.1f}°C"
                                    delta_display = f"Latest: {latest_val:.1f}°C"
                                elif "Energy" in label and "Joules" in label:
                                    if avg_val >= 1000:
                                        value_display = f"{avg_val/1000:.1f}kJ"
                                        delta_display = f"Latest: {latest_val/1000:.1f}kJ" if latest_val >= 1000 else f"Latest: {latest_val:.0f}J"
                                    else:
                                        value_display = f"{avg_val:.0f}J"
                                        delta_display = f"Latest: {latest_val:.0f}J"
                                elif "Clock" in label and "MHz" in label:
                                    if avg_val >= 1000:
                                        value_display = f"{avg_val/1000:.1f}GHz"
                                        delta_display = f"Latest: {latest_val/1000:.1f}GHz" if latest_val >= 1000 else f"Latest: {latest_val:.0f}MHz"
                                    else:
                                        value_display = f"{avg_val:.0f}MHz"
                                        delta_display = f"Latest: {latest_val:.0f}MHz"
                                elif "Memory Usage" in label and "GB" in label:
                                    # GPU Memory in GB
                                    value_display = f"{avg_val:.1f}GB"
                                    delta_display = f"Latest: {latest_val:.1f}GB"
                                elif "Memory Usage" in label and "bytes" in label:
                                    # Convert bytes to appropriate units
                                    if avg_val >= 1024**3:  # GB
                                        value_display = f"{avg_val/(1024**3):.1f}GB"
                                        if latest_val >= 1024**3:
                                            delta_display = f"Latest: {latest_val/(1024**3):.1f}GB"
                                        elif latest_val >= 1024**2:
                                            delta_display = f"Latest: {latest_val/(1024**2):.0f}MB"
                                        else:
                                            delta_display = f"Latest: {latest_val/1024:.0f}KB"
                                    elif avg_val >= 1024**2:  # MB
                                        value_display = f"{avg_val/(1024**2):.0f}MB"
                                        if latest_val >= 1024**2:
                                            delta_display = f"Latest: {latest_val/(1024**2):.0f}MB"
                                        else:
                                            delta_display = f"Latest: {latest_val/1024:.0f}KB"
                                    elif avg_val >= 1024:  # KB
                                        value_display = f"{avg_val/1024:.0f}KB"
                                        delta_display = f"Latest: {latest_val/1024:.0f}KB"
                                    else:
                                        value_display = f"{avg_val:.0f}B"
                                        delta_display = f"Latest: {latest_val:.0f}B"
                                elif "Available Space" in label or "Space" in label:
                                    # Storage metrics in bytes
                                    if avg_val >= 1024**4:  # TB
                                        value_display = f"{avg_val/(1024**4):.1f}TB"
                                        delta_display = f"Latest: {latest_val/(1024**4):.1f}TB" if latest_val >= 1024**4 else f"Latest: {latest_val/(1024**3):.0f}GB"
                                    elif avg_val >= 1024**3:  # GB
                                        value_display = f"{avg_val/(1024**3):.0f}GB"
                                        delta_display = f"Latest: {latest_val/(1024**3):.0f}GB" if latest_val >= 1024**3 else f"Latest: {latest_val/(1024**2):.0f}MB"
                                    else:
                                        value_display = f"{avg_val/(1024**2):.0f}MB"
                                        delta_display = f"Latest: {latest_val/(1024**2):.0f}MB"
                                elif "Network" in label and (
                                    "Receive" in label or "Transmit" in label
                                ):
                                    # Network metrics - bytes/sec
                                    if avg_val >= 1024**2:  # MB/s
                                        value_display = f"{avg_val/(1024**2):.1f}MB/s"
                                        delta_display = f"Latest: {latest_val/(1024**2):.1f}MB/s" if latest_val >= 1024**2 else f"Latest: {latest_val/1024:.0f}KB/s"
                                    elif avg_val >= 1024:  # KB/s
                                        value_display = f"{avg_val/1024:.0f}KB/s"
                                        delta_display = f"Latest: {latest_val/1024:.0f}KB/s"
                                    else:
                                        value_display = f"{avg_val:.0f}B/s"
                                        delta_display = f"Latest: {latest_val:.0f}B/s"
                                elif "Rate" in label and (
                                    "Request" in label or "HTTP" in label
                                ):
                                    # Request rates
                                    if avg_val >= 1000:
                                        value_display = f"{avg_val/1000:.1f}k/s"
                                        delta_display = f"Latest: {latest_val/1000:.1f}k/s" if latest_val >= 1000 else f"Latest: {latest_val:.1f}/s"
                                    else:
                                        value_display = f"{avg_val:.1f}/s"
                                        delta_display = f"Latest: {latest_val:.1f}/s"
                                elif "Latency" in label:
                                    # Latency metrics
                                    if avg_val >= 1:
                                        value_display = f"{avg_val:.2f}s"
                                        delta_display = f"Latest: {latest_val:.2f}s" if latest_val >= 1 else f"Latest: {latest_val*1000:.0f}ms"
                                    else:
                                        value_display = f"{avg_val*1000:.0f}ms"
                                        delta_display = f"Latest: {latest_val*1000:.0f}ms"
                                elif "Usage" in label and "%" in label:
                                    value_display = f"{avg_val:.1f}%"
                                    delta_display = f"Latest: {latest_val:.1f}%"
                                elif "Utilization" in label and "%" in label:
                                    value_display = f"{avg_val:.1f}%"
                                    delta_display = f"Latest: {latest_val:.1f}%"
                                elif "CPU" in label and "%" in label:
                                    value_display = f"{avg_val:.1f}%"
                                    delta_display = f"Latest: {latest_val:.1f}%"
                                elif "Memory" in label and "%" in label:
                                    value_display = f"{avg_val:.1f}%"
                                    delta_display = f"Latest: {latest_val:.1f}%"
                                elif "Error Rate" in label and "%" in label:
                                    value_display = f"{avg_val:.2f}%"
                                    delta_display = f"Latest: {latest_val:.2f}%"
                                elif (
                                    "Pods" in label
                                    or "Replicas" in label
                                    or "Nodes" in label
                                ):
                                    # Count metrics
                                    value_display = f"{avg_val:.0f}"
                                    delta_display = f"Latest: {latest_val:.0f}"
                                elif (
                                    "Restarts" in label
                                    or "Errors" in label
                                    or "Events" in label
                                ):
                                    # Rate metrics
                                    value_display = f"{avg_val:.2f}/s"
                                    delta_display = f"Latest: {latest_val:.2f}/s"
                                else:
                                    # Default formatting
                                    if avg_val >= 1000000:
                                        value_display = f"{avg_val/1000000:.1f}M"
                                        delta_display = f"Latest: {latest_val/1000000:.1f}M" if latest_val >= 1000000 else f"Latest: {latest_val/1000:.1f}k" if latest_val >= 1000 else f"Latest: {latest_val:.2f}"
                                    elif avg_val >= 1000:
                                        value_display = f"{avg_val/1000:.1f}k"
                                        delta_display = f"Latest: {latest_val/1000:.1f}k" if latest_val >= 1000 else f"Latest: {latest_val:.2f}"
                                    else:
                                        value_display = f"{avg_val:.2f}"
                                        delta_display = f"Latest: {latest_val:.2f}"

                                st.metric(
                                    label=label.replace(" (bytes/sec)", "")
                                    .replace(" (bytes)", "")
                                    .replace(" (%)", "")
                                    .replace(" (Watts)", "")
                                    .replace(" (°C)", "")
                                    .replace(" (Joules)", "")
                                    .replace(" (MHz)", ""),
                                    value=value_display,
                                    delta=delta_display,
                                )
                        else:
                            with cols[i % 3]:
                                st.metric(label=label, value="No data", delta="N/A")
                    except Exception as e:
                        with cols[i % 3]:
                            st.metric(label=label, value="Error", delta=str(e)[:20])
                else:
                    with cols[i % 3]:
                        st.metric(label=label, value="N/A", delta="No data")

            # Time series chart for key metrics
            if analysis_type == "Fleet Analysis":
                st.markdown("### 📈 Fleet Trends Over Time")
            else:
                st.markdown("### 📈 Trends Over Time")

            # Determine chart metrics based on category and scope
            chart_metrics = []
            if scope == "namespace_scoped":
                if metric_category == "Fleet Overview":
                    chart_metrics = [
                        "Namespace Pods Running",
                        "Container CPU Usage",
                        "Container Memory Usage",
                    ]
                elif metric_category == "Workloads & Pods":
                    chart_metrics = [
                        "Pods Running",
                        "Container CPU Usage",
                        "Pod Restarts (Rate)",
                    ]
                elif metric_category == "Compute & Resources":
                    chart_metrics = [
                        "Container CPU Throttling",
                        "Container Memory Failures",
                        "OOM Events",
                    ]
                elif metric_category == "Storage & Networking":
                    chart_metrics = [
                        "Container Network Receive",
                        "Container Network Transmit",
                        "Filesystem Usage",
                    ]
                elif metric_category == "Application Services":
                    chart_metrics = [
                        "Container Processes",
                        "Container File Descriptors",
                        "Container Threads",
                    ]
            else:
                if metric_category == "Fleet Overview":
                    chart_metrics = [
                        "Total Pods Running",
                        "Cluster CPU Usage (%)",
                        "GPU Utilization (%)",
                        "GPU Temperature (°C)",
                    ]
                elif metric_category == "Workloads & Pods":
                    chart_metrics = [
                        "Pods Running",
                        "Container CPU Usage",
                        "Pod Restarts (Rate)",
                    ]
                elif metric_category == "GPU & Accelerators":
                    chart_metrics = [
                        "GPU Utilization (%)",
                        "GPU Temperature (°C)",
                        "GPU Power Usage (Watts)",
                        "GPU Memory Usage (GB)",
                    ]
                elif metric_category == "Storage & Networking":
                    chart_metrics = [
                        "Network Receive Rate",
                        "Network Transmit Rate",
                        "Storage I/O Rate",
                    ]
                elif metric_category == "Application Services":
                    chart_metrics = [
                        "HTTP Request Rate",
                        "HTTP Error Rate (%)",
                        "HTTP P95 Latency",
                    ]

            # Filter chart metrics to only include those with data
            chart_metrics = [
                m for m in chart_metrics if m in metric_data and metric_data[m]
            ]

            dfs = []
            for label in chart_metrics:
                raw_data = metric_data.get(label, [])
                if raw_data:
                    try:
                        timestamps = [
                            datetime.fromisoformat(p["timestamp"]) for p in raw_data
                        ]
                        values = [p["value"] for p in raw_data]
                        df = pd.DataFrame({label: values}, index=timestamps)
                        dfs.append(df)
                    except Exception as e:
                        st.warning(f"Chart error for {label}: {e}")

            if dfs:
                chart_df = pd.concat(dfs, axis=1).fillna(0)
                st.line_chart(chart_df)
            else:
                st.info(f"No time series data available for {metric_category} metrics.")

            # Analysis scope information
            st.markdown(f"### ℹ️ Analysis Details")
            scope_text = (
                "Cluster-wide" if scope == "cluster_wide" else "Namespace scoped"
            )
            namespace_info = (
                f" | **Namespace:** {st.session_state.get('openshift_namespace', 'N/A')}"
                if scope == "namespace_scoped"
                else ""
            )
            category_info = f" | **Category:** {metric_category}"

            st.info(f"**Scope:** {scope_text}{namespace_info}{category_info}")

            # Additional fleet view information
            if analysis_type == "Fleet Analysis":
                total_metrics = len(metric_data)
                st.info(
                    f"🌐 **Fleet Analysis**: Monitoring {total_metrics} metric types across the entire OpenShift cluster"
                )

                # GPU Fleet Information
                if (
                    metric_category == "Fleet Overview"
                    or metric_category == "GPU & Accelerators"
                ):
                    gpu_info = get_gpu_info()
                    if gpu_info["total_gpus"] > 0:
                        gpu_summary = (
                            f"🖥️ **GPU Fleet**: {gpu_info['total_gpus']} GPUs detected"
                        )
                        if gpu_info["vendors"]:
                            gpu_summary += (
                                f" | **Vendors**: {', '.join(gpu_info['vendors'])}"
                            )
                        if gpu_info["models"]:
                            gpu_summary += f" | **Models**: {', '.join(gpu_info['models'][:3])}"  # Show first 3 models
                        if gpu_info["temperatures"]:
                            avg_temp = sum(gpu_info["temperatures"]) / len(
                                gpu_info["temperatures"]
                            )
                            gpu_summary += f" | **Avg Temp**: {avg_temp:.1f}°C"
                        st.info(gpu_summary)
                    elif metric_category == "GPU & Accelerators":
                        st.warning(
                            "⚠️ No GPU information detected. Check if DCGM metrics are available in your cluster."
                        )