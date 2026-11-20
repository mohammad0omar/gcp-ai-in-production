import re
from pathlib import Path

from config import REQUIRED_APIS

FOLDER = Path(__file__).resolve().parents[1]
EM_DASH = chr(0x2014)
API_PATTERN = r"[a-z]+\.googleapis\.com"


def _terraform_apis() -> set[str]:
    """Every API named in a `required_apis = [...]` list in terraform/."""
    found = set()
    for path in (FOLDER / "terraform").glob("*.tf"):
        for block in re.findall(r"required_apis\s*=\s*\[(.*?)\]", path.read_text(), re.DOTALL):
            found |= set(re.findall(API_PATTERN, block))
    return found


def test_terraform_matches_required_apis():
    assert _terraform_apis() == set(REQUIRED_APIS)


def test_exactly_one_project_service_resource_driven_by_the_list():
    text = "\n".join(p.read_text() for p in (FOLDER / "terraform").glob("*.tf"))
    blocks = re.findall(r'resource "google_project_service" "[^"]+" \{(.*?)\n\}', text, re.DOTALL)
    assert len(blocks) == 1
    assert "for_each = toset(local.required_apis)" in blocks[0]
    assert re.search(r"service\s*=\s*each\.value", blocks[0])


def test_readme_enable_step_lists_every_api():
    readme = (FOLDER / "README.md").read_text()
    step = re.search(r"gcloud services enable(.*?)```", readme, re.DOTALL)
    assert step, "README needs a `gcloud services enable` step"
    assert set(re.findall(API_PATTERN, step.group(1))) == set(REQUIRED_APIS)


def test_no_em_dash_anywhere():
    skip = {".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".terraform"}
    bad = [
        str(p.relative_to(FOLDER))
        for p in FOLDER.rglob("*")
        if p.is_file()
        and not skip & set(p.relative_to(FOLDER).parts)
        and p.suffix in {".py", ".md", ".tf", ".toml", ".yml", ".yaml", ".txt"}
        and EM_DASH in p.read_text(errors="ignore")
    ]
    assert bad == []


def test_gcloudignore_blocks_secrets():
    text = (FOLDER / ".gcloudignore").read_text()
    for pattern in (".env", "*.pem", "*.key"):
        assert pattern in text


def test_runtime_uses_predefined_model_role():
    text = (FOLDER / "terraform" / "main.tf").read_text()
    assert 'role    = "roles/aiplatform.user"' in text
    assert "google_project_iam_custom_role" not in text
