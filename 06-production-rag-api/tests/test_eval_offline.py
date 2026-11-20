"""The golden eval through the real /ask route with no Google calls.

A word-hash embedding stands in for Gemini, an in-memory list for pgvector, and a stub for
the model that cites the best excerpt. This checks the wiring (threshold, citations, scoring)
on every CI run. It does NOT measure Gemini retrieval quality: run eval.run_eval against the
deployed service for that.
"""

import hashlib
import json
import math
import re
from pathlib import Path

import pytest
from app import main
from eval import run_eval
from fastapi.testclient import TestClient

FOLDER = Path(__file__).resolve().parents[1]
STOP = {"the", "a", "an", "of", "is", "in", "on", "to", "be", "for", "can", "how", "what", "when", "does", "while", "per", "must", "may"}


def embed(text: str) -> list[float]:
    vector = [0.0] * 768
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if word not in STOP:
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % 768] += 1.0
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


@pytest.fixture
def corpus():
    return [
        {"doc_id": p.stem, "chunk": p.read_text().split("\n", 1)[1], "vector": embed(p.read_text())}
        for p in sorted((FOLDER / "docs").glob("*.txt"))
    ]


def test_golden_questions_pass_offline(corpus, monkeypatch):
    def search(vector, top_k, jurisdiction=None):
        scored = [
            {**c, "distance": 1 - sum(a * b for a, b in zip(vector, c["vector"], strict=True))}
            for c in corpus
        ]
        return sorted(scored, key=lambda r: r["distance"])[:top_k]

    monkeypatch.setattr(main, "embed_query", embed)
    monkeypatch.setattr(main, "search_chunks", search)
    monkeypatch.setattr(main, "MAX_DISTANCE", 0.95)  # hash vectors are sparse; this is a fixture
    monkeypatch.setattr(main, "generate_answer", lambda q, rows: f"Answer [{rows[0]['doc_id']}].")
    client = TestClient(main.app)
    golden = json.loads((FOLDER / "eval" / "golden.json").read_text())
    hits = run_eval.score(golden, lambda q: client.post("/ask", json={"question": q}).json())
    assert run_eval.verdict(hits) == 0
