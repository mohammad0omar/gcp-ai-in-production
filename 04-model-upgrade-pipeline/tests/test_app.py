import json
from types import SimpleNamespace

from app import main
from fastapi.testclient import TestClient
from google.genai import errors

client = TestClient(main.app)
GOOD = {"destination": "Paris", "days": 3, "highlights": ["Louvre"], "budget_level": "low"}


def fake_genai(text=None, error=None):
    calls = []

    def generate(model, contents, config):
        calls.append(model)
        if error:
            raise error
        return SimpleNamespace(text=text)

    fake = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    fake.calls = calls
    return fake


def test_model_id_comes_from_env(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "gemini-test-1")
    fake = fake_genai(json.dumps(GOOD))
    monkeypatch.setattr(main, "get_client", lambda: fake)
    response = client.post("/summarize", json={"text": "3 days in Paris"})
    assert response.status_code == 200 and response.json() == GOOD
    assert fake.calls == ["gemini-test-1"]
    assert client.get("/healthz").json()["model"] == "gemini-test-1"


def test_invalid_model_answer_is_502(monkeypatch):
    monkeypatch.setattr(main, "get_client", lambda: fake_genai("oops"))
    assert client.post("/summarize", json={"text": "x"}).status_code == 502


def test_busy_model_is_503_with_retry_after(monkeypatch):
    error = errors.APIError(429, {"error": {"message": "quota"}})
    monkeypatch.setattr(main, "get_client", lambda: fake_genai(error=error))
    response = client.post("/summarize", json={"text": "x"})
    assert response.status_code == 503 and response.headers["Retry-After"] == "5"


def test_transport_failure_is_504(monkeypatch):
    import httpx

    assert main.TRANSPORT_ERRORS  # httpx is importable in the dev environment
    monkeypatch.setattr(main, "get_client", lambda: fake_genai(error=httpx.ReadTimeout("slow")))
    assert client.post("/summarize", json={"text": "x"}).status_code == 504


def test_client_has_timeout_and_retry_budget():
    from unittest import mock

    from app import summarise

    with mock.patch.object(summarise.genai, "Client") as fake:
        summarise.make_client("proj", "global")
    options = fake.call_args.kwargs["http_options"]
    assert options.timeout == summarise.TIMEOUT_MS
    assert options.retry_options.attempts == summarise.RETRY_ATTEMPTS
