from pathlib import Path

FOLDER = Path(__file__).resolve().parents[1]
EM_DASH = chr(0x2014)
SKIP = {".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}


def test_no_em_dash_anywhere():
    bad = [
        str(p.relative_to(FOLDER))
        for p in FOLDER.rglob("*")
        if p.is_file() and not SKIP & set(p.relative_to(FOLDER).parts)
        and EM_DASH in p.read_text(errors="ignore")
    ]
    assert bad == []
