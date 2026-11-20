"""call(): one prompt, retries per model, fallback across models, one overall deadline.

Retried: 408, 429, 500, 502, 503, 504 and timeouts. Never retried: 400, 403, 404, others.
"""

import os
import random
import time
from collections.abc import Callable
from dataclasses import dataclass

from google import genai
from google.genai import types

from resilient_gemini import backoff
from resilient_gemini.classify import is_retryable, retry_after_seconds


class ResilientError(Exception):
    """Base class for errors raised by call()."""


class NonRetryableError(ResilientError):
    """The API said the request itself is wrong (400, 403, 404, ...). Retrying cannot help."""


class DeadlineExceeded(ResilientError):
    """The overall timeout_s ran out before any model answered in time."""


class AllModelsFailed(ResilientError):
    """Every model used all its attempts and kept failing with retryable errors."""


@dataclass(frozen=True)
class Result:
    text: str
    model_used: str
    attempts: int  # total calls made, across all models
    cached_tokens: int


def make_client(location: str | None = None) -> genai.Client:
    """Vertex AI client using Application Default Credentials.

    `location` defaults to the REGION environment variable, then `global` (the global endpoint).
    """
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise RuntimeError("Set GOOGLE_CLOUD_PROJECT to your project id.")
    return genai.Client(
        vertexai=True,
        project=project,
        location=location or os.environ.get("REGION", "global"),
    )


def _request_config(remaining_s: float, system_instruction: str | None) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=system_instruction,
        # One SDK request per attempt: the SDK must not retry or follow continuation
        # tokens behind our back, or our attempt count and deadline would be wrong.
        automatic_continuation=False,
        http_options=types.HttpOptions(
            # Milliseconds. Never ask for more time than is left.
            timeout=max(1, int(remaining_s * 1000)),
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def call(
    prompt: str,
    *,
    models: list[str],
    timeout_s: float,
    max_attempts: int,
    client=None,
    system_instruction: str | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    wall_clock: Callable[[], float] = time.time,
    rng: Callable[[], float] = random.random,
) -> Result:
    """Ask the first model; retry transient errors; move to the next model after max_attempts.

    The deadline starts before the client is built, and each request's timeout is the time
    left. Client setup (credential lookup) is inside the clock but cannot be interrupted. An answer that arrives after it is
    rejected. Limit: the SDK timeout applies to each network operation, so one slow request
    can overrun the deadline a little before we notice; we never return its answer.
    """
    deadline = clock() + timeout_s
    owned = client is None
    client = client or make_client()
    try:
        return _run(client, prompt, models, timeout_s, max_attempts, system_instruction,
                    deadline, sleep, clock, wall_clock, rng)
    finally:
        if owned:
            client.close()


def _run(client, prompt, models, timeout_s, max_attempts, system_instruction,
         deadline, sleep, clock, wall_clock, rng) -> Result:
    attempts = 0
    last_error: BaseException | None = None
    too_late = f"no answer within {timeout_s}s"

    for model in models:
        for attempt in range(1, max_attempts + 1):
            remaining = deadline - clock()
            if remaining <= 0:
                raise DeadlineExceeded(too_late) from last_error
            attempts += 1
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=_request_config(remaining, system_instruction),
                )
            except Exception as error:
                if clock() >= deadline:  # every exit path honours the deadline
                    raise DeadlineExceeded(too_late) from error
                if not is_retryable(error):
                    raise NonRetryableError(str(error)) from error
                last_error = error
                is_last_model = model == models[-1]
                if attempt == max_attempts and is_last_model:
                    break  # nothing left to try
                hint = retry_after_seconds(error, wall_clock)
                if attempt == max_attempts:
                    delay = hint or 0.0  # moving to the next model: wait only if told to
                elif hint is not None:
                    delay = hint
                else:
                    delay = backoff.full_jitter(attempt, rng=rng)
                if clock() + delay >= deadline:
                    raise DeadlineExceeded(too_late) from error
                if delay > 0:
                    sleep(delay)
                continue
            if clock() > deadline:
                raise DeadlineExceeded(too_late)  # answer came too late, drop it
            usage = response.usage_metadata
            cached = (usage.cached_content_token_count or 0) if usage else 0
            return Result(response.text or "", model, attempts, cached)

    raise AllModelsFailed(f"{attempts} attempts failed on {models}") from last_error
