"""Settings shared by the load test, the report and the deploy scripts. Defaults live here only.

The shell scripts read them with `python3 config.py --shell`, so nothing is typed twice.
"""

import os
import sys

# Gemma 4 instruction-tuned, the size the Cloud Run vLLM guide deploys.
GEMMA_MODEL_ID = "google/gemma-4-E4B-it"

# Gemini model on the other side of the comparison.
GEMINI_MODEL_ID = "gemini-3.8-flash"

# Fixed to `global` on purpose: prices.toml holds the global rate. A non-global
# endpoint has a different price, so it is not offered as a setting.
GEMINI_LOCATION = "global"

# Thinking level for the Gemini run. The model defaults to MEDIUM, which adds hidden
# reasoning tokens. A tagging task needs little, so the run uses LOW. Say which you used.
GEMINI_THINKING_LEVEL = os.environ.get("THINKING_LEVEL", "LOW")

# Region for the Cloud Run GPU service. RTX PRO 6000 is listed for us-central1.
REGION = os.environ.get("REGION", "us-central1")

# Cloud Run service and its runtime service account (no project roles).
SERVICE_NAME = os.environ.get("SERVICE", "coral-gemma-loadtest")
RUNTIME_SA_NAME = "coral-gemma-runtime"

# Instance cap. The default quota is 3 GPUs; the first run stays at 1.
MAX_INSTANCES = int(os.environ.get("MAX_INSTANCES", "1"))
MAX_INSTANCES_LIMIT = 3

# Every API the steps use. A test keeps this in step with the README.
REQUIRED_APIS = [
    "aiplatform.googleapis.com",
    "iam.googleapis.com",
    "run.googleapis.com",
]


def shell_exports() -> str:
    pairs = {
        "REGION": REGION,
        "SERVICE": SERVICE_NAME,
        "MODEL": GEMMA_MODEL_ID,
        "RUNTIME_SA_NAME": RUNTIME_SA_NAME,
        "MAX_INSTANCES": MAX_INSTANCES,
        "MAX_INSTANCES_LIMIT": MAX_INSTANCES_LIMIT,
    }
    return "\n".join(f"{key}={value}" for key, value in pairs.items())


if __name__ == "__main__" and "--shell" in sys.argv:
    print(shell_exports())
