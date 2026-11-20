import re
from pathlib import Path

from config import REQUIRED_APIS

FOLDER = Path(__file__).resolve().parents[1]
API = r"[a-z]+\.googleapis\.com"


def test_terraform_apis_match_config_if_terraform_exists():
    tf_dir = FOLDER / "terraform"
    if not tf_dir.exists():
        return
    text = "\n".join(p.read_text() for p in tf_dir.glob("*.tf"))
    assert set(re.findall(rf'"({API})"', text)) == set(REQUIRED_APIS)


def test_readme_enable_step_lists_exactly_the_required_apis():
    readme = (FOLDER / "README.md").read_text()
    enable_step = re.search(r"gcloud services enable(.*?)```", readme, re.DOTALL).group(1)
    found = re.findall(API, enable_step)
    assert sorted(found) == sorted(REQUIRED_APIS)


def test_deploy_scripts_do_not_enable_apis_a_second_time():
    for name in ("deploy_gemma.sh", "delete_gemma.sh"):
        assert "services enable" not in (FOLDER / "deploy" / name).read_text()


def test_no_em_dash_anywhere():
    bad = [
        str(p.relative_to(FOLDER))
        for p in FOLDER.rglob("*")
        if p.is_file()
        and ".venv" not in p.parts
        and "__pycache__" not in p.parts
        and p.suffix in {".py", ".md", ".toml", ".sh", ".txt"}
        and chr(0x2014) in p.read_text(errors="ignore")
    ]
    assert bad == []
