"""REQUIRED_APIS, the Terraform resource that enables APIs, and the README enable command agree."""

import re
from pathlib import Path

from config import REQUIRED_APIS

FOLDER = Path(__file__).resolve().parents[1]
MAIN_TF = (FOLDER / "terraform" / "main.tf").read_text()


def terraform_api_list() -> set[str]:
    block = re.search(r"required_apis = \[(.*?)\]", MAIN_TF, re.DOTALL).group(1)
    return set(re.findall(r'"([a-z]+\.googleapis\.com)"', block))


def test_terraform_list_matches_config():
    assert terraform_api_list() == set(REQUIRED_APIS)


def test_project_service_resource_uses_that_list():
    resource = re.search(r'resource "google_project_service" "api" \{(.*?)\n\}', MAIN_TF, re.DOTALL).group(1)
    assert "for_each = toset(local.required_apis)" in resource
    assert "service            = each.value" in resource


def test_no_other_api_names_in_terraform():
    everything = "\n".join(p.read_text() for p in (FOLDER / "terraform").glob("*.tf"))
    assert set(re.findall(r'"([a-z]+\.googleapis\.com)"', everything)) == set(REQUIRED_APIS)


def test_readme_enable_command_lists_every_api():
    readme = (FOLDER / "README.md").read_text()
    command = re.search(r"gcloud services enable(.*?)```", readme, re.DOTALL).group(1)
    assert set(re.findall(r"[a-z]+\.googleapis\.com", command)) == set(REQUIRED_APIS)
