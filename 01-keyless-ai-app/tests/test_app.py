from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app import main
from fastapi.testclient import TestClient
from google.genai import errors


@pytest.fixture
def client(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(main, "get_client", lambda: fake)
    return TestClient(main.app), fake


def test_summarize_ok(client):
    http, fake = client
    fake.models.generate_content.return_value = SimpleNamespace(text="Short summary.")
    res = http.post("/summarize", json={"text": "Customer cannot log in."})
    assert res.status_code == 200
    assert res.json() == {"summary": "Short summary."}


def test_429_returns_503(client):
    http, fake = client
    fake.models.generate_content.side_effect = errors.ClientError(
        429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}
    )
    res = http.post("/summarize", json={"text": "hello"})
    assert res.status_code == 503
    assert res.headers["Retry-After"] == "5"
    assert res.json() == {"error": "model busy, retry later"}


def test_input_too_long_rejected(client):
    http, fake = client
    res = http.post("/summarize", json={"text": "x" * 8_001})
    assert res.status_code == 422
    fake.models.generate_content.assert_not_called()


def test_healthz(client):
    http, _ = client
    assert http.get("/healthz").json() == {"status": "ok"}
