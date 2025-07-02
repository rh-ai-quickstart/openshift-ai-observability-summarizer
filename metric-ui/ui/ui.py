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
API_URL = os.getenv("MCP_API_URL", "http://localhost:8000")
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
page = st.sidebar.radio("Go to:", ["📊 vLLM Metric Summarizer", "🤖 Chat with Prometheus", "🔧 OpenShift Metrics"])


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
    try:
        res = requests.get(f"{API_URL}/models")
        models = res.json()
        # Extract unique namespaces from model names (format: "namespace | model")
        namespaces = sorted(
            list(set(model.split(" | ")[0] for model in models if " | " in model))
        )
        return namespaces
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
        st.sidebar.error(f"Error fetching multi-models: {e}")
        return []


@st.cache_data(ttl=300)
def get_model_config():
    """Fetch model configuration from API"""
    try:
        res = requests.get(f"{API_URL}/model_config")
        return res.json()
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
def get_openshift_namespaces():
    """Fetch available OpenShift namespaces from API"""
    try:
        res = requests.get(f"{API_URL}/openshift-namespaces")
        return res.json()
    except Exception as e:
        st.sidebar.error(f"Error fetching OpenShift namespaces: {e}")
        return []


@st.cache_data(ttl=300)
def get_vllm_metrics():
    """Fetch available vLLM metrics dynamically from API"""
    try:
        res = requests.get(f"{API_URL}/vllm-metrics")
        return res.json()
    except Exception as e:
        st.sidebar.error(f"Error fetching vLLM metrics: {e}")
        return {}


def model_requires_api_key(model_id, model_config):
    """Check if a model requires an API key based on unified configuration"""
    model_info = model_config.get(model_id, {})
    return model_info.get("requiresApiKey", False)


def clear_session_state():
    """Clear session state on errors"""
    for key in ["summary", "prompt", "metric_data"]:
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
        "Prompt Tokens Created",
        "P95 Latency (s)",
        "Requests Running",
        "GPU Usage (%)",
        "Output Tokens Created",
        "Inference Time (s)",
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

        # Use the shared function to get metrics data
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
        filename = f"ai_metrics_report.{report_format.lower()}"
        trigger_download(download_response.content, filename, mime_type)
    except requests.exceptions.HTTPError as http_err:
        st.error(f"HTTP error during report generation: {http_err}")
    except Exception as e:
        st.error(f"❌ Error during report generation: {e}")


model_list = get_models()
namespaces = get_namespaces()

# Add namespace selector in sidebar
selected_namespace = st.sidebar.selectbox("Select Namespace", namespaces)

# Filter models by selected namespace
filtered_models = [
    model for model in model_list if model.startswith(f"{selected_namespace} | ")
]
model_name = st.sidebar.selectbox("Select Model", filtered_models)

st.sidebar.markdown("### Select Timestamp Range")
if "selected_date" not in st.session_state:
    st.session_state["selected_date"] = datetime.now().date()
if "selected_time" not in st.session_state:
    st.session_state["selected_time"] = datetime.now().time()
selected_date = st.sidebar.date_input("Date", value=st.session_state["selected_date"])
selected_time = st.sidebar.time_input("Time", value=st.session_state["selected_time"])
selected_datetime = datetime.combine(selected_date, selected_time)
now = datetime.now()
if selected_datetime > now:
    st.sidebar.warning("Please select a valid timestamp before current time.")
    st.stop()
selected_start = int(selected_datetime.timestamp())
selected_end = int(now.timestamp())


st.sidebar.markdown("---")

# --- Select LLM ---
st.sidebar.markdown("### Select LLM for summarization")

# --- Multi-model support ---
multi_model_list = get_multi_models()
multi_model_name = st.sidebar.selectbox(
    "Select LLM for summarization", multi_model_list
)

# --- Define model key requirements ---
model_config = get_model_config()
current_model_requires_api_key = model_requires_api_key(multi_model_name, model_config)


# --- API Key Input ---
api_key = st.sidebar.text_input(
    label="🔑 API Key",
    type="password",
    value=st.session_state.get("api_key", ""),
    help="Enter your API key if required by the selected model",
    disabled=not current_model_requires_api_key,
)

# Caption to show key requirement status
if current_model_requires_api_key:
    st.sidebar.caption("⚠️ This model requires an API key.")

# Page-specific sidebar configuration
if page == "🔧 OpenShift Metrics":
    # OpenShift-specific sidebar controls
    st.sidebar.markdown("### OpenShift Configuration")
    
    # Get OpenShift metric groups and namespaces
    openshift_metric_groups = get_openshift_metric_groups()
    openshift_namespaces = get_openshift_namespaces()
    
    # 1. Analysis Scope Selection (Dropdown)
    scope_type = st.sidebar.selectbox(
        "Analysis Scope",
        ["Cluster-wide", "Namespace-specific"],
        help="Choose whether to analyze the entire cluster or a specific namespace"
    )
    
    # 2. Namespace Selection (Conditional - grayed out if cluster-wide)
    selected_openshift_namespace = None
    if scope_type == "Namespace-specific":
        selected_openshift_namespace = st.sidebar.selectbox(
            "Select Namespace", 
            openshift_namespaces,
            help="Choose the namespace to analyze"
        )
    else:
        # Show disabled dropdown for cluster-wide
        st.sidebar.selectbox(
            "Select Namespace", 
            ["All Namespaces (Cluster-wide)"],
            disabled=True,
            help="Namespace selection is disabled for cluster-wide analysis"
        )
    
    # 3. Metric Categories Selection
    selected_metric_category = st.sidebar.selectbox(
        "Metric Category", 
        openshift_metric_groups,
        help="Choose metric category to analyze"
    )
    
    st.sidebar.markdown("---")
    
    # Common elements for OpenShift page
    st.sidebar.markdown("### Select Timestamp Range")
    if "selected_date" not in st.session_state:
        st.session_state["selected_date"] = datetime.now().date()
    if "selected_time" not in st.session_state:
        st.session_state["selected_time"] = datetime.now().time()
    selected_date = st.sidebar.date_input("Date", value=st.session_state["selected_date"])
    selected_time = st.sidebar.time_input("Time", value=st.session_state["selected_time"])
    selected_datetime = datetime.combine(selected_date, selected_time)
    now = datetime.now()
    if selected_datetime > now:
        st.sidebar.warning("Please select a valid timestamp before current time.")
        st.stop()
    selected_start = int(selected_datetime.timestamp())
    selected_end = int(now.timestamp())
    
    st.sidebar.markdown("---")
    
    # --- Select LLM ---
    st.sidebar.markdown("### Select LLM for summarization")
    
    # --- Multi-model support ---
    multi_model_list = get_multi_models()
    multi_model_name = st.sidebar.selectbox(
        "Select LLM for summarization", multi_model_list
    )
    
    # --- Define model key requirements ---
    model_config = get_model_config()
    current_model_requires_api_key = model_requires_api_key(multi_model_name, model_config)
    current_model_cost = model_costs(multi_model_name, model_config)
    
    # --- API Key Input ---
    api_key = st.sidebar.text_input(
        label="🔑 API Key",
        type="password",
        value=st.session_state.get("api_key", ""),
        help="Enter your API key if required by the selected model",
        disabled=not current_model_requires_api_key,
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


else:
    # vLLM-specific sidebar controls (for pages 1 and 2)
    model_list = get_models()
    namespaces = get_namespaces()

    # Add namespace selector in sidebar
    selected_namespace = st.sidebar.selectbox("Select Namespace", namespaces)


# --- Report Generation ---
st.sidebar.markdown("---")
st.sidebar.markdown("### Download Report")

analysis_performed = st.session_state.get("analysis_performed", False)

if not analysis_performed:
    st.sidebar.warning("⚠️ Please analyze metrics first to generate a report.")

report_format = st.sidebar.selectbox(
    "Select Report Format", ["HTML", "PDF", "Markdown"], disabled=not analysis_performed
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

# --- 📊 Metric Summarizer Page ---
if page == "📊 Metric Summarizer":
    st.markdown("<h1>📊 AI Model Metric Summarizer</h1>", unsafe_allow_html=True)

    # Filter models by selected namespace
    filtered_models = [
        model for model in model_list if model.startswith(f"{selected_namespace} | ")
    ]
    model_name = st.sidebar.selectbox("Select Model", filtered_models)

    st.sidebar.markdown("### Select Timestamp Range")
    if "selected_date" not in st.session_state:
        st.session_state["selected_date"] = datetime.now().date()
    if "selected_time" not in st.session_state:
        st.session_state["selected_time"] = datetime.now().time()
    selected_date = st.sidebar.date_input("Date", value=st.session_state["selected_date"])
    selected_time = st.sidebar.time_input("Time", value=st.session_state["selected_time"])
    selected_datetime = datetime.combine(selected_date, selected_time)
    now = datetime.now()
    if selected_datetime > now:
        st.sidebar.warning("Please select a valid timestamp before current time.")
        st.stop()
    selected_start = int(selected_datetime.timestamp())
    selected_end = int(now.timestamp())

    st.sidebar.markdown("---")

    # --- Select LLM ---
    st.sidebar.markdown("### Select LLM for summarization")

    # --- Multi-model support ---
    multi_model_list = get_multi_models()
    multi_model_name = st.sidebar.selectbox(
        "Select LLM for summarization", multi_model_list
    )

    # --- Define model key requirements ---
    model_config = get_model_config()
    current_model_requires_api_key = model_requires_api_key(multi_model_name, model_config)
    current_model_cost = model_costs(multi_model_name, model_config)

    # --- API Key Input ---
    api_key = st.sidebar.text_input(
        label="🔑 API Key",
        type="password",
        value=st.session_state.get("api_key", ""),
        help="Enter your API key if required by the selected model",
        disabled=not current_model_requires_api_key,
    )

    # Caption to show key requirement status
    if current_model_requires_api_key:
        st.sidebar.caption("⚠️ This model requires an API key.")
    else:
        st.sidebar.caption("✅ No API key is required for this model.")

    # Optional validation warning if required key is missing
    if current_model_requires_api_key and not api_key:
        st.sidebar.warning("🚫 Please enter an API key to use this model.")

# --- 📊 vLLM Metric Summarizer Page ---
if page == "📊 vLLM Metric Summarizer":
    st.markdown("<h1>📊 vLLM Metric Summarizer</h1>", unsafe_allow_html=True)

    # --- Analyze Button ---
    if st.button("🔍 Analyze Metrics"):
        with st.spinner("Analyzing metrics..."):
            try:
                # Get parameters from sidebar
                params = {
                    "model_name": model_name,
                    "summarize_model_id": multi_model_name,
                    "start_ts": selected_start,
                    "end_ts": selected_end,
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
            question = st.text_input("Ask a follow-up question")
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
            
            # Get dynamic vLLM metrics and use the first 6 for display
            available_vllm_metrics = get_vllm_metrics()
            metrics = list(available_vllm_metrics.keys())[:6] if available_vllm_metrics else [
                "Prompt Tokens Created",
                "P95 Latency (s)", 
                "Requests Running",
                "GPU Usage (%)",
                "Output Tokens Created",
                "Inference Time (s)",
            ]

            cols = st.columns(3)
            for i, label in enumerate(metrics):
                with cols[i % 3]:
                    if label in calculated_metrics:
                        calc_data = calculated_metrics[label]
                        if (
                            calc_data["avg"] is not None
                            and calc_data["max"] is not None
                        ):
                            st.metric(
                                label=label,
                                value=f"{calc_data['avg']:.2f}",
                                delta=f"↑ Max: {calc_data['max']:.2f}",
                            )
                        else:
                            st.metric(label=label, value="N/A", delta="No data")
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
elif page == "🤖 Chat with Prometheus":
    st.markdown("<h1>Chat with Prometheus</h1>", unsafe_allow_html=True)
    st.markdown(f"Currently selected namespace: **{selected_namespace}**")
    st.markdown(
        "Ask questions like: `What's the P95 latency?`, `Is GPU usage stable?`, etc."
    )
    user_question = st.text_input("Your question")
    if st.button("Chat with Metrics"):
        if not user_question.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner("Querying and summarizing..."):
                try:
                    response = requests.post(
                        f"{API_URL}/chat-metrics",
                        json={
                            "model_name": model_name,
                            "question": user_question,
                            "start_ts": selected_start,
                            "end_ts": selected_end,
                            "namespace": selected_namespace,  # Add namespace to the request
                            "summarize_model_id": multi_model_name,
                            "api_key": api_key,
                        },
                    )
                    data = response.json()
                    promql = data.get("promql", "")
                    summary = data.get("summary", "")
                    if not summary:
                        st.error("Error: Missing summary in response from AI.")
                    else:
                        st.markdown("**Generated PromQL:**")
                        if promql:
                            st.code(promql, language="yaml")
                        else:
                            st.info("No direct PromQL generated for this question.")
                        st.markdown("**AI Summary:**")
                        st.text(summary)
                except Exception as e:
                    st.error(f"Error: {e}")

# --- 🔧 OpenShift Metrics Page ---
elif page == "🔧 OpenShift Metrics":
    st.markdown("<h1>🔧 OpenShift Metrics Dashboard</h1>", unsafe_allow_html=True)
    
    # Display current configuration
    scope_display = scope_type + (f" ({selected_openshift_namespace})" if selected_openshift_namespace else "")
    category_display = selected_metric_category
    st.markdown(f"**Analysis Scope:** {scope_display} | **Category:** {category_display}")
    
    # Fleet view indicator for cluster-wide
    if scope_type == "Cluster-wide":
        st.info("🌐 **Fleet View**: Analyzing metrics across the entire OpenShift cluster")
    
    # --- Analyze Button ---
    if st.button("🔍 Analyze OpenShift Metrics"):
        analysis_type = "Fleet Analysis" if scope_type == "Cluster-wide" else "Namespace Analysis"
        with st.spinner(f"Running {analysis_type}..."):
            try:
                # Get parameters for OpenShift analysis
                params = {
                    "metric_category": selected_metric_category,  # Specific category
                    "scope": scope_type.lower().replace("-", "_"),  # "cluster_wide" or "namespace_specific"
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
                st.session_state["openshift_metric_category"] = params["metric_category"]
                st.session_state["openshift_scope"] = params["scope"]
                st.session_state["openshift_namespace"] = params["namespace"]
                st.session_state["openshift_metric_data"] = result.get("metrics", {})
                st.session_state["openshift_analysis_type"] = analysis_type
                
                success_msg = f"✅ {analysis_type} completed successfully! Analyzed {len(result.get('metrics', {}))} metric types."
                st.success(success_msg)
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
            openshift_question = st.text_input("Ask a question about OpenShift metrics")
            if st.button("Ask OpenShift Assistant"):
                with st.spinner("OpenShift assistant is thinking..."):
                    try:
                        reply = requests.post(
                            f"{API_URL}/chat-openshift",
                            json={
                                "metric_category": st.session_state["openshift_metric_category"],
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
            
            if scope == "namespace_specific":
                # Show namespace-specific metrics that actually have data
                if metric_category == "Fleet Overview":
                    metrics_to_show = [
                        "Namespace Pods Running", "Namespace Pods Failed", "Container CPU Usage",
                        "Container Memory Usage", "Pod Restart Rate", "Container Network I/O"
                    ]
                elif metric_category == "Workloads & Pods":
                    metrics_to_show = [
                        "Pods Running", "Pods Pending", "Pods Failed",
                        "Pod Restarts (Rate)", "Container CPU Usage", "Container Memory Usage"
                    ]
                elif metric_category == "GPU & Accelerators":
                    metrics_to_show = [
                        "High CPU Containers", "Memory Intensive Pods", "Container CPU Throttling",
                        "Container Memory Pressure", "OOM Killed Containers", "High I/O Containers"
                    ]
                elif metric_category == "Storage & Networking":
                    metrics_to_show = [
                        "PV Claims Bound", "PV Claims Pending", "Container Network Receive",
                        "Container Network Transmit", "Network Errors", "Filesystem Usage"
                    ]
                elif metric_category == "Application Services":
                    metrics_to_show = [
                        "HTTP Request Rate", "HTTP Error Rate (%)", "Service Endpoints",
                        "Container Processes", "Container File Descriptors", "Container Threads"
                    ]
                else:
                    metrics_to_show = list(metric_data.keys())[:6]
            else:
                # Cluster-wide metrics (original)
                if metric_category == "Fleet Overview":
                    metrics_to_show = [
                        "Total Pods Running", "Total Pods Failed", "Cluster CPU Usage (%)",
                        "Cluster Memory Usage (%)", "GPU Utilization (%)", "Nodes Ready"
                    ]
                elif metric_category == "Workloads & Pods":
                    metrics_to_show = [
                        "Pods Running", "Pods Pending", "Pods Failed",
                        "Pod Restarts (Rate)", "Container CPU Usage", "Container Memory Usage"
                    ]
                elif metric_category == "GPU & Accelerators":
                    metrics_to_show = [
                        "GPU Utilization (%)", "GPU Memory Used (%)", "GPU Temperature (°C)",
                        "GPU Power Usage (Watts)", "GPU Total Energy (Joules)", "GPU Memory Clock (MHz)"
                    ]
                elif metric_category == "Storage & Networking":
                    metrics_to_show = [
                        "PV Available Space", "PVC Bound", "Storage I/O Rate",
                        "Network Receive Rate", "Network Transmit Rate", "Network Errors"
                    ]
                elif metric_category == "Application Services":
                    metrics_to_show = [
                        "HTTP Request Rate", "HTTP Error Rate (%)", "HTTP P95 Latency",
                        "Services Available", "Ingress Request Rate", "Load Balancer Backends"
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
                                # Add units for specific metrics
                                if "Power Usage" in label and "Watts" in label:
                                    value_display = f"{latest_val:.2f} Watts"
                                    delta_display = f"Avg: {avg_val:.2f} Watts"
                                elif "Temperature" in label and "°C" in label:
                                    value_display = f"{latest_val:.1f}°C"
                                    delta_display = f"Avg: {avg_val:.1f}°C"
                                elif "Energy" in label and "Joules" in label:
                                    value_display = f"{latest_val:.0f} J"
                                    delta_display = f"Avg: {avg_val:.0f} J"
                                elif "Clock" in label and "MHz" in label:
                                    value_display = f"{latest_val:.0f} MHz"
                                    delta_display = f"Avg: {avg_val:.0f} MHz"
                                else:
                                    value_display = f"{latest_val:.2f}"
                                    delta_display = f"Avg: {avg_val:.2f}"
                                
                                st.metric(
                                    label=label.replace(" (bytes/sec)", "").replace(" (bytes)", "").replace(" (%)", "").replace(" (Watts)", "").replace(" (°C)", "").replace(" (Joules)", "").replace(" (MHz)", ""),
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
            if scope == "namespace_specific":
                if metric_category == "Fleet Overview":
                    chart_metrics = ["Namespace Pods Running", "Container CPU Usage", "Container Memory Usage"]
                elif metric_category == "Workloads & Pods":
                    chart_metrics = ["Pods Running", "Container CPU Usage", "Pod Restarts (Rate)"]
                elif metric_category == "GPU & Accelerators":
                    chart_metrics = ["High CPU Containers", "Memory Intensive Pods", "Container CPU Throttling"]
                elif metric_category == "Storage & Networking":
                    chart_metrics = ["Container Network Receive", "Container Network Transmit", "Filesystem Usage"]
                elif metric_category == "Application Services":
                    chart_metrics = ["Container Processes", "Container File Descriptors", "Container Threads"]
            else:
                if metric_category == "Fleet Overview":
                    chart_metrics = ["Total Pods Running", "Cluster CPU Usage (%)", "Cluster Memory Usage (%)", "GPU Utilization (%)"]
                elif metric_category == "Workloads & Pods":
                    chart_metrics = ["Pods Running", "Container CPU Usage", "Pod Restarts (Rate)"]
                elif metric_category == "GPU & Accelerators":
                    chart_metrics = ["GPU Utilization (%)", "GPU Memory Used (%)", "GPU Temperature (°C)"]
                elif metric_category == "Storage & Networking":
                    chart_metrics = ["Network Receive Rate", "Network Transmit Rate", "Storage I/O Rate"]
                elif metric_category == "Application Services":
                    chart_metrics = ["HTTP Request Rate", "HTTP Error Rate (%)", "HTTP P95 Latency"]
            
            # Filter chart metrics to only include those with data
            chart_metrics = [m for m in chart_metrics if m in metric_data and metric_data[m]]
            
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
            scope_text = "Cluster-wide" if scope == "cluster_wide" else "Namespace-specific"
            namespace_info = f" | **Namespace:** {st.session_state.get('openshift_namespace', 'N/A')}" if scope == "namespace_specific" else ""
            category_info = f" | **Category:** {metric_category}"
            
            st.info(f"**Scope:** {scope_text}{namespace_info}{category_info}")
            
            # Additional fleet view information
            if analysis_type == "Fleet Analysis":
                total_metrics = len(metric_data)
                st.info(f"🌐 **Fleet Analysis**: Monitoring {total_metrics} metric types across the entire OpenShift cluster")
