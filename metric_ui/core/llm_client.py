"""
LLM Client and Prompt Building Functions

Contains all business logic for interacting with LLMs (local and external),
building prompts, and processing LLM responses.
"""

import re
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime

from .config import MODEL_CONFIG, LLM_API_TOKEN, LLAMA_STACK_URL, VERIFY_SSL


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
    if is_external:
        if provider == "google":
            # Google Gemini response format
            if "candidates" not in response_json or not response_json["candidates"]:
                raise ValueError(f"Invalid {provider} response format")

            candidate = response_json["candidates"][0]
            if "content" not in candidate or "parts" not in candidate["content"]:
                raise ValueError(f"Invalid {provider} response structure")

            parts = candidate["content"]["parts"]
            if not parts or "text" not in parts[0]:
                raise ValueError(f"Invalid {provider} response content")

            return parts[0]["text"].strip()
        else:
            # OpenAI and other providers using "choices" format
            if "choices" not in response_json or not response_json["choices"]:
                raise ValueError(f"Invalid {provider} response format")

            return response_json["choices"][0]["message"]["content"].strip()
    else:
        # Local model response format
        if "choices" not in response_json or not response_json["choices"]:
            raise ValueError(f"Invalid {provider} response format")
        return response_json["choices"][0]["text"].strip()


def _clean_llm_summary_string(text: str) -> str:
    """Remove non-printable ASCII characters and normalize whitespace"""
    # Remove any non-printable ASCII characters (except common whitespace like space, tab, newline)
    cleaned_text = re.sub(r"[^\x20-\x7E\n\t]", "", text)
    # Replace multiple spaces/newlines/tabs with single spaces, then strip leading/trailing whitespace
    return re.sub(r"\s+", " ", cleaned_text).strip()


def summarize_with_llm(
    prompt: str,
    summarize_model_id: str,
    api_key: Optional[str] = None,
    messages: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Summarize content using an LLM (local or external).
    
    Args:
        prompt: The content to summarize
        summarize_model_id: Model identifier from MODEL_CONFIG
        api_key: API key for external models (optional for local models)
        messages: Previous conversation messages (optional)
        
    Returns:
        LLM-generated summary text
    """
    headers = {"Content-Type": "application/json"}

    # Get model configuration
    model_info = MODEL_CONFIG.get(summarize_model_id, {})
    is_external = model_info.get("external", False)

    # Building LLM messages array
    llm_messages = []
    if messages:
        llm_messages.extend(messages)
    # Ensure the new prompt is always added as the last user message
    llm_messages.append({"role": "user", "content": prompt})

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

        # Provider-specific authentication and payload
        if provider == "google":
            # Google Gemini API format
            headers["x-goog-api-key"] = api_key

            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
            }
        else:
            # OpenAI and compatible APIs
            headers["Authorization"] = f"Bearer {api_key}"

            payload = {
                "model": model_name,
                "messages": llm_messages,
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

        # Combine all messages into a single prompt
        prompt_text = ""
        if messages:
            for msg in messages:
                prompt_text += f"{msg['role']}: {msg['content']}\n"
        prompt_text += prompt  # Add the current prompt

        payload = {
            "model": summarize_model_id,
            "prompt": prompt_text,
            "temperature": 0.5,
            "max_tokens": 1000,
        }

        response_json = _make_api_request(
            f"{LLAMA_STACK_URL}/completions", headers, payload, verify_ssl=VERIFY_SSL
        )

        return _validate_and_extract_response(
            response_json, is_external=False, provider="LLM"
        )


def build_chat_prompt(user_question: str, metrics_summary: str) -> str:
    """Build a chat prompt combining user question with metrics context"""
    prompt = f"""
You are an expert AI model performance analyst. I have some vLLM metrics data and need help interpreting it.

Here's the metrics summary:
{metrics_summary}

User question: {user_question}

Please provide a helpful analysis focusing on:
1. Directly answering the user's question based on the metrics
2. Any performance insights or recommendations
3. Potential issues or optimizations to consider

Keep your response focused and actionable.
"""
    return prompt.strip()


def build_prompt(metric_dfs, model_name: str) -> str:
    """Build analysis prompt for vLLM metrics data"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    prompt = f"""
You are an expert AI model performance analyst. Please analyze the following vLLM metrics for model '{model_name}' and provide a comprehensive summary.

Current Analysis Time: {current_time}

METRICS DATA:
"""
    
    for metric_name, df in metric_dfs.items():
        if df is not None and not df.empty:
            prompt += f"\n=== {metric_name.upper()} ===\n"
            # Add DataFrame summary
            prompt += f"Data points: {len(df)}\n"
            if 'value' in df.columns:
                prompt += f"Latest value: {df['value'].iloc[-1] if len(df) > 0 else 'N/A'}\n"
                prompt += f"Average: {df['value'].mean():.2f}\n"
                prompt += f"Min: {df['value'].min():.2f}, Max: {df['value'].max():.2f}\n"
    
    prompt += """

ANALYSIS REQUIREMENTS:
1. **Performance Summary**: Overall health and performance status
2. **Key Metrics Analysis**: Interpret the most important metrics
3. **Trends and Patterns**: Identify any concerning trends
4. **Recommendations**: Actionable suggestions for optimization
5. **Alerting**: Any metrics that warrant immediate attention

Please provide a clear, structured analysis that would be useful for both technical teams and stakeholders.
"""
    
    return prompt.strip()


def build_openshift_prompt(
    metric_dfs, metric_category, namespace=None, scope_description=None
):
    """
    Build prompt for OpenShift metrics analysis
    
    Note: This function depends on describe_trend() and detect_anomalies() 
    which will be moved to core/metrics.py later.
    """
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
        # TODO: Import these functions from core.metrics when available
        # trend = describe_trend(df)
        # anomaly = detect_anomalies(df, label)
        trend = "stable"  # Placeholder
        anomaly = "normal"  # Placeholder
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


def build_openshift_chat_prompt(
    question: str,
    metrics_context: str,
    time_range_info: Optional[Dict[str, Any]] = None,
    chat_scope: str = "namespace_specific",
    target_namespace: str = None,
) -> str:
    """Build specialized prompt for OpenShift/Kubernetes queries"""
    # Build scope context
    if chat_scope == "fleet_wide":
        scope_context = "You are analyzing **fleet-wide OpenShift/Kubernetes metrics across ALL namespaces**.\n\n"
    elif target_namespace:
        scope_context = f"You are analyzing OpenShift/Kubernetes metrics for namespace: **{target_namespace}**.\n\n"
    else:
        scope_context = "You are analyzing OpenShift/Kubernetes metrics.\n\n"
    
    # Build time range context
    time_context = ""
    time_range_syntax = "5m"  # default
    if time_range_info:
        time_duration = time_range_info.get("duration_str", "")
        time_range_syntax = time_range_info.get("rate_syntax", "5m")
        time_context = f"""**🕐 TIME RANGE CONTEXT:**
The user asked about: **{time_duration}**
Use time range syntax `[{time_range_syntax}]` in PromQL queries where appropriate.

"""

    # Common OpenShift metrics for reference
    common_metrics = """**📊 Comprehensive OpenShift/Kubernetes Metrics:**
- Pods: `sum(kube_pod_status_phase{phase="Running"})`, `sum(kube_pod_status_phase{phase="Failed"})`
- Deployments: `sum(kube_deployment_status_replicas_ready)`, `sum(kube_deployment_spec_replicas)`
- Services: `sum(kube_service_info)`, `sum(kube_endpoint_address_available)`
- Jobs: `sum(kube_job_status_active)`, `sum(kube_job_status_succeeded)`, `sum(kube_job_status_failed)`
- Storage: `sum(kube_persistentvolume_info)`, `sum(kube_persistentvolumeclaim_info)`
- Config: `sum(kube_configmap_info)`, `sum(kube_secret_info)`
- Nodes: `sum(kube_node_info)`, `sum(kube_node_status_condition{condition="Ready"})`
- CPU: `100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[5m])) * 100)`
- Memory: `100 - (sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes) * 100)`
- Containers: `count(count by (image)(container_spec_image))`, `sum(kube_pod_container_status_running)`
- Workloads: `sum(kube_daemonset_status_number_ready)`, `sum(kube_statefulset_status_replicas_ready)`

"""

    return f"""
You are a Senior Site Reliability Engineer (SRE) expert in OpenShift/Kubernetes observability. Your task is to analyze the provided metrics and answer the user's question with precise, actionable insights.

{scope_context}{time_context}{common_metrics}

**Current Metrics Status:**
{metrics_context.strip()}

**Your Task:**
Provide a concise, technical response that directly answers the user's question based on the metrics data provided.

**JSON Output Schema:**
- "promqls" (list of strings, optional): 1-2 relevant PromQL queries that support your answer. Use correct OpenShift/Kubernetes metric names and proper time ranges [{time_range_syntax}].
- "summary" (string, required): A direct, technical answer (2-3 sentences) explaining the current state and any recommendations.

**Rules:**
- Use double quotes for all JSON keys and string values
- No trailing commas
- Base your answer ONLY on the provided metrics data
- If no data is available, state that clearly
- For pod counts, use `kube_pod_status_phase` metrics
- For cluster-wide queries, avoid namespace filters
- Be specific with numbers when available

**User Question:** {question}
""".strip()


def build_flexible_llm_prompt(
    question: str,
    model_name: str,
    metrics_context: str,
    generated_tokens_sum: Optional[float] = None,
    selected_namespace: str = None,
    alerts_context: str = "",
    time_range_info: Optional[Dict[str, Any]] = None,
    chat_scope: str = "namespace_specific",
) -> str:
    """
    Build flexible LLM prompt for various metric analysis scenarios
    
    Note: This function depends on get_vllm_metrics() and add_namespace_filter()
    which will be moved to core/metrics.py and core/utils.py later.
    """
    # Safely handle generated_tokens_sum formatting
    summary_tokens_generated = ""
    if generated_tokens_sum is not None:
        try:
            # Convert to float if it's a string
            if isinstance(generated_tokens_sum, str):
                tokens_value = float(generated_tokens_sum)
            else:
                tokens_value = float(generated_tokens_sum)
            summary_tokens_generated = f"A total of {tokens_value:.2f} tokens were generated across all models and namespaces."
        except (ValueError, TypeError):
            summary_tokens_generated = f"Token generation data: {generated_tokens_sum}"

    # Build scope context
    if chat_scope == "fleet_wide":
        namespace_context = f"You are analyzing **fleet-wide metrics across ALL namespaces** for model **{model_name}**.\n\n"
    elif selected_namespace:
        namespace_context = f"You are currently focused on the namespace: **{selected_namespace}** and model **{model_name}**.\n\n"
    else:
        namespace_context = ""
    
    # Build time range context for the LLM
    time_context = ""
    time_range_syntax = "5m"  # default
    if time_range_info:
        time_duration = time_range_info.get("duration_str", "")
        time_range_syntax = time_range_info.get("rate_syntax", "5m")
        time_context = f"""**🕐 CRITICAL TIME RANGE REQUIREMENTS:**
The user asked about: **{time_duration}**

**MANDATORY PromQL Syntax Rules:**
✅ ALWAYS add time range `[{time_range_syntax}]` to metrics that need it
✅ For P95/P99 latency: `histogram_quantile(0.95, sum(rate(vllm:e2e_request_latency_seconds_bucket[{time_range_syntax}])) by (le))`  
✅ For rates: `rate(vllm:request_prompt_tokens_created[{time_range_syntax}])`
✅ For averages over time: `avg_over_time(vllm:num_requests_running[{time_range_syntax}])`
❌ NEVER use: `vllm:metric_name{{namespace="...", }}` (trailing comma)
❌ NEVER use: `vllm:metric_name{{namespace="..."}}` (missing time range)

"""

    # TODO: Import get_vllm_metrics() and add_namespace_filter() from core modules when available
    # For now, use placeholder metrics list
    metrics_list = "- Placeholder metrics list (to be replaced with actual metrics from core.metrics)"

    # The task is to analyze and connect the dots.
    return f"""
You are a world-class Senior Production Engineer, an expert in observability and root cause analysis. Your primary skill is correlating different types of telemetry data (metrics, alerts, logs, traces) to form a complete picture of system health and answer user questions with deep, actionable insights.

{namespace_context}{time_context}**Complete Observability Context:**
# Available Metrics:
# {metrics_list}

# Current Metric Status:
{metrics_context.strip()}

# Current Alert Status:
# {alerts_context.strip()}

{summary_tokens_generated.strip()}

**Your Task:**
Analyze the complete operational context provided above to give a concise, insightful, and actionable answer to the user's question.
- **Correlate data:** If a metric is abnormal, check if any alerts or other data could explain why.
- **Handling Insufficient Data:** If the context does not contain the information needed to answer the user's question, you MUST state that clearly and directly in the summary. Do not try to guess or hallucinate an answer.
- **Respond in JSON:** Your entire response must be a single, complete JSON object.

**JSON Output Schema:**
- "promqls" (list of strings, optional): A list of 1-2 (not more) relevant PromQL query strings that support your summary. You MUST use valid PromQL queries with proper time ranges [{time_range_syntax}]. Do not use the friendly name. Include alert query or metric query or both based on the context.
- "summary" (string, required): A thoughtful paragraph (2-4 sentences) that directly answers the user's question. Explain the meaning of the metric value or alert, what it implies for the system, and recommend an action if needed. Connect different pieces of context where possible. Sound like a senior engineer.

# Rules for JSON output:
# - Use double quotes for all keys and string values.
# - No trailing commas.
# - No line breaks within string values.
# - No comments.
# - Use only the context provided.
# - If appropriate, briefly recommend one action or area to investigate.
# - The summary field in the JSON should contain a single plain-text paragraph
# - Do NOT restate the question.
# - Do NOT copy the example, only learn how to answer the question.
# - If the context indicates there are no alerts, the 'summary' MUST explicitly state that no alerts were found.
# - MANDATORY: All PromQL queries MUST include proper time range syntax like [{time_range_syntax}]

**User Question:** {question}
**Response:**""".strip() 