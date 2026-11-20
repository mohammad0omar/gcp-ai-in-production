import re
from pathlib import Path

from config import REQUIRED_APIS

FOLDER = Path(__file__).resolve().parents[1]
API_PATTERN = r"[a-z]+\.googleapis\.com"


def test_terraform_apis_match_if_terraform_exists():
    tf_files = list((FOLDER / "terraform").glob("*.tf")) if (FOLDER / "terraform").exists() else []
    if not tf_files:
        return
    text = "\n".join(p.read_text() for p in tf_files)
    assert set(re.findall(rf'"({API_PATTERN})"', text)) == set(REQUIRED_APIS)


def test_every_api_is_in_the_readme_enable_step():
    readme = (FOLDER / "README.md").read_text()
    enable = readme.split("gcloud services enable", 1)[1].split("```", 1)[0]
    assert set(re.findall(API_PATTERN, enable)) == set(REQUIRED_APIS)
