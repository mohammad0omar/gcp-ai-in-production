"""Score a model on the golden set. Exit 1 when the score is under the threshold.

Usage: python eval/run_eval.py --model gemini-3.8-flash --golden eval/golden.jsonl --threshold 0.9
A case scores 0 when the answer is not valid JSON of the right shape (schema check),
otherwise the share of expected fields that match exactly.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.summarise import TRANSPORT_ERRORS, parse_answer, summarise
from google.genai import errors


def score_answer(raw: str, expected: dict) -> tuple[float, bool]:
    """Return (score, schema_ok) for one raw model answer."""
    answer = parse_answer(raw)
    if answer is None:
        return 0.0, False
    matches = sum(1 for key, value in expected.items() if answer.get(key) == value)
    return matches / len(expected), True


def load_cases(path: str) -> list[dict]:
    lines = Path(path).read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def run_eval(model: str, cases: list[dict], client, threshold: float) -> tuple[float, int]:
    """Run every case, print a table, return (mean score, exit code)."""
    print(f"{'case':<16}{'schema':<8}{'score':<6}")
    total = 0.0
    malformed = 0
    for case in cases:
        try:
            raw = summarise(client, model, case["text"])
        except (errors.APIError, *TRANSPORT_ERRORS) as exc:  # one failing call scores 0, it must not hide the other cases
            print(f"{case['id']:<16}{'error':<8}{0.0:<6}  {type(exc).__name__}")
            continue
        score, schema_ok = score_answer(raw, case["expected"])
        total += score
        malformed += 0 if schema_ok else 1
        print(f"{case['id']:<16}{'ok' if schema_ok else 'BAD':<8}{score:<6.2f}")
    mean = total / len(cases) if cases else 0.0
    # Two gates: the mean score, and a schema gate where ONE malformed answer is enough to fail.
    ok = mean >= threshold and malformed == 0
    verdict = "PASS" if ok else "FAIL"
    print(f"model={model} score={mean:.3f} threshold={threshold} malformed={malformed} {verdict}")
    return mean, 0 if ok else 1


def main(argv: list[str] | None = None, client=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--golden", default="eval/golden.jsonl")
    parser.add_argument("--threshold", type=float, default=0.9)
    args = parser.parse_args(argv)
    if client is None:
        from app.summarise import make_client
        from config import GEMINI_LOCATION

        client = make_client(os.environ["GOOGLE_CLOUD_PROJECT"], GEMINI_LOCATION)
    _, code = run_eval(args.model, load_cases(args.golden), client, args.threshold)
    return code


if __name__ == "__main__":
    sys.exit(main())
