#!/usr/bin/env python3
"""
Core LLM Summary Service
Moved from metrics_api.py to separate business logic
"""

import os
import json
import re
from typing import Dict, List, Any, Optional
from datetime import datetime

# Import LLM client
from .llm_client import summarize_with_llm

def generate_llm_summary(question: str, thanos_data: Dict[str, Any], model_id: str, api_key: str, namespace: str) -> str:
    """
    Generate LLM summary from Thanos data
    """
    try:
        print(f"🧠 Generating LLM summary for: {question}")
        
        # Check if we have any successful data
        successful_data = {k: v for k, v in thanos_data.items() if v.get("status") == "success"}
        
        if not successful_data:
            return "❌ No data available to analyze. Please check your query and try again."
        
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
        summary = summarize_with_llm(prompt, model_id, api_key, max_tokens=300)
        
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
        print(f"❌ Error generating LLM summary: {e}")
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


def extract_alert_names_from_thanos_data(thanos_data: Dict[str, Any]) -> List[str]:
    """
    Extract alert names from Thanos data
    """
    alert_names = []
    
    for metric_key, metric_info in thanos_data.items():
        if metric_info.get("status") == "success":
            data = metric_info.get("data", {})
            result = data.get("result", [])
            
            if result and len(result) > 0:
                for series in result:
                    if isinstance(series, dict) and "metric" in series:
                        metric = series["metric"]
                        alert_name = metric.get("alertname", "")
                        if alert_name and alert_name not in alert_names:
                            alert_names.append(alert_name)
    
    return alert_names


def generate_alert_analysis(alert_names: List[str], namespace: str) -> str:
    """
    Generate analysis for specific alerts
    """
    if not alert_names:
        return "✅ No alerts found in the current time range."
    
    try:
        # Build alert analysis prompt
        alert_list = "\n".join([f"- {alert}" for alert in alert_names])
        
        prompt = f"""You are a senior Site Reliability Engineer (SRE) analyzing alerts for namespace: {namespace}.

Active Alerts:
{alert_list}

Provide a BRIEF analysis in 3-4 lines maximum:
- Overall severity level
- One key action needed
- Impact assessment

Keep it concise and actionable."""

        # Use a default model if none specified
        model_id = "gpt-3.5-turbo"  # Default fallback
        api_key = os.getenv("OPENAI_API_KEY", "")
        
        if not api_key:
            return f"⚠️ Alert Analysis: Found {len(alert_names)} active alerts in {namespace}. Please check your API key configuration."
        
        summary = summarize_with_llm(prompt, model_id, api_key, max_tokens=200)
        
        if not summary or summary.strip() == "":
            return f"⚠️ Alert Analysis: Found {len(alert_names)} active alerts in {namespace}. Unable to generate detailed analysis."
        
        cleaned_summary = _clean_llm_summary_string(summary)
        formatted_summary = _format_summary_structure(cleaned_summary)
        return _truncate_summary(formatted_summary)
        
    except Exception as e:
        print(f"❌ Error generating alert analysis: {e}")
        return f"⚠️ Alert Analysis: Found {len(alert_names)} active alerts in {namespace}. Error generating detailed analysis: {str(e)}"


def analyze_unknown_alert_with_llm(alert_name: str, namespace: str) -> str:
    """
    Analyze an unknown alert using LLM
    """
    try:
        prompt = f"""You are a senior Site Reliability Engineer (SRE) analyzing an unknown alert.

Alert Name: {alert_name}
Namespace: {namespace}

Provide a BRIEF analysis in 2-3 lines:
- Likely cause or severity
- One immediate action
- Keep it concise."""

        # Use a default model if none specified
        model_id = "gpt-3.5-turbo"  # Default fallback
        api_key = os.getenv("OPENAI_API_KEY", "")
        
        if not api_key:
            return f"⚠️ Unknown Alert Analysis: Alert '{alert_name}' in {namespace}. Please check your API key configuration."
        
        summary = summarize_with_llm(prompt, model_id, api_key, max_tokens=150)
        
        if not summary or summary.strip() == "":
            return f"⚠️ Unknown Alert Analysis: Alert '{alert_name}' in {namespace}. Unable to generate analysis."
        
        cleaned_summary = _clean_llm_summary_string(summary)
        formatted_summary = _format_summary_structure(cleaned_summary)
        return _truncate_summary(formatted_summary)
        
    except Exception as e:
        print(f"❌ Error analyzing unknown alert: {e}")
        return f"⚠️ Unknown Alert Analysis: Alert '{alert_name}' in {namespace}. Error generating analysis: {str(e)}" 