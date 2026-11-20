"""Call Gemini, label the request for billing, and log one usage line per call.

The log line goes to stdout as JSON. Cloud Logging reads it as jsonPayload and the
log sink copies it to BigQuery. The raw customer id never leaves this module.
"""

import hashlib
import hmac
import json
import os
import re
import sys
import time

from config import (
    FEATURES,
    LABEL_CUSTOMER,
    LABEL_FEATURE,
    LABEL_MAX_LEN,
    MIN_SALT_CHARS,
    MODEL_ID,
    USAGE_EVENT,
)
from google import genai
from google.genai import types

KEY_PATTERN = re.compile(r"[a-z][a-z0-9_-]*")  # keys start with a letter; use fullmatch
VALUE_PATTERN = re.compile(r"[a-z0-9_-]*")
# The timeout applies to ONE attempt. With 3 attempts the caller can wait about 90 s plus
# back-off. A retry replays the whole generation, so a retried call can be billed twice.
# The usage line is written once per generate() call, after the final response.
TIMEOUT_MS = 30_000
RETRY = types.HttpRetryOptions(attempts=3, http_status_codes=[429, 503])


def load_salt() -> bytes:
    """Read the hash key from the environment. Fail early and clearly if it is weak."""
    salt = os.environ.get("CUSTOMER_HASH_SALT", "")
    if len(salt) < MIN_SALT_CHARS:
        raise RuntimeError(
            f"CUSTOMER_HASH_SALT must be set to a random value of at least {MIN_SALT_CHARS} chars"
        )
    return salt.encode()


def is_transport_error(exc: Exception) -> bool:
    """True for timeouts and connection failures the SDK re-raises after its retries.

    The SDK uses httpx or httpx2 (or aiohttp), and httpx2 errors are not httpx errors, so
    match on the module name instead of importing a client library that may be missing.
    """
    module = type(exc).__module__
    # google.auth.exceptions holds TransportError and RefreshError (token fetch failures).
    return (
        module.split(".")[0] in {"httpx", "httpx2", "aiohttp"}
        or module == "google.auth.exceptions"
        or isinstance(exc, (TimeoutError, ConnectionError))
    )


def hash_customer(customer_id: str) -> str:
    """Keyed hash, 16 hex chars: stable per customer, useless without the salt."""
    return hmac.new(load_salt(), customer_id.encode(), hashlib.sha256).hexdigest()[:16]


def build_labels(feature: str, customer_hash: str) -> dict[str, str]:
    """Request labels that Cloud Billing will carry. Raises on a value the API would reject."""
    if feature not in FEATURES:
        raise ValueError(f"unknown feature: {feature}")
    labels = {LABEL_FEATURE: feature, LABEL_CUSTOMER: customer_hash}
    for key, value in labels.items():
        if not KEY_PATTERN.fullmatch(key) or not VALUE_PATTERN.fullmatch(value):
            raise ValueError(f"invalid label: {key}={value!r}")
        if not 1 <= len(key) <= LABEL_MAX_LEN or len(value) > LABEL_MAX_LEN:
            raise ValueError(f"label too long: {key}")
    return labels


def usage_record(
    feature: str,
    customer_hash: str,
    response: types.GenerateContentResponse,
    latency_ms: int,
) -> dict:
    """Flat dict with the token counts. Missing counts become 0."""
    meta = response.usage_metadata
    return {
        "event": USAGE_EVENT,
        "feature": feature,
        "customer_id": customer_hash,  # the HASH, never the raw id
        "model": MODEL_ID,
        "prompt_tokens": (meta.prompt_token_count if meta else 0) or 0,
        "output_tokens": (meta.candidates_token_count if meta else 0) or 0,
        "cached_tokens": (meta.cached_content_token_count if meta else 0) or 0,
        "thoughts_tokens": (meta.thoughts_token_count if meta else 0) or 0,
        "latency_ms": latency_ms,
    }


def log_usage(record: dict) -> None:
    """One JSON line on stdout. `severity` is a special field Cloud Logging understands."""
    print(json.dumps({"severity": "INFO", **record}), file=sys.stdout, flush=True)


def generate(
    client: genai.Client, feature: str, customer_id: str, contents: str, system: str
) -> types.GenerateContentResponse:
    """Call Gemini with labels, a timeout and retries on 429 and 503, then log usage."""
    customer_hash = hash_customer(customer_id)
    config = types.GenerateContentConfig(
        system_instruction=system,
        labels=build_labels(feature, customer_hash),
        http_options=types.HttpOptions(timeout=TIMEOUT_MS, retry_options=RETRY),
    )
    started = time.monotonic()
    response = client.models.generate_content(
        model=MODEL_ID, contents=contents, config=config
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    log_usage(usage_record(feature, customer_hash, response, latency_ms))
    return response
