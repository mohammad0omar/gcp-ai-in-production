from app import main
from conftest import FakeClient, api_error, ok_response
from fastapi.testclient import TestClient


def make_client(monkeypatch, outcomes):
    fake = FakeClient(outcomes)
    monkeypatch.setattr(main, "make_client", lambda location: fake)
    monkeypatch.setattr(main.google.auth, "default", lambda scopes=None: (None, None))
    monkeypatch.setattr(main, "SLEEP", lambda s: None)
    return TestClient(main.app), fake


def test_summarise_ok(monkeypatch):
    client, fake = make_client(monkeypatch, [ok_response("short")])
    with client:
        body = client.post("/summarise", json={"text": "long text"}).json()
    assert body["summary"] == "short"
    assert body["model_used"] == main.MODELS[0]
    # The document is the contents; the policy is the system instruction.
    assert fake.calls[0]["contents"] == "long text"
    assert fake.calls[0]["config"].system_instruction == main.POLICY


def test_summarise_busy_is_clean_503(monkeypatch):
    client, _ = make_client(monkeypatch, [api_error(429)] * 20)
    with client:
        response = client.post("/summarise", json={"text": "x"})
    assert response.status_code == 503
    assert response.json() == {"error": "model busy, retry later"}


def test_summarise_bad_request_is_502(monkeypatch):
    client, _ = make_client(monkeypatch, [api_error(400)])
    with client:
        assert client.post("/summarise", json={"text": "x"}).status_code == 502


def test_missing_project_fails_at_startup(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    import pytest

    with pytest.raises(RuntimeError), TestClient(main.app):
        pass


def test_missing_credentials_fail_at_startup(monkeypatch):
    import google.auth.exceptions
    import pytest

    def no_adc(scopes=None):
        raise google.auth.exceptions.DefaultCredentialsError("no adc")

    monkeypatch.setattr(main.google.auth, "default", no_adc)
    with pytest.raises(google.auth.exceptions.DefaultCredentialsError), TestClient(main.app):
        pass
