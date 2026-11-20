#!/usr/bin/env bash
# Run every static and unit check for one tutorial folder. Exit 0 means pass.
set -euo pipefail

folder="${1:?usage: scripts/check_folder.sh <folder>}"
folder="${folder%/}"

uvx ruff check "$folder"
python3 -m compileall -q "$folder"
uv run pytest "$folder/tests" -q

if [ -d "$folder/terraform" ]; then
  terraform -chdir="$folder/terraform" fmt -check -recursive
  terraform -chdir="$folder/terraform" init -backend=false -input=false
  terraform -chdir="$folder/terraform" validate
fi
