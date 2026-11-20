"""Fennel Health Supplies inbox. Pub/Sub push -> redact -> Gemini -> Firestore.

Status codes are the contract with Pub/Sub: 2xx acks the message, anything else is
retried (and after 5 attempts goes to the dead letter topic).
"""

import base64
import binascii
import logging

import httpx
from config import MAX_RAW_CHARS
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from google.api_core import exceptions as gax
from google.genai import errors as genai_errors
from pydantic import BaseModel

from app import store
from app.auth import verify_push
from app.redact import looks_unredacted, redact
from app.triage import triage

# Never log the email body, raw or redacted. Log ids and outcomes only.
log = logging.getLogger("inbox")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="pii-safe-inbox")


class PubsubMessage(BaseModel):
    data: str = ""
    messageId: str


class PushBody(BaseModel):
    message: PubsubMessage
    subscription: str = ""


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _decode(data: str) -> str:
    try:
        return base64.b64decode(data, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        raise HTTPException(
            status_code=400, detail="message data is not base64 text"
        ) from None


# The Gen AI SDK can use httpx or its fork httpx2 (it depends on both), so catch both bases.
HTTP_TRANSPORT_ERRORS: tuple[type[Exception], ...] = (httpx.TransportError,)
HTTP_BASE_ERRORS: tuple[type[Exception], ...] = ()
try:
    import httpx2

    HTTP_TRANSPORT_ERRORS += (httpx2.TransportError,)
    HTTP_BASE_ERRORS += (httpx2.HTTPError,)
except ImportError:  # pragma: no cover
    pass

# Errors that a retry can fix. Pub/Sub redelivers after any non-2xx, so these answer 503.
TRANSIENT = (
    gax.ServiceUnavailable,
    gax.DeadlineExceeded,
    gax.ResourceExhausted,
    gax.Aborted,
    gax.InternalServerError,
    gax.RetryError,
    *HTTP_TRANSPORT_ERRORS,
)
# Same codes the Gen AI SDK treats as retryable.
TRANSIENT_HTTP = (408, 429, 500, 502, 503, 504)


# Everything a Google client or the HTTP layer can raise. Anything else is a bug and surfaces
# as FastAPI's plain 500, which Pub/Sub also retries.
UPSTREAM_ERRORS = (
    gax.GoogleAPICallError,
    gax.RetryError,
    genai_errors.APIError,
    httpx.HTTPError,
    *HTTP_BASE_ERRORS,
)


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, genai_errors.APIError):
        return exc.code in TRANSIENT_HTTP
    return isinstance(exc, TRANSIENT)


def _process(message_id: str, raw: str) -> dict:
    if store.already_processed(message_id):
        log.info("duplicate message_id=%s ignored", message_id)
        return {"status": "duplicate"}

    if len(raw) > MAX_RAW_CHARS:
        store.save_needs_review(message_id, "too_large", None)
        log.warning(
            "message_id=%s too large (%d chars), needs_review", message_id, len(raw)
        )
        return {"status": "needs_review"}

    redacted = redact(raw)
    if looks_unredacted(redacted):
        # DLP is probabilistic. If something email-like or card-like survived, do not send
        # it to a model, and do not store it either.
        store.save_needs_review(message_id, "possible_pii_left", None)
        log.warning(
            "message_id=%s possible PII left after DLP, needs_review", message_id
        )
        return {"status": "needs_review"}

    ticket = triage(redacted)
    if ticket is None:
        store.save_needs_review(message_id, "invalid_model_output", redacted)
        log.warning("message_id=%s invalid model output, needs_review", message_id)
        return {"status": "needs_review"}  # 200: redelivery would give the same answer

    created = store.save_ticket(message_id, ticket.model_dump())
    log.info(
        "message_id=%s category=%s created=%s", message_id, ticket.category, created
    )
    return {"status": "ok" if created else "duplicate"}


@app.post("/pubsub")
def pubsub(body: PushBody, authorization: str | None = Header(default=None)):
    verify_push(authorization)
    message_id = body.message.messageId
    raw = _decode(body.message.data)
    try:
        return _process(message_id, raw)
    except UPSTREAM_ERRORS as exc:
        # Any failure before the final write is a non-2xx, so the message is never acked
        # without a ticket or a review record. Responses carry no detail from the error.
        if _is_transient(exc):
            log.error(
                "message_id=%s transient error %s", message_id, type(exc).__name__
            )
            return JSONResponse({"error": "temporary failure, retry"}, status_code=503)
        log.error("message_id=%s permanent error %s", message_id, type(exc).__name__)
        return JSONResponse({"error": "processing failed"}, status_code=500)
