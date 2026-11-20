"""Harbor Lane support-note summariser. Calls Gemini with the Cloud Run identity (ADC)."""

import importlib
import os
import threading

from config import GEMINI_LOCATION, GEMINI_TIMEOUT_SECONDS, MODEL_ID
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field

MAX_CHARS = 8_000
BUSY = {"error": "model busy, retry later"}

app = FastAPI(title="note-summariser")



def _transport_errors() -> tuple[type[Exception], ...]:
    """Timeout and network errors from the HTTP library the installed google-genai uses.

    google-genai 3.x uses httpx2, older versions use httpx. Import by name so a missing
    library cannot stop the app from starting.
    """
    found = []
    for name in ("httpx2", "httpx"):
        try:
            found.append(importlib.import_module(name).TransportError)
        except (ImportError, AttributeError):
            continue
    return tuple(found)


TRANSPORT_ERRORS = _transport_errors()
_client: genai.Client | None = None
_client_lock = threading.Lock()


class Note(BaseModel):
    text: str = Field(max_length=MAX_CHARS)


def get_client() -> genai.Client:
    """Create the client once, on first use, even when cold requests arrive together."""
    global _client
    with _client_lock:
        if _client is None:
            # Vertex mode with no key: the client finds the Cloud Run service account through ADC.
            _client = genai.Client(
                vertexai=True,
                project=os.environ["GOOGLE_CLOUD_PROJECT"],
                location=GEMINI_LOCATION,
                http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_SECONDS * 1000),  # milliseconds
            )
    return _client


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/summarize")
def summarize(note: Note):
    try:
        response = get_client().models.generate_content(
            model=MODEL_ID,
            contents=note.text,
            config=types.GenerateContentConfig(
                system_instruction="Summarise this support note in two sentences."
            ),
        )
    except errors.APIError as exc:
        if exc.code in (429, 503):
            return JSONResponse(BUSY, status_code=503, headers={"Retry-After": "5"})
        raise
    except TRANSPORT_ERRORS:
        # Timeout or network failure: do not leave the caller waiting for the Cloud Run deadline.
        return JSONResponse({"error": "model unreachable"}, status_code=504)
    if not response.text:
        # Blocked or empty answer: say so instead of returning a blank summary with 200.
        return JSONResponse({"error": "model returned no summary"}, status_code=502)
    return {"summary": response.text}
