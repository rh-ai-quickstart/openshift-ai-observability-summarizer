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
from .response_validator import ResponseType

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

        question_lower = question.lower()

        # === SPECIAL HANDLING FOR ALERTS ===
        if any(word in question_lower for word in ["alert", "alerts", "firing", "warning", "critical", "problem", "issue"]):
            alert_names = extract_alert_names_from_thanos_data(thanos_data)
            scope = "fleet-wide" if namespace == "" else f"namespace '{namespace}'"
            if alert_names:
                alert_analysis = generate_alert_analysis(alert_names, namespace)
                return f"🚨 **ALERT ANALYSIS FOR {scope.upper()}**\n\n{alert_analysis}"
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

def analyze_unknown_alert_with_llm(alert_name: str, namespace: str) -> str:
    """
    Use intelligent analysis for unknown alerts based on naming patterns
    """
    severity = "🔴 WARNING"  # Default to warning
    
    # Simple heuristics based on alert name
    if any(word in alert_name.lower() for word in ["down", "failed", "error", "critical"]):
        severity = "🔴 CRITICAL"
    elif any(word in alert_name.lower() for word in ["high", "slow", "latency", "pending"]):
        severity = "🟡 WARNING"
    elif any(word in alert_name.lower() for word in ["info", "recommendation", "deprecated"]):
        severity = "🟡 INFO"
    
    analysis = f"### {severity} {alert_name}\n"
    
    # Provide intelligent analysis based on naming patterns
    if "api" in alert_name.lower():
        analysis += "**What it means:** API-related issue that may affect cluster functionality\n"
        analysis += "**Investigation:** Check API server logs and endpoint availability\n"
        analysis += "**Action required:** Verify API server health and network connectivity\n"
        analysis += "**Troubleshooting commands:**\n"
        analysis += "```\noc get apiserver\noc logs -n openshift-kube-apiserver apiserver-xxx\n```"
    elif "node" in alert_name.lower() or "kubelet" in alert_name.lower():
        analysis += "**What it means:** Worker node or kubelet issue affecting workload scheduling\n"
        analysis += "**Investigation:** Check node status and kubelet logs\n"
        analysis += "**Action required:** Investigate node health and resource availability\n"
        analysis += "**Troubleshooting commands:**\n"
        analysis += "```\noc get nodes\noc describe node <node-name>\n```"
    elif "pod" in alert_name.lower() or "container" in alert_name.lower():
        analysis += "**What it means:** Pod or container issue affecting application workloads\n"
        analysis += "**Investigation:** Check pod status and logs\n"
        analysis += "**Action required:** Investigate application health and resource constraints\n"
        analysis += "**Troubleshooting commands:**\n"
        if namespace:
            analysis += f"```\noc get pods -n {namespace}\noc logs -n {namespace} <pod-name>\n```"
        else:
            analysis += "```\noc get pods -A\noc logs <pod-name> -n <namespace>\n```"
    else:
        # Generic analysis for completely unknown alerts
        analysis += f"**What it means:** Alert '{alert_name}' requires investigation\n"
        analysis += "**Investigation:** Review alert definition and current cluster state\n"
        analysis += "**Action required:** Check related OpenShift components and logs\n"
        analysis += "**Troubleshooting commands:**\n"
        analysis += f"```\noc get prometheusrule -A | grep -i {alert_name.lower()}\n```"
    
    return analysis


def generate_alert_analysis(alert_names: List[str], namespace: str) -> str:
    """
    Generate detailed, actionable analysis for SRE and MLOps teams
    """
    analysis_parts = []
    
    # Alert knowledge base with detailed troubleshooting
    alert_kb = {
        "VLLMDummyServiceInfo": {
            "severity": "🟡 INFO",
            "meaning": "Test alert for vLLM service monitoring - indicates the model is processing requests",
            "investigation": "Check vLLM service logs and request metrics",
            "action": "This is typically a test alert. Verify if this should be disabled in production.",
            "commands": [
                f"oc logs -n {namespace} -l app=llama-3-2-3b-instruct",
                f"oc get pods -n {namespace} -l app=llama-3-2-3b-instruct"
            ]
        },
        "GPUOperatorNodeDeploymentDriverFailed": {
            "severity": "🔴 WARNING", 
            "meaning": "NVIDIA GPU driver deployment failed on worker nodes",
            "investigation": "Check GPU operator pods and node status for driver installation issues",
            "action": "Investigate GPU operator logs, verify node labels, check for driver compatibility issues",
            "commands": [
                "oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true",
                "oc logs -n nvidia-gpu-operator -l app=gpu-operator",
                "oc get pods -n nvidia-gpu-operator"
            ]
        },
        "GPUOperatorNodeDeploymentFailed": {
            "severity": "🔴 WARNING",
            "meaning": "NVIDIA GPU operator failed to deploy components on nodes", 
            "investigation": "Check GPU operator deployment status and node compatibility",
            "action": "Review GPU operator configuration, verify node selectors, check resource constraints",
            "commands": [
                "oc describe clusterpolicy gpu-cluster-policy",
                "oc get nodes --show-labels | grep nvidia",
                "oc logs -n nvidia-gpu-operator deployment/gpu-operator"
            ]
        },
        "GPUOperatorReconciliationFailed": {
            "severity": "🔴 WARNING",
            "meaning": "GPU operator failed to reconcile desired state with actual cluster state",
            "investigation": "Check GPU operator controller logs for reconciliation errors",
            "action": "Restart GPU operator, verify CRD status, check for resource conflicts",
            "commands": [
                "oc get clusterpolicy -o yaml",
                "oc logs -n nvidia-gpu-operator -l control-plane=controller-manager",
                "oc delete pods -n nvidia-gpu-operator -l app=gpu-operator"
            ]
        },
        "ClusterMonitoringOperatorDeprecatedConfig": {
            "severity": "🟡 INFO",
            "meaning": "Cluster monitoring is using deprecated configuration options",
            "investigation": "Review cluster-monitoring-config ConfigMap for deprecated fields",
            "action": "Update monitoring configuration to use current API versions before next upgrade",
            "commands": [
                "oc get configmap cluster-monitoring-config -n openshift-monitoring -o yaml",
                "oc get clusterversion"
            ]
        },
        "ClusterNotUpgradeable": {
            "severity": "🟡 INFO", 
            "meaning": "Cluster has conditions preventing upgrade (usually due to deprecated APIs)",
            "investigation": "Check cluster version status for upgrade blocking conditions",
            "action": "Review upgrade blockers, update deprecated API usage, resolve blocking conditions",
            "commands": [
                "oc get clusterversion -o yaml",
                "oc adm upgrade",
                "oc get clusteroperators"
            ]
        },
        "InsightsRecommendationActive": {
            "severity": "🟡 INFO",
            "meaning": "Red Hat Insights has recommendations for cluster optimization",
            "investigation": "Review insights recommendations in OpenShift console or Red Hat Hybrid Cloud Console",
            "action": "Follow insights recommendations to improve cluster security, performance, or reliability",
            "commands": [
                "oc logs -n openshift-insights deployment/insights-operator",
                "echo 'Visit: https://console.redhat.com/openshift/insights/advisor/'"
            ]
        }
    }
    
    analysis_parts.append(f"## Alert Summary: {len(alert_names)} Active Alert(s)")
    analysis_parts.append("")
    
    for alert_name in alert_names:
        if alert_name in alert_kb:
            alert = alert_kb[alert_name]
            analysis_parts.append(f"### {alert['severity']} {alert_name}")
            analysis_parts.append(f"**Issue:** {alert['meaning']}")
            analysis_parts.append(f"**Action:** {alert['action']}")
            analysis_parts.append("**Commands:**")
            for cmd in alert['commands']:
                analysis_parts.append(f"```\n{cmd}\n```")
            analysis_parts.append("")
        else:
            # Use LLM to analyze unknown alerts
            llm_analysis = analyze_unknown_alert_with_llm(alert_name, namespace)
            analysis_parts.append(llm_analysis)
            analysis_parts.append("")
    
    analysis_parts.append("### Next Steps")
    analysis_parts.append("1. Run the diagnostic commands above")
    analysis_parts.append("2. Check logs and recent changes")
    analysis_parts.append("3. Document any fixes in your runbooks")
    
    return "\n".join(analysis_parts)

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


