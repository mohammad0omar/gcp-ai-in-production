"""Locust file: GemmaUser (vLLM on Cloud Run) and GeminiUser (google-genai) on the same prompt.

Run one side at a time, each in its own process:
    locust -f loadtest/locustfile.py GemmaUser --headless -u 8 -r 1 -t 5m
Each completed request fires ONE Locust request event (name = side, response time = whole
answer) and ONE custom `stream_metrics` event (TTFT in seconds, tokens per second). The
custom event also writes a row to a new results/records-*.csv for report.py.
Neither side retries: one attempt per request, so both runs measure comparable attempts.
"""

import os
import time

import httpx
from config import (
    GEMINI_LOCATION,
    GEMINI_MODEL_ID,
    GEMINI_THINKING_LEVEL,
    GEMMA_MODEL_ID,
)
from locust import User, between, task
from locust.event import EventHook

from loadtest.measure import output_tokens_per_second, ttft_from_stream_timestamps
from loadtest.records import append_record, new_records_path
from loadtest.streams import StreamResult, read_gemini_stream, read_gemma_stream

# One fixed prompt. Your numbers depend on prompt and answer sizes; change this to your own tickets.
PROMPT = (
    "Tag this support ticket with one category and one urgency. "
    "Ticket: My invoice for March shows two charges and the app crashes when I open it."
)
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "128"))
STREAM_DEADLINE_S = 60.0  # whole answer; checked between chunks
READ_TIMEOUT_S = 10.0  # one stalled read; httpx applies it to each chunk, so a stall cannot pass the deadline by much

# Custom event: listeners get side, ttft_s, tokens_per_second, visible_tokens, billed_tokens, ok, started_at.
stream_metrics = EventHook()
_RECORDS_PATH = new_records_path()


@stream_metrics.add_listener
def _write_row(side, ttft_s, tokens_per_second, visible_tokens, billed_tokens, ok, started_at, **_kw):
    append_record(
        _RECORDS_PATH,
        {
            "side": side,
            "ttft_s": "" if ttft_s is None else f"{ttft_s:.4f}",
            "output_tokens": visible_tokens,
            "billed_output_tokens": billed_tokens,
            "tokens_per_second": "" if tokens_per_second is None else f"{tokens_per_second:.2f}",
            "started_at": f"{started_at:.3f}",
            "ended_at": f"{time.time():.3f}",
            "ok": int(ok),
        },
    )


def _finish(environment, side: str, started_at: float, start: float, result: StreamResult) -> None:
    """Fire the one request event and the one custom metrics event for a finished request."""
    ttft = ttft_from_stream_timestamps(start, result.chunk_times)
    tps = output_tokens_per_second(result.visible_tokens, result.chunk_times)
    environment.events.request.fire(
        request_type="STREAM",
        name=side,
        response_time=(time.perf_counter() - start) * 1000,  # Locust wants milliseconds
        response_length=0,  # token counts travel in the custom event
        exception=None if result.ok else RuntimeError(result.error),
        context={},
    )
    stream_metrics.fire(
        side=side,
        ttft_s=ttft,
        tokens_per_second=tps,
        visible_tokens=result.visible_tokens,
        billed_tokens=result.billed_tokens,
        ok=result.ok,
        started_at=started_at,
    )


class GemmaUser(User):
    """Streams /v1/chat/completions from the vLLM service through `gcloud run services proxy`."""

    wait_time = between(0.5, 1.5)

    def on_start(self):
        base = os.environ.get("GEMMA_URL", "http://localhost:9090").rstrip("/")
        self.client = httpx.Client(base_url=base, timeout=httpx.Timeout(STREAM_DEADLINE_S, read=READ_TIMEOUT_S))

    def on_stop(self):
        self.client.close()

    @task
    def tag_ticket(self):
        body = {
            "model": GEMMA_MODEL_ID,
            "messages": [{"role": "user", "content": PROMPT}],
            "max_tokens": MAX_OUTPUT_TOKENS,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        started_at, start = time.time(), time.perf_counter()
        try:
            with self.client.stream("POST", "/v1/chat/completions", json=body) as response:
                response.raise_for_status()
                result = read_gemma_stream(response.iter_lines(), start + STREAM_DEADLINE_S)
        except httpx.HTTPError as error:
            result = StreamResult(error=str(error))
        _finish(self.environment, "gemma", started_at, start, result)


class GeminiUser(User):
    """Streams the same prompt from Gemini with ADC (no API key). Needs roles/aiplatform.user."""

    wait_time = between(0.5, 1.5)

    def on_start(self):
        from google import genai
        from google.genai import types

        self.types = types
        self.client = genai.Client(
            enterprise=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=GEMINI_LOCATION,
            http_options=types.HttpOptions(
                timeout=int(STREAM_DEADLINE_S * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),  # one attempt, like the Gemma side
            ),
        )

    def on_stop(self):
        self.client.close()

    @task
    def tag_ticket(self):
        config = self.types.GenerateContentConfig(
            max_output_tokens=MAX_OUTPUT_TOKENS,
            thinking_config=self.types.ThinkingConfig(thinking_level=GEMINI_THINKING_LEVEL),
        )
        started_at, start = time.time(), time.perf_counter()
        try:
            stream = self.client.models.generate_content_stream(
                model=GEMINI_MODEL_ID, contents=PROMPT, config=config
            )
            result = read_gemini_stream(stream, start + STREAM_DEADLINE_S)
        except Exception as error:  # noqa: BLE001 - any SDK or network error is a failed request
            result = StreamResult(error=str(error))
        _finish(self.environment, "gemini", started_at, start, result)
