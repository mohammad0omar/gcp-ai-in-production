"""Exponential backoff with full jitter.

Full jitter means the wait is a random number between 0 and the exponential ceiling.
Callers that failed at the same moment then retry at different moments, so a burst of
429 errors does not come back as the same burst one second later.
"""

import random
from collections.abc import Callable

BASE_S = 1.0
CAP_S = 30.0


def ceiling(attempt: int, base: float = BASE_S, cap: float = CAP_S) -> float:
    """Upper bound of the wait after failed attempt number `attempt` (1 for the first)."""
    return min(cap, base * 2 ** (attempt - 1))


def full_jitter(
    attempt: int,
    *,
    rng: Callable[[], float] = random.random,
    base: float = BASE_S,
    cap: float = CAP_S,
) -> float:
    """A random wait in [0, ceiling(attempt)]. `rng` returns a float in [0, 1)."""
    return rng() * ceiling(attempt, base, cap)
