import re
from pathlib import Path

import yaml
from config import REQUIRED_APIS

FOLDER = Path(__file__).resolve().parents[1]
FORBIDDEN = ["api_key=", "GOOGLE_API_KEY", "GEMINI_API_KEY", "credentials_json", '"private_key"']
SKIP_DIRS = {"tests", ".terraform", "__pycache__", ".pytest_cache", ".ruff_cache"}
DEPLOY = FOLDER / ".github-example" / "deploy.yml"


def test_no_keys_anywhere():
    hits = []
    for path in FOLDER.rglob("*"):
        rel = path.relative_to(FOLDER)
        if not path.is_file() or SKIP_DIRS & set(rel.parts):
            continue
        if path.name in ("README.md", "FACTS.md", ".terraform.lock.hcl"):
            continue  # prose may name the things we do not use
        text = path.read_text(errors="ignore")
        hits += [f"{rel}: {word}" for word in FORBIDDEN if word in text]
    assert hits == []


def test_apis_listed():
    tf_text = "\n".join(p.read_text() for p in (FOLDER / "terraform").glob("*.tf"))
    in_terraform = set(re.findall(r'"([a-z]+\.googleapis\.com)"', tf_text))
    assert in_terraform == set(REQUIRED_APIS)


def test_workflow_has_no_secrets():
    text = DEPLOY.read_text()
    workflow = yaml.safe_load(text)
    assert workflow["permissions"]["id-token"] == "write"
    assert not re.search(r"secrets\.", text)
