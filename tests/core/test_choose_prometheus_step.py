import re

import pytest

from core.metrics import choose_prometheus_step


def parse_step_to_seconds(step: str) -> int:
    assert isinstance(step, str) and step, "step must be a non-empty string"
    m = re.fullmatch(r"(\d+)([smh])", step)
    assert m, f"invalid step format: {step}"
    value = int(m.group(1))
    unit = m.group(2)
    if unit == "s":
        return value
    if unit == "m":
        return value * 60
    if unit == "h":
        return value * 3600
    raise AssertionError(f"unsupported unit in step: {unit}")


@pytest.mark.parametrize(
    "duration,expected_min_bucket",
    [
        # Very short ranges should clamp to at least 30s
        (60, 30),
        (1800, 30),  # 30 minutes
        # 6 days should round up from ~48s to 60s (1m)
        (6 * 24 * 3600, 60),
        # 30 days should round to 5m (300s) or higher
        (30 * 24 * 3600, 300),
        # 90 days should be at least 15m (900s) or higher
        (90 * 24 * 3600, 900),
    ],
)
def test_choose_prometheus_step_monotonic_buckets(duration: int, expected_min_bucket: int) -> None:
    start = 0
    end = duration
    step = choose_prometheus_step(start, end)
    step_seconds = parse_step_to_seconds(step)
    assert step_seconds >= expected_min_bucket


def test_points_within_limit_default() -> None:
    # With default max_points=11000, ensure chosen step keeps samples <= 11000
    start = 0
    end = 6 * 24 * 3600  # 6 days
    step = choose_prometheus_step(start, end)
    step_seconds = parse_step_to_seconds(step)
    # Inclusive endpoints -> approx samples = floor(duration/step)+1
    approx_points = (end - start) // step_seconds + 1
    assert approx_points <= 11000


def test_custom_limits_and_min_step() -> None:
    # Tighter points limit forces a larger step
    start = 0
    end = 24 * 3600  # 1 day
    step_default = choose_prometheus_step(start, end)
    step_tight = choose_prometheus_step(start, end, max_points_per_series=1000)
    assert parse_step_to_seconds(step_tight) >= parse_step_to_seconds(step_default)

    # Larger min_step_seconds increases the result
    step_min30 = choose_prometheus_step(start, end, min_step_seconds=30)
    step_min300 = choose_prometheus_step(start, end, min_step_seconds=300)
    assert parse_step_to_seconds(step_min300) >= 300
    assert parse_step_to_seconds(step_min300) >= parse_step_to_seconds(step_min30)


@pytest.mark.parametrize(
    "start,end",
    [
        (1000, 1000),  # zero duration
        (2000, 1000),  # inverted range
    ],
)
def test_edge_cases_non_positive_duration(start: int, end: int) -> None:
    step = choose_prometheus_step(start, end)
    # Should at least return the minimum bucket of 30s by default
    assert parse_step_to_seconds(step) >= 30


