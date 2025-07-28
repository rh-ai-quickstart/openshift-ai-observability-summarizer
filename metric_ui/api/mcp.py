from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import pandas as pd
import requests
from datetime import datetime, timezone, timedelta, time
from scipy.stats import linregress
import os
import json
import re
from typing import List, Dict, Any, Optional
import uuid
import sys
from collections import defaultdict
from dateparser.search import search_dates

# Add current directory and parent directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)  # For local development (metric_ui/)
sys.path.insert(0, current_dir)  # For container deployment (/app/)

from report_assets.report_renderer import (
    generate_html_report,
    generate_markdown_report,
    generate_pdf_report,
    ReportSchema,
    MetricCard,
)

# Import from core business logic
from core.metrics import (
    get_models_helper,
    discover_vllm_metrics,
    discover_dcgm_metrics,
    discover_openshift_metrics,
    get_vllm_metrics,
    get_openshift_metrics,
    discover_cluster_metrics_dynamically,
    get_all_metrics,
    get_namespace_specific_metrics,
    fetch_metrics,
    fetch_openshift_metrics,
)
from core.analysis import (
    detect_anomalies,
    describe_trend,
    compute_health_score,
)
from core.reports import (
    save_report,
    get_report_path,
    build_report_schema,
)
from core.alerts import (
    fetch_alerts_from_prometheus,
    fetch_all_rule_definitions as _fetch_all_rule_definitions,
)
from core.llm_client import (
    summarize_with_llm,
    build_prompt,
    build_chat_prompt, 
    build_openshift_prompt,
    build_openshift_chat_prompt,
    build_flexible_llm_prompt,
    _make_api_request,
    _validate_and_extract_response,
    _clean_llm_summary_string,
    extract_time_range_with_info,
    extract_time_range,
    add_namespace_filter,
    fix_promql_syntax,
    format_alerts_for_ui
)
from core.models import (
    AnalyzeRequest,
    ChatRequest,
    ChatPrometheusRequest,
    ChatMetricsRequest,
    OpenShiftAnalyzeRequest,
    OpenShiftChatRequest,
    ReportRequest,
    MetricsCalculationRequest,
    MetricsCalculationResponse,
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

# --- Helpers ---














# helper functions for Chat with Prometheus











@app.get("/health")
def health():
    return {"status": "ok"}





@app.get("/models")
def list_models():
    return get_models_helper()


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
            "vllm:gpu_cache_usage_perc",
        ]

        namespace_set = set()

        # Try different time windows: 7 days, 24 hours, 1 hour
        time_windows = [7 * 24 * 3600, 24 * 3600, 3600]  # 7 days  # 24 hours  # 1 hour

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
                    print(
                        f"Error checking {metric_name} with {time_window}s window: {e}"
                    )
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


@app.post("/chat-metrics")
def chat_metrics(req: ChatMetricsRequest):
    """
    Enhanced chat endpoint that supports ALL metrics (vLLM, OpenShift, GPU) with fleet-wide and namespace-specific scope
    """
    try:
        # 1. Extract time range with enhanced info for LLM context
        start_ts, end_ts, time_range_info = extract_time_range_with_info(req.question, req.start_ts, req.end_ts)
        
        # 2. Determine scope - fleet-wide or namespace-specific
        is_fleet_wide = req.chat_scope == "fleet_wide"
        target_namespace = None if is_fleet_wide else req.namespace
        
        # 3. Determine query type and fetch appropriate metrics
        question_lower = req.question.lower()
        is_all_models_query = (
            "all models currently deployed" in question_lower
            or "list all models" in question_lower
            or "what models are deployed" in question_lower.replace("?", "")
        )
        is_tokens_generated_query = "how many tokens generated" in question_lower

        metrics_data_summary = ""
        generated_tokens_sum_value = None

        # 4. Get ALL available metrics (vLLM, OpenShift, GPU)
        all_metrics = get_all_metrics()
        
        # 5. Fetch metric data for relevant metrics based on query type and scope
        if is_tokens_generated_query:
            # Focus on token generation metrics
            vllm_metrics = get_vllm_metrics()
            metric_dfs = {
                label: fetch_metrics(
                    query, req.model_name, start_ts, end_ts, namespace=target_namespace
                )
                for label, query in vllm_metrics.items()
                if "token" in label.lower()
            }
            
            output_tokens_df = metric_dfs.get("Output Tokens Created")
            if output_tokens_df is not None and not output_tokens_df.empty:
                generated_tokens_sum_value = output_tokens_df["value"].sum()
                scope_desc = "across all namespaces" if is_fleet_wide else f"in namespace {req.namespace}"
                metrics_data_summary = f"Output Tokens Created {scope_desc}: Total Generated = {generated_tokens_sum_value:.2f}"
            else:
                scope_desc = "across all namespaces" if is_fleet_wide else f"in namespace {req.namespace}"
                metrics_data_summary = f"Output Tokens Created {scope_desc}: No data available to calculate sum."

        elif is_all_models_query:
            # For "all models" query, fetch globally deployed models directly
            deployed_models_list = _get_models_helper()

            if is_fleet_wide:
                # Show all models across all namespaces
                metrics_data_summary = (
                    f"Models deployed fleet-wide: " + ", ".join(deployed_models_list)
                    if deployed_models_list
                    else "No models found fleet-wide"
                )
            else:
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
            # For other metric-specific queries, intelligently select relevant metrics
            # Try to determine what type of metrics the user is asking about
            
            # PRIORITIZE fleet-wide vs namespace-specific detection first
            if is_fleet_wide or any(keyword in question_lower for keyword in ["cluster", "fleet", "entire", "total", "all namespaces", "cluster-wide"]):
                # FLEET-WIDE queries - use only OpenShift/Kubernetes metrics, never vLLM
                print(f"🔍 Detected FLEET-WIDE query: {req.question}")
                openshift_metrics = get_openshift_metrics()
                
                # Smart metric selection based on query content
                relevant_metrics = {}
                
                # Services & Networking
                if any(keyword in question_lower for keyword in ["service", "services", "endpoint", "endpoints", "ingress", "network", "loadbalancer", "clusterip"]):
                    relevant_metrics.update(openshift_metrics.get("Services & Networking", {}))
                
                # Jobs & Workloads  
                if any(keyword in question_lower for keyword in ["job", "jobs", "cronjob", "cronjobs", "daemonset", "daemonsets", "statefulset", "statefulsets"]):
                    relevant_metrics.update(openshift_metrics.get("Jobs & Workloads", {}))
                
                # Storage & Config
                if any(keyword in question_lower for keyword in ["volume", "volumes", "pv", "pvc", "storage", "configmap", "configmaps", "secret", "secrets", "storageclass"]):
                    relevant_metrics.update(openshift_metrics.get("Storage & Config", {}))
                
                # Pods & Containers
                if any(keyword in question_lower for keyword in ["pod", "pods", "container", "containers"]):
                    relevant_metrics.update(openshift_metrics.get("Workloads & Pods", {}))
                    relevant_metrics.update(openshift_metrics.get("Fleet Overview", {}))
                
                # CPU, Memory, Nodes
                if any(keyword in question_lower for keyword in ["cpu", "memory", "node", "nodes", "compute"]):
                    relevant_metrics.update(openshift_metrics.get("Fleet Overview", {}))
                
                # Deployments
                if any(keyword in question_lower for keyword in ["deployment", "deployments", "replica", "replicas"]):
                    relevant_metrics.update({
                        "Total Deployments": "sum(kube_deployment_status_replicas_ready)",
                        "Deployment Replicas Available": "sum(kube_deployment_status_replicas_available)", 
                        "Deployment Replicas Desired": "sum(kube_deployment_spec_replicas)",
                        "Total Pods Running": "sum(kube_pod_status_phase{phase='Running'})",
                    })
                
                # Images & Containers
                if any(keyword in question_lower for keyword in ["image", "images", "container images"]):
                    relevant_metrics.update({
                        "Container Images": "count(count by (image)(container_spec_image))",
                        "Running Containers": "sum(kube_pod_container_status_running)",
                        "Total Pods Running": "sum(kube_pod_status_phase{phase='Running'})",
                    })
                
                # If no specific category detected, try dynamic discovery or use Fleet Overview
                if not relevant_metrics:
                    print("🔍 No static metrics matched, trying dynamic discovery...")
                    dynamic_metrics = discover_cluster_metrics_dynamically()
                    
                    # Try to find relevant metrics from dynamic discovery based on keywords
                    for label, query in dynamic_metrics.items():
                        label_lower = label.lower()
                        if any(keyword in label_lower for keyword in question_lower.split()):
                            relevant_metrics[label] = query
                            if len(relevant_metrics) >= 6:  # Limit to avoid overwhelming
                                break
                    
                    # If still no metrics found, use Fleet Overview as final fallback
                    if not relevant_metrics:
                        relevant_metrics = openshift_metrics.get("Fleet Overview", {})
                
                metric_dfs = {
                    label: fetch_openshift_metrics(
                        query, start_ts, end_ts, namespace=None  # No namespace filter for fleet-wide
                    )
                    for label, query in list(relevant_metrics.items())[:8]
                }
                
                # Build fleet-wide summary
                metrics_data_summary = f"Fleet-wide OpenShift cluster analysis:\n"
                for label, df in metric_dfs.items():
                    if df.empty:
                        metrics_data_summary += f"- {label}: No data available\n"
                    else:
                        latest = df["value"].iloc[-1] if not df.empty else 0
                        avg = df["value"].mean()
                        metrics_data_summary += f"- {label}: Current={latest:.2f}, Average={avg:.2f}\n"
                        
            elif any(keyword in question_lower for keyword in [
                # Core Kubernetes resources
                "pod", "pods", "container", "containers", "kubernetes", "openshift", "k8s",
                "node", "nodes", "deployment", "deployments", "service", "services", 
                "pv", "pvc", "ingress", "endpoint", "endpoints",
                # Workload types
                "job", "jobs", "cronjob", "cronjobs", "daemonset", "daemonsets", 
                "statefulset", "statefulsets", "replicaset", "replicasets",
                # Storage & Config
                "volume", "volumes", "storage", "configmap", "configmaps", 
                "secret", "secrets", "storageclass", "snapshot",
                # Networking
                "network", "networking", "loadbalancer", "clusterip", "nodeport",
                # Additional cluster concepts
                "namespace", "namespaces", "cluster", "kube", "replica", "replicas"
            ]):
                # Namespace-specific OpenShift/Kubernetes query
                print(f"🔍 Detected namespace-specific OpenShift/Kubernetes query: {req.question}")
                openshift_metrics = get_openshift_metrics()
                
                # For pod queries, focus on Workloads & Pods
                if "pod" in question_lower:
                    relevant_metrics = openshift_metrics.get("Workloads & Pods", {})
                else:
                    # Use all openshift metrics, flattened
                    relevant_metrics = {}
                    for category, metrics in openshift_metrics.items():
                        relevant_metrics.update(metrics)
                
                metric_dfs = {
                    label: fetch_openshift_metrics(
                        query, start_ts, end_ts, namespace=target_namespace
                    )
                    for label, query in list(relevant_metrics.items())[:8]
                }
                
                # Build namespace-specific summary
                metrics_data_summary = f"OpenShift metrics analysis for namespace {target_namespace}:\n"
                for label, df in metric_dfs.items():
                    if df.empty:
                        metrics_data_summary += f"- {label}: No data\n"
                    else:
                        avg = df["value"].mean()
                        latest = df["value"].iloc[-1] if not df.empty else 0
                        metrics_data_summary += f"- {label}: Latest={latest:.2f}, Avg={avg:.2f}\n"
                        
            elif any(keyword in question_lower for keyword in ["gpu", "temperature", "power", "memory utilization", "energy", "dcgm"]):
                # GPU-related query - fetch GPU metrics
                print(f"🔍 Detected GPU query: {req.question}")
                gpu_metrics = {k: v for k, v in all_metrics.items() if "GPU:" in k}
                metric_dfs = {
                    label.replace("GPU: ", ""): fetch_metrics(
                        query, req.model_name, start_ts, end_ts, namespace=target_namespace
                    )
                    for label, query in gpu_metrics.items()
                }
                # Build metrics summary using existing function
                metrics_data_summary = build_prompt(metric_dfs, req.model_name)
                
            else:
                # vLLM or general query - fetch vLLM metrics
                print(f"🔍 Detected vLLM/general query: {req.question}")
                vllm_metrics = get_vllm_metrics()
                metric_dfs = {
                    label: fetch_metrics(
                        query, req.model_name, start_ts, end_ts, namespace=target_namespace
                    )
                    for label, query in vllm_metrics.items()
                }
                # Build metrics summary using existing function
                metrics_data_summary = build_prompt(metric_dfs, req.model_name)

        # 6. Build the enhanced prompt with time range and scope context
        # Determine if this is an OpenShift query for specialized prompt
        is_openshift_query = (
            is_fleet_wide or 
            any(keyword in question_lower for keyword in ["cluster", "fleet", "entire", "total", "all namespaces", "cluster-wide"]) or
            any(keyword in question_lower for keyword in [
                # Core Kubernetes resources
                "pod", "pods", "container", "containers", "kubernetes", "openshift", "k8s",
                "node", "nodes", "deployment", "deployments", "service", "services", 
                "pv", "pvc", "ingress", "endpoint", "endpoints",
                # Workload types
                "job", "jobs", "cronjob", "cronjobs", "daemonset", "daemonsets", 
                "statefulset", "statefulsets", "replicaset", "replicasets",
                # Storage & Config
                "volume", "volumes", "storage", "configmap", "configmaps", 
                "secret", "secrets", "storageclass", "snapshot",
                # Networking
                "network", "networking", "loadbalancer", "clusterip", "nodeport",
                # System resources
                "cpu usage", "memory usage", "cpu", "memory", "compute",
                # Images and additional concepts
                "image", "images", "replica", "replicas", "namespace", "namespaces"
            ])
        )
        
        if is_openshift_query:
            prompt = build_openshift_chat_prompt(
                question=req.question,
                metrics_context=metrics_data_summary,
                time_range_info=time_range_info,
                chat_scope=req.chat_scope,
                target_namespace=target_namespace,
            )
        else:
            prompt = build_flexible_llm_prompt(
                question=req.question,
                model_name=req.model_name,
                metrics_context=metrics_data_summary,
                generated_tokens_sum=generated_tokens_sum_value,
                selected_namespace=target_namespace,
                time_range_info=time_range_info,
                chat_scope=req.chat_scope,
            )
        
        # 6. Get LLM response
        llm_response = summarize_with_llm(prompt, req.summarize_model_id, req.api_key)

        # Debug LLM response
        print("🧠 Raw LLM response:", llm_response)

        # 7. Enhanced JSON parsing (from the better chat-metrics implementation you showed)
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

            # Find the first complete JSON object (more precise matching)
            json_start = cleaned_response.find('{')
            if json_start == -1:
                raise ValueError(f"No JSON object found in response: '{cleaned_response}'")
            
            # Find the matching closing brace for the first JSON object
            brace_count = 0
            json_end = json_start
            in_string = False
            escape_next = False
            
            for i, char in enumerate(cleaned_response[json_start:], json_start):
                if escape_next:
                    escape_next = False
                    continue
                if char == '\\':
                    escape_next = True
                    continue
                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = i + 1
                            break
            
            if brace_count != 0:
                raise ValueError(f"Malformed JSON object in response: '{cleaned_response}'")
            
            json_string = cleaned_response[json_start:json_end]
            print("⚙️ Extracted JSON string:", json_string)

            # Clean the JSON string - be more careful with escaped quotes
            # First, fix escaped quotes in PromQL queries - specifically in namespace values
            json_string = re.sub(r'namespace=\\"([^"]*)\\"', r'namespace="\1"', json_string)
            print("⚙️ After fixing namespace escaped quotes:", json_string)
            
            # Fix any remaining escaped quotes
            json_string = re.sub(r'\\\"', '"', json_string)
            print("⚙️ After fixing escaped quotes:", json_string)
            
            # Remove any excessive whitespace but preserve structure
            json_string = re.sub(r'\n\s*', ' ', json_string)
            json_string = re.sub(r'\s{2,}', ' ', json_string)
            print("⚙️ After whitespace normalization:", json_string)

            # Remove trailing commas
            json_string = re.sub(r",\s*}", "}", json_string)
            json_string = re.sub(r",\s*]", "]", json_string)
            print("⚙️ After trailing comma removal:", json_string)

            print("🔍 Final Cleaned JSON string for parsing:", json_string)

            # Parse the JSON - try multiple approaches for robustness
            try:
                parsed = json.loads(json_string)
            except json.JSONDecodeError:
                # If that fails, try with ast.literal_eval for safer parsing
                import ast
                try:
                    # Replace any remaining problematic patterns
                    fixed_json = json_string.replace('\\"', '"')
                    parsed = json.loads(fixed_json)
                except json.JSONDecodeError:
                    # Last resort: manually extract the important parts
                    promqls_match = re.search(r'"promqls":\s*\[(.*?)\]', json_string, re.DOTALL)
                    summary_match = re.search(r'"summary":\s*"(.*?)"(?=\s*[,}])', json_string, re.DOTALL)
                    
                    parsed = {
                        "promqls": [promqls_match.group(1).strip('"')] if promqls_match else [],
                        "summary": summary_match.group(1) if summary_match else ""
                    }

            # Extract and clean the fields
            promqls = parsed.get("promqls", [])
            promql = promqls[0] if promqls else ""
            if isinstance(promql, list):
                promql = promql[0] if promql else ""
            promql = promql.strip() if promql else ""
            summary = _clean_llm_summary_string(parsed.get("summary", ""))

            # Fix PromQL syntax issues and ensure proper time range syntax
            if promql:
                promql = fix_promql_syntax(promql, time_range_info.get("rate_syntax", "5m"))
                
                # Handle namespace filtering based on chat scope
                if is_fleet_wide:
                    # Fleet-wide: Remove any namespace filters to query across all namespaces
                    promql = re.sub(r"\{([^}]*)namespace=[^,}]*(,)?", r"{\1", promql)
                    promql = re.sub(r"namespace=[^,}]*(,)?", "", promql)
                    # Clean up any resulting empty braces or trailing commas
                    promql = re.sub(r"\{\s*,", "{", promql)
                    promql = re.sub(r",\s*\}", "}", promql)
                    promql = re.sub(r"\{\s*\}", "", promql)
                elif req.namespace:
                    # Namespace-specific: Ensure the correct namespace is in PromQL
                    # Remove existing namespace labels from PromQL if present
                    promql = re.sub(r"\{([^}]*)namespace=[^,}]*(,)?", r"{\1", promql)
                    # Add the correct namespace
                    if "{" in promql:
                        promql = promql.replace("{", f'{{namespace="{req.namespace}", ')
                    else:
                        # If no existing curly braces, add them with the namespace
                        promql = f"{promql}{{namespace='{req.namespace}'}}"
                
                # Final cleanup of any syntax issues
                promql = fix_promql_syntax(promql, time_range_info.get("rate_syntax", "5m"))

            if not summary:
                raise ValueError("Empty summary in response")

            return {
                "promql": promql, 
                "summary": summary,
                "time_range": time_range_info.get("duration_str", ""),
                "metrics_type": "all",
                "chat_scope": req.chat_scope
            }

        except json.JSONDecodeError as e:
            print(f"⚠️ JSON Decode Error: {e}")
            return {
                "promql": "",
                "summary": f"Failed to parse response: {e}. Raw response: {llm_response}",
                "time_range": time_range_info.get("duration_str", ""),
                "chat_scope": req.chat_scope
            }
        except ValueError as e:
            print(f"⚠️ Value Error: {e}")
            return {
                "promql": "",
                "summary": f"Failed to process response: {e}. Raw response: {llm_response}",
                "time_range": time_range_info.get("duration_str", ""),
                "chat_scope": req.chat_scope
            }
        except Exception as e:
            print(f"⚠️ Unexpected error: {e}")
            return {
                "promql": "",
                "summary": f"An unexpected error occurred: {e}. Raw response: {llm_response}",
                "time_range": time_range_info.get("duration_str", ""),
                "chat_scope": req.chat_scope
            }

    except Exception as e:
        print(f"Error in chat_metrics: {e}")
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
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid metric category: {req.metric_category}",
                    )
                metrics_to_fetch = openshift_metrics[req.metric_category]
            else:
                metrics_to_fetch = namespace_metrics
        else:
            # For cluster-wide analysis, check against cluster-wide metrics
            if req.metric_category not in openshift_metrics:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid metric category: {req.metric_category}",
                )
            metrics_to_fetch = openshift_metrics[req.metric_category]

        # Determine namespace for fetching based on scope
        namespace_for_query = req.namespace if req.scope == "namespace_scoped" else None

        metric_dfs = {}
        # Fetch metrics for the specified category
        for label, query in metrics_to_fetch.items():
            try:
                df = fetch_openshift_metrics(
                    query, req.start_ts, req.end_ts, namespace_for_query
                )
                metric_dfs[label] = df
            except Exception as e:
                print(f"Error fetching {label}: {e}")
                metric_dfs[label] = pd.DataFrame()

        # Build scope description
        scope_description = f"{req.scope.replace('_', ' ').title()}"
        if req.scope == "namespace_scoped" and req.namespace:
            scope_description += f" ({req.namespace})"

        # Build metrics summary for the LLM
        metrics_data_summary = build_openshift_prompt(
            metric_dfs, req.metric_category, namespace_for_query, scope_description
        )

        # Create a simple prompt for OpenShift chat
        context_description = (
            f"OpenShift {req.metric_category} metrics for **{scope_description}**"
        )

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
            json_match = re.search(r"\{.*\}", llm_response, re.DOTALL)
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


@app.post("/analyze-openshift")
def analyze_openshift(req: OpenShiftAnalyzeRequest):
    """Analyze OpenShift metrics for a specific category and scope"""
    try:
        openshift_metrics = get_openshift_metrics()
        
        # Validate metric category based on scope
        if req.scope == "namespace_scoped" and req.namespace:
            # For namespace-scoped analysis, check against namespace-specific metrics first
            namespace_metrics = get_namespace_specific_metrics(req.metric_category)
            if not namespace_metrics:
                # Fall back to cluster-wide metrics if no namespace-specific metrics available
                if req.metric_category not in openshift_metrics:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid metric category: {req.metric_category}",
                    )
                metrics_to_fetch = openshift_metrics[req.metric_category]
            else:
                metrics_to_fetch = namespace_metrics
        else:
            # For cluster-wide analysis, check against cluster-wide metrics
            if req.metric_category not in openshift_metrics:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid metric category: {req.metric_category}",
                )
            metrics_to_fetch = openshift_metrics[req.metric_category]

        # Determine namespace for fetching based on scope
        namespace_for_query = req.namespace if req.scope == "namespace_scoped" else None

        metric_dfs = {}
        # Fetch metrics for the specified category
        for label, query in metrics_to_fetch.items():
            try:
                df = fetch_openshift_metrics(
                    query, req.start_ts, req.end_ts, namespace_for_query
                )
                metric_dfs[label] = df
            except Exception as e:
                print(f"Error fetching {label}: {e}")
                metric_dfs[label] = pd.DataFrame()

        # Build scope description for prompt
        scope_description = f"{req.scope.replace('_', ' ').title()}"
        if req.scope == "namespace_scoped" and req.namespace:
            scope_description += f" ({req.namespace})"

        # Build metrics summary for the LLM using OpenShift-specific prompt
        prompt = build_openshift_prompt(
            metric_dfs, req.metric_category, namespace_for_query, scope_description
        )

        # Get LLM summary
        summary = summarize_with_llm(prompt, req.summarize_model_id, req.api_key)

        # Serialize metrics data
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


@app.post("/calculate-metrics")
def calculate_metrics(req: MetricsCalculationRequest):
    """Calculate statistics for provided metrics data"""
    try:
        calculated_metrics = {}
        
        for label, data_points in req.metrics_data.items():
            if not data_points:
                calculated_metrics[label] = {
                    "avg": None,
                    "min": None,
                    "max": None,
                    "latest": None,
                    "count": 0
                }
                continue
                
            # Extract values from data points
            values = []
            for point in data_points:
                if isinstance(point, dict) and "value" in point:
                    try:
                        value = float(point["value"])
                        if not (pd.isna(value) or value != value):  # Check for NaN
                            values.append(value)
                    except (ValueError, TypeError):
                        continue
                        
            if values:
                calculated_metrics[label] = {
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values), 
                    "latest": values[-1],
                    "count": len(values)
                }
            else:
                calculated_metrics[label] = {
                    "avg": None,
                    "min": None,
                    "max": None,
                    "latest": None,
                    "count": 0
                }
        
        return {"calculated_metrics": calculated_metrics}
        
    except Exception as e:
        print(f"Error calculating metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Error calculating metrics: {e}")


@app.get("/openshift-metric-groups") 
def get_openshift_metric_groups():
    """Get available OpenShift metric group categories"""
    openshift_metrics = get_openshift_metrics()
    return list(openshift_metrics.keys())


@app.get("/openshift-namespace-metric-groups")
def get_openshift_namespace_metric_groups():
    """Get OpenShift metric groups that work with namespace filtering"""
    return [
        "Workloads & Pods",
        "Storage & Networking", 
        "Application Services"
    ]


@app.get("/vllm-metrics")
def get_vllm_metrics_endpoint():
    """Get available vLLM metrics endpoint for UI"""
    return get_vllm_metrics()


@app.get("/gpu-info") 
def get_gpu_info():
    """Get GPU information"""
    try:
        # Get GPU metrics to determine GPU info
        dcgm_metrics = discover_dcgm_metrics()
        
        gpu_info = {
            "total_gpus": 0,
            "vendors": [],
            "models": [], 
            "temperatures": [],
            "power_usage": []
        }
        
        # Try to get some basic GPU info from metrics
        if dcgm_metrics:
            # Estimate number of GPUs (this is a rough estimate)
            if "GPU Temperature (°C)" in dcgm_metrics:
                try:
                    headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
                    response = requests.get(
                        f"{PROMETHEUS_URL}/api/v1/query",
                        headers=headers,
                        params={"query": "DCGM_FI_DEV_GPU_TEMP"},
                        verify=verify,
                        timeout=30,
                    )
                    response.raise_for_status()
                    result = response.json()["data"]["result"]
                    
                    gpu_info["total_gpus"] = len(result)
                    temperatures = [float(series["value"][1]) for series in result if series["value"]]
                    gpu_info["temperatures"] = temperatures
                    
                    if temperatures:
                        gpu_info["vendors"] = ["NVIDIA"]  # DCGM typically means NVIDIA
                        gpu_info["models"] = ["GPU"]  # Generic for now
                        
                except Exception as e:
                    print(f"Error getting GPU details: {e}")
        
        return gpu_info
        
    except Exception as e:
        print(f"Error getting GPU info: {e}")
        return {
            "total_gpus": 0,
            "vendors": [],
            "models": [],
            "temperatures": [],
            "power_usage": []
        }


@app.get("/openshift-namespaces")
def get_openshift_namespaces():
    """Get list of namespaces with OpenShift resources"""
    try:
        headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
        
        # Query for namespaces from kube metrics
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            headers=headers,
            params={"query": "group by (namespace) (kube_pod_info)"},
            verify=verify,
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()["data"]["result"]
        
        namespaces = set()
        for series in result:
            namespace = series["metric"].get("namespace", "").strip()
            if namespace and namespace not in ["", "kube-system", "openshift-system"]:
                namespaces.add(namespace)
        
        # Add fallback namespaces if none found
        if not namespaces:
            namespaces.update(["default", "openshift-monitoring", "knative-serving"])
            
        return sorted(list(namespaces))
        
    except Exception as e:
        print(f"Error getting OpenShift namespaces: {e}")
        return ["default", "openshift-monitoring", "knative-serving"]


@app.get("/debug-metrics")
def debug_metrics():
    """Debug endpoint to diagnose metric collection issues"""
    debug_info = {
        "prometheus_url": PROMETHEUS_URL,
        "connection_status": "unknown",
        "available_metrics": {},
        "gpu_metrics_found": [],
        "dcgm_metrics_found": [],
        "alternative_gpu_metrics": [],
        "retention_info": {},
        "time_range_availability": {}
    }
    
    try:
        headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
        
        # Test Prometheus connection
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/label/__name__/values",
            headers=headers,
            verify=verify,
            timeout=30,
        )
        response.raise_for_status()
        all_metrics = response.json()["data"]
        debug_info["connection_status"] = "success"
        debug_info["total_metrics_available"] = len(all_metrics)
        
        # Look for GPU-related metrics
        gpu_related = []
        dcgm_metrics = []
        nvidia_metrics = []
        
        for metric in all_metrics:
            metric_lower = metric.lower()
            if "gpu" in metric_lower or "dcgm" in metric_lower:
                gpu_related.append(metric)
            if metric.startswith("DCGM_"):
                dcgm_metrics.append(metric)
            if "nvidia" in metric_lower:
                nvidia_metrics.append(metric)
        
        debug_info["gpu_metrics_found"] = gpu_related[:20]  # Limit to first 20
        debug_info["dcgm_metrics_found"] = dcgm_metrics
        debug_info["nvidia_metrics_found"] = nvidia_metrics
        
        # Check for alternative GPU monitoring metrics
        alternative_patterns = ["nvidia_smi", "gpu_utilization", "gpu_memory", "gpu_temperature"]
        alternative_metrics = []
        for pattern in alternative_patterns:
            matches = [m for m in all_metrics if pattern in m.lower()]
            alternative_metrics.extend(matches)
        debug_info["alternative_gpu_metrics"] = alternative_metrics
        
        # Test historical data availability by checking different time windows
        test_metric = "kube_pod_status_phase"  # Common metric that should exist
        if test_metric in all_metrics:
            time_windows = {
                "1_day": 24 * 3600,
                "1_week": 7 * 24 * 3600,
                "1_month": 30 * 24 * 3600,
                "3_months": 90 * 24 * 3600,
                "6_months": 180 * 24 * 3600,
                "1_year": 365 * 24 * 3600
            }
            
            current_time = int(datetime.now().timestamp())
            for window_name, seconds_ago in time_windows.items():
                start_time = current_time - seconds_ago
                try:
                    test_response = requests.get(
                        f"{PROMETHEUS_URL}/api/v1/query_range",
                        headers=headers,
                        params={
                            "query": test_metric,
                            "start": start_time,
                            "end": current_time,
                            "step": "1h"
                        },
                        verify=verify,
                        timeout=30,
                    )
                    if test_response.status_code == 200:
                        result = test_response.json()["data"]["result"]
                        debug_info["time_range_availability"][window_name] = {
                            "available": len(result) > 0,
                            "data_points": sum(len(series["values"]) for series in result) if result else 0
                        }
                    else:
                        debug_info["time_range_availability"][window_name] = {
                            "available": False,
                            "error": f"HTTP {test_response.status_code}"
                        }
                except Exception as e:
                    debug_info["time_range_availability"][window_name] = {
                        "available": False,
                        "error": str(e)
                    }
        
        # Get retention info if available
        try:
            config_response = requests.get(
                f"{PROMETHEUS_URL}/api/v1/status/config",
                headers=headers,
                verify=verify,
                timeout=30,
            )
            if config_response.status_code == 200:
                config_data = config_response.json()
                if "data" in config_data and "yaml" in config_data["data"]:
                    yaml_config = config_data["data"]["yaml"]
                    if "retention" in yaml_config.lower():
                        debug_info["retention_info"]["config_available"] = True
                        # Extract retention setting (simplified)
                        import re
                        retention_match = re.search(r'retention[:\s]+([^\n\r]+)', yaml_config, re.IGNORECASE)
                        if retention_match:
                            debug_info["retention_info"]["retention_setting"] = retention_match.group(1).strip()
        except Exception as e:
            debug_info["retention_info"]["error"] = str(e)
        
    except Exception as e:
        debug_info["connection_status"] = f"failed: {e}"
    
    return debug_info


@app.get("/test-historical")
def test_historical_queries():
    """Test endpoint for historical data queries"""
    test_queries = [
        "CPU usage in June",
        "Memory usage in April", 
        "Pods running last 6 months",
        "GPU utilization past 3 months",
        "Show me data from May 2024"
    ]
    
    results = {}
    for query in test_queries:
        try:
            start_ts, end_ts, time_info = extract_time_range_with_info(query, None, None)
            start_date = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M")
            end_date = datetime.fromtimestamp(end_ts).strftime("%Y-%m-%d %H:%M")
            
            results[query] = {
                "start_date": start_date,
                "end_date": end_date,
                "duration": time_info.get("duration_str", ""),
                "rate_syntax": time_info.get("rate_syntax", ""),
                "hours_span": time_info.get("hours", 0)
            }
        except Exception as e:
            results[query] = {"error": str(e)}
    
    return results


@app.get("/all-metrics")
def get_all_metrics_endpoint():
    """Debug endpoint to list all available metrics, grouped by type (vLLM, GPU, OpenShift)"""
    all_metrics = get_all_metrics()
    
    # Group metrics by type
    grouped_metrics = {
        "vLLM": {k: v for k, v in all_metrics.items() if "vLLM:" in k},
        "GPU": {k: v for k, v in all_metrics.items() if "GPU:" in k},
        "OpenShift": {k: v for k, v in all_metrics.items() if "OpenShift" in k}
    }
    
    return grouped_metrics


@app.get("/deployment-info")
def get_deployment_info(namespace: str, model: str):
    """Get deployment information for a specific model in a namespace"""
    try:
        headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
        
        # Try to get pod creation date from Kubernetes metrics
        query = f'kube_pod_info{{namespace="{namespace}"}}'
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            headers=headers,
            params={"query": query},
            verify=verify,
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()["data"]["result"]
        
        deployment_date = None
        is_new_deployment = False
        
        if result:
            # Find the most recent pod for this model
            current_time = datetime.now()
            for pod_info in result:
                pod_name = pod_info["metric"].get("pod", "")
                # Check if pod name contains model-related keywords
                if any(keyword in pod_name.lower() for keyword in [model.lower().split("/")[-1], "llama", "instruct"]):
                    # Get pod creation time - this is an approximation since we don't have exact creation time
                    # We'll estimate based on when we first saw metrics for this namespace
                    break
            
            # Check if we have recent vLLM metrics for this namespace (within last 7 days)
            try:
                one_week_ago = int((current_time - timedelta(days=7)).timestamp())
                vllm_query = f'vllm:cache_config_info{{namespace="{namespace}"}}'
                vllm_response = requests.get(
                    f"{PROMETHEUS_URL}/api/v1/query_range",
                    headers=headers,
                    params={
                        "query": vllm_query,
                        "start": one_week_ago,
                        "end": int(current_time.timestamp()),
                        "step": "1h"
                    },
                    verify=verify,
                    timeout=30,
                )
                vllm_response.raise_for_status()
                vllm_result = vllm_response.json()["data"]["result"]
                
                if not vllm_result:
                    # No vLLM metrics in the last week - likely new deployment
                    is_new_deployment = True
                    deployment_date = current_time.strftime("%Y-%m-%d")
                else:
                    # Check if metrics started recently (within last 3 days)
                    three_days_ago = current_time - timedelta(days=3)
                    for series in vllm_result:
                        values = series.get("values", [])
                        if values:
                            first_timestamp = float(values[0][0])
                            first_time = datetime.fromtimestamp(first_timestamp)
                            if first_time > three_days_ago:
                                is_new_deployment = True
                                deployment_date = first_time.strftime("%Y-%m-%d")
                            break
                            
            except Exception as e:
                print(f"Error checking vLLM metrics timeline: {e}")
                # Fallback: assume new deployment if no vLLM metrics
                is_new_deployment = True
                deployment_date = current_time.strftime("%Y-%m-%d")
        else:
            # No pod info found - likely new deployment
            is_new_deployment = True
            deployment_date = datetime.now().strftime("%Y-%m-%d")
        
        message = None
        if is_new_deployment:
            message = (f"New deployment detected in namespace '{namespace}'. "
                      f"Metrics will appear once the model starts processing requests. "
                      f"This typically takes 5-10 minutes after the first inference request.")
        
        return {
            "is_new_deployment": is_new_deployment,
            "deployment_date": deployment_date,
            "message": message,
            "namespace": namespace,
            "model": model
        }
        
    except Exception as e:
        print(f"Error getting deployment info for {namespace}/{model}: {e}")
        # Fallback response
        return {
            "is_new_deployment": True,
            "deployment_date": datetime.now().strftime("%Y-%m-%d"),
            "message": f"Unable to determine deployment status. If this is a new deployment, metrics will appear shortly.",
            "namespace": namespace,
            "model": model
        }

# --- Report Generation ---


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
