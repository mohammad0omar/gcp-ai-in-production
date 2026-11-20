import sys
from pathlib import Path

# The agent package lives in agents/; the folder name starts with a digit, so
# put both on the path to import config and the package.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agents"))
