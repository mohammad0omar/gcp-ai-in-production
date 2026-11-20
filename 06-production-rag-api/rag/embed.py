"""Embed text with Gemini. Documents and questions use different task types."""

import os
from functools import lru_cache

from config import (
    EMBED_MAX_TEXTS_PER_BATCH,
    EMBED_TOKEN_BUDGET,
    EMBEDDING_DIM,
    EMBEDDING_MODEL_ID,
    GEMINI_LOCATION,
    GENAI_TIMEOUT_SECONDS,
    TOKENS_PER_WORD,
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


def batches(texts: list[str]) -> list[list[str]]:
    """Group texts so each request stays under the token budget and the text-count limit."""
    result: list[list[str]] = []
    current: list[str] = []
    used = 0.0
    for text in texts:
        tokens = len(text.split()) * TOKENS_PER_WORD
        if current and (used + tokens > EMBED_TOKEN_BUDGET or len(current) >= EMBED_MAX_TEXTS_PER_BATCH):
            result.append(current)
            current, used = [], 0.0
        current.append(text)
        used += tokens
    return result + [current] if current else result


def embed_documents(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for batch in batches(texts):
        vectors += _embed(batch, "RETRIEVAL_DOCUMENT")
    return vectors


def embed_query(question: str) -> list[float]:
    return _embed([question], "RETRIEVAL_QUERY")[0]
