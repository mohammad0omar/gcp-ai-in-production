import ast
import re
from pathlib import Path

from config import EMBEDDING_DIM

FOLDER = Path(__file__).resolve().parents[1]
PY_DIRS = ["app", "rag", "eval"]


def test_sql_uses_parameters():
    """No f-string, concatenation or % formatting may build SQL text."""
    offenders = []
    for directory in PY_DIRS:
        for path in (FOLDER / directory).rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.JoinedStr) and re.search(
                    r"\b(SELECT|INSERT|UPDATE|DELETE)\b", ast.unparse(node), re.IGNORECASE
                ):
                    offenders.append(f"{path.name}:{node.lineno} f-string")
                if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "execute":
                    arg = node.args[0] if node.args else None
                    if isinstance(arg, (ast.JoinedStr, ast.BinOp)):
                        offenders.append(f"{path.name}:{node.lineno} built SQL")
    assert offenders == []


def test_schema_matches_config():
    schema = (FOLDER / "sql" / "schema.sql").read_text()
    assert "CREATE EXTENSION IF NOT EXISTS vector" in schema
    assert f"vector({EMBEDDING_DIM})" in schema
    assert "hnsw" in schema and "vector_cosine_ops" in schema
    assert "jurisdiction" in schema


def test_no_em_dash_anywhere():
    skip = {".terraform", "__pycache__", ".venv", ".pytest_cache", ".ruff_cache"}
    dash = chr(0x2014)
    bad = [
        str(path.relative_to(FOLDER))
        for path in FOLDER.rglob("*")
        if path.is_file() and not skip & set(path.parts) and dash in path.read_text(errors="ignore")
    ]
    assert bad == []


def test_gcloudignore_keeps_terraform_state_out():
    lines = (FOLDER / ".gcloudignore").read_text().splitlines()
    assert "*" in lines
    assert not any("terraform" in line and line.startswith("!") for line in lines)
    assert "!Dockerfile" in lines


def test_runtime_requirements_are_pinned():
    pins = [
        line
        for line in (FOLDER / "app" / "requirements.txt").read_text().splitlines()
        if line and not line.startswith(("#", " "))
    ]
    assert pins and all("==" in line for line in pins)
