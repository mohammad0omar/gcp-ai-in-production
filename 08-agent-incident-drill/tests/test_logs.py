import json
import logging

from opentelemetry.sdk.trace import TracerProvider
from pebble_support import tools
from pebble_support.logs import JsonFormatter
from pebble_support.orders import reset_refunds


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.lines = []

    def emit(self, record):
        self.lines.append(json.loads(self.format(record)))


def _run_with_span(call):
    handler = Capture()
    logger = logging.getLogger("pebble.tools")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    tracer = TracerProvider().get_tracer("test")
    try:
        with tracer.start_as_current_span("execute_tool") as span:
            call()
            ctx = span.get_span_context()
    finally:
        logger.removeHandler(handler)
    return handler.lines, format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


def test_log_line_has_trace_field():
    reset_refunds()
    lines, trace_id, span_id = _run_with_span(lambda: tools.refund_order("PP-1001", 1000, "USD"))
    assert len(lines) == 1
    line = lines[0]
    assert line["logging.googleapis.com/trace"] == trace_id
    assert line["logging.googleapis.com/spanId"] == span_id
    assert line["logging.googleapis.com/trace_sampled"] is True


def test_log_line_has_decision_and_reason():
    reset_refunds()
    lines, _, _ = _run_with_span(lambda: tools.refund_order("PP-1002", 8900, "EUR"))
    line = lines[0]
    assert line["severity"] == "WARNING"
    assert line["tool"] == "refund_order"
    assert line["decision"] == "refused"
    assert line["reason"] == "over_limit"
    assert line["order_id"] == "PP-1002"


def test_one_log_line_per_tool_call():
    reset_refunds()
    lines, _, _ = _run_with_span(lambda: tools.lookup_order("PP-1001"))
    assert len(lines) == 1
    assert lines[0]["decision"] == "allowed"
    assert lines[0]["severity"] == "INFO"


def test_log_without_span_has_no_trace_field():
    handler = Capture()
    logger = logging.getLogger("pebble.tools")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        tools.lookup_order("PP-1001")
    finally:
        logger.removeHandler(handler)
    assert "logging.googleapis.com/trace" not in handler.lines[0]
