import json
from pathlib import Path
from types import SimpleNamespace

from eval.run_eval import load_cases, main, score_answer

GOLDEN = str(Path(__file__).resolve().parents[1] / "eval" / "golden.jsonl")
CASES = load_cases(GOLDEN)


class FakeClient:
    """Returns the expected answer, or garbage for the cases listed in `broken`."""

    def __init__(self, broken=()):
        self.broken = set(broken)
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, model, contents, config):
        case = next(c for c in CASES if c["text"] == contents)
        if case["id"] in self.broken:
            return SimpleNamespace(text="not json at all")
        answer = {**case["expected"], "highlights": ["x"]}
        return SimpleNamespace(text=json.dumps(answer))


def test_golden_has_twelve_cases():
    assert len(CASES) == 12


def test_score_exact_and_schema():
    expected = {"destination": "Paris", "days": 3, "budget_level": "low"}
    good = {"destination": "Paris", "days": 3, "highlights": ["a"], "budget_level": "low"}
    assert score_answer(json.dumps(good), expected) == (1.0, True)
    one_wrong = {**good, "days": 4}
    score, ok = score_answer(json.dumps(one_wrong), expected)
    assert ok and abs(score - 2 / 3) < 1e-9
    assert score_answer("nope", expected) == (0.0, False)
    missing_key = {"destination": "Paris", "days": 3, "budget_level": "low"}
    assert score_answer(json.dumps(missing_key), expected) == (0.0, False)
    string_days = {**good, "days": "3"}
    assert score_answer(json.dumps(string_days), expected) == (0.0, False)


def test_eval_pass_and_fail_exit_codes(capsys):
    args = ["--model", "m", "--golden", GOLDEN, "--threshold", "0.9"]
    assert main(args, client=FakeClient()) == 0
    # 3 of 12 cases broken: score 0.75, under 0.9.
    assert main(args, client=FakeClient(broken={"paris-3d", "kyoto-5d", "rome-3d"})) == 1
    assert "FAIL" in capsys.readouterr().out


def test_transport_failure_scores_zero_and_finishes_the_table(capsys):
    import httpx

    client = FakeClient()
    real = client.models.generate_content

    def flaky(model, contents, config):
        if "Louvre" in contents:
            raise httpx.ConnectError("down")
        return real(model, contents, config)

    client.models = SimpleNamespace(generate_content=flaky)
    code = main(["--model", "m", "--golden", GOLDEN, "--threshold", "0.95"], client=client)
    out = capsys.readouterr().out
    assert code == 1 and "ConnectError" in out and "kyoto-5d" in out
