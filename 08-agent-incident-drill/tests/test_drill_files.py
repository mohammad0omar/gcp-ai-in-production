from pathlib import Path

FOLDER = Path(__file__).resolve().parents[1]
SECTIONS = ["Timeline", "Impact", "Detection", "Root cause", "What went well", "Action items"]


def test_postmortem_template_has_blameless_sections():
    text = (FOLDER / "drill" / "postmortem_template.md").read_text()
    for section in SECTIONS:
        assert section in text
    assert "Owner" in text
    assert "blameless" in text.lower()


REFUSAL_QUERY = (
    'resource.type="cloud_run_revision"\n'
    'resource.labels.service_name="pebble-agent"\n'
    'resource.labels.revision_name="PASTE_FAULT_REV_HERE"\n'
    'jsonPayload.tool="refund_order"\n'
    'jsonPayload.decision="refused"\n'
    'jsonPayload.reason="currency_mismatch"'
)
AUDIT_QUERY = (
    'protoPayload.serviceName="run.googleapis.com"\n'
    'protoPayload.methodName=("google.cloud.run.v2.Services.UpdateService"'
    ' OR "google.cloud.run.v1.Services.ReplaceService")\n'
    'resource.labels.service_name="pebble-agent"'
)


def test_runbook_contains_complete_queries_and_commands():
    text = (FOLDER / "drill" / "README.md").read_text()
    assert REFUSAL_QUERY in text
    assert AUDIT_QUERY in text
    assert "**Span name**" in text and "execute_tool refund_order" in text
    assert "set -o pipefail" in text
    assert "--update-env-vars=DRILL_FAULT=wrong_currency" in text
    assert "--remove-env-vars=DRILL_FAULT" in text
    assert "update-traffic $SERVICE --region $REGION --to-revisions=$BASELINE_REV=100" in text
    assert "jq -n --arg" in text


def test_drill_prompts_leave_currency_to_the_lookup():
    text = (FOLDER / "drill" / "README.md").read_text()
    prompts = [line for line in text.splitlines() if line.startswith("ask ")]
    assert prompts
    assert all("GBP" not in line and "USD" not in line for line in prompts)
    assert "--fail-with-body" in text


def test_deploy_command_keeps_message_content_out_of_spans():
    readme = (FOLDER / "README.md").read_text()
    assert "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false" in readme
    assert "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false" in (FOLDER / "Dockerfile").read_text()
