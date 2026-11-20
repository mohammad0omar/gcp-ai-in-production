"""Settings shared by the library, the demo app and the checks. Model ids live here and nowhere else."""

import os

# Primary model: Gemini 3.8 Flash, GA. Model page lists `global` as a location.
MODEL_ID = "gemini-3.8-flash"

# Fallback model, tried when MODEL_ID keeps failing. A smaller, cheaper model. Both models
# run on Standard PayGo shared capacity, so the fallback is not a guaranteed separate pool.
# GA and listed for `global`, retirement July 2027 or later.
FALLBACK_MODEL_ID = "gemini-3.5-flash-lite"

# Location for Gemini calls, overridable with REGION. "global" is the global endpoint:
# higher availability than one region, but no data-residency guarantee (see README).
REGION = os.environ.get("REGION", "global")

# Every API this tutorial needs. A test keeps this in step with the README enable step.
REQUIRED_APIS = [
    "aiplatform.googleapis.com",
]
