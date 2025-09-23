"""
Alert handling and Prometheus alert integration functions.

This module contains functions for fetching and processing alerts from
Prometheus/Thanos, including alert rule definitions and active alert data.
All functions are framework-agnostic and focused on alert data retrieval.
"""

import requests
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from common.pylogger import get_python_logger
from .metrics import choose_prometheus_step

from .config import PROMETHEUS_URL, THANOS_TOKEN, VERIFY_SSL

# Initialize structured logger once - other modules should use logging.getLogger(__name__)
get_python_logger()

logger = logging.getLogger(__name__)


def fetch_alerts_from_prometheus(
    start_ts: int, end_ts: int, namespace: Optional[str] = None
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Fetches active alerts for a time range and enriches them with their
    full rule definitions for maximum context.
    
    Args:
        start_ts: Start timestamp (Unix epoch)
        end_ts: End timestamp (Unix epoch)
        namespace: Optional namespace filter
        
    Returns:
        Tuple of (promql_query, alerts_data_list)
    """
    headers = {"Authorization": f"Bearer {THANOS_TOKEN}"}
    promql_query = f'ALERTS{{namespace="{namespace}"}}' if namespace else "ALERTS"
    step = choose_prometheus_step(start_ts, end_ts)
    params = {
        "query": promql_query,
        "start": start_ts,
        "end": end_ts,
        "step": step,
    }
    logger.debug("Fetching Prometheus alerts, query: %s, start: %s, end: %s: step: %s", promql_query, start_ts, end_ts, step)

    try:
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            headers=headers,
            params=params,
            verify=VERIFY_SSL,
            timeout=30,  # Add timeout
        )
        response.raise_for_status()
        result = response.json()["data"]["result"]
    except requests.exceptions.ConnectionError as e:
        logger.warning("Prometheus connection error for alerts query '%s': %s", promql_query, e)
        return promql_query, []  # Return empty alerts on connection error
    except requests.exceptions.Timeout as e:
        logger.warning("Prometheus timeout for alerts query '%s': %s", promql_query, e)
        return promql_query, []  # Return empty alerts on timeout
    except requests.exceptions.RequestException as e:
        logger.warning("Prometheus request error for alerts query '%s': %s", promql_query, e)
        return promql_query, []  # Return empty alerts on other request errors

    alerts_data = []
    for series in result:
        alertname = series["metric"].get("alertname")
        severity = series["metric"].get("severity")
        alertstate = series["metric"].get("alertstate")  # "firing" or "inactive"
        for_duration = series["metric"].get("for")
        labels = series["metric"]
        
        for val in series["values"]:
            timestamp = datetime.fromtimestamp(float(val[0]))
            is_firing = int(float(val[1]))
            alerts_data.append(
                {
                    "alertname": alertname,
                    "severity": severity,
                    "alertstate": alertstate,
                    "timestamp": timestamp.isoformat(),
                    "is_firing": is_firing,
                    "for_duration": for_duration,
                    "labels": labels,
                }
            )
    
    return promql_query, alerts_data


def fetch_all_rule_definitions() -> Dict[str, Dict[str, Any]]:
    """
    Fetches all rule definitions from the Prometheus API and returns them
    as a dictionary keyed by alert name.
    
    Returns:
        Dictionary mapping alert names to their rule definitions
        
    Example return format:
        {
            "HighCPUUsage": {
                "name": "HighCPUUsage",
                "expression": "cpu_usage > 80",
                "duration": "5m",
                "labels": {"severity": "warning"}
            }
        }
    """
    definitions = {}
    
    try:
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/rules", 
            verify=VERIFY_SSL,
            timeout=30
        )
        response.raise_for_status()
        groups = response.json()["data"]["groups"]
        
        for group in groups:
            for rule in group.get("rules", []):
                alert_name = rule.get("alert") or rule.get("name")
                if alert_name:
                    # Store the entire rule object for full context
                    definitions[alert_name] = {
                        "name": alert_name,
                        "expression": rule.get("expr", "N/A"),
                        "duration": rule.get("for", "0s"),
                        "labels": rule.get("labels", {}),
                    }
    except Exception as e:
        logger.error("Error fetching rule definitions: %s", e)
    
    return definitions 