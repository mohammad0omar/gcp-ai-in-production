"""Structured JSON logs for Cloud Run that link to Cloud Trace.

Cloud Run's logging agent reads one JSON object per line from stdout. It moves
`severity`, `message` and the three `logging.googleapis.com/...` keys into the
log entry, which is how Logs Explorer and Trace Explorer find each other.
"""

import json
import logging
import sys

from opentelemetry import trace

TRACE_KEY = "logging.googleapis.com/trace"
SPAN_KEY = "logging.googleapis.com/spanId"
SAMPLED_KEY = "logging.googleapis.com/trace_sampled"
FIELDS_ATTR = "fields"


class JsonFormatter(logging.Formatter):
    """One JSON object per record, with trace correlation when a span is active."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {"severity": record.levelname, "message": record.getMessage()}
        entry.update(getattr(record, FIELDS_ATTR, {}))
        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:
            # Current docs recommend the bare trace id (no projects/.../traces/ prefix).
            entry[TRACE_KEY] = format(ctx.trace_id, "032x")
            entry[SPAN_KEY] = format(ctx.span_id, "016x")
            entry[SAMPLED_KEY] = ctx.trace_flags.sampled
        return json.dumps(entry, default=str)


def configure_logging() -> None:
    """Send every log line to stdout as JSON. Call once at start up."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


def log_tool_call(tool: str, decision: str, reason: str, **fields) -> None:
    """Write exactly one line per tool call: what was asked, what we decided, and why."""
    level = logging.INFO if decision in ("allowed", "refunded") else logging.WARNING
    logging.getLogger("pebble.tools").log(
        level,
        f"{tool} {decision}: {reason}",
        extra={FIELDS_ATTR: {"tool": tool, "decision": decision, "reason": reason, **fields}},
    )
