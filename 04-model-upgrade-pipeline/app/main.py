"""Larkspur Travel itinerary summariser. The model id comes from the MODEL_ID environment variable."""

import os
from functools import lru_cache

from config import GEMINI_LOCATION, MODEL_ID
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from google import genai
from google.genai import errors
from pydantic import BaseModel, Field

from app.summarise import TRANSPORT_ERRORS, make_client, parse_answer, summarise

MAX_CHARS = 8_000

app = FastAPI(title="itinerary-summariser")


class Itinerary(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_CHARS)


def model_id() -> str:
    # Set per revision by the pipeline: `--set-env-vars MODEL_ID=...`.
    return os.environ.get("MODEL_ID", MODEL_ID)


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    # No key: the client finds the Cloud Run service account through ADC.
    return make_client(os.environ["GOOGLE_CLOUD_PROJECT"], GEMINI_LOCATION)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "model": model_id()}


@app.post("/summarize")
def summarize(itinerary: Itinerary):
    try:
        raw = summarise(get_client(), model_id(), itinerary.text)
    except errors.APIError as exc:
        if exc.code in (429, 503):
            return JSONResponse(
                {"error": "model busy, retry later"}, status_code=503, headers={"Retry-After": "5"}
            )
        raise
    except TRANSPORT_ERRORS:
        # Timeout or transport failure after the retries: a clean 504 instead of a stack trace.
        return JSONResponse({"error": "model did not answer in time"}, status_code=504)
    answer = parse_answer(raw)
    if answer is None:
        # A 502 counts as an error for the canary watch, which is what we want from a bad model.
        return JSONResponse({"error": "model returned an invalid answer"}, status_code=502)
    return answer
