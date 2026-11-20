"""Through the real ADK FastAPI app: POST /run with the model mocked, spans in memory."""

from pathlib import Path

from fastapi.testclient import TestClient
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.models.google_llm import Gemini
from pebble_support.orders import reset_refunds
from test_run_trace import EXPORTER, FakeModel

AGENTS = Path(__file__).resolve().parents[1] / "agents"


def test_run_endpoint_exports_refund_tool_span(monkeypatch):
    reset_refunds()
    EXPORTER.clear()
    # Swap only the network call. Agent, tools, runner and routes are the real ones.
    monkeypatch.setattr(Gemini, "generate_content_async", FakeModel.generate_content_async)
    # Same arguments as main.py except trace_to_cloud, which needs Google credentials.
    app = get_fast_api_app(
        agents_dir=str(AGENTS), web=False, auto_create_session=True,
        max_llm_calls=4, use_local_storage=False,
    )
    body = {
        "app_name": "pebble_support",
        "user_id": "u",
        "session_id": "s-api",
        "new_message": {"role": "user", "parts": [{"text": "refund PP-1001"}]},
    }
    response = TestClient(app).post("/run", json=body)
    assert response.status_code == 200, response.text
    names = {span.name for span in EXPORTER.get_finished_spans()}
    assert "execute_tool refund_order" in names
    assert "refunded" in response.text
    reset_refunds()
