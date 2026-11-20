import logging

import httpx
import httpx2
import pytest
from app import auth, store
from conftest import AUDIENCE, GOOD, PUSH_SA, push
from google.api_core import exceptions as gax
from google.auth import exceptions as auth_exceptions
from google.genai import errors


def test_redaction_before_model_call(world):
    assert push(world).status_code == 200
    sent = " ".join(world.models.seen)
    for secret in ("jo@example.com", "7700 900123", "4111", "Jo Smith"):
        assert secret not in sent
    assert "[EMAIL_ADDRESS]" in sent and "[PHONE_NUMBER]" in sent
    assert world.db.data["tickets"]["m1"]["category"] == "delivery"


def test_dlp_request_asks_for_all_four_types_and_replaces_with_type(world):
    push(world)
    ((request, timeout),) = world.dlp.requests
    assert request["parent"] == "projects/proj/locations/global"
    names = [t["name"] for t in request["inspect_config"]["info_types"]]
    assert names == [
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "CREDIT_CARD_NUMBER",
        "PERSON_NAME",
    ]
    (transformation,) = request["deidentify_config"]["info_type_transformations"][
        "transformations"
    ]
    assert [t["name"] for t in transformation["info_types"]] == names
    assert transformation["primitive_transformation"] == {
        "replace_with_info_type_config": {}
    }
    assert timeout is not None and world.dlp.retry is None


def test_email_is_wrapped_as_data(world):
    push(world)
    assert world.models.seen[0].startswith("<email>\n") and world.models.seen[
        0
    ].endswith("\n</email>")


def test_duplicate_message_ignored(world):
    world.models.replies = [GOOD, GOOD]
    assert push(world).json()["status"] == "ok"
    assert push(world).json()["status"] == "duplicate"
    assert (
        len(world.models.seen) == 1
    )  # the second delivery never reached DLP or Gemini
    assert world.dlp.calls == 1
    assert len(world.db.data["tickets"]) == 1


def test_competing_deliveries_cannot_create_ticket_and_review(world, monkeypatch):
    """Both deliveries pass the early check; one gets a ticket, the other bad JSON."""
    monkeypatch.setattr(store, "already_processed", lambda message_id: False)
    world.models.replies = [GOOD, "bad", "bad"]
    push(world)
    push(world)
    assert "m1" in world.db.data["tickets"]
    assert world.db.data.get("needs_review", {}) == {}
    assert list(world.db.data["processed"]) == ["m1"]


def test_bad_model_json_goes_to_needs_review(world):
    world.models.replies = [
        "not json",
        '{"category": "weird"}',
    ]  # first try plus one retry
    response = push(world)
    assert response.status_code == 200
    assert len(world.models.seen) == 2
    review = world.db.data["needs_review"]["m1"]
    assert review["reason"] == "invalid_model_output"
    assert "jo@example.com" not in review["redacted_text"]
    assert world.db.data.get("tickets", {}) == {}


def test_retry_recovers_after_one_bad_reply(world):
    world.models.replies = ["oops", GOOD]
    assert push(world).json()["status"] == "ok"


def test_oversize_goes_to_needs_review_without_body(world):
    assert push(world, text="x" * 30_000).status_code == 200
    assert world.db.data["needs_review"]["m1"]["redacted_text"] is None
    assert world.models.seen == []


def test_pii_left_after_dlp_fails_closed(world):
    # The fake DLP only knows the spaced card format, like a detector missing a variant.
    leaked = "My card is 4111-1111-1111-1111, where is my order?"
    assert push(world, text=leaked).status_code == 200
    assert world.models.seen == []
    review = world.db.data["needs_review"]["m1"]
    assert review["reason"] == "possible_pii_left" and review["redacted_text"] is None


def test_logs_never_contain_the_body(world, caplog):
    caplog.set_level(logging.DEBUG)
    push(world)
    assert "jo@example.com" not in caplog.text and "4111" not in caplog.text
    assert "Where is my order" not in caplog.text


def test_push_auth_rejects_wrong_audience(world):
    assert push(world, token=f"https://evil.example|{PUSH_SA}").status_code == 401
    assert world.models.seen == [] and world.dlp.calls == 0


def test_push_auth_rejects_wrong_service_account(world):
    assert (
        push(world, token=f"{AUDIENCE}|other@proj.iam.gserviceaccount.com").status_code
        == 403
    )


def test_push_auth_requires_bearer(world):
    body = {"message": {"data": "", "messageId": "x"}}
    assert world.client.post("/pubsub", json=body).status_code == 401


def test_invalid_issuer_is_401_not_a_crash(world, monkeypatch):
    def bad(*a, **k):
        raise auth_exceptions.GoogleAuthError("wrong issuer")

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", bad)
    assert push(world).status_code == 401


def test_cert_fetch_failure_is_503(world, monkeypatch):
    def down(*a, **k):
        raise auth_exceptions.TransportError("certs unreachable")

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", down)
    assert push(world).status_code == 503


def test_unconfigured_auth_fails_closed(world, monkeypatch):
    monkeypatch.delenv("PUSH_AUDIENCE")
    assert push(world).status_code == 500


def _gemini(exc):
    def boom(*a, **k):
        raise exc

    return boom


@pytest.mark.parametrize(
    "exc",
    [
        errors.ServerError(
            503, {"error": {"message": "busy", "status": "UNAVAILABLE"}}
        ),
        errors.ClientError(
            429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}}
        ),
        errors.ServerError(
            502, {"error": {"message": "gateway", "status": "UNAVAILABLE"}}
        ),
        errors.ClientError(
            408, {"error": {"message": "timeout", "status": "DEADLINE_EXCEEDED"}}
        ),
        httpx.ReadTimeout("slow"),
        httpx2.ReadTimeout("slow"),
    ],
)
def test_transient_gemini_errors_return_503(world, monkeypatch, exc):
    monkeypatch.setattr(world.models, "generate_content", _gemini(exc))
    response = push(world)
    assert response.status_code == 503
    assert "slow" not in response.text and "quota" not in response.text
    assert world.db.data.get("tickets", {}) == {}


def test_permanent_gemini_error_is_500_not_503(world, monkeypatch):
    exc = errors.ClientError(
        400, {"error": {"message": "bad request", "status": "INVALID_ARGUMENT"}}
    )
    monkeypatch.setattr(world.models, "generate_content", _gemini(exc))
    assert push(world).status_code == 500


def test_failed_review_write_is_not_acked(world):
    world.models.replies = ["bad", "bad"]
    world.db.commit_error = gax.ServiceUnavailable("firestore down")
    response = push(world)
    assert response.status_code == 503
    assert "firestore down" not in response.text


def test_failed_ticket_write_is_not_acked(world):
    world.db.commit_error = gax.DeadlineExceeded("slow")
    assert push(world).status_code == 503


def test_permanent_firestore_error_is_500(world):
    world.db.commit_error = gax.PermissionDenied("no role")
    assert push(world).status_code == 500
