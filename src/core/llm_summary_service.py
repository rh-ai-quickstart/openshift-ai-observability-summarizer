#!/usr/bin/env python3
"""
Core LLM Summary Service
Moved from metrics_api.py to separate business logic
"""

import os
import json
import re
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from common.pylogger import get_python_logger

# Import LLM client
from .llm_client import summarize_with_llm
from .response_validator import ResponseType

# Initialize structured logger once - other modules should use logging.getLogger(__name__)
get_python_logger()

logger = logging.getLogger(__name__)

from .config import CHAT_SCOPE_FLEET_WIDE, FLEET_WIDE_DISPLAY

def generate_llm_summary(question: str, thanos_data: Dict[str, Any], model_id: str, api_key: str, namespace: str) -> str:
    """
    Generate LLM summary from Thanos data
    """
    try:
        logger.info("Generating LLM summary for: %s", question)
        
        # Check if we have any successful data
        successful_data = {k: v for k, v in thanos_data.items() if v.get("status") == "success"}
        
        if not successful_data:
            return "❌ No data available to analyze. Please check your query and try again."

        question_lower = question.lower()

        # === SPECIAL HANDLING FOR ALERTS ===
        if any(word in question_lower for word in ["alert", "alerts", "firing", "warning", "critical", "problem", "issue"]):
            alert_infos = extract_alert_info_from_thanos_data(thanos_data)
            scope = CHAT_SCOPE_FLEET_WIDE if (namespace == "" or namespace == FLEET_WIDE_DISPLAY) else f"namespace '{namespace}'"
            if alert_infos:
                alert_analysis = generate_alert_analysis_with_llm(alert_infos, namespace, model_id=model_id, api_key=api_key)
                return f"🚨 **TOTAL OF {len(alert_infos)} ALERT(S) FOUND IN {scope.upper()}**\n\n{alert_analysis}"
            else:
                return f"✅ No alerts currently firing in {scope}. All systems appear to be operating normally."

        # === REGULAR METRIC HANDLING ===
        # Build context for LLM
        context_parts = []
        
        for metric_key, metric_info in successful_data.items():
            promql = metric_info.get("promql", "")
            data = metric_info.get("data", {})
            
            if not data or not data.get("result"):
                continue
            
            # Extract the most recent value
            result = data["result"]
            if result and len(result) > 0:
                # Get the latest data point
                latest_point = result[0] if isinstance(result, list) else result
                
                if isinstance(latest_point, dict) and "values" in latest_point:
                    values = latest_point["values"]
                    if values and len(values) > 0:
                        # Get the most recent value
                        latest_value = values[-1][1] if len(values[-1]) > 1 else "N/A"
                        context_parts.append(f"{promql}: {latest_value}")
        
        if not context_parts:
            return "❌ No valid data points found. Please check your query and try again."
        
        # Build the prompt
        context = "\n".join(context_parts)
        
        prompt = f"""You are a senior Site Reliability Engineer (SRE) analyzing metrics for namespace: {namespace}.

Question: {question}

Metrics Data:
{context}

Provide ONLY a structured summary in this exact format (no additional text or instructions):
Current value: [value]
Meaning: [brief explanation]
Immediate concern: [None or specific concern]
Key insight: [one key observation]

Do not include any formatting instructions, notes, or additional commentary."""

        # Generate summary with LLM
        # Use GENERAL_CHAT validation for free-form summaries
        summary = summarize_with_llm(
            prompt,
            model_id,
            ResponseType.GENERAL_CHAT,
            api_key=api_key,
            max_tokens=300,
        )
        
        if not summary or summary.strip() == "":
            return "❌ Failed to generate summary. Please try again."
        
        # Clean up the summary
        cleaned_summary = _clean_llm_summary_string(summary)
        
        # Format the summary with proper structure
        formatted_summary = _format_summary_structure(cleaned_summary)
        
        # Ensure summary is not too long (max 5 lines)
        formatted_summary = _truncate_summary(formatted_summary)
        
        return formatted_summary
        
    except Exception as e:
        logger.error("Error generating LLM summary: %s", e)
        return f"❌ Error generating summary: {str(e)}"


def _clean_llm_summary_string(summary: str) -> str:
    """
    Clean and format LLM summary string
    """
    if not summary:
        return ""
    
    # Remove common LLM artifacts
    summary = summary.strip()
    
    # Remove markdown code blocks
    summary = re.sub(r'```.*?```', '', summary, flags=re.DOTALL)
    
    # Remove formatting instructions and meta-comments
    summary = re.sub(r'Please format.*?\.', '', summary, flags=re.DOTALL)
    summary = re.sub(r'🔍 Scope:.*?$', '', summary, flags=re.MULTILINE)
    summary = re.sub(r'Do not include.*?\.', '', summary, flags=re.DOTALL)
    summary = re.sub(r'Keep.*?\.', '', summary, flags=re.DOTALL)
    
    # Remove any remaining meta-comments that might be attached to sections
    summary = re.sub(r'Please format.*?$', '', summary, flags=re.MULTILINE)
    summary = re.sub(r'🔍 Scope:.*?$', '', summary, flags=re.MULTILINE)
    summary = re.sub(r'Note:.*?$', '', summary, flags=re.MULTILINE)
    summary = re.sub(r'\(Note:.*?\)', '', summary, flags=re.DOTALL)
    
    # Remove extra whitespace
    summary = re.sub(r'\n\s*\n', '\n\n', summary)
    
    # Remove leading/trailing whitespace
    summary = summary.strip()
    
    return summary


def _truncate_summary(summary: str) -> str:
    """
    Truncate summary to maximum 5 lines
    """
    if not summary:
        return ""
    
    # Split into lines and take first 5 non-empty lines
    lines = [line.strip() for line in summary.split('\n') if line.strip()]
    truncated_lines = lines[:5]
    
    return '\n'.join(truncated_lines)


def _format_summary_structure(summary: str) -> str:
    """
    Format summary with proper line breaks and structure
    """
    if not summary:
        return ""
    
    # Check if summary contains structured format
    if 'Current value:' in summary and 'Meaning:' in summary:
        # Extract and format structured parts
        formatted_parts = []
        
        # Extract Current value
        if 'Current value:' in summary:
            current_start = summary.find('Current value:') + len('Current value:')
            meaning_start = summary.find('Meaning:')
            if meaning_start > current_start:
                current_value = summary[current_start:meaning_start].strip()
                formatted_parts.append(f"Current value: {current_value}")
        
        # Extract Meaning
        if 'Meaning:' in summary:
            meaning_start = summary.find('Meaning:') + len('Meaning:')
            concern_start = summary.find('Immediate concern:')
            if concern_start > meaning_start:
                meaning_text = summary[meaning_start:concern_start].strip()
                formatted_parts.append(f"Meaning: {meaning_text}")
            else:
                # If no Immediate concern, take everything after Meaning
                meaning_text = summary[meaning_start:].strip()
                formatted_parts.append(f"Meaning: {meaning_text}")
        
        # Extract Immediate concern
        if 'Immediate concern:' in summary:
            concern_start = summary.find('Immediate concern:') + len('Immediate concern:')
            insight_start = summary.find('Key insight:')
            if insight_start > concern_start:
                concern_text = summary[concern_start:insight_start].strip()
                formatted_parts.append(f"Immediate concern: {concern_text}")
            else:
                # If no Key insight, take everything after Immediate concern
                concern_text = summary[concern_start:].strip()
                formatted_parts.append(f"Immediate concern: {concern_text}")
        
        # Extract Key insight
        if 'Key insight:' in summary:
            insight_start = summary.find('Key insight:') + len('Key insight:')
            insight_text = summary[insight_start:].strip()
            # Clean up any unwanted text that might be attached
            insight_text = re.sub(r'Please format.*?$', '', insight_text, flags=re.MULTILINE)
            insight_text = re.sub(r'🔍 Scope:.*?$', '', insight_text, flags=re.MULTILINE)
            insight_text = re.sub(r'Note:.*?$', '', insight_text, flags=re.MULTILINE)
            insight_text = insight_text.strip()
            formatted_parts.append(f"Key insight: {insight_text}")
        
        if formatted_parts:
            return '\n\n'.join(formatted_parts)
    
    # Fallback: return original summary with basic line breaks
    return summary.replace('. ', '.\n\n').replace(': ', ':\n\n')

 

def generate_alert_analysis_with_llm(alert_infos: List[Dict[str, str]], namespace: str, model_id: Optional[str] = None, api_key: Optional[str] = None) -> str:
    """
    Generate analysis for specific alerts
    """
    if not alert_infos:
        return "✅ No alerts found in the current time range."
    
    try:
        # Build alert analysis prompt
        def _format_alert(info: Dict[str, str]) -> str:
            name = info.get("alertname", "UnknownAlert")
            sev = info.get("severity", "unknown")
            ns = info.get("namespace", "")
            ns_part = f", namespace: {ns}" if ns else ""
            return f"- {name}, severity: {sev}{ns_part}"

        # Sort alerts by severity before formatting the list
        sorted_alert_infos = sort_alert_infos_by_severity(alert_infos)
        alert_list = "\n".join([_format_alert(info) for info in sorted_alert_infos])
        ns_info = f"namespace: {namespace}" if namespace != "FLEET_WIDE" else "FLEET_WIDE"
        prompt = f"""You are a senior Site Reliability Engineer (SRE) analyzing alerts for {ns_info}.

Firing Alerts:
{alert_list}

For each alert, provide an analysis with 5-7 lines maximum:
- **Severity:** Severity of the alert
- **Impact:** Impact assessment
- **Action:** One key action needed to resolve the alert
- **Troubleshooting commands:** Any commands needed to investigate the alert.
- **Namespace:** Namespace of the alert if available.

In your response, use the following format as the title of each alert section:
### [Alert Name]

Keep your response concise and do NOT add any additional notes or commentary.
"""

        summary = summarize_with_llm(
            prompt,
            model_id,
            ResponseType.GENERAL_CHAT,
            api_key=api_key,
            max_tokens=2000,
        )
        
        if not summary or summary.strip() == "":
            return f"⚠️ Alert Analysis: Found {len(alert_infos)} active alerts in {namespace}. Unable to generate detailed analysis."
        
        return clean_alert_analysis_output(summary, sorted_alert_infos)
        
    except Exception as e:
        logger.error("Error generating alert analysis: %s", e)
        return f"⚠️ Alert Analysis: Found {len(alert_infos)} active alerts in {namespace}. Error generating detailed analysis: {str(e)}"

    

def extract_alert_info_from_thanos_data(thanos_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Extract structured alert information from Thanos data.
    Returns a list of dicts with keys: 'alertname', 'namespace', 'severity'.
    Deduplicates by alert name and takes the first occurrence.
    """
    alert_infos: List[Dict[str, str]] = []
    seen_alert_names = set()

    for metric_key, metric_info in thanos_data.items():
        if metric_info.get("status") == "success":
            data = metric_info.get("data", {})
            result = data.get("result", [])

            if result and len(result) > 0:
                for series in result:
                    if isinstance(series, dict) and "metric" in series:
                        metric = series["metric"]
                        alert_name = metric.get("alertname")
                        if not alert_name or alert_name in seen_alert_names:
                            continue
                        severity = metric.get("severity", "unknown")
                        namespace_val = metric.get("namespace", "")
                        alert_infos.append(
                            {
                                "alertname": alert_name,
                                "namespace": namespace_val,
                                "severity": severity,
                            }
                        )
                        seen_alert_names.add(alert_name)

    return alert_infos


def sort_alert_infos_by_severity(alert_infos: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Sort a list of alert info dicts by severity in the order:
    critical, warning, info, low/none (unknown also last).

    Each alert info dict is expected to have a 'severity' field.
    Unknown severities are treated as lowest priority.
    """
    def severity_rank(severity_value: Optional[str]) -> int:
        value = (severity_value or "").strip().lower()
        if value == "critical":
            return 0
        if value == "warning":
            return 1
        if value == "info":
            return 2
        if value in ("low", "none"):
            return 3
        return 3  # Unknowns go last

    # Stable sort; secondary key by alert name for deterministic output
    return sorted(
        alert_infos,
        key=lambda info: (
            severity_rank(info.get("severity")),
            (info.get("alertname") or "").lower(),
        ),
    )


def clean_alert_analysis_output(raw_output: str, alert_infos: List[Dict[str, str]]) -> str:
    """
    Post-process the LLM output for alert analysis with two goals:
    1) If all alerts have a section, trim everything after the end of the last
       alert section.
    2) Otherwise, remove any trailing content starting at the first detected
       duplicate alert section (best-effort cleanup).

    Alert sections are identified primarily by headers following the format
    "### [Alert Name]" as instructed in the prompt. For robustness,
    list items that include the alert name are also considered.
    """
    if not raw_output:
        return raw_output

    text = raw_output
    # Prepare alert name patterns for robust matching
    alert_names = [info.get("alertname", "") for info in alert_infos if info.get("alertname")]
    if not alert_names:
        return text

    # Normalize to avoid Unicode punctuation issues
    try:
        import unicodedata
        text = unicodedata.normalize("NFKC", text)
        alert_names = [unicodedata.normalize("NFKC", name) for name in alert_names]
    except Exception:
        pass

    # Line-based parsing for deterministic behavior
    lines = text.splitlines(keepends=True)
    alert_names_lower_list = [n.lower() for n in alert_names]
    alert_names_lower = set(alert_names_lower_list)

    # Collect header line indices for alert sections and detect duplicates
    header_indices: List[int] = []
    header_name_by_index: Dict[int, str] = {}
    seen_headers: set = set()

    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("### "):
            header_text = stripped[4:].strip()
            header_text_lower = header_text.lower()
            # Normalize header core up to a colon if present
            header_core = header_text_lower.split(":", 1)[0].strip()
            # Match if header starts with an alert name or equals it
            matched_name = None
            if header_core in alert_names_lower:
                matched_name = header_core
            else:
                for name in alert_names_lower_list:
                    if header_text_lower.startswith(name):
                        matched_name = name
                        break
            if matched_name is not None:
                if matched_name in seen_headers:
                    # Duplicate alert section detected -> truncate before this header
                    return "".join(lines[:idx]).rstrip()
                seen_headers.add(matched_name)
                header_indices.append(idx)
                header_name_by_index[idx] = matched_name

    # Trim after the expected last alert section if present
    last_alert_name = None
    for info in alert_infos[::-1]:
        candidate = (info.get("alertname") or "").strip().lower()
        if candidate:
            last_alert_name = candidate
            break

    if last_alert_name is not None:
        # Find the header index for the last alert
        last_indices = [i for i, name in header_name_by_index.items() if name == last_alert_name]
        if last_indices:
            last_idx = min(last_indices)  # first occurrence of that header
            # Find end of section: next header, or first non-section line
            next_header_idx = None
            end_idx = None
            for j in range(last_idx + 1, len(lines)):
                ls = lines[j].lstrip()
                if ls.startswith("### "):
                    next_header_idx = j
                    end_idx = j
                    break
                # Allow typical section content lines: bullets, code fences, or blank
                if not (ls.startswith("- ") or ls.startswith("* ") or ls.startswith("```") or ls.strip() == ""):
                    end_idx = j
                    break
            if end_idx is None:
                end_idx = len(lines)
            return "".join(lines[:end_idx]).rstrip()

    return text

