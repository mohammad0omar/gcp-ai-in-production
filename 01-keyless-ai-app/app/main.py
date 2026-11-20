"""Harbor Lane support-note summariser. Calls Gemini with the Cloud Run identity (ADC)."""

import os
from functools import lru_cache

from config import GEMINI_LOCATION, MODEL_ID
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field

MAX_CHARS = 8_000
BUSY = {"error": "model busy, retry later"}

app = FastAPI(title="note-summariser")


class Note(BaseModel):
    text: str = Field(max_length=MAX_CHARS)


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    # Vertex mode with no key: the client finds the Cloud Run service account through ADC.
    return genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=GEMINI_LOCATION,
    )


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
    return {"summary": response.text or ""}
