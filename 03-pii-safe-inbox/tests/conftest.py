"""Fakes for every Google client. Nothing here touches the network."""

import base64
import json
import re
from types import SimpleNamespace

import pytest
from app import auth, redact, store, triage
from fastapi.testclient import TestClient
from google.api_core.exceptions import AlreadyExists

AUDIENCE = "https://inbox.fennel-health.example"
PUSH_SA = "pusher@proj.iam.gserviceaccount.com"
RAW = "Hi, I am Jo Smith, jo@example.com, phone +44 7700 900123, card 4111 1111 1111 1111. Where is my order?"
GOOD = json.dumps(
    {"category": "delivery", "urgency": "normal", "summary": "Asks where an order is."}
)


class FakeDlp:
    """Stands in for DLP. It redacts only the info types the request asks for."""

    def __init__(self):
        self.requests = []

    @property
    def calls(self):
        return len(self.requests)

    def deidentify_content(self, request, retry="unset", timeout=None):
        self.requests.append((request, timeout))
        self.retry = retry
        wanted = {t["name"] for t in request["inspect_config"]["info_types"]}
        text = request["item"]["value"]
        if "EMAIL_ADDRESS" in wanted:
            text = re.sub(r"\S+@\S+?,", "[EMAIL_ADDRESS],", text)
        if "PHONE_NUMBER" in wanted:
            text = text.replace("+44 7700 900123", "[PHONE_NUMBER]")
        if "CREDIT_CARD_NUMBER" in wanted:
            text = text.replace("4111 1111 1111 1111", "[CREDIT_CARD_NUMBER]")
        if "PERSON_NAME" in wanted:
            text = text.replace("Jo Smith", "[PERSON_NAME]")
        return SimpleNamespace(item=SimpleNamespace(value=text))


class FakeModels:
    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def generate_content(self, model, contents, config):
        self.seen.append(contents)
        return SimpleNamespace(text=self.replies.pop(0))


class FakeDoc:
    def __init__(self, docs, key, name):
        self.docs, self.key, self.name = docs, key, name

    def get(self, retry="unset", timeout=None):
        assert retry is None and timeout is not None  # bounded: no hidden retry window
        return SimpleNamespace(exists=self.key in self.docs)


class FakeBatch:
    def __init__(self, db):
        self.db, self.writes = db, []

    def create(self, doc, data):
        self.writes.append((doc, data))

    def commit(self, retry="unset", timeout=None):
        assert retry is None and timeout is not None
        if self.db.commit_error:
            raise self.db.commit_error
        if any(doc.key in doc.docs for doc, _ in self.writes):
            raise AlreadyExists("exists")  # all or nothing, like a real batch
        for doc, data in self.writes:
            doc.docs[doc.key] = data


class FakeDb:
    def __init__(self):
        self.data = {}
        self.commit_error = None

    def collection(self, name):
        docs = self.data.setdefault(name, {})
        return SimpleNamespace(document=lambda key: FakeDoc(docs, key, name))

    def batch(self):
        return FakeBatch(self)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    monkeypatch.setenv("PUSH_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("PUSH_SERVICE_ACCOUNT", PUSH_SA)


@pytest.fixture
def world(monkeypatch, env):
    dlp, db = FakeDlp(), FakeDb()
    models = FakeModels([GOOD])
    monkeypatch.setattr(redact, "get_dlp_client", lambda: dlp)
    monkeypatch.setattr(triage, "get_client", lambda: SimpleNamespace(models=models))
    monkeypatch.setattr(store, "get_db", lambda: db)

    def fake_verify(token, request, audience=None):
        aud, _, email = token.partition("|")
        if aud != audience:
            raise ValueError("Token has wrong audience")
        return {"email": email, "email_verified": True}

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)
    from app.main import app

    return SimpleNamespace(
        client=TestClient(app, raise_server_exceptions=False),
        dlp=dlp,
        db=db,
        models=models,
    )


def push(world, message_id="m1", text=RAW, token=f"{AUDIENCE}|{PUSH_SA}"):
    body = {
        "message": {
            "data": base64.b64encode(text.encode()).decode(),
            "messageId": message_id,
        },
        "subscription": "projects/proj/subscriptions/s",
    }
    return world.client.post(
        "/pubsub", json=body, headers={"Authorization": f"Bearer {token}"}
    )
