import re
from pathlib import Path

from config import REQUIRED_APIS

FOLDER = Path(__file__).resolve().parents[1]
API = r"[a-z]+\.googleapis\.com"


def test_terraform_matches_if_present():
    tf_dir = FOLDER / "terraform"
    if not tf_dir.exists():
        return
    text = "\n".join(p.read_text() for p in tf_dir.glob("*.tf"))
    # Only the `service = "..."` argument of google_project_service resources counts.
    blocks = re.findall(r'resource "google_project_service"[^{]*\{(.*?)\n\}', text, re.DOTALL)
    found = {m for b in blocks for m in re.findall(rf'service\s*=\s*"({API})"', b)}
    assert found == set(REQUIRED_APIS)


def test_readme_enable_step_lists_every_api():
    readme = (FOLDER / "README.md").read_text()
    step = next(line for line in readme.splitlines() if "gcloud services enable" in line)
    assert set(re.findall(API, step)) == set(REQUIRED_APIS)
