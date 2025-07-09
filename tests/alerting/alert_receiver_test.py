from metric_ui.alerting.alert_receiver import is_new_vllm_alert
import pytest
import copy
from datetime import datetime, timezone, timedelta

@pytest.fixture
def base_alert():
    """Base alert fixture that can be modified for different test scenarios"""
    return {
        "annotations": {},
        "endsAt": "2025-07-09T14:23:01.895Z",
        "receivers": [{"name": "Default"}],
        "startsAt": "2025-07-08T17:31:01.895Z",  # Old timestamp
        "status": {"inhibitedBy": [], "silencedBy": [], "state": "active"},
        "updatedAt": "2025-07-09T14:19:01.908Z",
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

def test_is_new_vllm_alert_returns_false_for_test_alert(base_alert):
    """Test that alerts marked as test_alert=true return False"""
    alert = copy.deepcopy(base_alert)
    alert["labels"]["test_alert"] = "true"
    assert is_new_vllm_alert(alert, 60) == False

def test_is_new_vllm_alert_returns_false_for_old_alert(base_alert):
    """Test that alerts older than time window return False"""
    alert = copy.deepcopy(base_alert)
    assert is_new_vllm_alert(alert, 60) == False

def test_is_new_vllm_alert_returns_true_for_new_vllm_alert(base_alert):
    """Test that new VLLM alerts return True"""
    alert = copy.deepcopy(base_alert)
    now = datetime.now(timezone.utc)
    alert["startsAt"] = now.isoformat().replace('+00:00', 'Z')
    assert is_new_vllm_alert(alert, 60) == True

def test_is_new_vllm_alert_returns_false_for_non_vllm_alert(base_alert):
    """Test that non-VLLM alerts return False"""
    alert = copy.deepcopy(base_alert)
    alert["labels"]["alertname"] = "ClusterAlert"
    now = datetime.now(timezone.utc)
    alert["startsAt"] = now.isoformat().replace('+00:00', 'Z')
    assert is_new_vllm_alert(alert, 60) == False

