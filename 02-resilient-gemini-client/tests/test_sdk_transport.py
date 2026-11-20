"""Real google-genai client over a mock HTTP transport: count the requests actually sent."""

import httpx
import pytest
from google import genai
from google.genai import errors, types
from resilient_gemini.resilient import _request_config


def make_client(handler, **retry):
    return genai.Client(
        api_key="test",  # the mock transport never leaves the machine
        http_options=types.HttpOptions(
            httpx_client=httpx.Client(transport=httpx.MockTransport(handler)),
            retry_options=types.HttpRetryOptions(**retry) if retry else None,
        ),
    )


def test_one_attempt_sends_one_http_request_even_if_client_retries():
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(503, json={"error": {"code": 503, "message": "x", "status": "UNAVAILABLE"}})

    client = make_client(handler, attempts=5, initial_delay=0.01)  # a client that would retry
    with pytest.raises(errors.ServerError):
        client.models.generate_content(model="m", contents="hi", config=_request_config(5, None))
    assert len(sent) == 1


def test_config_turns_off_continuation_and_sets_system_instruction():
    config = _request_config(2.5, "be brief")
    assert config.automatic_continuation is False
    assert config.system_instruction == "be brief"
    assert config.http_options.timeout == 2500
    assert config.http_options.retry_options.attempts == 1
