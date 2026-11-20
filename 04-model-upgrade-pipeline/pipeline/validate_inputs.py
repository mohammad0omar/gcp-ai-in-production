"""Check the build inputs before anything else runs. Substitutions are caller-controlled, so allow only plain values."""

import os
import re
import sys

# Environment variable -> pattern it must fully match.
RULES = {
    "CANDIDATE_MODEL": r"gemini-[a-z0-9.\-]{1,40}",
    "SERVICE": r"[a-z][a-z0-9\-]{0,48}",
    "REGION": r"[a-z]+-[a-z]+[0-9]+",
    "REPO": r"[a-z][a-z0-9\-]{0,62}",
    "EVAL_THRESHOLD": r"(0(\.[0-9]+)?|1(\.0+)?)",
    # At most 30: 30 min watch + 3 min settle + earlier steps + rollback must fit the 3600 s build timeout.
    "WATCH_MINUTES": r"([1-9]|[12][0-9]|30)",
    "MAX_ERROR_RATE": r"(0(\.[0-9]+)?|1(\.0+)?)",
}


def check(env: dict[str, str]) -> list[str]:
    """Return one message per bad or missing value."""
    problems = []
    for name, pattern in RULES.items():
        value = env.get(name, "")
        if not re.fullmatch(pattern, value):
            problems.append(f"{name}={value!r} does not match {pattern}")
    return problems


def main() -> int:
    problems = check(dict(os.environ))
    for line in problems:
        print(f"BAD INPUT: {line}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
