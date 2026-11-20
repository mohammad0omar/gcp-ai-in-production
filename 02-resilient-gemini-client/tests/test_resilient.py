import random
from datetime import UTC, datetime
from email.utils import format_datetime

import httpx
import pytest
from conftest import FakeClient, api_error, ok_response
from resilient_gemini import backoff, resilient
from resilient_gemini.classify import retry_after_seconds

WALL_NOW = 1_800_000_000.0  # fixed epoch seconds for Retry-After dates


def run(client, clock, **overrides):
    args = {
        "models": ["primary", "backup"],
        "timeout_s": 100.0,
        "max_attempts": 3,
        "client": client,
    }
    args.update(overrides)
    return resilient.call(
        "hi", sleep=clock.sleep, clock=clock, wall_clock=lambda: WALL_NOW, rng=lambda: 1.0, **args
    )


def test_backoff_grows_and_caps():
    ceilings = [backoff.ceiling(n) for n in range(1, 9)]
    assert ceilings[:5] == [1.0, 2.0, 4.0, 8.0, 16.0]
    assert ceilings[5:] == [30.0, 30.0, 30.0]


def test_full_jitter_within_bounds():
    rng = random.Random(7)
    for attempt in range(1, 10):
        for _ in range(200):
            delay = backoff.full_jitter(attempt, rng=rng.random)
            assert 0.0 <= delay <= backoff.ceiling(attempt)
    assert backoff.full_jitter(3, rng=lambda: 0.0) == 0.0
    assert backoff.full_jitter(3, rng=lambda: 0.5) == 2.0  # half of the ceiling 4.0


def test_falls_back_on_429(clock):
    client = FakeClient([api_error(429)] * 3 + [ok_response("from backup")])
    result = run(client, clock)
    assert result.model_used == "backup"
    assert result.text == "from backup"
    assert [c["model"] for c in client.calls] == ["primary"] * 3 + ["backup"]


def test_no_retry_on_400(clock):
    for code in (400, 403, 404):
        client = FakeClient([api_error(code), ok_response()])
        with pytest.raises(resilient.NonRetryableError):
            run(client, clock)
        assert len(client.calls) == 1
    assert clock.sleeps == []


def test_total_deadline_respected(clock):
    client = FakeClient([api_error(503)] * 50, clock=clock, call_cost_s=4.0)
    with pytest.raises(resilient.DeadlineExceeded):
        run(client, clock, timeout_s=20.0, max_attempts=10)
    assert clock.now <= 24.0  # may finish the call in flight, never starts another


def test_late_success_is_rejected(clock):
    client = FakeClient([ok_response()], clock=clock, call_cost_s=2.0)
    with pytest.raises(resilient.DeadlineExceeded):
        run(client, clock, timeout_s=1.0)


def test_late_failure_on_last_attempt_is_a_deadline_error(clock):
    client = FakeClient([api_error(503)], clock=clock, call_cost_s=2.0)
    with pytest.raises(resilient.DeadlineExceeded):
        run(client, clock, timeout_s=1.0, models=["primary"], max_attempts=1)


def test_deadline_starts_before_client_setup(clock, monkeypatch):
    def slow_make_client():
        clock.now += 5.0  # credential lookup is slow
        return FakeClient([ok_response()])

    monkeypatch.setattr(resilient, "make_client", slow_make_client)
    with pytest.raises(resilient.DeadlineExceeded):
        run(None, clock, timeout_s=3.0)


def test_retry_after_honoured(clock):
    client = FakeClient([api_error(429, retry_after="7"), ok_response()])
    result = run(client, clock)
    assert clock.sleeps == [7.0]
    assert result.attempts == 2


def test_retry_after_http_date():
    when = datetime.fromtimestamp(WALL_NOW + 12, tz=UTC)
    error = api_error(429, retry_after=format_datetime(when, usegmt=True))
    assert retry_after_seconds(error, lambda: WALL_NOW) == 12.0
    assert retry_after_seconds(api_error(429, retry_after="garbage")) is None


def test_retry_after_applies_before_fallback(clock):
    client = FakeClient([api_error(429)] * 2 + [api_error(429, retry_after="9"), ok_response()])
    result = run(client, clock)
    assert result.model_used == "backup"
    assert clock.sleeps == [1.0, 2.0, 9.0]  # jitter, jitter, then the hint before the fallback


def test_result_reports_model_used(clock):
    client = FakeClient([ok_response("done", cached=12)])
    result = run(client, clock)
    assert (result.text, result.model_used, result.attempts, result.cached_tokens) == (
        "done",
        "primary",
        1,
        12,
    )


def test_timeout_is_retried(clock):
    client = FakeClient([httpx.ReadTimeout("slow"), ok_response()])
    assert run(client, clock).attempts == 2


@pytest.mark.parametrize("code", [408, 502])
def test_408_and_502_are_retried(clock, code):
    assert run(FakeClient([api_error(code), ok_response()]), clock).attempts == 2


def test_all_models_exhausted(clock):
    client = FakeClient([api_error(500)] * 6)
    with pytest.raises(resilient.AllModelsFailed):
        run(client, clock)
    assert [c["model"] for c in client.calls] == ["primary"] * 3 + ["backup"] * 3


def test_request_timeout_shrinks_as_time_passes(clock):
    client = FakeClient([api_error(503), ok_response()], clock=clock, call_cost_s=1.0)
    run(client, clock, timeout_s=10.0)
    first, second = (c["config"].http_options.timeout for c in client.calls)
    assert first == 10_000
    assert second == 8_000  # 1 s call plus 1 s sleep already spent


def test_late_non_retryable_error_is_a_deadline_error(clock):
    client = FakeClient([api_error(400)], clock=clock, call_cost_s=2.0)
    with pytest.raises(resilient.DeadlineExceeded):
        run(client, clock, timeout_s=1.0)


def test_retry_after_asctime_date_is_utc_not_local(monkeypatch):
    import time

    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    try:
        # asctime form carries no zone; WALL_NOW + 30 s in UTC
        stamp = datetime.fromtimestamp(WALL_NOW + 30, tz=UTC).strftime("%a %b %e %H:%M:%S %Y")
        assert retry_after_seconds(api_error(429, retry_after=stamp), lambda: WALL_NOW) == 30.0
    finally:
        monkeypatch.undo()
        time.tzset()


def test_httpx2_timeout_is_retried_when_installed(clock):
    from resilient_gemini import classify

    class FakeTimeout(Exception):
        pass

    # Simulate httpx2 being importable by adding its timeout type to the lookup tuple.
    original = classify._TIMEOUT_TYPES
    classify._TIMEOUT_TYPES = (*original, FakeTimeout)
    try:
        assert classify.is_retryable(FakeTimeout())
        assert run(FakeClient([FakeTimeout(), ok_response()]), clock).attempts == 2
    finally:
        classify._TIMEOUT_TYPES = original
