"""Firestore access. The Pub/Sub message id is the id of every record about that message.

No client retries here: each call has one timeout and Pub/Sub redelivery is the retry, so the
time budget in config.py holds.

Each message gets a marker in `processed/{id}` plus one result document, written in one
atomic batch. The marker is created with create(), which fails if it exists, so two
deliveries that race can never leave both a ticket and a needs_review record.
"""

from functools import lru_cache

from config import FIRESTORE_TIMEOUT_S
from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore

PROCESSED = "processed"
TICKETS = "tickets"
NEEDS_REVIEW = "needs_review"


@lru_cache(maxsize=1)
def get_db() -> firestore.Client:
    return firestore.Client()


def already_processed(message_id: str) -> bool:
    """Cheap early check so ordinary redeliveries skip DLP and Gemini."""
    marker = get_db().collection(PROCESSED).document(message_id)
    return marker.get(retry=None, timeout=FIRESTORE_TIMEOUT_S).exists


def _finish(collection: str, message_id: str, data: dict) -> bool:
    """Write marker and result atomically. False means another delivery won."""
    db = get_db()
    batch = db.batch()
    stamp = firestore.SERVER_TIMESTAMP
    batch.create(
        db.collection(PROCESSED).document(message_id),
        {"outcome": collection, "at": stamp},
    )
    batch.create(
        db.collection(collection).document(message_id), {**data, "created_at": stamp}
    )
    try:
        batch.commit(retry=None, timeout=FIRESTORE_TIMEOUT_S)
    except AlreadyExists:
        return False
    return True


def save_ticket(message_id: str, ticket: dict) -> bool:
    return _finish(TICKETS, message_id, ticket)


def save_needs_review(
    message_id: str, reason: str, redacted_text: str | None, source: dict
) -> bool:
    # Only redacted text is ever stored, and not even that when DLP may have missed something.
    # `source` (subscription, message id, publish time) lets a person find the original in the
    # dead letter or push subscription while it is retained, without storing the email here.
    data = {"reason": reason, "redacted_text": redacted_text, "source": source}
    return _finish(NEEDS_REVIEW, message_id, data)
