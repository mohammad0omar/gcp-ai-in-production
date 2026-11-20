from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.genai import errors
from rag import embed, ingest
from rag.retry import with_retries


def fake_response(n, dim=768):
    return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1] * dim) for _ in range(n)])


def test_embed_documents_batches_and_uses_document_task(monkeypatch):
    client = MagicMock()
    client.models.embed_content.side_effect = lambda **kw: fake_response(len(kw["contents"]))
    monkeypatch.setattr(embed, "get_client", lambda: client)
    vectors = embed.embed_documents([f"t{i}" for i in range(40)])
    assert len(vectors) == 40
    assert client.models.embed_content.call_count == 1  # 40 short texts fit one request
    config = client.models.embed_content.call_args.kwargs["config"]
    assert config.task_type == "RETRIEVAL_DOCUMENT"
    assert config.output_dimensionality == 768


def test_embed_query_uses_query_task(monkeypatch):
    client = MagicMock()
    client.models.embed_content.side_effect = lambda **kw: fake_response(1)
    monkeypatch.setattr(embed, "get_client", lambda: client)
    embed.embed_query("hello")
    assert client.models.embed_content.call_args.kwargs["config"].task_type == "RETRIEVAL_QUERY"


def test_retries_then_succeeds():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise errors.APIError(503, {"error": {"message": "busy"}})
        return "ok"

    assert with_retries(flaky, sleep=lambda s: None) == "ok"
    assert calls["n"] == 3


def test_does_not_retry_client_errors():
    def bad():
        raise errors.APIError(400, {"error": {"message": "bad"}})

    with pytest.raises(errors.APIError):
        with_retries(bad, sleep=lambda s: None)


def test_gives_up_after_attempts():
    def always():
        raise errors.APIError(503, {"error": {"message": "busy"}})

    with pytest.raises(errors.APIError):
        with_retries(always, attempts=3, sleep=lambda s: None)


def run_ingest(docs, monkeypatch):
    monkeypatch.setattr(ingest, "embed_documents", lambda texts: [[0.1] * 768 for _ in texts])
    cursor = MagicMock()
    count = ingest.write(cursor, ingest.prepare(docs))
    return count, [call.args for call in cursor.execute.call_args_list]


def test_ingest_replaces_a_document_then_inserts(tmp_path, monkeypatch):
    (tmp_path / "fire-code-7.txt").write_text("jurisdiction: city\nExits stay unlocked.")
    count, calls = run_ingest(tmp_path, monkeypatch)
    assert count == 1
    assert calls[0] == (ingest.DELETE_DOC_SQL, ("fire-code-7",))
    sql, params = calls[1]
    assert sql == ingest.INSERT_SQL
    assert params[:4] == ("fire-code-7-0", "fire-code-7", "city", "Exits stay unlocked.")
    assert params[4].startswith("[0.1,")


def test_changed_corpus_leaves_no_stale_rows(tmp_path, monkeypatch):
    long_text = " ".join(f"w{i}" for i in range(1000))
    (tmp_path / "a.txt").write_text(long_text)
    (tmp_path / "b.txt").write_text("short")
    count, calls = run_ingest(tmp_path, monkeypatch)
    assert count == 3  # a has 2 chunks, b has 1
    # Second run: a shrank to one chunk, b was removed. Old a-1 is deleted by the per-doc DELETE.
    (tmp_path / "a.txt").write_text("now short")
    (tmp_path / "b.txt").unlink()
    count, calls = run_ingest(tmp_path, monkeypatch)
    assert count == 1
    assert calls[0] == (ingest.DELETE_DOC_SQL, ("a",))
    assert calls[-1] == (ingest.DELETE_REMOVED_SQL, (["a"],))


def test_embeddings_are_computed_before_any_database_call(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("text")
    order = []
    monkeypatch.setattr(ingest, "embed_documents", lambda t: order.append("embed") or [[0.1] * 768])
    monkeypatch.setattr(ingest, "connect", lambda: order.append("connect") or MagicMock())
    monkeypatch.setattr(ingest, "ROOT", tmp_path.parent)
    (tmp_path.parent / "docs").mkdir(exist_ok=True)
    (tmp_path.parent / "docs" / "a.txt").write_text("text")
    ingest.main()
    assert order == ["embed", "connect"]


def test_empty_docs_directory_does_not_empty_the_table(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "ROOT", tmp_path)
    (tmp_path / "docs").mkdir()
    monkeypatch.setattr(ingest, "connect", lambda: pytest.fail("connected"))
    assert ingest.main() == 1


def test_batches_respect_the_token_budget_and_text_limit():
    big = " ".join(["w"] * 800)  # 1200 estimated tokens
    groups = embed.batches([big] * 30)
    assert sum(len(g) for g in groups) == 30
    assert all(len(g) * 1200 <= 20_000 for g in groups)
    assert len(embed.batches(["a"] * 600)) == 3  # 250 + 250 + 100
    assert embed.batches([]) == []


def test_document_with_no_text_is_rejected_before_any_embedding(tmp_path, monkeypatch):
    (tmp_path / "empty.txt").write_text("jurisdiction: city\n   \n")
    monkeypatch.setattr(ingest, "embed_documents", lambda t: pytest.fail("embedded"))
    with pytest.raises(ValueError, match="empty.txt"):
        ingest.prepare(tmp_path)


def test_first_retry_waits_about_a_second():
    waits = []
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise errors.APIError(503, {"error": {"message": "busy"}})

    with_retries(flaky, sleep=waits.append)
    assert 0.5 <= waits[0] <= 1.0
