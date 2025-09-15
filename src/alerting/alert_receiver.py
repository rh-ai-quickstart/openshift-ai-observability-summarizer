import requests
import json
import os
import datetime
import logging
from llama_stack_client import LlamaStackClient
from typing import Any
from common.pylogger import get_python_logger

# Initialize structured logger once - other modules should use logging.getLogger(__name__)
get_python_logger()

logger = logging.getLogger(__name__)

# --- CONFIG ---
ALERTMANAGER_URL = os.getenv("ALERTMANAGER_URL", "http://localhost:9093")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
LLAMA_STACK_URL = os.getenv("LLAMA_STACK_URL", "http://localhost:8321")
TIME_WINDOW = int(os.getenv("TIME_WINDOW", 60))

# Handle token input from volume or literal
token_input = os.getenv("AUTH_TOKEN", "/var/run/secrets/kubernetes.io/serviceaccount/token")
if os.path.exists(token_input):
    with open(token_input, "r") as f:
        AUTH_TOKEN = f.read().strip()
else:
    AUTH_TOKEN = token_input

# CA bundle location (mounted via ConfigMap)
CA_BUNDLE_PATH = "/etc/pki/ca-trust/extracted/pem/ca-bundle.crt"
verify = CA_BUNDLE_PATH if os.path.exists(CA_BUNDLE_PATH) else True

# pull active alerts from Alertmanager
def get_active_alerts() -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    endpoint = f"{ALERTMANAGER_URL}/api/v2/alerts"
    verify = CA_BUNDLE_PATH if os.path.exists(CA_BUNDLE_PATH) else True
    try:
        response = requests.get(
            endpoint,
            headers=headers,
            verify=verify,
        )
        response.raise_for_status()  
        logger.info("Alerts successfully retrieved from Alertmanager")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error("Error querying Alertmanager: %s", e)
        return []

def send_slack_message(payload: dict[str, Any]) -> bool:
    headers = {"Content-Type": "application/json"}
    if SLACK_WEBHOOK_URL == "":
        logger.warning("No Slack URL found")
        return False
    try:
        response = requests.post(SLACK_WEBHOOK_URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        logger.info("Slack message sent successfully")
        return True
    except requests.exceptions.RequestException as e:
        logger.error("Error sending Slack message: %s", e)
        return False
    
# generate a description based on the alert labels
def generate_description(labels: str) -> str:
    try:
        # --- LLAMASTACK SETUP ---
        client = LlamaStackClient(base_url=LLAMA_STACK_URL)
        llm = next(m for m in client.models.list() if m.model_type == "llm")

        labels = json.dumps(labels)
        prompt = """
        You are an AI assistant designed to generate concise, informative, and *technically detailed* Slack message descriptions for OpenShift vLLM alerts. Your task is to analyze the provided alert data, *especially the 'expr' and 'for' fields*, and create a clear, actionable description of the problem.

        Provide only the description text. Start the description with "This alert..." or "This alert indicates..." to briefly summarize the general nature of the alert. Then, use a Markdown bulleted list to detail the following points:
        1.  Interpret the expression and 'for' value to explain what the issue is in plain, understandable English. Do NOT mention "Prometheus Query Language" or include the raw expression string in your explanation. Instead, describe the metric and threshold being monitored and for how long.
        2.  **Affected components:** Mention the model_name, pod, namespace, and service to clearly identify what is impacted. This should be in a clear bulleted list.
        3.  Provide initial troubleshooting steps or common solutions to resolve the issue in a single sentence.

        Do not add any prefixes like 'ALERT:' or 'Severity:' or a separate summary line. The output should be ready to be embedded directly into a Slack message.

        Here is the alert data: 
        """
        response = client.inference.chat_completion(
            model_id=llm.identifier,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": labels},
            ],
            stream=False
        )

        return str(response.completion_message.content)
    except Exception as e:
        return "This alert indicates a VLLM service issue that requires attention. Please check the affected pod and service status, review recent deployments or configuration changes, and consult the monitoring dashboard for additional context."
    
# formats slack message for a single alert
def format_slack_message(alert_data: dict[str, Any]) -> dict[str, Any]:
    alertname = alert_data['labels'].get('alertname', 'N/A')
    severity = alert_data['labels'].get('severity', 'info').upper()
    generator_url = alert_data.get('generatorURL', 'No generator URL.')
    starts_at_iso = alert_data.get('startsAt')

    description = generate_description(alert_data['labels'])

    # get firing start time in UTC
    starts_at_iso = alert_data.get('startsAt')
    starts_at_formatted = "N/A"
    if starts_at_iso:
        try:
            dt_object_utc = datetime.datetime.fromisoformat(starts_at_iso.replace('Z', '+00:00'))
            starts_at_formatted = dt_object_utc.strftime('%Y-%m-%d %H:%M:%S UTC')
        except ValueError:
            pass

    color_emoji = ""
    if severity == "CRITICAL":
        color_emoji = ":red_circle: "
    elif severity == "WARNING":
        color_emoji = ":large_orange_circle: "
    elif severity == "INFO":
        color_emoji = ":large_blue_circle: "

    message_text = (
        f"{color_emoji}*ALERT: {alertname} [{severity}]*\n\n"
        f"{description}\n\n"
        f"Started At: {starts_at_formatted}\n"
        f"<{generator_url}|View on console>"
    )

    payload = {
        "text": message_text,
        "mrkdwn": True
    }

    return payload

# filters Alertmanager alerts by name + time and sends a slack message for each resulting alert
def process_vllm_alerts_and_notify(alerts: list[dict[str, Any]], time_window: int = TIME_WINDOW) -> None:
    if alerts:
        found = False
        for alert in alerts:
            if is_new_vllm_alert(alert, time_window):
                alertname = alert['labels'].get('alertname', '')
                logger.info("Found NEW relevant VLLM Alert: %s", alertname)
                slack_payload = format_slack_message(alert)
                send_slack_message(slack_payload)
                found = True
        if not found:
            logger.info("No new alerts found")
    else:
        logger.info("No alerts to process")

# check if alert is a new VLLM alert that started within the given time window
def is_new_vllm_alert(alert: dict[str, Any], time_window: int = TIME_WINDOW) -> bool:
    alertname = alert['labels'].get('alertname', '')
    starts_at_iso = alert.get('startsAt')
    test_alert_label = alert['labels'].get('test_alert', 'false').lower()
    
    if not alertname.startswith("VLLM") or test_alert_label == 'true':
        return False
    
    if starts_at_iso:
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            time_threshold = now_utc - datetime.timedelta(seconds=time_window)
            alert_start_time_utc = datetime.datetime.fromisoformat(starts_at_iso.replace('Z', '+00:00'))
            return alert_start_time_utc >= time_threshold
        except ValueError:
            logger.warning("Could not parse startsAt time for alert '%s': %s", alertname, starts_at_iso)
            return False
    
    return False

def generate_test():
    alert = json.loads('{"alertname": "VLLMHighAverageInferenceTime", "container": "kserve-container", "endpoint": "vllm-serving-runtime-metrics", "engine": "0", "expr": "rate(vllm:request_inference_time_seconds_sum[5m]) / rate(vllm:request_inference_time_seconds_count[5m]) > 2", "for": "5m", "instance": "10.129.2.73:8080", "job": "llama-3-2-3b-instruct-metrics", "model_name": "meta-llama/Llama-3.2-3B-Instruct", "namespace": "m3", "pod": "llama-3-2-3b-instruct-predictor-9fd74489-c6dwt", "prometheus": "openshift-user-workload-monitoring/user-workload", "service": "llama-3-2-3b-instruct-metrics", "severity": "warning"}')
    desc = generate_description(alert)
    logger.info("%s", desc)

def main():
    alerts = get_active_alerts()
    process_vllm_alerts_and_notify(alerts)

if __name__ == "__main__":
    main()
    # generate_test()