import ast
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app import main
from config import MODEL_ID
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
    kwargs = fake.models.generate_content.call_args.kwargs
    assert kwargs["model"] == MODEL_ID
    assert kwargs["contents"] == "Customer cannot log in."


@pytest.mark.parametrize("code", [429, 503])
def test_busy_model_returns_503_with_retry_after(client, code):
    http, fake = client
    error_class = errors.ClientError if code == 429 else errors.ServerError
    fake.models.generate_content.side_effect = error_class(code, {"error": {"code": code}})
    res = http.post("/summarize", json={"text": "hello"})
    assert res.status_code == 503
    assert res.headers["Retry-After"] == "5"
    assert res.json() == {"error": "model busy, retry later"}


@pytest.mark.parametrize("library", ["httpx2", "httpx"])
def test_timeout_returns_504(client, library):
    # Whichever HTTP library the SDK uses, its timeout becomes the documented 504.
    module = pytest.importorskip(library)
    http, fake = client
    fake.models.generate_content.side_effect = module.ReadTimeout("slow")
    assert http.post("/summarize", json={"text": "hello"}).status_code == 504


def test_the_sdk_transport_is_handled():
    # google-genai 3.x talks through httpx2; the handler must cover what the SDK really uses.
    import google.genai._api_client as sdk_client

    used = "httpx2" if hasattr(sdk_client, "httpx2") else "httpx"
    module = pytest.importorskip(used)
    assert module.TransportError in main.TRANSPORT_ERRORS


def test_main_has_no_top_level_httpx_import():
    tree = ast.parse(Path(main.__file__).read_text())
    names = [a.name for n in tree.body if isinstance(n, ast.Import) for a in n.names]
    names += [n.module for n in tree.body if isinstance(n, ast.ImportFrom)]
    assert not [n for n in names if n and n.split(".")[0].startswith("httpx")]


def test_app_starts_when_httpx_is_missing():
    # Block httpx and httpx2 imports for the handler lookup, as in a clean image.
    code = (
        "import sys; sys.modules['httpx']=None; sys.modules['httpx2']=None; "
        "import app.main as m; assert m.TRANSPORT_ERRORS == ()"
    )
    folder = Path(main.__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-c", code], cwd=folder, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_empty_answer_is_not_a_200(client):
    http, fake = client
    fake.models.generate_content.return_value = SimpleNamespace(text=None)
    assert http.post("/summarize", json={"text": "hello"}).status_code == 502


def test_input_too_long_rejected(client):
    http, fake = client
    res = http.post("/summarize", json={"text": "x" * 8_001})
    assert res.status_code == 422
    fake.models.generate_content.assert_not_called()


def test_client_is_created_once(monkeypatch):
    created = MagicMock()
    monkeypatch.setattr(main.genai, "Client", created)
    monkeypatch.setattr(main, "_client", None)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo")
    first, second = main.get_client(), main.get_client()
    assert first is second
    created.assert_called_once()
    assert created.call_args.kwargs["vertexai"] is True


def test_healthz(client):
    http, _ = client
    assert http.get("/healthz").json() == {"status": "ok"}
