"""The one place that talks to Gemini. The app and the eval both call it, so the eval tests the real prompt."""

import importlib
import json

from google import genai
from google.genai import types

# Bounded calls: 30 s per attempt, 3 attempts with backoff on transient errors (the SDK retries 408, 429, 5xx).
TIMEOUT_MS = 30_000
RETRY_ATTEMPTS = 3

SYSTEM_PROMPT = (
    "You summarise a trip itinerary. Answer with JSON only, no prose, with exactly these keys: "
    '"destination" (string), "days" (integer), "highlights" (list of strings), '
    '"budget_level" (one of "low", "medium", "high").'
)

# Field name -> accepted Python type. The schema check and the app share this.
SCHEMA = {"destination": str, "days": int, "highlights": list, "budget_level": str}
BUDGET_LEVELS = {"low", "medium", "high"}


def _transport_errors() -> tuple[type[Exception], ...]:
    """The HTTP library's error class, found by name so a missing library is not an import error."""
    found = []
    for name in ("httpx", "httpx2"):
        try:
            found.append(importlib.import_module(name).HTTPError)
        except (ImportError, AttributeError):
            continue
    return tuple(found)


# Timeouts and connection failures after the SDK's own retries. An empty tuple catches nothing.
TRANSPORT_ERRORS = _transport_errors()


def make_client(project: str, location: str) -> genai.Client:
    """Vertex mode with no key (ADC), with a timeout and a retry budget. The app and the eval share it."""
    return genai.Client(
        vertexai=True,
        project=project,
        location=location,
        http_options=types.HttpOptions(
            timeout=TIMEOUT_MS,
            retry_options=types.HttpRetryOptions(attempts=RETRY_ATTEMPTS),
        ),
    )


def summarise(client, model: str, text: str) -> str:
    """Call the model and return its raw text. `client` is a google-genai Client or a test double."""
    response = client.models.generate_content(
        model=model,
        contents=text,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )
    return response.text or ""


def parse_answer(raw: str) -> dict | None:
    """Return the parsed answer, or None when it is not valid JSON that matches SCHEMA."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or set(data) != set(SCHEMA):
        return None
    for key, kind in SCHEMA.items():
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, kind):
            return None
    if data["budget_level"] not in BUDGET_LEVELS:
        return None
    if not all(isinstance(item, str) for item in data["highlights"]):
        return None
    return data
