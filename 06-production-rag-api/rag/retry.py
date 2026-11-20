"""Retry a Gemini call on busy or flaky errors: exponential backoff with jitter, few attempts."""

import random
import time
from collections.abc import Callable

from config import GENAI_MAX_ATTEMPTS
from google.genai import errors

RETRYABLE = {429, 500, 503, 504}


def with_retries[T](
    call: Callable[[], T],
    attempts: int = GENAI_MAX_ATTEMPTS,
    base_delay: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    for attempt in range(attempts):
        try:
            return call()
        except errors.APIError as exc:
            if exc.code not in RETRYABLE or attempt == attempts - 1:
                raise
            sleep(base_delay * 2**attempt * random.uniform(0.5, 1.0))
    raise AssertionError("unreachable")
