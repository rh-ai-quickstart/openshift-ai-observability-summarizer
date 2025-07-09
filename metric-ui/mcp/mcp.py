import base64
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import pandas as pd
import requests
from datetime import datetime
from scipy.stats import linregress
import os
import json
import re
from typing import List, Dict, Any, Optional
import uuid

from report_assets.report_renderer import (
    generate_html_report,
    generate_markdown_report,
    generate_pdf_report,
    ReportSchema,
    MetricCard,
)


app = FastAPI()

# --- CONFIG ---
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
LLAMA_STACK_URL = os.getenv("LLAMA_STACK_URL", "http://localhost:8321/v1/openai/v1")
LLM_API_TOKEN = os.getenv("LLM_API_TOKEN", "")

# Load unified model configuration from environment
MODEL_CONFIG = {}
try:
    model_config_str = os.getenv("MODEL_CONFIG", "{}")
    MODEL_CONFIG = json.loads(model_config_str)
except Exception as e:
    print(f"Warning: Could not parse MODEL_CONFIG: {e}")
    MODEL_CONFIG = {}

# Handle token input from volume or literal
token_input = os.getenv(
    "THANOS_TOKEN", "/var/run/secrets/kubernetes.io/serviceaccount/token"
)
if os.path.exists(token_input):
    with open(token_input, "r") as f:
        THANOS_TOKEN = f.read().strip()
else:
    THANOS_TOKEN = token_input

# CA bundle location (mounted via ConfigMap)
CA_BUNDLE_PATH = "/etc/pki/ca-trust/extracted/pem/ca-bundle.crt"
verify = CA_BUNDLE_PATH if os.path.exists(CA_BUNDLE_PATH) else True

# --- Dynamic Metric Discovery Functions ---

def discover_vllm_metrics():
    """Dynamically discover available vLLM metrics from Prometheus, including GPU metrics"""
    try:
        headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/label/__name__/values",
            headers=headers,
            verify=verify,
        )
        response.raise_for_status()
        all_metrics = response.json()["data"]
        
        # Create friendly names for metrics
        metric_mapping = {}
        
        # First, add GPU metrics (DCGM) that are relevant for vLLM monitoring
        gpu_metrics = {
            "GPU Temperature (°C)": "DCGM_FI_DEV_GPU_TEMP",
            "GPU Power Usage (Watts)": "DCGM_FI_DEV_POWER_USAGE", 
            "GPU Memory Usage (GB)": "DCGM_FI_DEV_FB_USED / (1024*1024*1024)",
            "GPU Energy Consumption (Joules)": "DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION",
            "GPU Memory Temperature (°C)": "DCGM_FI_DEV_MEMORY_TEMP",
            "GPU Utilization (%)": "DCGM_FI_DEV_GPU_UTIL",
        }
        
        for friendly_name, metric_name in gpu_metrics.items():
            if metric_name in all_metrics:
                metric_mapping[friendly_name] = f"avg({metric_name})"
        
        # Filter for vLLM metrics
        vllm_metrics = [metric for metric in all_metrics if metric.startswith("vllm:")]
        
        # Add vLLM-specific metrics
        for metric in vllm_metrics:
            # Convert metric name to friendly display name
            friendly_name = metric.replace("vllm:", "").replace("_", " ").title()
            
            # Special handling for common metrics
            if "token" in metric.lower() and "prompt" in metric.lower():
                friendly_name = "Prompt Tokens Created"
            elif "token" in metric.lower() and ("generation" in metric.lower() or "output" in metric.lower()):
                friendly_name = "Output Tokens Created"
            elif "latency" in metric.lower() and "e2e" in metric.lower():
                friendly_name = "P95 Latency (s)"
            elif "gpu" in metric.lower() and "usage" in metric.lower() and "perc" in metric.lower():
                friendly_name = "GPU Usage (%)"
            elif "request" in metric.lower() and "running" in metric.lower():
                friendly_name = "Requests Running"
            elif "inference" in metric.lower() and "time" in metric.lower():
                friendly_name = "Inference Time (s)"
            else:
                # Keep original friendly conversion
                friendly_name = metric.replace("vllm:", "").replace("_", " ").title()
                
            metric_mapping[friendly_name] = metric
            
        return metric_mapping
    except Exception as e:
        print(f"Error discovering vLLM metrics: {e}")
        # Enhanced fallback with comprehensive GPU metrics and vLLM metrics
        return {
            "GPU Temperature (°C)": "avg(DCGM_FI_DEV_GPU_TEMP)",
            "GPU Power Usage (Watts)": "avg(DCGM_FI_DEV_POWER_USAGE)",
            "GPU Memory Usage (GB)": "avg(DCGM_FI_DEV_FB_USED) / (1024*1024*1024)",
            "GPU Energy Consumption (Joules)": "avg(DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION)",
            "GPU Memory Temperature (°C)": "avg(DCGM_FI_DEV_MEMORY_TEMP)",
            "GPU Utilization (%)": "avg(DCGM_FI_DEV_GPU_UTIL)",
            "Prompt Tokens Created": "vllm:request_prompt_tokens_created",
            "Output Tokens Created": "vllm:request_generation_tokens_created",
            "Requests Running": "vllm:num_requests_running",
            "P95 Latency (s)": "vllm:e2e_request_latency_seconds_count",
            "Inference Time (s)": "vllm:request_inference_time_seconds_count",
        }

def discover_dcgm_metrics():
    """Dynamically discover available DCGM GPU metrics"""
    try:
        headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/label/__name__/values",
            headers=headers,
            verify=verify,
        )
        response.raise_for_status()
        all_metrics = response.json()["data"]
        
        # Filter for DCGM metrics
        dcgm_metrics = [metric for metric in all_metrics if metric.startswith("DCGM_")]
        
        # Create a mapping of useful DCGM metrics for fleet monitoring
        dcgm_mapping = {}
        fb_used_metric = None
        
        for metric in dcgm_metrics:
            if "GPU_TEMP" in metric:
                dcgm_mapping["GPU Temperature (°C)"] = f"avg({metric})"
            elif "POWER_USAGE" in metric:
                dcgm_mapping["GPU Power Usage (Watts)"] = f"avg({metric})"
            elif "GPU_UTIL" in metric:
                dcgm_mapping["GPU Utilization (%)"] = f"avg({metric})"
            elif "MEMORY_TEMP" in metric:
                dcgm_mapping["GPU Memory Temperature (°C)"] = f"avg({metric})"
            elif "TOTAL_ENERGY_CONSUMPTION" in metric:
                dcgm_mapping["GPU Energy Consumption (Joules)"] = f"avg({metric})"
            elif "FB_USED" in metric:
                fb_used_metric = metric
                dcgm_mapping["GPU Memory Used (bytes)"] = f"avg({metric})"
            elif "FB_TOTAL" in metric:
                dcgm_mapping["GPU Memory Total (bytes)"] = f"avg({metric})"
            elif "SM_CLOCK" in metric:
                dcgm_mapping["GPU SM Clock (MHz)"] = f"avg({metric})"
            elif "MEM_CLOCK" in metric:
                dcgm_mapping["GPU Memory Clock (MHz)"] = f"avg({metric})"
        
        # Add GPU Memory Usage in GB if we found the FB_USED metric
        if fb_used_metric:
            dcgm_mapping["GPU Memory Usage (GB)"] = f"avg({fb_used_metric}) / (1024*1024*1024)"
        
        return dcgm_mapping
    except Exception as e:
        print(f"Error discovering DCGM metrics: {e}")
        return {}

def discover_openshift_metrics():
    """Return static, well-tested OpenShift/Kubernetes metrics organized by category"""
    return {
        "Fleet Overview": {
            # 6 most important cluster-wide metrics with enhanced GPU monitoring
            "Total Pods Running": "sum(kube_pod_status_phase{phase='Running'})",
            "Total Pods Failed": "sum(kube_pod_status_phase{phase='Failed'})",
            "Cluster CPU Usage (%)": "100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[5m])) * 100)",
            "Cluster Memory Usage (%)": "100 - (sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes) * 100)",
            "GPU Utilization (%)": "avg(DCGM_FI_DEV_GPU_UTIL)",
            "GPU Temperature (°C)": "avg(DCGM_FI_DEV_GPU_TEMP)",
        },
        "Workloads & Pods": {
            # 6 most important pod/container metrics
            "Pods Running": "sum(kube_pod_status_phase{phase='Running'})",
            "Pods Pending": "sum(kube_pod_status_phase{phase='Pending'})",
            "Pods Failed": "sum(kube_pod_status_phase{phase='Failed'})",
            "Pod Restarts (Rate)": "sum(rate(kube_pod_container_status_restarts_total[5m]))",
            "Container CPU Usage": "sum(rate(container_cpu_usage_seconds_total[5m]))",
            "Container Memory Usage": "sum(container_memory_usage_bytes)",
        },

        "GPU & Accelerators": {
            # 🚀 Comprehensive GPU fleet monitoring with DCGM metrics
            "GPU Temperature (°C)": "avg(DCGM_FI_DEV_GPU_TEMP)",
            "GPU Power Usage (Watts)": "avg(DCGM_FI_DEV_POWER_USAGE)",
            "GPU Utilization (%)": "avg(DCGM_FI_DEV_GPU_UTIL)",
            "GPU Memory Usage (GB)": "avg(DCGM_FI_DEV_FB_USED) / (1024*1024*1024)",
            "GPU Energy Consumption (Joules)": "avg(DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION)",
            "GPU Memory Temperature (°C)": "avg(DCGM_FI_DEV_MEMORY_TEMP)",
        },
        "Storage & Networking": {
            # 6 storage and network metrics
            "PV Available Space": "sum(kube_persistentvolume_capacity_bytes)",
            "PVC Bound": "sum(kube_persistentvolumeclaim_status_phase{phase='Bound'})",
            "Storage I/O Rate": "sum(rate(container_fs_reads_total[5m]) + rate(container_fs_writes_total[5m]))",
            "Network Receive Rate": "sum(rate(container_network_receive_bytes_total[5m]))",
            "Network Transmit Rate": "sum(rate(container_network_transmit_bytes_total[5m]))",
            "Network Errors": "sum(rate(container_network_receive_errors_total[5m]) + rate(container_network_transmit_errors_total[5m]))",
        },
        "Application Services": {
            # 6 application-level metrics
            "HTTP Request Rate": "sum(rate(http_requests_total[5m]))",
            "HTTP Error Rate (%)": "sum(rate(http_requests_total{status=~'5..'}[5m])) / sum(rate(http_requests_total[5m])) * 100",
            "HTTP P95 Latency": "histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))",
            "Services Available": "sum(up)",
            "Ingress Request Rate": "sum(rate(nginx_ingress_controller_requests[5m]))",
            "Load Balancer Backends": "sum(haproxy_server_up)",
        },
    }

# Cache discovered metrics to avoid repeated API calls
_vllm_metrics_cache = None
_openshift_metrics_cache = None
_cache_timestamp = None
CACHE_TTL = 300  # 5 minutes

def get_vllm_metrics():
    """Get vLLM metrics with caching"""
    global _vllm_metrics_cache, _cache_timestamp
    
    current_time = datetime.now().timestamp()
    if _vllm_metrics_cache is None or _cache_timestamp is None or (current_time - _cache_timestamp) > CACHE_TTL:
        _vllm_metrics_cache = discover_vllm_metrics()
        _cache_timestamp = current_time
    
    return _vllm_metrics_cache

def get_openshift_metrics():
    """Get OpenShift metrics with caching"""
    global _openshift_metrics_cache, _cache_timestamp
    
    current_time = datetime.now().timestamp()
    if _openshift_metrics_cache is None or _cache_timestamp is None or (current_time - _cache_timestamp) > CACHE_TTL:
        _openshift_metrics_cache = discover_openshift_metrics()
        _cache_timestamp = current_time
    
    return _openshift_metrics_cache


# --- Request Models ---
class AnalyzeRequest(BaseModel):
    model_name: str
    start_ts: int
    end_ts: int
    summarize_model_id: str
    api_key: Optional[str] = None


class ChatRequest(BaseModel):
    model_name: str
    prompt_summary: str
    question: str
    summarize_model_id: str
    api_key: Optional[str] = None


class ChatMetricsRequest(BaseModel):
    model_name: str
    question: str
    start_ts: int
    end_ts: int
    namespace: str
    summarize_model_id: str
    api_key: Optional[str] = None


class ReportRequest(BaseModel):
    model_name: str
    start_ts: int
    end_ts: int
    summarize_model_id: str
    format: str
    api_key: Optional[str] = None
    health_prompt: Optional[str] = None
    llm_summary: Optional[str] = None
    metrics_data: Optional[Dict[str, Any]] = None
    trend_chart_image: Optional[str] = None


class MetricsCalculationRequest(BaseModel):
    metrics_data: Dict[str, List[Dict[str, Any]]]


class MetricsCalculationResponse(BaseModel):
    calculated_metrics: Dict[str, Dict[str, Optional[float]]]


# --- Helpers ---
def fetch_metrics(query, model_name, start, end, namespace=None):
    # Handle GPU metrics that don't have model_name labels (they're global/node-level metrics)
    if query.startswith("avg(DCGM_") or "DCGM_" in query:
        # GPU metrics are node-level, not model-specific
        promql_query = query
    else:
        # Handle vLLM metrics that have model_name and namespace labels
        if namespace:
            namespace = namespace.strip()
            if "|" in model_name:
                model_namespace, actual_model_name = map(
                    str.strip, model_name.split("|", 1)
                )
                promql_query = (
                    f'{query}{{model_name="{actual_model_name}", namespace="{namespace}"}}'
                )
            else:
                promql_query = (
                    f'{query}{{model_name="{model_name}", namespace="{namespace}"}}'
                )
        else:
            # Original logic if no namespace is explicitly provided (for backward compatibility or other endpoints)
            if "|" in model_name:
                namespace, model_name = map(str.strip, model_name.split("|", 1))
                promql_query = (
                    f'{query}{{model_name="{model_name}", namespace="{namespace}"}}'
                )
            else:
                model_name = model_name.strip()
                promql_query = f'{query}{{model_name="{model_name}"}}'

    headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
    response = requests.get(
        f"{PROMETHEUS_URL}/api/v1/query_range",
        headers=headers,
        params={"query": promql_query, "start": start, "end": end, "step": "30s"},
        verify=verify,
    )
    response.raise_for_status()
    result = response.json()["data"]["result"]

    rows = []
    for series in result:
        for val in series["values"]:
            ts = datetime.fromtimestamp(float(val[0]))
            value = float(val[1])
            
            # Handle NaN values that can't be JSON serialized
            if pd.isna(value) or value != value:  # Check for NaN
                value = 0.0  # Convert NaN to 0 for JSON compatibility
            
            row = dict(series["metric"])
            row["timestamp"] = ts
            row["value"] = value
            rows.append(row)

    return pd.DataFrame(rows)


def detect_anomalies(df, label):
    if df.empty:
        return "No data"
    mean = df["value"].mean()
    std = df["value"].std()
    p90 = df["value"].quantile(0.9)
    latest_val = df["value"].iloc[-1]
    if latest_val > p90:
        return f"⚠️ {label} spike (latest={latest_val:.2f}, >90th pct)"
    elif latest_val < (mean - std):
        return f"⚠️ {label} unusually low (latest={latest_val:.2f}, mean={mean:.2f})"
    return f"{label} stable (latest={latest_val:.2f}, mean={mean:.2f})"


def describe_trend(df):
    if df.empty or len(df) < 2:
        return "not enough data"
    df = df.sort_values("timestamp")
    x = (df["timestamp"] - df["timestamp"].min()).dt.total_seconds()
    y = df["value"]
    if x.nunique() <= 1:
        return "flat"
    slope, *_ = linregress(x, y)
    if slope > 0.01:
        return "increasing"
    elif slope < -0.01:
        return "decreasing"
    return "stable"


def compute_health_score(metric_dfs):
    score, reasons = 0, []
    if "P95 Latency (s)" in metric_dfs and not metric_dfs["P95 Latency (s)"].empty:
        mean = metric_dfs["P95 Latency (s)"]["value"].mean()
        if mean > 2:
            score -= 2
            reasons.append(f"High Latency (avg={mean:.2f}s)")
    if "GPU Usage (%)" in metric_dfs and not metric_dfs["GPU Usage (%)"].empty:
        mean = metric_dfs["GPU Usage (%)"]["value"].mean()
        if mean < 10:
            score -= 1
            reasons.append(f"Low GPU Utilization (avg={mean:.2f}%)")
    if "Requests Running" in metric_dfs and not metric_dfs["Requests Running"].empty:
        mean = metric_dfs["Requests Running"]["value"].mean()
        if mean > 10:
            score -= 1
            reasons.append(f"Too many requests (avg={mean:.2f})")
    return score, reasons


def build_prompt(metric_dfs, model_name):
    score, _ = compute_health_score(metric_dfs)
    header = f"You are evaluating model **{model_name}**.\n\n🩺 Health Score: {score}\n\n📊 **Metrics**:\n"
    lines = []
    for label, df in metric_dfs.items():
        if df.empty:
            lines.append(f"- {label}: No data")
            continue
        trend = describe_trend(df)
        anomaly = detect_anomalies(df, label)
        avg = df["value"].mean()
        # Add an indication if data is present
        data_status = "Data present" if not df.empty else "No data"
        lines.append(
            f"- {label}: Avg={avg:.2f}, Trend={trend}, {anomaly} ({data_status})"
        )
    return f"""{header}
{chr(10).join(lines)}

🔍 Please analyze:
1. What's going well?
2. What's problematic?
3. Recommendations?
""".strip()


def build_chat_prompt(user_question: str, metrics_summary: str) -> str:
    return f"""
You are a senior MLOps engineer reviewing real-time Prometheus metrics and providing operational insights.

Your task is to answer **ANY type of observability question**, whether specific (e.g., "What is GPU usage?") or generic (e.g., "What's going wrong?", "Can I send more load?").

Use ONLY the information in the **metrics summary** to answer.

---
📊 Metrics Summary:
{metrics_summary.strip()}
---

🧠 Guidelines:
- Use your judgment as an MLOps expert.
- If the metrics look abnormal or risky, call it out.
- If something seems healthy, confirm it clearly.
- Do NOT restate the user's question.
- NEVER say "I'm an assistant" or explain how you're generating your response.
- Do NOT exceed 100 words.
- Use real metric names (e.g., "GPU Usage (%)", "P95 Latency (s)").
- Be direct, like a technical Slack message.
- If the user asks about scaling or sending more load, use "Requests Running", "Latency", or "GPU Usage" to justify your answer.

---
👤 User Prompt:
{user_question.strip()}
---

Now provide a concise, technical summary that answers it.
""".strip()


def _make_api_request(
    url: str, headers: dict, payload: dict, verify_ssl: bool = True
) -> dict:
    """Make API request with consistent error handling"""
    response = requests.post(url, headers=headers, json=payload, verify=verify_ssl)
    response.raise_for_status()
    return response.json()


def _validate_and_extract_response(
    response_json: dict, is_external: bool, provider: str = "LLM"
) -> str:
    """Validate response format and extract content"""
    if "choices" not in response_json or not response_json["choices"]:
        raise ValueError(f"Invalid {provider} response format")

    if is_external:
        return response_json["choices"][0]["message"]["content"].strip()
    else:
        return response_json["choices"][0]["text"].strip()


# New helper function to aggressively clean LLM summary strings
def _clean_llm_summary_string(text: str) -> str:
    # Remove any non-printable ASCII characters (except common whitespace like space, tab, newline)
    cleaned_text = re.sub(r"[^\x20-\x7E\n\t]", "", text)
    # Replace multiple spaces/newlines/tabs with single spaces, then strip leading/trailing whitespace
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()
    return cleaned_text


def summarize_with_llm(
    prompt: str, summarize_model_id: str, api_key: Optional[str] = None
) -> str:
    headers = {"Content-Type": "application/json"}

    # Get model configuration
    model_info = MODEL_CONFIG.get(summarize_model_id, {})
    is_external = model_info.get("external", False)

    if is_external:
        # External model (like OpenAI, Anthropic, etc.)
        if not api_key:
            raise ValueError(
                f"API key required for external model {summarize_model_id}"
            )

        # Get provider-specific configuration
        provider = model_info.get("provider", "openai")
        api_url = model_info.get("apiUrl", "https://api.openai.com/v1/chat/completions")
        model_name = model_info.get("modelName")

        headers["Authorization"] = f"Bearer {api_key}"

        # Convert to OpenAI chat format
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
            "max_tokens": 1000,
        }

        response_json = _make_api_request(api_url, headers, payload, verify_ssl=True)
        return _validate_and_extract_response(
            response_json, is_external=True, provider=provider
        )

    else:
        # Local model (deployed in cluster)
        if LLM_API_TOKEN:
            headers["Authorization"] = f"Bearer {LLM_API_TOKEN}"

        payload = {
            "model": summarize_model_id,
            "prompt": prompt,
            "temperature": 0.5,
            "max_tokens": 1000,
        }

        response_json = _make_api_request(
            f"{LLAMA_STACK_URL}/completions", headers, payload, verify_ssl=verify
        )

        return _validate_and_extract_response(
            response_json, is_external=False, provider="LLM"
        )


@app.get("/health")
def health():
    return {"status": "ok"}


# Helper to get models (extracted from list_models endpoint)
def _get_models_helper():
    try:
        headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
        
        # Try multiple vLLM metrics with longer time windows
        vllm_metrics_to_check = [
            "vllm:request_prompt_tokens_created",
            "vllm:request_prompt_tokens_total", 
            "vllm:avg_generation_throughput_toks_per_s",
            "vllm:num_requests_running",
            "vllm:gpu_cache_usage_perc"
        ]
        
        model_set = set()
        
        # Try different time windows: 7 days, 24 hours, 1 hour
        time_windows = [
            7 * 24 * 3600,  # 7 days
            24 * 3600,      # 24 hours  
            3600            # 1 hour
        ]
        
        for time_window in time_windows:
            for metric_name in vllm_metrics_to_check:
                try:
                    response = requests.get(
                        f"{PROMETHEUS_URL}/api/v1/series",
                        headers=headers,
                        params={
                            "match[]": metric_name,
                            "start": int((datetime.now().timestamp()) - time_window),
                            "end": int(datetime.now().timestamp()),
                        },
                        verify=verify,
                    )
                    response.raise_for_status()
                    series = response.json()["data"]

                    for entry in series:
                        model = entry.get("model_name", "").strip()
                        namespace = entry.get("namespace", "").strip()
                        if model and namespace:
                            model_set.add(f"{namespace} | {model}")
                    
                    # If we found models, return them
                    if model_set:
                        return sorted(list(model_set))
                        
                except Exception as e:
                    print(f"Error checking {metric_name} with {time_window}s window: {e}")
                    continue
        
        return sorted(list(model_set))
    except Exception as e:
        print("Error getting models:", e)
        return []


@app.get("/models")
def list_models():
    return _get_models_helper()


@app.get("/namespaces")
def list_namespaces():
    try:
        headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
        
        # Try multiple vLLM metrics with longer time windows
        vllm_metrics_to_check = [
            "vllm:request_prompt_tokens_created",
            "vllm:request_prompt_tokens_total", 
            "vllm:avg_generation_throughput_toks_per_s",
            "vllm:num_requests_running",
            "vllm:gpu_cache_usage_perc"
        ]
        
        namespace_set = set()
        
        # Try different time windows: 7 days, 24 hours, 1 hour
        time_windows = [
            7 * 24 * 3600,  # 7 days
            24 * 3600,      # 24 hours  
            3600            # 1 hour
        ]
        
        for time_window in time_windows:
            for metric_name in vllm_metrics_to_check:
                try:
                    response = requests.get(
                        f"{PROMETHEUS_URL}/api/v1/series",
                        headers=headers,
                        params={
                            "match[]": metric_name,
                            "start": int((datetime.now().timestamp()) - time_window),
                            "end": int(datetime.now().timestamp()),
                        },
                        verify=verify,
                    )
                    response.raise_for_status()
                    series = response.json()["data"]

                    for entry in series:
                        namespace = entry.get("namespace", "").strip()
                        model = entry.get("model_name", "").strip()
                        if namespace and model:
                            namespace_set.add(namespace)
                    
                    # If we found namespaces, return them
                    if namespace_set:
                        return sorted(list(namespace_set))
                        
                except Exception as e:
                    print(f"Error checking {metric_name} with {time_window}s window: {e}")
                    continue
        
        return sorted(list(namespace_set))
    except Exception as e:
        print("Error getting namespaces:", e)
        return []


@app.get("/multi_models")
def list_multi_models():
    """Get available summarization models from configuration"""
    return list(MODEL_CONFIG.keys())


@app.get("/model_config")
def get_model_config():
    return MODEL_CONFIG


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    try:
        vllm_metrics = get_vllm_metrics()
        metric_dfs = {
            label: fetch_metrics(query, req.model_name, req.start_ts, req.end_ts)
            for label, query in vllm_metrics.items()
        }
        prompt = build_prompt(metric_dfs, req.model_name)

        summary = summarize_with_llm(prompt, req.summarize_model_id, req.api_key)

        # Ensure both columns exist, even if the DataFrame is empty
        serialized_metrics = {}
        for label, df in metric_dfs.items():
            for col in ["timestamp", "value"]:
                if col not in df.columns:
                    df[col] = pd.Series(
                        dtype="datetime64[ns]" if col == "timestamp" else "float"
                    )
            serialized_metrics[label] = df[["timestamp", "value"]].to_dict(
                orient="records"
            )

        return {
            "model_name": req.model_name,
            "health_prompt": prompt,
            "llm_summary": summary,
            "metrics": serialized_metrics,
        }
    except Exception as e:
        # Handle API key errors and other LLM-related errors
        raise HTTPException(
            status_code=500, detail="Please check your API Key or try again later."
        )


@app.post("/chat")
def chat(req: ChatRequest):
    try:
        prompt = build_chat_prompt(
            user_question=req.question, metrics_summary=req.prompt_summary
        )

        # Get LLM response using helper function
        response = summarize_with_llm(prompt, req.summarize_model_id, req.api_key)

        return {"response": _clean_llm_summary_string(response)}
    except Exception as e:
        # Handle API key errors and other LLM-related errors
        raise HTTPException(
            status_code=500, detail="Please check your API Key or try again later."
        )


def build_flexible_llm_prompt(
    question: str,
    model_name: str,
    metrics_data_summary: str,
    generated_tokens_sum: float = None,
    selected_namespace: str = None,
) -> str:
    vllm_metrics = get_vllm_metrics()
    metrics_list = "\n".join(
        [f'- "{label}" (PromQL: {query})' for label, query in vllm_metrics.items()]
    )

    summary_tokens_generated = ""
    if generated_tokens_sum is not None:
        summary_tokens_generated = f"A total of {generated_tokens_sum:.2f} tokens were generated across all models and namespaces."

    namespace_context = (
        f"You are currently focused on the namespace: **{selected_namespace}**\n\n"
        if selected_namespace
        else ""
    )

    return f"""
{namespace_context}You are a distinguished engineer and MLOps expert, renowned for your ability to synthesize complex operational data into clear, insightful recommendations.

Your task: Given the user's question and the current metric status, provide a PromQL query and a summary.

Available Metrics:
{metrics_list}

Current Metric Status:
{metrics_data_summary.strip()}

IMPORTANT: Respond with a single, complete JSON object with EXACTLY two fields:
"promql": (string) A relevant PromQL query (empty string if not applicable). Do NOT include a namespace label in the PromQL query.
"summary": (string) Write a short, thoughtful paragraph as if you are advising a team of engineers. Offer clear, actionable insights, and sound like a senior technical leader. Use plain text only. Do NOT use markdown or any nested JSON-like structures within this string. Include actual values from "Current Metric Status" when relevant.

Rules for JSON output:
- Use double quotes for all keys and string values.
- No trailing commas.
- No line breaks within string values.
- No comments.

Example:
{{
  "promql": "count by(model_name) (vllm:request_prompt_tokens_created)",
  "summary": "Based on the current metrics, the system is operating within expected parameters. However, I recommend monitoring the request rate closely as a precaution. If you anticipate increased load, consider scaling resources proactively to maintain performance."
}}

Question: {question}
Response:""".strip()


@app.post("/chat-metrics")
def chat_metrics(req: ChatMetricsRequest):
    # Determine if the question is about listing all models globally or namespace-specific
    question_lower = req.question.lower()
    is_all_models_query = (
        "all models currently deployed" in question_lower
        or "list all models" in question_lower
        or "what models are deployed" in question_lower.replace("?", "")
    )
    is_tokens_generated_query = "how many tokens generated" in question_lower

    metrics_data_summary = ""
    generated_tokens_sum_value = None

    vllm_metrics = get_vllm_metrics()
    metric_dfs = {
        label: fetch_metrics(
            query, req.model_name, req.start_ts, req.end_ts, namespace=req.namespace
        )
        for label, query in vllm_metrics.items()
    }

    if is_tokens_generated_query:
        output_tokens_df = metric_dfs.get("Output Tokens Created")
        if output_tokens_df is not None and not output_tokens_df.empty:
            generated_tokens_sum_value = output_tokens_df["value"].sum()
            metrics_data_summary = f"Output Tokens Created: Total Generated = {generated_tokens_sum_value:.2f}"
        else:
            metrics_data_summary = (
                "Output Tokens Created: No data available to calculate sum."
            )

    elif is_all_models_query:
        # For "all models" query, fetch globally deployed models directly
        deployed_models_list = _get_models_helper()

        # Filter models by namespace from the request
        deployed_models_list = [
            model for model in deployed_models_list if f"| {req.namespace}" in model
        ]
        metrics_data_summary = (
            f"Models in namespace {req.namespace}: " + ", ".join(deployed_models_list)
            if deployed_models_list
            else f"No models found in namespace {req.namespace}"
        )
    else:
        # For other metric-specific queries, fetch for the selected model
        # Reuse existing summary builder for the selected model's metrics
        metrics_data_summary = build_prompt(metric_dfs, req.model_name)

    prompt = build_flexible_llm_prompt(
        req.question,
        req.model_name,
        metrics_data_summary,
        generated_tokens_sum=generated_tokens_sum_value,
        selected_namespace=req.namespace,
    )
    llm_response = summarize_with_llm(prompt, req.summarize_model_id, req.api_key)

    # Debug LLM response
    print("🧠 Raw LLM response:", llm_response)

    try:
        # Step 1: Clean the response
        cleaned_response = llm_response.strip()
        print("⚙️ After initial strip:", cleaned_response)

        # Remove any markdown code block markers
        cleaned_response = re.sub(r"```json\s*|\s*```", "", cleaned_response)
        print("⚙️ After markdown removal:", cleaned_response)

        # Remove any leading/trailing whitespace and newlines
        cleaned_response = cleaned_response.strip()
        print("⚙️ After final strip:", cleaned_response)

        # Find the JSON object (more robust regex for nested braces)
        json_match = re.search(r"\{.*?\}", cleaned_response, re.DOTALL)
        if not json_match:
            raise ValueError(f"No JSON object found in response: '{cleaned_response}'")

        json_string = json_match.group(0)
        print("⚙️ Extracted JSON string:", json_string)

        # Clean the JSON string
        # Remove any newlines and extra spaces
        json_string = re.sub(r"\s+", " ", json_string)
        print("⚙️ After whitespace normalization:", json_string)

        # Ensure proper key quoting
        json_string = re.sub(
            r"([{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', json_string
        )
        print("⚙️ After key quoting:", json_string)

        # Fix any double-quoted keys
        json_string = re.sub(r'"([^"]+)"\s*"\s*:', r'"\1":', json_string)
        print("⚙️ After double-quoted key fix:", json_string)

        # Removed the problematic value quoting regex
        print("⚙️ Value quoting regex removed.")

        # Remove trailing commas
        json_string = re.sub(r",\s*}", "}", json_string)
        print("⚙️ After trailing comma removal:", json_string)

        print("🔍 Final Cleaned JSON string for parsing:", json_string)

        # Parse the JSON
        parsed = json.loads(json_string)

        # Extract and clean the fields
        promql = parsed.get("promql", "").strip()
        summary = _clean_llm_summary_string(parsed.get("summary", ""))

        # Aggressively ensure the correct namespace is in PromQL
        if promql:
            # Remove existing namespace labels from PromQL if present
            promql = re.sub(r"\{([^}]*)namespace=[^,}]*(,)?", r"{\1", promql)
            # Add the correct namespace. Handle cases where there are no existing labels or existing labels.
            if "{" in promql:
                promql = promql.replace("{", f'{{namespace="{req.namespace}", ')
            else:
                # If no existing curly braces, add them with the namespace
                promql = f"{promql}{{namespace='{req.namespace}'}}"

        if not summary:
            raise ValueError("Empty summary in response")

        return {"promql": promql, "summary": summary}

    except json.JSONDecodeError as e:
        print(f"⚠️ JSON Decode Error: {e}")
        print(f"Problematic JSON string: {json_string}")
        return {
            "promql": "",
            "summary": f"Failed to parse response: {e}. Problematic string: '{json_string}'",
        }
    except ValueError as e:
        print(f"⚠️ Value Error: {e}")
        return {
            "promql": "",
            "summary": f"Failed to process response: {e}. Problematic string: '{json_string}'",
        }
    except Exception as e:
        print(f"⚠️ Unexpected error: {e}")
        return {
            "promql": "",
            "summary": f"An unexpected error occurred: {e}. Raw LLM output: {llm_response}",
        }


# helper functions for report generation
def save_report(report_content, format: str) -> str:
    report_id = str(uuid.uuid4())
    reports_dir = "/tmp/reports"
    os.makedirs(reports_dir, exist_ok=True)

    report_path = os.path.join(reports_dir, f"{report_id}.{format.lower()}")

    # Handle both string and bytes content
    if isinstance(report_content, bytes):
        with open(report_path, "wb") as f:
            f.write(report_content)
    else:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)

    return report_id


def get_report_path(report_id: str) -> str:
    """Get file path for report ID"""

    reports_dir = "/tmp/reports"

    # Try to find the file with any extension
    for file in os.listdir(reports_dir):
        if file.startswith(report_id):
            return os.path.join(reports_dir, file)

    raise FileNotFoundError(f"Report {report_id} not found")


def calculate_metric_stats(metric_data):
    """Calculate average and max values for metrics data"""
    if not metric_data:
        return None, None
    try:
        values = [point["value"] for point in metric_data]
        avg_val = sum(values) / len(values) if values else None
        max_val = max(values) if values else None
        return avg_val, max_val
    except Exception:
        return None, None


def build_report_schema(
    metrics_data: Dict[str, Any],
    summary: str,
    model_name: str,
    start_ts: int,
    end_ts: int,
    summarize_model_id: str,
    trend_chart_image: Optional[str] = None,
) -> ReportSchema:
    from datetime import datetime

    # Extract available metrics from the metrics_data dictionary
    key_metrics = list(metrics_data.keys())
    metric_cards = []
    for metric_name in key_metrics:
        data = metrics_data.get(metric_name, [])
        avg_val, max_val = calculate_metric_stats(data)
        metric_cards.append(
            MetricCard(
                name=metric_name,
                avg=avg_val,
                max=max_val,
                values=data,
            )
        )
    return ReportSchema(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        model_name=model_name,
        start_date=datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M:%S"),
        end_date=datetime.fromtimestamp(end_ts).strftime("%Y-%m-%d %H:%M:%S"),
        summarize_model_id=summarize_model_id,
        summary=summary,
        metrics=metric_cards,
        trend_chart_image=trend_chart_image,
    )


@app.get("/download_report/{report_id}")
def download_report(report_id: str):
    """Download generated report"""
    report_path = get_report_path(report_id)
    return FileResponse(report_path)


@app.post("/generate_report")
def generate_report(request: ReportRequest):
    """Generate report in requested format"""
    # Check if we have analysis data from UI session
    if (
        request.health_prompt is None
        or request.llm_summary is None
        or request.metrics_data is None
    ):
        raise HTTPException(
            status_code=400,
            detail="No analysis data provided. Please run analysis first.",
        )

    # Build the unified report schema once
    report_schema = build_report_schema(
        request.metrics_data,
        request.llm_summary,
        request.model_name,
        request.start_ts,
        request.end_ts,
        request.summarize_model_id,
        request.trend_chart_image,
    )

    # Generate report content based on format
    match request.format.lower():
        case "html":
            report_content = generate_html_report(report_schema)
        case "pdf":
            report_content = generate_pdf_report(report_schema)
        case "markdown":
            report_content = generate_markdown_report(report_schema)
        case _:
            raise HTTPException(
                status_code=400, detail=f"Unsupported format: {request.format}"
            )

    # Save and send
    report_id = save_report(report_content, request.format)
    return {"report_id": report_id, "download_url": f"/download_report/{report_id}"}


@app.post("/calculate-metrics", response_model=MetricsCalculationResponse)
def calculate_metrics_endpoint(request: MetricsCalculationRequest):
    """Calculate average and max values for metrics data"""
    calculated_metrics = {}

    for metric_name, metric_data in request.metrics_data.items():
        avg_val, max_val = calculate_metric_stats(metric_data)
        calculated_metrics[metric_name] = {"avg": avg_val, "max": max_val}

    return MetricsCalculationResponse(calculated_metrics=calculated_metrics)

# --- OpenShift Helper Functions ---

def fetch_openshift_metrics(query, start, end, namespace=None):
    """Fetch OpenShift metrics with optional namespace filtering"""
    headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
    
    # Add namespace filter to the query if specified
    if namespace:
        import re
        
        # Skip if namespace already exists in the query
        if f'namespace="{namespace}"' in query:
            pass  # Already has the correct namespace
        else:
            # Simple string replacements for common patterns
            
            # Pattern 1: sum(metric_name)
            pattern1 = r'sum\(([a-zA-Z_:][a-zA-Z0-9_:]*)\)'
            if re.search(pattern1, query):
                query = re.sub(pattern1, f'sum(\\1{{namespace="{namespace}"}})', query)
            
            # Pattern 2: sum(rate(metric_name[5m]))
            elif re.search(r'sum\(rate\([a-zA-Z_:][a-zA-Z0-9_:]*\[[^\]]+\]\)\)', query):
                pattern2 = r'sum\(rate\(([a-zA-Z_:][a-zA-Z0-9_:]*)\[([^\]]+)\]\)\)'
                query = re.sub(pattern2, f'sum(rate(\\1{{namespace="{namespace}"}}[\\2]))', query)
            
            # Pattern 3: rate(metric_name[5m])
            elif re.search(r'rate\([a-zA-Z_:][a-zA-Z0-9_:]*\[[^\]]+\]\)', query):
                pattern3 = r'rate\(([a-zA-Z_:][a-zA-Z0-9_:]*)\[([^\]]+)\]\)'
                query = re.sub(pattern3, f'rate(\\1{{namespace="{namespace}"}}[\\2])', query)
            
            # Pattern 4: metric_name{existing_labels}
            elif re.search(r'[a-zA-Z_:][a-zA-Z0-9_:]*\{[^}]*\}', query):
                pattern4 = r'([a-zA-Z_:][a-zA-Z0-9_:]*)\{([^}]*)\}'
                query = re.sub(pattern4, f'\\1{{namespace="{namespace}",\\2}}', query)
            
            # Pattern 5: simple metric_name (no labels)
            elif re.search(r'^[a-zA-Z_:][a-zA-Z0-9_:]*$', query):
                query = f'{query}{{namespace="{namespace}"}}'
            
            # Pattern 6: handle other aggregations (avg, count, etc.)
            else:
                for func in ['avg', 'count', 'max', 'min']:
                    pattern = f'{func}\\(([a-zA-Z_:][a-zA-Z0-9_:]*)\\)'
                    if re.search(pattern, query):
                        query = re.sub(pattern, f'{func}(\\1{{namespace="{namespace}"}})', query)
                        break
    
    response = requests.get(
        f"{PROMETHEUS_URL}/api/v1/query_range",
        headers=headers,
        params={"query": query, "start": start, "end": end, "step": "30s"},
        verify=verify,
    )
    response.raise_for_status()
    result = response.json()["data"]["result"]

    rows = []
    for series in result:
        for val in series["values"]:
            ts = datetime.fromtimestamp(float(val[0]))
            value = float(val[1])
            
            # Handle NaN values that can't be JSON serialized
            if pd.isna(value) or value != value:  # Check for NaN
                value = 0.0  # Convert NaN to 0 for JSON compatibility
            
            row = dict(series["metric"])
            row["timestamp"] = ts
            row["value"] = value
            rows.append(row)

    return pd.DataFrame(rows)


def build_openshift_prompt(metric_dfs, metric_category, namespace=None, scope_description=None):
    """Build prompt for OpenShift metrics analysis"""
    if scope_description:
        scope = scope_description
    else:
        scope = f"namespace **{namespace}**" if namespace else "cluster-wide"
    
    header = f"You are evaluating OpenShift **{metric_category}** metrics for {scope}.\n\n📊 **Metrics**:\n"
    analysis_focus = f"{metric_category.lower()} performance and health"
    
    lines = []
    for label, df in metric_dfs.items():
        if df.empty:
            lines.append(f"- {label}: No data")
            continue
        avg = df["value"].mean()
        latest = df["value"].iloc[-1] if not df.empty else 0
        trend = describe_trend(df)
        anomaly = detect_anomalies(df, label)
        lines.append(
            f"- {label}: Avg={avg:.2f}, Latest={latest:.2f}, Trend={trend}, {anomaly}"
        )
    
    analysis_questions = f"""🔍 Please analyze:
1. What's the current state of {analysis_focus}?
2. Are there any performance or reliability concerns?
3. What actions should be taken?
4. Any optimization recommendations?"""
    
    return f"""{header}
{chr(10).join(lines)}

{analysis_questions}
""".strip()


# --- OpenShift Request Models ---
class OpenShiftAnalyzeRequest(BaseModel):
    metric_category: str  # Specific category
    scope: str  # "cluster_wide" or "namespace_scoped"
    namespace: Optional[str] = None  # Required if scope is "namespace_scoped"
    start_ts: int
    end_ts: int
    summarize_model_id: str
    api_key: Optional[str] = None


class OpenShiftChatRequest(BaseModel):
    metric_category: str  # Specific category
    scope: str  # "cluster_wide" or "namespace_scoped"
    question: str
    namespace: Optional[str] = None  # Required if scope is "namespace_scoped"
    start_ts: int
    end_ts: int
    summarize_model_id: str
    api_key: Optional[str] = None


def get_namespace_specific_metrics(category):
    """Get metrics that actually have namespace labels for namespace-specific analysis"""
    
    namespace_aware_metrics = {
        "Fleet Overview": {
            # Metrics that work with namespace filtering
            "Deployment Replicas Ready": "sum(kube_deployment_status_replicas_ready)",
            "Pods Running": "sum(kube_pod_status_phase{phase='Running'})",
            "Pods Failed": "sum(kube_pod_status_phase{phase='Failed'})",
            "Container CPU Usage": "sum(rate(container_cpu_usage_seconds_total[5m]))",
            "Container Memory Usage": "sum(container_memory_usage_bytes)",
            "Pod Restart Rate": "sum(rate(kube_pod_container_status_restarts_total[5m]))",
        },
                "Workloads & Pods": {
            # Pod and container metrics naturally have namespace labels
            "Pods Running": "sum(kube_pod_status_phase{phase='Running'})",
            "Pods Pending": "sum(kube_pod_status_phase{phase='Pending'})",
            "Pods Failed": "sum(kube_pod_status_phase{phase='Failed'})",
            "Pod Restarts (Rate)": "sum(rate(kube_pod_container_status_restarts_total[5m]))",
            "Container CPU Usage": "sum(rate(container_cpu_usage_seconds_total[5m]))",
            "Container Memory Usage": "sum(container_memory_usage_bytes)",
        },
        "Compute & Resources": {
            # Container-level compute and resource metrics
            "Container CPU Throttling": "sum(container_cpu_cfs_throttled_seconds_total)",
            "Container Memory Failures": "sum(container_memory_failcnt)",
            "OOM Events": "sum(container_oom_events_total)",
            "Container Processes": "sum(container_processes)",
            "Container Threads": "sum(container_threads)",
            "Container File Descriptors": "sum(container_file_descriptors)",
        },
        "Storage & Networking": {
            # Storage and network metrics that have namespace context
            "PV Claims Bound": "sum(kube_persistentvolumeclaim_status_phase{phase='Bound'})",
            "PV Claims Pending": "sum(kube_persistentvolumeclaim_status_phase{phase='Pending'})",
            "Container Network Receive": "sum(rate(container_network_receive_bytes_total[5m]))",
            "Container Network Transmit": "sum(rate(container_network_transmit_bytes_total[5m]))",
            "Network Errors": "sum(rate(container_network_receive_errors_total[5m]) + rate(container_network_transmit_errors_total[5m]))",
            "Filesystem Usage": "sum(container_fs_usage_bytes)",
        },
        "Application Services": {
            # Application metrics that work at namespace level
            "HTTP Request Rate": "sum(rate(http_requests_total[5m]))",
            "HTTP Error Rate (%)": "sum(rate(http_requests_total{status=~'5..'}[5m])) / sum(rate(http_requests_total[5m])) * 100",
            "Available Endpoints": "sum(kube_endpoint_address_available)",
            "Container Processes": "sum(container_processes)",
            "Container File Descriptors": "sum(container_file_descriptors)",
            "Container Threads": "sum(container_threads)",
        },
    }
    
    return namespace_aware_metrics.get(category, {})


# --- OpenShift Endpoints ---

@app.get("/openshift-metric-groups")
def list_openshift_metric_groups():
    """Get available OpenShift metric groups"""
    return list(get_openshift_metrics().keys())


@app.get("/openshift-namespace-metric-groups")
def list_openshift_namespace_metric_groups():
    """Get available OpenShift metric groups for namespace-specific analysis"""
    # Return only categories that have namespace-specific implementations
    # These are the categories that make sense at namespace level
    return ["Fleet Overview", "Workloads & Pods", "Compute & Resources", "Storage & Networking", "Application Services"]


@app.get("/vllm-metrics")
def list_vllm_metrics():
    """Get available vLLM metrics dynamically"""
    return get_vllm_metrics()


@app.get("/dcgm-metrics")
def list_dcgm_metrics():
    """Get available DCGM GPU metrics"""
    return discover_dcgm_metrics()


@app.get("/gpu-info")
def get_gpu_info():
    """Get GPU vendor and model information from DCGM metrics"""
    try:
        headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
        
        # Try to get GPU info from various metrics
        info_queries = [
            "DCGM_FI_DEV_GPU_TEMP",  # Basic GPU metric to check GPU availability
            "gpu_operator_gpu_nodes_total",  # GPU operator metrics
            "vendor_model:node_accelerator_cards:sum",  # Vendor/model info
        ]
        
        gpu_info = {
            "total_gpus": 0,
            "vendors": [],
            "models": [],
            "temperatures": [],
            "power_usage": [],
        }
        
        for query in info_queries:
            try:
                response = requests.get(
                    f"{PROMETHEUS_URL}/api/v1/query",
                    headers=headers,
                    params={"query": query},
                    verify=verify,
                )
                response.raise_for_status()
                result = response.json()["data"]["result"]
                
                if result and query == "DCGM_FI_DEV_GPU_TEMP":
                    # Extract GPU count and current temperatures
                    gpu_info["total_gpus"] = len(result)
                    gpu_info["temperatures"] = [float(item["value"][1]) for item in result]
                    
                    # Extract vendor/model from labels if available
                    for item in result:
                        labels = item.get("metric", {})
                        if "vendor" in labels:
                            gpu_info["vendors"].append(labels["vendor"])
                        if "model" in labels:
                            gpu_info["models"].append(labels["model"])
                        if "device" in labels:
                            gpu_info["models"].append(labels["device"])
                            
            except Exception as e:
                print(f"Error querying {query}: {e}")
                continue
        
        # Remove duplicates and sort
        gpu_info["vendors"] = sorted(list(set(gpu_info["vendors"])))
        gpu_info["models"] = sorted(list(set(gpu_info["models"])))
        
        return gpu_info
    except Exception as e:
        print(f"Error fetching GPU info: {e}")
        return {"total_gpus": 0, "vendors": [], "models": [], "temperatures": [], "power_usage": []}


@app.get("/openshift-namespaces")
def list_openshift_namespaces():
    """Get available OpenShift namespaces from kube-state-metrics"""
    try:
        headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/series",
            headers=headers,
            params={
                "match[]": "kube_pod_info",
                "start": int((datetime.now().timestamp()) - 86400),  # last 24 hours
                "end": int(datetime.now().timestamp()),
            },
            verify=verify,
        )
        response.raise_for_status()
        series = response.json()["data"]

        namespace_set = set()
        for entry in series:
            namespace = entry.get("namespace", "").strip()
            if namespace and namespace not in ["kube-system", "openshift-system", "openshift-monitoring"]:
                namespace_set.add(namespace)
        return sorted(list(namespace_set))
    except Exception as e:
        print("Error getting OpenShift namespaces:", e)
        return []


@app.post("/analyze-openshift")
def analyze_openshift(req: OpenShiftAnalyzeRequest):
    """Analyze OpenShift metrics for a specific category"""
    try:
        openshift_metrics = get_openshift_metrics()
        
        # Validate metric category based on scope
        if req.scope == "namespace_scoped" and req.namespace:
            # For namespace-scoped analysis, check against namespace-specific metrics first
            namespace_metrics = get_namespace_specific_metrics(req.metric_category)
            if not namespace_metrics:
                # Fall back to cluster-wide metrics if no namespace-specific metrics available
                if req.metric_category not in openshift_metrics:
                    raise HTTPException(status_code=400, detail=f"Invalid metric category: {req.metric_category}")
                metrics_to_fetch = openshift_metrics[req.metric_category]
            else:
                metrics_to_fetch = namespace_metrics
        else:
            # For cluster-wide analysis, check against cluster-wide metrics
            if req.metric_category not in openshift_metrics:
                raise HTTPException(status_code=400, detail=f"Invalid metric category: {req.metric_category}")
            metrics_to_fetch = openshift_metrics[req.metric_category]
        
        # Determine namespace for fetching based on scope and available metrics
        # Don't use namespace filtering if we fell back to cluster-wide metrics (like GPU)
        namespace_for_query = None
        if req.scope == "namespace_scoped" and req.namespace:
            # Only apply namespace filtering if we have actual namespace-specific metrics
            original_ns_metrics = get_namespace_specific_metrics(req.metric_category)
            if original_ns_metrics:
                namespace_for_query = req.namespace
        
        metric_dfs = {}
        for label, query in metrics_to_fetch.items():
            try:
                df = fetch_openshift_metrics(query, req.start_ts, req.end_ts, namespace_for_query)
                metric_dfs[label] = df
            except Exception as e:
                print(f"Error fetching {label}: {e}")
                metric_dfs[label] = pd.DataFrame()  # Empty DataFrame for failed queries
        
        # Build analysis prompt
        scope_description = f"{req.scope.replace('_', ' ').title()}"
        if req.scope == "namespace_scoped" and req.namespace:
            # Check if we fell back to cluster-wide metrics
            original_ns_metrics = get_namespace_specific_metrics(req.metric_category)
            if original_ns_metrics:
                scope_description += f" ({req.namespace})"
            else:
                scope_description += f" ({req.namespace}) - Note: {req.metric_category} metrics are cluster-wide"
            
        prompt = build_openshift_prompt(metric_dfs, req.metric_category, namespace_for_query, scope_description)
        summary = summarize_with_llm(prompt, req.summarize_model_id, req.api_key)

        # Serialize metrics for frontend
        serialized_metrics = {}
        for label, df in metric_dfs.items():
            # Ensure required columns exist
            for col in ["timestamp", "value"]:
                if col not in df.columns:
                    df[col] = pd.Series(
                        dtype="datetime64[ns]" if col == "timestamp" else "float"
                    )
            
            # Handle any remaining NaN values before serialization
            if not df.empty and "value" in df.columns:
                df["value"] = df["value"].fillna(0.0)  # Replace NaN with 0
            
            serialized_metrics[label] = df[["timestamp", "value"]].to_dict(
                orient="records"
            )

        return {
            "metric_category": req.metric_category,
            "scope": req.scope,
            "namespace": req.namespace,
            "health_prompt": prompt,
            "llm_summary": summary,
            "metrics": serialized_metrics,
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in analyze_openshift: {e}")
        raise HTTPException(
            status_code=500, detail="Please check your API Key or try again later."
        )


@app.post("/chat-openshift")
def chat_openshift(req: OpenShiftChatRequest):
    """Chat about OpenShift metrics for a specific category"""
    try:
        openshift_metrics = get_openshift_metrics()
        
        # Validate metric category based on scope
        if req.scope == "namespace_scoped" and req.namespace:
            # For namespace-scoped analysis, check against namespace-specific metrics first
            namespace_metrics = get_namespace_specific_metrics(req.metric_category)
            if not namespace_metrics:
                # Fall back to cluster-wide metrics if no namespace-specific metrics available
                if req.metric_category not in openshift_metrics:
                    raise HTTPException(status_code=400, detail=f"Invalid metric category: {req.metric_category}")
                metrics_to_fetch = openshift_metrics[req.metric_category]
            else:
                metrics_to_fetch = namespace_metrics
        else:
            # For cluster-wide analysis, check against cluster-wide metrics
            if req.metric_category not in openshift_metrics:
                raise HTTPException(status_code=400, detail=f"Invalid metric category: {req.metric_category}")
            metrics_to_fetch = openshift_metrics[req.metric_category]
        
        # Determine namespace for fetching based on scope
        namespace_for_query = req.namespace if req.scope == "namespace_scoped" else None
        
        metric_dfs = {}
        # Fetch metrics for the specified category
        for label, query in metrics_to_fetch.items():
            try:
                df = fetch_openshift_metrics(query, req.start_ts, req.end_ts, namespace_for_query)
                metric_dfs[label] = df
            except Exception as e:
                print(f"Error fetching {label}: {e}")
                metric_dfs[label] = pd.DataFrame()
        
        # Build scope description
        scope_description = f"{req.scope.replace('_', ' ').title()}"
        if req.scope == "namespace_scoped" and req.namespace:
            scope_description += f" ({req.namespace})"
        
        # Build metrics summary for the LLM
        metrics_data_summary = build_openshift_prompt(metric_dfs, req.metric_category, namespace_for_query, scope_description)
        
        # Create a simple prompt for OpenShift chat
        context_description = f"OpenShift {req.metric_category} metrics for **{scope_description}**"
            
        prompt = f"""You are a senior Site Reliability Engineer (SRE) analyzing {context_description}.

Current Metrics:
{metrics_data_summary}

User Question: {req.question}

Provide a concise technical response focusing on operational insights and recommendations. Respond with JSON format:
{{"promql": "relevant_query_if_applicable", "summary": "your_analysis"}}"""

        llm_response = summarize_with_llm(prompt, req.summarize_model_id, req.api_key)

        # Simple JSON parsing
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                promql = parsed.get("promql", "").strip()
                summary = parsed.get("summary", llm_response).strip()
                
                # Add namespace filtering to PromQL if specified and not already present
                if promql and req.namespace and "namespace=" not in promql:
                    if "{" in promql:
                        promql = promql.replace("{", f'{{namespace="{req.namespace}", ')
                    else:
                        promql = f'{promql}{{namespace="{req.namespace}"}}'
                
                return {"promql": promql, "summary": summary}
        except json.JSONDecodeError:
            pass
        
        # Fallback
        return {"promql": "", "summary": llm_response}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in chat_openshift: {e}")
        raise HTTPException(
            status_code=500, detail="Please check your API Key or try again later."
        )


@app.get("/debug-metrics")
def debug_metrics():
    """Debug endpoint to check available metrics"""
    try:
        headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/label/__name__/values",
            headers=headers,
            verify=verify,
        )
        response.raise_for_status()
        all_metrics = response.json()["data"]
        
        # Categorize metrics
        dcgm_metrics = [m for m in all_metrics if m.startswith("DCGM_")]
        vllm_metrics = [m for m in all_metrics if m.startswith("vllm:")]
        kube_metrics = [m for m in all_metrics if m.startswith("kube_")]
        container_metrics = [m for m in all_metrics if m.startswith("container_")]
        
        return {
            "total_metrics": len(all_metrics),
            "dcgm_metrics": {
                "count": len(dcgm_metrics),
                "examples": dcgm_metrics[:10]  # First 10
            },
            "vllm_metrics": {
                "count": len(vllm_metrics),
                "examples": vllm_metrics[:10]
            },
            "kube_metrics": {
                "count": len(kube_metrics),
                "examples": kube_metrics[:10]
            },
            "container_metrics": {
                "count": len(container_metrics),
                "examples": container_metrics[:10]
            },
            "gpu_info": get_gpu_info(),
            "discovered_vllm": discover_vllm_metrics(),
            "discovered_dcgm": discover_dcgm_metrics()
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/debug-query")
def debug_query(req: dict):
    """Debug query rewriting for namespace filtering"""
    query = req.get("query", "")
    namespace = req.get("namespace", "")
    
    print(f"Original query: {query}")
    print(f"Namespace: {namespace}")
    
    # Simulate the query rewriting logic from fetch_openshift_metrics
    if namespace:
        if not query.startswith(('sum(', 'avg(', 'count(', 'max(', 'min(')):
            # Check if query already has labels
            if "{" in query:
                # Insert namespace into existing label set
                query = query.replace("{", f'{{namespace="{namespace}",')
            else:
                # Add namespace label to query without existing labels
                query = f'{query}{{namespace="{namespace}"}}'
        else:
            # For aggregated queries, add namespace filter inside the aggregation
            import re
            # Find the first metric name inside parentheses
            match = re.search(r'(\w+\([^{(]+)(\{[^}]*\})?', query)
            print(f"Regex match: {match}")
            if match:
                base_part = match.group(1)
                labels_part = match.group(2) if match.group(2) else "{}"
                print(f"Base part: {base_part}")
                print(f"Labels part: {labels_part}")
                
                if labels_part == "{}":
                    # No existing labels
                    new_labels = f'{{namespace="{namespace}"}}'
                else:
                    # Has existing labels, add namespace
                    new_labels = labels_part.replace("{", f'{{namespace="{namespace}",')
                print(f"New labels: {new_labels}")
                
                # Replace the original pattern with the namespace-filtered version
                old_pattern = match.group(0)
                new_pattern = base_part + new_labels
                print(f"Replacing '{old_pattern}' with '{new_pattern}'")
                query = query.replace(old_pattern, new_pattern)
    
    print(f"Final query: {query}")
    return {"original": req.get("query", ""), "rewritten": query, "namespace": namespace}
