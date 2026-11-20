"""Cloud Run entry point: ADK's FastAPI app with traces going to Cloud Trace.

`trace_to_cloud=True` makes ADK export its spans (one per agent run, model call
and tool call) to Cloud Trace using GOOGLE_CLOUD_PROJECT. Run it with:
    python -m uvicorn main:app --host 0.0.0.0 --port 8080
"""

from pathlib import Path

from agents.pebble_support.logs import configure_logging
from config import MAX_LLM_CALLS
from google.adk.cli.fast_api import get_fast_api_app

configure_logging()

app = get_fast_api_app(
    agents_dir=str(Path(__file__).parent / "agents"),
    web=False,  # no dev UI on a public URL
    trace_to_cloud=True,
    max_llm_calls=MAX_LLM_CALLS,
    use_local_storage=False,  # sessions in memory; the container filesystem is not durable
    auto_create_session=True,  # first /run call for a session id creates it
)
