import json
from pathlib import Path

from eval import run_eval

FOLDER = Path(__file__).resolve().parents[1]


def test_golden_has_ten_questions_with_existing_docs():
    golden = json.loads((FOLDER / "eval" / "golden.json").read_text())
    assert len(golden) == 10
    docs = {p.stem for p in (FOLDER / "docs").glob("*.txt")}
    assert {g["expected_doc"] for g in golden} <= docs


def test_passes_with_eight_citations():
    golden = [{"question": f"q{i}", "expected_doc": "a"} for i in range(10)]
    answers = {f"q{i}": {"answer": "x [a]" if i < 8 else "x"} for i in range(10)}
    assert run_eval.score(golden, lambda q: answers[q]) == 8


def test_main_fails_below_threshold(monkeypatch):
    golden = [{"question": f"q{i}", "expected_doc": "a"} for i in range(10)]
    answers = {f"q{i}": {"answer": "x [a]" if i < 7 else "x"} for i in range(10)}
    assert run_eval.verdict(run_eval.score(golden, lambda q: answers[q])) == 1
    assert run_eval.verdict(8) == 0


def test_http_error_counts_as_one_failed_case():
    import requests

    golden = [{"question": f"q{i}", "expected_doc": "a"} for i in range(10)]

    def ask(q):
        if q == "q0":
            raise requests.HTTPError("500")
        return {"answer": "x [a]"}

    assert run_eval.score(golden, ask) == 9
