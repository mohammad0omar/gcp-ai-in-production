import importlib
import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from google.genai import errors, types


def load_app(monkeypatch, client):
    monkeypatch.setenv("CUSTOMER_HASH_SALT", "s" * 32)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    from app import main

    main = importlib.reload(main)
    monkeypatch.setattr(main, "get_client", lambda: client)
    return TestClient(main.app)


def body(feature="smart_reply"):
    return {"feature": feature, "customer_id": "acme-corp", "text": "secret prompt"}


def test_success_returns_text(monkeypatch):
    client = MagicMock()
    client.models.generate_content.return_value = types.GenerateContentResponse(
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=1)
    )
    assert (
        load_app(monkeypatch, client).post("/generate", json=body()).status_code == 200
    )


def test_unknown_feature_is_422(monkeypatch):
    app = load_app(monkeypatch, MagicMock())
    assert app.post("/generate", json=body("nope")).status_code == 422


def test_exhausted_retries_give_clean_503_without_prompt_or_customer(
    monkeypatch, capsys
):
    client = MagicMock()
    client.models.generate_content.side_effect = errors.ServerError(503, {"error": {}})
    response = load_app(monkeypatch, client).post("/generate", json=body())
    assert response.status_code == 503
    out = capsys.readouterr().out
    assert "secret prompt" not in out and "acme-corp" not in out
    assert json.loads(out.strip().splitlines()[-1])["code"] == 503


def test_transport_error_is_clean_503(monkeypatch):
    class ReadTimeout(Exception):
        pass

    ReadTimeout.__module__ = "httpx2._exceptions"
    client = MagicMock()
    client.models.generate_content.side_effect = ReadTimeout("slow")
    response = load_app(monkeypatch, client).post("/generate", json=body())
    assert response.status_code == 503


def test_unrelated_error_still_raises(monkeypatch):
    client = MagicMock()
    client.models.generate_content.side_effect = KeyError("bug")
    app = load_app(monkeypatch, client)
    with pytest.raises(KeyError):
        app.post("/generate", json=body())


def test_startup_fails_without_salt(monkeypatch):
    monkeypatch.delenv("CUSTOMER_HASH_SALT", raising=False)
    from app import main

    with pytest.raises(RuntimeError), TestClient(main.app):
        pass


def test_google_auth_errors_are_clean_503(monkeypatch):
    class RefreshError(Exception):
        pass

    RefreshError.__module__ = "google.auth.exceptions"
    client = MagicMock()
    client.models.generate_content.side_effect = RefreshError("token")
    assert (
        load_app(monkeypatch, client).post("/generate", json=body()).status_code == 503
    )
