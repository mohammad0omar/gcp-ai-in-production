"""Offline end-to-end check: a real ADK run with a fake model and an in-memory span exporter.

It proves two things the unit tests cannot: the tool log line carries the same trace and
span id as the `execute_tool` span ADK really exports, and prompt text and tool payloads
stay out of span attributes when ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false.
"""

import asyncio
import json
import logging

import pytest
from google.adk.agents import Agent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pebble_support.logs import JsonFormatter
from pebble_support.orders import reset_refunds
from pebble_support.tools import lookup_order, refund_order

PROMPT = "SECRET-PROMPT-TEXT refund order PP-1001"
TOOL_PAYLOAD = "Box of 12 stamps"  # appears only in lookup_order's result

EXPORTER = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(EXPORTER))
trace.set_tracer_provider(_provider)


class FakeModel(BaseLlm):
    """Scripted model: lookup_order, then refund_order, then a closing sentence."""

    model: str = "fake"

    async def generate_content_async(self, llm_request, stream=False):
        calls = sum(
            1 for c in llm_request.contents for p in c.parts or [] if p.function_response
        )
        if calls == 0:
            part = types.Part.from_function_call(name="lookup_order", args={"order_id": "PP-1001"})
        elif calls == 1:
            part = types.Part.from_function_call(
                name="refund_order",
                args={"order_id": "PP-1001", "amount_minor": 1000, "currency": "GBP"},
            )
        else:
            part = types.Part(text="Done.")
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.lines = []

    def emit(self, record):
        self.lines.append(json.loads(self.format(record)))


def _run_agent():
    reset_refunds()
    EXPORTER.clear()
    handler = Capture()
    logger = logging.getLogger("pebble.tools")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    agent = Agent(name="pebble_support", model=FakeModel(), tools=[lookup_order, refund_order])
    runner = InMemoryRunner(agent=agent, app_name="drill")

    async def go():
        await runner.session_service.create_session(app_name="drill", user_id="u", session_id="s")
        message = types.Content(role="user", parts=[types.Part(text=PROMPT)])
        async for _ in runner.run_async(user_id="u", session_id="s", new_message=message):
            pass

    try:
        asyncio.run(go())
    finally:
        logger.removeHandler(handler)
    return handler.lines, EXPORTER.get_finished_spans()


def _attribute_text(spans) -> str:
    return " ".join(str(v) for s in spans for v in s.attributes.values())


def test_tool_log_line_matches_exported_tool_span(monkeypatch):
    monkeypatch.setenv("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", "false")
    lines, spans = _run_agent()
    tool_spans = {s.name: s for s in spans if s.name.startswith("execute_tool")}
    assert set(tool_spans) >= {"execute_tool lookup_order", "execute_tool refund_order"}
    for tool in ("lookup_order", "refund_order"):
        span = tool_spans[f"execute_tool {tool}"].get_span_context()
        line = next(entry for entry in lines if entry["tool"] == tool)
        assert line["logging.googleapis.com/trace"] == format(span.trace_id, "032x")
        assert line["logging.googleapis.com/spanId"] == format(span.span_id, "016x")


def test_message_content_stays_out_of_spans_when_disabled(monkeypatch):
    # Test the strictest case: legacy schema pinned, content switch off.
    monkeypatch.setenv("ADK_TELEMETRY_SCHEMA_VERSION_OPT_IN", "1")
    monkeypatch.setenv("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", "false")
    _, spans = _run_agent()
    text = _attribute_text(spans)
    assert "SECRET-PROMPT-TEXT" not in text
    assert TOOL_PAYLOAD not in text


def test_control_content_is_captured_when_enabled(monkeypatch):
    """Without this, the test above could pass because nothing is ever captured.

    ADK 2.x writes the new span schema by default, which carries no message content
    unless asked. Pinning schema 1 (the legacy attributes) shows what the knob guards.
    """
    monkeypatch.setenv("ADK_TELEMETRY_SCHEMA_VERSION_OPT_IN", "1")
    monkeypatch.setenv("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", "true")
    _, spans = _run_agent()
    text = _attribute_text(spans)
    assert "SECRET-PROMPT-TEXT" in text or TOOL_PAYLOAD in text


@pytest.fixture(autouse=True)
def _clean():
    yield
    reset_refunds()
