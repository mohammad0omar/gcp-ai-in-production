import re
from pathlib import Path

from config import (
    ACK_DEADLINE_S,
    AUTH_TIMEOUT_S,
    DLP_TIMEOUT_S,
    FIRESTORE_CALLS,
    FIRESTORE_TIMEOUT_S,
    MODEL_ATTEMPTS,
    MODEL_TIMEOUT_S,
    REQUEST_TIMEOUT_S,
    REQUIRED_APIS,
)

FOLDER = Path(__file__).resolve().parents[1]
TF = "\n".join(p.read_text() for p in (FOLDER / "terraform").glob("*.tf"))


def test_apis_listed():
    """Terraform's required_apis local, the README enable command and config agree."""
    block = re.search(r"required_apis = \[(.*?)\]", TF, re.DOTALL).group(1)
    in_terraform = set(re.findall(r'"([a-z]+\.googleapis\.com)"', block))
    assert in_terraform == set(REQUIRED_APIS)
    # Every google_project_service must come from that list, so nothing else is enabled.
    assert len(re.findall(r'resource "google_project_service"', TF)) == 1
    assert "for_each = toset(local.required_apis)" in TF


def test_readme_enable_and_disable_commands_list_exactly_the_apis():
    readme = (FOLDER / "README.md").read_text()
    for verb in ("enable", "disable"):
        command = re.search(
            rf"gcloud services {verb}((?: [^\n]*\\\n)*[^\n]*)", readme
        ).group(1)
        assert set(re.findall(r"[a-z]+\.googleapis\.com", command)) == set(
            REQUIRED_APIS
        ), verb


def test_time_budget_fits_both_deadlines():
    worst = (
        AUTH_TIMEOUT_S
        + DLP_TIMEOUT_S
        + MODEL_TIMEOUT_S * MODEL_ATTEMPTS
        + FIRESTORE_TIMEOUT_S * FIRESTORE_CALLS
    )
    assert worst < REQUEST_TIMEOUT_S < ACK_DEADLINE_S
    assert f'timeout         = "{REQUEST_TIMEOUT_S}s"' in TF
    assert f"ack_deadline_seconds       = {ACK_DEADLINE_S}" in TF
