"""Embed text with Gemini. Documents and questions use different task types."""

import os
from functools import lru_cache

from config import (
    EMBED_BATCH_SIZE,
    EMBEDDING_DIM,
    EMBEDDING_MODEL_ID,
    GEMINI_LOCATION,
    GENAI_TIMEOUT_SECONDS,
)
from google import genai
from google.genai import types

from rag.retry import with_retries


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    # Vertex mode with no key: the client finds the Cloud Run service account through ADC.
    return genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=GEMINI_LOCATION,
        http_options=types.HttpOptions(timeout=GENAI_TIMEOUT_SECONDS * 1000),
    )


def _embed(texts: list[str], task_type: str) -> list[list[float]]:
    config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBEDDING_DIM)
    response = with_retries(
        lambda: get_client().models.embed_content(
            model=EMBEDDING_MODEL_ID, contents=texts, config=config
        )
    )
    return [list(item.values) for item in response.embeddings]


def embed_documents(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        vectors += _embed(texts[start : start + EMBED_BATCH_SIZE], "RETRIEVAL_DOCUMENT")
    return vectors


def embed_query(question: str) -> list[float]:
    return _embed([question], "RETRIEVAL_QUERY")[0]
