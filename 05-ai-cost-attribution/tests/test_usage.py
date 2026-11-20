import hashlib
import hmac
import json
from unittest.mock import MagicMock

import pytest
from app import usage
from config import FEATURES, LABEL_MAX_LEN, MODEL_ID
from google.genai import types

SALT = "s" * 32


@pytest.fixture(autouse=True)
def salt(monkeypatch):
    monkeypatch.setenv("CUSTOMER_HASH_SALT", SALT)


def fake_response(prompt=10, out=5, cached=2, thoughts=7):
    meta = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=prompt,
        candidates_token_count=out,
        cached_content_token_count=cached,
        thoughts_token_count=thoughts,
    )
    return types.GenerateContentResponse(usage_metadata=meta)


def run(customer="acme-corp", feature="ticket_summary"):
    client = MagicMock()
    client.models.generate_content.return_value = fake_response()
    usage.generate(client, feature, customer, "hello", "be brief")
    return client


def test_usage_log_line_fields(capsys):
    run()
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["feature"] == "ticket_summary"
    assert record["model"] == MODEL_ID
    assert record["prompt_tokens"] == 10
    assert record["output_tokens"] == 5
    assert record["cached_tokens"] == 2
    assert record["thoughts_tokens"] == 7
    assert record["event"] == "ai_usage"
    assert "customer_hash" not in record
    assert len(record["customer_id"]) == 16


def test_customer_id_hashed(capsys):
    client = run(customer="acme-corp")
    out = capsys.readouterr().out
    assert "acme-corp" not in out
    labels = client.models.generate_content.call_args.kwargs["config"].labels
    assert "acme-corp" not in json.dumps(labels)
    assert json.loads(out)["customer_id"] == labels["customer"]
    assert usage.hash_customer("acme-corp") == usage.hash_customer("acme-corp")
    assert usage.hash_customer("acme-corp") != usage.hash_customer("other")


def test_labels_valid():
    for feature in FEATURES:
        labels = usage.build_labels(feature, usage.hash_customer("c1"))
        for key, value in labels.items():
            assert key == key.lower() and value == value.lower()
            assert 1 <= len(key) <= LABEL_MAX_LEN
            assert len(value) <= LABEL_MAX_LEN


def test_bad_labels_rejected():
    with pytest.raises(ValueError):
        usage.build_labels("Not A Feature", "abc")
    with pytest.raises(ValueError):
        usage.build_labels("ticket_summary", "UPPER")


def test_missing_usage_metadata_counts_zero():
    record = usage.usage_record(
        "smart_reply", "abc", types.GenerateContentResponse(), 5
    )
    assert record["prompt_tokens"] == 0


def test_hash_matches_fixed_hmac_vector():
    expected = hmac.new(SALT.encode(), b"acme-corp", hashlib.sha256).hexdigest()[:16]
    assert usage.hash_customer("acme-corp") == expected


def test_label_length_boundary_and_newline():
    usage.build_labels("ticket_summary", "a" * 63)
    with pytest.raises(ValueError):
        usage.build_labels("ticket_summary", "a" * 64)
    with pytest.raises(ValueError):
        usage.build_labels("ticket_summary", "abc\n")


@pytest.mark.parametrize("value", ["", "short"])
def test_weak_or_missing_salt_rejected(monkeypatch, value):
    monkeypatch.setenv("CUSTOMER_HASH_SALT", value)
    with pytest.raises(RuntimeError):
        usage.hash_customer("c1")
    monkeypatch.delenv("CUSTOMER_HASH_SALT")
    with pytest.raises(RuntimeError):
        usage.load_salt()
