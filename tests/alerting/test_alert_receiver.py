from src.alerting.alert_receiver import (
    is_new_vllm_alert,
    format_slack_message,
    send_slack_message,
    get_active_alerts,
    process_vllm_alerts_and_notify,
    generate_description
)
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, Mock
import json
import requests


class TestAlertReceiver:
    """Test alert receiver functionality"""
    
    @pytest.fixture
    def alert(self):
        """Base alert fixture that can be modified for different test scenarios"""
        return {
            "annotations": {},
            "endsAt": "2025-07-09T14:23:01.895Z",
            "receivers": [{"name": "Default"}],
            "startsAt": "2025-07-08T17:31:01.895Z",  # Old timestamp
            "status": {"inhibitedBy": [], "silencedBy": [], "state": "active"},
            "updatedAt": "2025-07-09T14:19:01.908Z",
            "generatorURL": "https://console.example.com/monitoring/alertdetails?foo=bar",
            "labels": {
                "alertname": "VLLMDummyServiceInfo",
                "container": "kserve-container",
                "endpoint": "vllm-serving-runtime-metrics",
                "engine": "0",
                "expr": "rate(vllm:request_success_total[1m]) >= 0",
                "finished_reason": "length",
                "for": "0s",
                "instance": "10.129.5.199:8080",
                "job": "llama-3-2-3b-instruct-metrics",
                "model_name": "meta-llama/Llama-3.2-3B-Instruct",
                "namespace": "m6",
                "pod": "llama-3-2-3b-instruct-predictor-b5d9df9bc-89bhv",
                "prometheus": "openshift-user-workload-monitoring/user-workload",
                "service": "llama-3-2-3b-instruct-metrics",
                "severity": "info",
                "test_alert": "false"
            }
        }

    @pytest.fixture
    def recent_alert(self, alert):
        """Alert fixture with recent timestamp"""
        now = datetime.now(timezone.utc)
        alert["startsAt"] = now.isoformat().replace('+00:00', 'Z')
        return alert


class TestIsNewVllmAlert(TestAlertReceiver):
    """Test the is_new_vllm_alert function with various alert scenarios"""
    
    def test_returns_false_for_test_alert(self, alert):
        """Test that alerts marked as test_alert=true return False"""
        alert["labels"]["test_alert"] = "true"
        assert is_new_vllm_alert(alert, 60) == False

    def test_returns_false_for_old_alert(self, alert):
        """Test that alerts older than time window return False"""
        assert is_new_vllm_alert(alert, 60) == False

    def test_returns_true_for_new_vllm_alert(self, recent_alert):
        """Test that new VLLM alerts return True"""
        assert is_new_vllm_alert(recent_alert, 60) == True

    def test_returns_false_for_non_vllm_alert(self, recent_alert):
        """Test that non-VLLM alerts return False"""
        recent_alert["labels"]["alertname"] = "ClusterAlert"
        assert is_new_vllm_alert(recent_alert, 60) == False


class TestFormatSlackMessage(TestAlertReceiver):
    """Test the format_slack_message function"""

    @patch('src.alerting.alert_receiver.generate_description')
    def test_formats_alert_severity(self, mock_generate, alert):
        """Test formatting of critical severity alert"""
        alert["labels"]["severity"] = "critical"
        mock_generate.return_value = "Test description for critical alert"
        
        result = format_slack_message(alert)
        
        assert ":red_circle:" in result["text"]
        assert "CRITICAL" in result["text"]
        assert "Test description for critical alert" in result["text"]
        assert result["mrkdwn"] == True
        
    @patch('src.alerting.alert_receiver.generate_description')
    def test_handles_missing_generator_url(self, mock_generate, alert):
        """Test handling of missing generatorURL"""
        del alert["generatorURL"]
        mock_generate.return_value = "Test description"
        
        result = format_slack_message(alert)
        
        assert "No generator URL" in result["text"]

    @patch('src.alerting.alert_receiver.generate_description')
    def test_timestamp_formatting(self, mock_generate, alert):
        """Test that timestamps are formatted correctly"""
        alert["startsAt"] = "2025-01-15T10:30:45.123Z"
        mock_generate.return_value = "Test description"
        
        result = format_slack_message(alert)
        
        assert "2025-01-15 10:30:45 UTC" in result["text"]

    @patch('src.alerting.alert_receiver.generate_description')
    def test_invalid_timestamp_handling(self, mock_generate, alert):
        """Test handling of invalid timestamps"""
        alert["startsAt"] = "invalid-timestamp"
        mock_generate.return_value = "Test description"
        
        result = format_slack_message(alert)
        
        assert "N/A" in result["text"]


class TestSendSlackMessage:
    """Test the send_slack_message function"""

    @patch('src.alerting.alert_receiver.SLACK_WEBHOOK_URL', 'https://hooks.slack.com/test')
    @patch('requests.post')
    def test_successful_slack_message_send(self, mock_post):
        """Test successful Slack message sending"""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        payload = {"text": "Test message"}
        result = send_slack_message(payload)
        
        assert result == True
        mock_post.assert_called_once()
        assert mock_post.call_args[1]['headers']['Content-Type'] == 'application/json'

    @patch('src.alerting.alert_receiver.SLACK_WEBHOOK_URL', '')
    def test_no_slack_url_returns_false(self):
        """Test that missing Slack URL returns False"""
        payload = {"text": "Test message"}
        result = send_slack_message(payload)
        
        assert result == False

    @patch('src.alerting.alert_receiver.SLACK_WEBHOOK_URL', 'https://hooks.slack.com/test')
    @patch('requests.post')
    def test_slack_request_exception_handling(self, mock_post):
        """Test handling of request exceptions"""
        mock_post.side_effect = requests.exceptions.RequestException("Network error")
        
        payload = {"text": "Test message"}
        result = send_slack_message(payload)
        
        assert result == False

    @patch('src.alerting.alert_receiver.SLACK_WEBHOOK_URL', 'https://hooks.slack.com/test')
    @patch('requests.post')
    def test_slack_http_error_handling(self, mock_post):
        """Test handling of HTTP errors"""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mock_post.return_value = mock_response
        
        payload = {"text": "Test message"}
        result = send_slack_message(payload)
        
        assert result == False


class TestGetActiveAlerts:
    """Test the get_active_alerts function"""

    @patch('src.alerting.alert_receiver.AUTH_TOKEN', 'test-token')
    @patch('src.alerting.alert_receiver.ALERTMANAGER_URL', 'http://alertmanager:9093')
    @patch('requests.get')
    def test_successful_alerts_retrieval(self, mock_get):
        """Test successful retrieval of alerts from Alertmanager"""
        mock_alerts = [{"labels": {"alertname": "TestAlert"}}]
        mock_response = Mock()
        mock_response.json.return_value = mock_alerts
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = get_active_alerts()
        
        assert result == mock_alerts
        mock_get.assert_called_once()
        assert mock_get.call_args[1]['headers']['Authorization'] == 'Bearer test-token'

    @patch('requests.get')
    def test_alertmanager_request_exception(self, mock_get):
        """Test handling of request exceptions when querying Alertmanager"""
        mock_get.side_effect = requests.exceptions.RequestException("Connection error")
        
        result = get_active_alerts()
        
        assert result == []

    @patch('requests.get')
    def test_alertmanager_http_error(self, mock_get):
        """Test handling of HTTP errors from Alertmanager"""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("401 Unauthorized")
        mock_get.return_value = mock_response
        
        result = get_active_alerts()
        
        assert result == []


class TestProcessVllmAlertsAndNotify(TestAlertReceiver):
    """Test the process_vllm_alerts_and_notify function"""

    @patch('src.alerting.alert_receiver.send_slack_message')
    @patch('src.alerting.alert_receiver.format_slack_message')
    def test_processes_new_vllm_alerts(self, mock_format, mock_send, recent_alert):
        """Test processing of new VLLM alerts"""
        mock_format.return_value = {"text": "Formatted message"}
        mock_send.return_value = True
        
        alerts = [recent_alert]
        process_vllm_alerts_and_notify(alerts, 60)
        
        mock_format.assert_called_once_with(recent_alert)
        mock_send.assert_called_once_with({"text": "Formatted message"})

    @patch('src.alerting.alert_receiver.send_slack_message')
    def test_ignores_old_alerts(self, mock_send, alert):
        """Test that old alerts are ignored"""
        alerts = [alert]  # This alert is old by default
        process_vllm_alerts_and_notify(alerts, 60)
        
        mock_send.assert_not_called()

    @patch('src.alerting.alert_receiver.send_slack_message')
    def test_ignores_non_vllm_alerts(self, mock_send, recent_alert):
        """Test that non-VLLM alerts are ignored"""
        recent_alert["labels"]["alertname"] = "KubernetesAlert"
        alerts = [recent_alert]
        process_vllm_alerts_and_notify(alerts, 60)
        
        mock_send.assert_not_called()

    @patch('src.alerting.alert_receiver.send_slack_message')
    @patch('src.alerting.alert_receiver.format_slack_message')
    def test_processes_multiple_alerts(self, mock_format, mock_send, recent_alert):
        """Test processing multiple alerts"""
        mock_format.return_value = {"text": "Formatted message"}
        mock_send.return_value = True
        
        # Create second alert
        second_alert = recent_alert.copy()
        second_alert["labels"] = recent_alert["labels"].copy()
        second_alert["labels"]["alertname"] = "VLLMHighLatency"
        
        alerts = [recent_alert, second_alert]
        process_vllm_alerts_and_notify(alerts, 60)
        
        assert mock_format.call_count == 2
        assert mock_send.call_count == 2

    @patch('src.alerting.alert_receiver.send_slack_message')
    def test_handles_empty_alert_list(self, mock_send):
        """Test handling of empty alert list"""
        # Should not raise any exceptions
        process_vllm_alerts_and_notify([], 60)
        mock_send.assert_not_called()


class TestGenerateDescription:
    """Test the generate_description function"""

    @patch('src.alerting.alert_receiver.LlamaStackClient')
    def test_generates_description_successfully(self, mock_client_class):
        """Test successful description generation"""
        # Mock the LlamaStack client and response
        mock_client = Mock()
        mock_model = Mock()
        mock_model.identifier = "test-model"
        mock_model.model_type = "llm"
        mock_client.models.list.return_value = [mock_model]
        
        mock_response = Mock()
        mock_response.completion_message.content = "Generated alert description"
        mock_client.inference.chat_completion.return_value = mock_response
        
        mock_client_class.return_value = mock_client
        
        labels = json.dumps({"alertname": "VLLMHighLatency", "severity": "warning"})
        result = generate_description(labels)
        
        assert result == "Generated alert description"
        mock_client.inference.chat_completion.assert_called_once()

    @patch('src.alerting.alert_receiver.LlamaStackClient')
    def test_handles_llm_service_failure(self, mock_client_class):
        """Test handling of LLM service failures"""
        mock_client_class.side_effect = Exception("LLM service unavailable")
        
        labels = json.dumps({"alertname": "VLLMHighLatency", "severity": "warning"})
        
        # Should return hardcoded fallback string when LLM service fails
        result = generate_description(labels)
        expected_fallback = "This alert indicates a VLLM service issue that requires attention. Please check the affected pod and service status, review recent deployments or configuration changes, and consult the monitoring dashboard for additional context."
        assert result == expected_fallback