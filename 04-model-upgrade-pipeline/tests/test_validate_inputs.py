from pipeline.validate_inputs import check

GOOD = {
    "CANDIDATE_MODEL": "gemini-3.8-flash",
    "SERVICE": "itinerary-summariser",
    "REGION": "europe-west1",
    "REPO": "larkspur",
    "EVAL_THRESHOLD": "0.9",
    "WATCH_MINUTES": "10",
    "MAX_ERROR_RATE": "0.02",
}


def test_good_inputs_pass():
    assert check(GOOD) == []


def test_shell_metacharacters_and_missing_values_are_rejected():
    bad = {**GOOD, "CANDIDATE_MODEL": "gemini-3.8-flash; rm -rf x", "WATCH_MINUTES": "10$(id)"}
    assert len(check(bad)) == 2
    assert check({k: v for k, v in GOOD.items() if k != "REGION"}) != []


def test_watch_minutes_over_the_build_timeout_budget_is_rejected():
    assert check({**GOOD, "WATCH_MINUTES": "30"}) == []
    assert check({**GOOD, "WATCH_MINUTES": "99"}) != []
    assert check({**GOOD, "WATCH_MINUTES": "31"}) != []
