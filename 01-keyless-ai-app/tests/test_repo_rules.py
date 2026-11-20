import re
from pathlib import Path

import yaml
from config import REGION, REQUIRED_APIS

FOLDER = Path(__file__).resolve().parents[1]
TERRAFORM = "\n".join(p.read_text() for p in sorted((FOLDER / "terraform").glob("*.tf")))
FORBIDDEN = ["api_key=", "GOOGLE_API_KEY", "GEMINI_API_KEY", "credentials_json", '"private_key"']
SKIP_DIRS = {"tests", ".terraform", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv"}
DEPLOY = FOLDER / ".github-example" / "deploy.yml"


def test_no_keys_anywhere():
    hits = []
    for path in FOLDER.rglob("*"):
        rel = path.relative_to(FOLDER)
        if not path.is_file() or SKIP_DIRS & set(rel.parts):
            continue
        text = path.read_text(errors="ignore")
        hits += [f"{rel}: {word}" for word in FORBIDDEN if word in text]
    assert hits == []


def test_apis_listed():
    # The list lives in locals.required_apis and the service resource must loop over it.
    block = re.search(r"required_apis\s*=\s*\[(.*?)\]", TERRAFORM, re.DOTALL)
    assert block, "locals.required_apis missing"
    listed = set(re.findall(r'"([a-z]+\.googleapis\.com)"', block.group(1)))
    assert listed == set(REQUIRED_APIS)
    resource = re.search(r'resource "google_project_service" "api" \{(.*?)\n\}', TERRAFORM, re.DOTALL)
    assert resource and "for_each = toset(local.required_apis)" in resource.group(1)
    assert re.search(r"service\s*=\s*each\.value", resource.group(1))


def test_terraform_region_default_matches_config():
    match = re.search(r'variable "region" \{.*?default\s*=\s*"([^"]+)"', TERRAFORM, re.DOTALL)
    assert match and match.group(1) == REGION


def test_wif_pins_ids_and_main():
    condition = re.search(r"attribute_condition\s*=\s*(.+)", TERRAFORM).group(1)
    for needle in ("repository_id", "repository_owner_id", "refs/heads/main"):
        assert needle in condition
    assert "attribute.repository_id/" in TERRAFORM


def test_workflow_has_no_secrets():
    text = DEPLOY.read_text()
    workflow = yaml.safe_load(text)
    assert workflow["permissions"]["id-token"] == "write"
    assert not re.search(r"secrets\s*[.\[]", text)  # secrets.NAME and secrets['NAME']
    assert "--no-allow-unauthenticated" in text
    assert "--invoker-iam-check" in text
    assert "--no-invoker-iam-check" not in text
    assert "concurrency" in workflow


def test_runtime_uses_predefined_gemini_role():
    assert 'role    = "roles/aiplatform.user"' in TERRAFORM
    assert "google_project_iam_custom_role" not in TERRAFORM
