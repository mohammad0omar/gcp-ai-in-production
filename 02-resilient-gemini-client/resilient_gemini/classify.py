"""Decide whether an error is worth a retry, and read a Retry-After hint from it."""

import time
from collections.abc import Callable
from datetime import UTC
from email.utils import parsedate_to_datetime

import httpx
from google.genai import errors

# Transient: timeout, rate limit, server fault, bad gateway, unavailable, gateway timeout.
# The Google retry strategy page lists 408, 429 and 5xx as transient. We keep the 5xx list
# short and explicit: 500, 502, 503, 504.
RETRYABLE_CODES = frozenset({408, 429, 500, 502, 503, 504})


def is_retryable(error: BaseException) -> bool:
    """True for 408, 429, 500, 502, 503, 504 and timeouts. 400, 403, 404 and the rest are not."""
    if isinstance(error, errors.APIError):
        return error.code in RETRYABLE_CODES
    return isinstance(error, httpx.TimeoutException | TimeoutError)


def retry_after_seconds(
    error: BaseException, now: Callable[[], float] = time.time
) -> float | None:
    """Seconds to wait from a Retry-After header (delta-seconds or HTTP-date), or None.

    `now` is the wall clock in epoch seconds, injected so tests do not depend on the date.
    """
    headers = getattr(getattr(error, "response", None), "headers", None)
    if not headers:
        return None
    value = headers.get("retry-after") or headers.get("Retry-After")
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:  # asctime form and "-0000" carry no zone: HTTP dates are UTC
                when = when.replace(tzinfo=UTC)
            seconds = when.timestamp() - now()
        except (TypeError, ValueError):
            return None
    return max(0.0, seconds)
