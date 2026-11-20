import re
from pathlib import Path

import config

README = (Path(__file__).resolve().parents[1] / "README.md").read_text()


def test_worst_case_fits_the_cloud_run_timeout():
    per_call = config.MODEL_ATTEMPTS * config.MODEL_TIMEOUT_S + config.MODEL_MAX_DELAY_S
    assert config.MAX_LLM_CALLS * per_call < config.CLOUD_RUN_TIMEOUT_S


def test_readme_deploys_with_the_same_timeout_and_one_instance():
    assert f"--timeout {config.CLOUD_RUN_TIMEOUT_S}" in README
    assert re.search(r"--max-instances 1\b", README)
