import subprocess
from pathlib import Path

import config

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"


def test_script_has_safety_flags():
    text = (DEPLOY / "deploy_gemma.sh").read_text()
    for flag in ("--service-account", "--invoker-iam-check", "--no-allow-unauthenticated",
                 "--max-instances", '--max "$MAX_INSTANCES"', "--no-cpu-throttling"):
        assert flag in text


def test_script_does_not_repeat_config_defaults():
    text = (DEPLOY / "deploy_gemma.sh").read_text() + (DEPLOY / "delete_gemma.sh").read_text()
    for value in (config.GEMMA_MODEL_ID, config.SERVICE_NAME, config.REGION):
        assert value not in text


def test_shell_exports_come_from_config():
    out = subprocess.run(
        ["python3", str(DEPLOY.parent / "config.py"), "--shell"], capture_output=True, text=True, check=True
    ).stdout
    assert f"MODEL={config.GEMMA_MODEL_ID}" in out
    assert f"MAX_INSTANCES_LIMIT={config.MAX_INSTANCES_LIMIT}" in out
    assert config.MAX_INSTANCES <= config.MAX_INSTANCES_LIMIT


def test_service_account_is_deleted_only_if_the_script_created_it():
    deploy = (DEPLOY / "deploy_gemma.sh").read_text()
    delete = (DEPLOY / "delete_gemma.sh").read_text()
    assert ".created_service_account" in deploy and "service-accounts create" in deploy
    assert 'cat "$MARKER"' in delete and "did not create" in delete
    assert "Not attaching it" in deploy and "exit 1" in deploy  # unmarked existing account stops the deploy
    assert "status=1" in delete  # a failed account delete is not reported as success
    # The marker pins the account's uniqueId, so a deleted and recreated account with the
    # same email is neither attached nor deleted.
    for text in (deploy, delete):
        assert "value(uniqueId)" in text
        assert '"$RUNTIME_SA $CURRENT_ID"' in text
    assert 'echo "$RUNTIME_SA $NEW_ID" > "$MARKER"' in deploy
    # The account goes only after the service delete succeeded and the service is confirmed gone.
    assert delete.index("services describe") < delete.index("service-accounts delete")
    assert 'if [ "$status" -ne 0 ]' in delete
