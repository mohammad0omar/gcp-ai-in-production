#!/usr/bin/env bash
# Run every static and unit check for one tutorial folder. Exit 0 means pass.
# A folder with its own pyproject.toml runs its tests in its own uv project.
# LOCAL_SKIP_TF_INIT=1 skips terraform init and validate where the Terraform
# registry cannot be reached; CI never sets it, so CI always validates.
set -euo pipefail

folder="${1:?usage: scripts/check_folder.sh <folder>}"
folder="${folder%/}"
folder="${folder##*/}"
cd "$(dirname "$0")/.."

uvx ruff check "$folder"
python3 -m compileall -q "$folder"

if [ -f "$folder/pyproject.toml" ]; then
  (cd "$folder" && uv run pytest tests -q)
else
  uv run pytest "$folder/tests" -q
fi

# Runtime import smoke test: install only what the container installs, then
# import the entry module. Catches dev-only imports (for example httpx) that
# unit tests hide because the dev environment has them.
if [ -f "$folder/Dockerfile" ]; then
  tmp="$(mktemp -d)"
  if [ -f "$folder/app/requirements.txt" ]; then
    uv venv -q "$tmp/venv"
    uv pip install -q --python "$tmp/venv/bin/python" -r "$folder/app/requirements.txt"
    (cd "$folder" && GOOGLE_CLOUD_PROJECT=smoke-test "$tmp/venv/bin/python" -c "import app.main")
  elif [ -f "$folder/uv.lock" ] && [ -f "$folder/main.py" ]; then
    (cd "$folder" && UV_PROJECT_ENVIRONMENT="$tmp/venv" uv sync -q --frozen --no-dev --no-install-project \
      && GOOGLE_CLOUD_PROJECT=smoke-test TRACE_TO_CLOUD=false "$tmp/venv/bin/python" -c "import main")
  fi
  rm -rf "$tmp"
  echo "runtime import smoke test passed"
fi

if [ -d "$folder/terraform" ]; then
  terraform -chdir="$folder/terraform" fmt -check -recursive
  if [ "${LOCAL_SKIP_TF_INIT:-0}" = "1" ]; then
    echo "WARNING: terraform init and validate skipped (LOCAL_SKIP_TF_INIT=1); CI runs them." >&2
  else
    terraform -chdir="$folder/terraform" init -backend=false -input=false
    terraform -chdir="$folder/terraform" validate
  fi
fi
