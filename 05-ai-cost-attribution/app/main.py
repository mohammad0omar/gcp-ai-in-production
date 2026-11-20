"""Tidewell demo service: one endpoint that makes a labelled Gemini call on Cloud Run.

Cloud Run gives the service a runtime identity; the client finds it through ADC.
There is no API key. The salt comes from Secret Manager as an environment variable.
"""

import json
import os
from contextlib import asynccontextmanager
from functools import lru_cache

from config import GEMINI_LOCATION
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from google import genai
from google.genai import errors
from pydantic import BaseModel, Field

from app import usage


@asynccontextmanager
async def lifespan(_app: FastAPI):
    usage.load_salt()  # the container fails to start if the salt is missing or weak
    yield


app = FastAPI(title="tidewell-ai", lifespan=lifespan)


class Job(BaseModel):
    feature: str
    customer_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=8_000)


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    return genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=GEMINI_LOCATION,
    )


@app.post("/generate")
def generate(job: Job):
    try:
        response = usage.generate(
            get_client(),
            job.feature,
            job.customer_id,
            job.text,
            "Answer in two sentences.",
        )
    except ValueError:
        return JSONResponse({"error": "unknown feature"}, status_code=422)
    except Exception as exc:
        if not (isinstance(exc, errors.APIError) or usage.is_transport_error(exc)):
            raise
        # Log the status code or error class only: no prompt text, no customer id.
        code = exc.code if isinstance(exc, errors.APIError) else type(exc).__name__
        print(json.dumps({"severity": "ERROR", "event": "ai_error", "code": code}))
        return JSONResponse({"error": "model unavailable"}, status_code=503)
    return {"text": response.text or ""}
