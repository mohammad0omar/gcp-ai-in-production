"""Shared test helpers: a fake clock, a fake Gemini client and error builders."""

from types import SimpleNamespace

import pytest
from google.genai import errors


class FakeClock:
    """Time that only moves when the code sleeps. No real waiting in tests."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeClient:
    """Stands in for genai.Client. Each call pops the next outcome: an exception or a response."""

    def __init__(self, outcomes, clock: FakeClock | None = None, call_cost_s: float = 0.0) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []
        self.clock = clock
        self.call_cost_s = call_cost_s
        self.models = SimpleNamespace(generate_content=self._generate_content)

    def close(self) -> None:
        self.closed = True

    def _generate_content(self, *, model, contents, config=None):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.clock is not None:
            self.clock.now += self.call_cost_s  # the call takes this long, whatever its timeout
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def ok_response(text: str = "hello", cached: int | None = 0):
    usage = SimpleNamespace(cached_content_token_count=cached)
    return SimpleNamespace(text=text, usage_metadata=usage)


def api_error(code: int, retry_after: str | None = None) -> errors.APIError:
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    response = SimpleNamespace(headers=headers)
    payload = {"error": {"code": code, "message": "boom", "status": "TEST"}}
    cls = errors.ClientError if code < 500 else errors.ServerError
    return cls(code, payload, response)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
