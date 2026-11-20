import re
from pathlib import Path

from config import REQUIRED_APIS

FOLDER = Path(__file__).resolve().parents[1]


def test_terraform_apis_match_config():
    text = (FOLDER / "terraform" / "main.tf").read_text()
    block = re.search(r"apis = \[(.*?)\]", text, re.DOTALL).group(1)
    in_terraform = set(re.findall(r'"([a-z]+\.googleapis\.com)"', block))
    assert in_terraform == set(REQUIRED_APIS)
    assert "google_project_service" in text and "toset(local.apis)" in text


def test_readme_enable_command_lists_every_api():
    readme = (FOLDER / "README.md").read_text()
    command = re.search(r"gcloud services enable(.*?)```", readme, re.DOTALL).group(1)
    assert set(re.findall(r"[a-z]+\.googleapis\.com", command)) == set(REQUIRED_APIS)


def test_no_em_dash():
    for path in FOLDER.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".sql", ".tf", ".md", ".toml"}:
            if ".venv" in path.parts or ".terraform" in path.parts:
                continue
            assert chr(0x2014) not in path.read_text(), path
