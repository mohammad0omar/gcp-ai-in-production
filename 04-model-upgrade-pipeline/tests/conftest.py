import sys
from pathlib import Path

# The folder name starts with a digit, so put it on the path to import config, app and pipeline.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
