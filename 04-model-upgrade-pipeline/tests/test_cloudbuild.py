"""Check cloudbuild.yaml: step order, and run the rollout shell steps against a fake gcloud."""

import os
import stat
import subprocess
from pathlib import Path

import yaml

FOLDER = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((FOLDER / "cloudbuild.yaml").read_text())
SUBS = {**CONFIG["substitutions"], "PROJECT_ID": "proj", "BUILD_ID": "abcdef1234567890"}

# A fake gcloud: logs every call, answers `describe` from FAKE_* variables.
FAKE_GCLOUD = """#!/usr/bin/env bash
echo "$*" >> "$CALLS"
case "$*" in
  *"$FAKE_FAIL"*) [ -n "$FAKE_FAIL" ] && exit 1 ;;
esac
if [ "$2" = "services" ] && [ "$3" = "describe" ]; then
  case "$*" in
    *"traffic[0].percent)"*) echo "$FAKE_PCT0" ;;
    *"traffic[1].percent)"*) echo "$FAKE_PCT1" ;;
    *"traffic[0].revisionName,"*) printf '%s' "$FAKE_SPLIT" | tr ' ' '\\t' ; echo ;;
    *"traffic[0].revisionName)"*) echo "$FAKE_SERVING" ;;
  esac
fi
exit 0
"""


def step(step_id):
    return next(s for s in CONFIG["steps"] if s["id"] == step_id)


def render(text: str) -> str:
    """Do what Cloud Build does: fill in substitutions, turn $$ into $."""
    text = text.replace("$$", "\0")  # keep escaped dollars out of the substitution pass
    for key, value in SUBS.items():
        text = text.replace("${" + key + "}", value).replace("$" + key, value)
    return text.replace("\0", "$")


def run_step(step_id, tmp_path, fake, marker=False):
    work = tmp_path / "workspace"
    work.mkdir()
    (work / "previous_revision").write_text("svc-00001\n")
    (work / "candidate.txt").write_text("svc-cabcdef12\n")
    if marker:
        (work / "canary_failed").write_text("failed\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gcloud = bin_dir / "gcloud"
    gcloud.write_text(FAKE_GCLOUD)
    gcloud.chmod(gcloud.stat().st_mode | stat.S_IEXEC)
    env = {"FAKE_FAIL": "", "PATH": f"{bin_dir}:{os.environ['PATH']}", "CALLS": str(tmp_path / "calls.log"), **fake}
    env.update(item.split("=", 1) for item in map(render, step(step_id)["env"]))
    script = render(step(step_id)["args"][1]).replace("/workspace", str(work))
    result = subprocess.run(["bash", "-c", script], check=False, env=env, capture_output=True, text=True)
    calls = (tmp_path / "calls.log").read_text() if (tmp_path / "calls.log").exists() else ""
    return result, calls


def test_cloudbuild_step_order():
    ids = [s["id"] for s in CONFIG["steps"]]
    assert ids == [
        "test",
        "eval-candidate",
        "build",
        "push",
        "deploy-candidate",
        "canary-10",
        "watch",
        "rollback-if-failed",
        "promote",
    ]


def test_canary_and_candidate_flags():
    deploy = step("deploy-candidate")["args"][1]
    assert "--no-traffic" in deploy and "--tag candidate" in deploy
    assert "MODEL_ID=$$CANDIDATE_MODEL" in deploy
    assert "to-latest" not in yaml.dump(CONFIG)  # promotion names the exact revision


def test_substitutions_are_not_pasted_into_shell_source():
    for s in CONFIG["steps"]:
        if s.get("entrypoint") == "bash":
            assert "${_" not in s["args"][1], s["id"]


def test_deploy_refuses_a_traffic_split(tmp_path):
    result, calls = run_step("deploy-candidate", tmp_path, {"FAKE_PCT0": "90", "FAKE_PCT1": "10"})
    assert result.returncode == 1
    assert "run deploy" not in calls


def test_deploy_runs_from_clean_state(tmp_path):
    fake = {"FAKE_PCT0": "100", "FAKE_PCT1": "", "FAKE_SERVING": "svc-00001"}
    result, calls = run_step("deploy-candidate", tmp_path, fake)
    assert result.returncode == 0, result.stderr
    assert "--no-traffic" in calls and "--revision-suffix cabcdef12" in calls
    assert "MODEL_ID=gemini-3.8-flash,GOOGLE_CLOUD_PROJECT=proj" in calls


def test_canary_moves_10_percent_to_the_exact_revision(tmp_path):
    result, calls = run_step("canary-10", tmp_path, {})
    assert result.returncode == 0, result.stderr
    assert "--to-revisions svc-cabcdef12=10" in calls
    assert (tmp_path / "workspace" / "shift_epoch").read_text().strip().isdigit()


def test_rollback_runs_and_fails_the_build(tmp_path):
    fake = {"FAKE_SPLIT": "svc-00001 100 "}
    result, calls = run_step("rollback-if-failed", tmp_path, fake, marker=True)
    assert result.returncode == 1
    assert "--to-revisions svc-00001=100" in calls
    assert "Rolled back" in result.stdout


def test_failed_rollback_command_is_reported(tmp_path):
    result, _ = run_step("rollback-if-failed", tmp_path, {"FAKE_FAIL": "update-traffic"}, marker=True)
    assert result.returncode == 1 and "ROLLBACK FAILED" in result.stdout


def test_failed_rollback_verification_is_reported(tmp_path):
    result, _ = run_step("rollback-if-failed", tmp_path, {"FAKE_SPLIT": "svc-00002 90 svc-00001 10"}, marker=True)
    assert result.returncode == 1 and "ROLLBACK FAILED" in result.stdout


def test_failed_describe_during_rollback_is_reported(tmp_path):
    result, _ = run_step("rollback-if-failed", tmp_path, {"FAKE_FAIL": "describe"}, marker=True)
    assert result.returncode == 1 and "ROLLBACK FAILED" in result.stdout


def test_no_rollback_when_canary_is_healthy(tmp_path):
    result, calls = run_step("rollback-if-failed", tmp_path, {}, marker=False)
    assert result.returncode == 0 and calls == ""


def test_promote_refuses_when_the_split_changed(tmp_path):
    for n, split in enumerate(["svc-00001 100 ", "svc-00001 90 svc-cother 10 ", "svc-00001 80 svc-cabcdef12 10 svc-cx 10"]):
        case = tmp_path / str(n)
        case.mkdir()
        result, calls = run_step("promote", case, {"FAKE_SPLIT": split})
        assert result.returncode == 1, split
        assert "update-traffic" not in calls


def test_promote_names_the_candidate_when_the_split_is_ours(tmp_path):
    for n, split in enumerate([
        "svc-00001 90 svc-cabcdef12 10 ",
        "svc-cabcdef12 10 svc-00001 90 ",
        "svc-00001 90 svc-cabcdef12 10 svc-cabcdef12 0",  # tag-only entry with 0 percent
        "svc-00001 90 svc-cabcdef12 10 svc-ctagonly",  # tag-only entry with no percent
    ]):
        case = tmp_path / str(n)
        case.mkdir()
        result, calls = run_step("promote", case, {"FAKE_SPLIT": split})
        assert result.returncode == 0, result.stderr
        assert "--to-revisions svc-cabcdef12=100" in calls


def test_rollback_ignores_tag_only_entries(tmp_path):
    fake = {"FAKE_SPLIT": "svc-00001 100 svc-cabcdef12 0 svc-cabcdef12"}
    result, _ = run_step("rollback-if-failed", tmp_path, fake, marker=True)
    assert "Rolled back" in result.stdout and "ROLLBACK FAILED" not in result.stdout


def test_every_step_before_the_watch_has_a_timeout():
    before = ["test", "eval-candidate", "build", "push", "deploy-candidate", "canary-10"]
    total = sum(int(step(i)["timeout"].rstrip("s")) for i in before)
    watch = int(step("watch")["timeout"].rstrip("s"))
    build = int(CONFIG["timeout"].rstrip("s"))
    assert total + watch + 600 <= build  # room for the rollback step


def test_watch_step_installs_nothing_after_traffic_moves():
    assert "pip install" not in step("watch")["args"][1]
    assert "pydeps" in step("test")["args"][1]
