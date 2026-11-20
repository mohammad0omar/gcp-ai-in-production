"""Ask the 10 golden questions. Exit 1 if fewer than 8 answers cite the expected document.

Usage: ID_TOKEN=$(gcloud auth print-identity-token) python -m eval.run_eval https://SERVICE_URL
"""

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

import requests

GOLDEN = Path(__file__).with_name("golden.json")
PASS_MARK = 8
REQUEST_TIMEOUT_SECONDS = 120  # matches the 120s Cloud Run timeout of the service


def score(golden: list[dict], ask: Callable[[str], dict]) -> int:
    hits = 0
    for item in golden:
        try:
            answer = ask(item["question"]).get("answer", "")
        except requests.RequestException as exc:
            print(f"failed: {item['question']!r}: {exc}")  # one HTTP error is one failed case
            continue
        hits += f"[{item['expected_doc']}]" in answer
    return hits


def verdict(hits: int) -> int:
    print(f"{hits}/10 answers cited the expected document (need {PASS_MARK})")
    return 0 if hits >= PASS_MARK else 1


def main(url: str) -> int:
    headers = {"Authorization": f"Bearer {os.environ['ID_TOKEN']}"}

    def ask(question: str) -> dict:
        response = requests.post(
            f"{url}/ask", json={"question": question}, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        return response.json()

    return verdict(score(json.loads(GOLDEN.read_text()), ask))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1].rstrip("/")))
