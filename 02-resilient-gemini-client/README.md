# Resilient Gemini client (Saltmarsh Docs)

Saltmarsh Docs is a document startup. Its summary button calls Gemini. On a busy morning the button started failing with 429 errors, then everyone clicked it again. This folder is the fix: a small library, `resilient_gemini`, and a demo FastAPI endpoint that uses it.

What `resilient_gemini.call(...)` does:

- Retries only on 408, 429, 500, 502, 503, 504 and timeouts (the statuses Google's docs list as transient). It never retries 400, 403, 404 or anything else.
- Waits with exponential backoff and full jitter (base 1 s, cap 30 s). If the error carries a numeric `Retry-After`, it waits that long instead.
- After `max_attempts` on one model, it moves to the next model in your list.
- Never spends more than `timeout_s` in total. Each request also gets a timeout equal to the time left.
- Returns a `Result` with `text`, `model_used`, `attempts` and `cached_tokens`.

Nothing here was run against a live Google Cloud project. See "How this was checked".

## Steps

Use a dedicated project for this tutorial, so cleanup is one command and cannot touch anything else. Every command below names the project explicitly; none of them changes your default `gcloud` project.

1. Create a project and link a billing account. Gemini calls need a billing-enabled project.

   ```bash
   export PROJECT_ID=saltmarsh-resilient-demo   # pick a unique id
   gcloud projects create $PROJECT_ID
   gcloud billing projects link $PROJECT_ID --billing-account=YOUR_BILLING_ACCOUNT_ID
   ```

2. Enable the API first:

   ```bash
   gcloud services enable aiplatform.googleapis.com --project=$PROJECT_ID
   ```

3. Sign in with Application Default Credentials (ADC). Be aware: `gcloud auth application-default login` **replaces** any ADC you already have on this machine and `set-quota-project` changes its quota project, and deleting the project later does not restore them. To keep your own ADC untouched, use a separate gcloud configuration directory for this tutorial, in the same shell:

   ```bash
   export SALTMARSH_GCLOUD_DIR=$(mktemp -d)   # a throwaway gcloud config just for this tutorial
   export CLOUDSDK_CONFIG=$SALTMARSH_GCLOUD_DIR
   unset GOOGLE_APPLICATION_CREDENTIALS  # it takes precedence over the ADC file, so it would hide the login below
   gcloud auth login
   gcloud auth application-default login
   gcloud auth application-default set-quota-project $PROJECT_ID
   export GOOGLE_CLOUD_PROJECT=$PROJECT_ID
   ```

   (Do steps 1 and 2 before this, with your normal config. Or skip user ADC and use service account impersonation: `gcloud auth application-default login --impersonate-service-account=SA_EMAIL`, which still writes ADC, so combine it with `CLOUDSDK_CONFIG`.)

   If you are the project owner you already have enough access. For a dedicated runtime identity (a service account), the inference permission is `aiplatform.endpoints.predict`; the predefined role `roles/aiplatform.user` (Agent Platform User) contains it but also grants more, so use a custom role with only that permission when you can. Setting up the project (enabling APIs, linking billing) needs separate admin permissions, and the caller must be allowed to use the quota project (`serviceusage.services.use`).

4. Install [uv](https://docs.astral.sh/uv/), enter this folder, and run the tests:

   ```bash
   cd 02-resilient-gemini-client
   uv run pytest tests -q
   ```

5. Start the demo and call it. This is a loopback demo: it has no authentication and the command below binds to 127.0.0.1. Do not expose it on a network, or anyone who can reach it spends your model budget.

   ```bash
   uv run uvicorn app.main:app --host 127.0.0.1 --port 8080
   ```

   In a second terminal:

   ```bash
   curl -s localhost:8080/summarise -H 'content-type: application/json' \
     -d '{"text": "Saltmarsh Docs stores contracts. Contracts have owners and renewal dates."}'
   ```

   The answer includes `model_used` and `attempts`, so you can see a fallback happen. The summarising instruction is sent as a system instruction; the document is passed as untrusted content. A system instruction reduces, but does not remove, the chance that a document steers the summary.

6. Use it in your own code:

   ```python
   from config import FALLBACK_MODEL_ID, MODEL_ID
   from resilient_gemini import call

   result = call(
       "Summarise this contract.",
       models=[MODEL_ID, FALLBACK_MODEL_ID],
       timeout_s=25,
       max_attempts=3,
   )
   print(result.model_used, result.attempts)
   ```

   `call` builds a client for you when you pass none (it uses `GOOGLE_CLOUD_PROJECT` and `REGION`) and closes it afterwards. If you pass your own client, you close it.

Model ids live in `config.py`. Check the [model list](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models) before you copy them, because models retire.

## Retry rules in one place

- Retried: 408, 429, 500, 502, 503, 504 and client-side timeouts. Google's [retry strategy](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/retry-strategy) lists 408, 429 and 5xx as transient.
- Never retried: 400, 403, 404 and anything else. The request itself is wrong.
- Wait: random between 0 and min(30 s, 1 s * 2^(attempt-1)). A `Retry-After` header (seconds or HTTP date) replaces the random wait, and is also honoured before moving to the fallback model. If the wait would pass the deadline, `DeadlineExceeded` is raised.
- Deadline: starts before the client is built. Each request's timeout is the time left. An answer or error that arrives after the deadline is replaced by `DeadlineExceeded`, including non-retryable errors. Client setup (credential lookup) counts against the budget but cannot be interrupted, and the SDK timeout applies to each network operation, so a very slow request can overrun the deadline a little before it is noticed.
- `timeout_s` is a best-effort budget: each attempt gets the remaining time as its HTTP timeout, but a single slow read can overrun it by up to one read timeout, and a hard cancel would need a thread or an async task.
- One attempt means one HTTP request: the library turns off the SDK's own retries and continuation follow-ups.
- A client-side timeout leaves the server outcome unknown, so a retry after a timeout can produce a second billable generation.

## The global endpoint

`REGION` defaults to `global`, and `config.py` and the library both use it as the Gemini location. The global endpoint serves requests from anywhere in the world and, per Google, gives higher availability and reliability than a single region. Prefer it when you want fewer capacity errors and you do not have a data-residency rule. Google also states that endpoints do not guarantee data residency or in-region ML processing. If a rule pins your data to a region or multi-region (for example `eu`), set `REGION` to that location, check that both model pages list it (the fallback may differ), and read the [data residency](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/data-residency) page for the controls that apply. Details: [locations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations).

## Why retries without jitter make 429 storms worse

A 429 means the shared limit is full. If a thousand callers all wait exactly 2 s and retry, the next wave hits at the same instant, the limit fills again, and they all wait 4 s together. The load comes back in lockstep. Full jitter picks a random wait between 0 and the ceiling, so the retries spread out and the limit can drain. That is why `backoff.full_jitter` returns `rng() * ceiling`, not `ceiling`. The SDK can retry for you too, but it is off unless you set `retry_options`, and this library keeps its own retries so it can enforce one deadline across models.

## Quota, capacity and Provisioned Throughput

Two different things return 429. A quota you can see and raise, and shared capacity pressure with no number to raise. Standard PayGo runs on shared capacity and has [usage tiers](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/standard-paygo): your prioritized throughput threshold rises with spend over a rolling 30 days. So:

- If the 429 message names a quota, open the Cloud console, go to **Quotas & System Limits**, filter by that quota name, and request an adjustment if it is adjustable. See [quotas](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/quotas), [view and manage quotas](https://docs.cloud.google.com/docs/quotas/view-manage) and the [429 troubleshooting guide](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/deploy/error-code-429).
- If it points at shared capacity, there may be nothing to raise. Check your usage tier, spread load, and keep the fallback. Both default models use Standard PayGo shared capacity, so the fallback helps when one model is busier, but it is not a guaranteed separate pool.

[Provisioned Throughput](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/provisioned-throughput) is a fixed-cost, fixed-term subscription that reserves throughput for a model in the locations you choose; pay as you go charges per use with no reservation. Consider it when traffic is steady and 429s hurt a real-time feature. Retries and fallback still matter in both cases.

## What this costs

The code runs on your machine and calls Gemini, so the cost is Gemini usage. Per the [pricing page](https://cloud.google.com/model-garden/pricing), you are charged only for requests that return a 200; 4xx and 5xx responses are not charged for input or output. A client-side timeout is different: the server may still finish the generation, so a retry after a timeout can bill twice. Provisioned Throughput has its own fixed price on the same page. No total is given here because it depends on your traffic.

## Clean up

Everything was created in the dedicated project, so delete it. This removes the enabled API and any IAM binding with it:

```bash
gcloud projects delete $PROJECT_ID
```

Then undo the local changes. If you used a separate config directory in `SALTMARSH_GCLOUD_DIR`, delete it only if it is under the temp dir (the check below does that) and unset the variables; your own ADC was never touched:

```bash
case "$SALTMARSH_GCLOUD_DIR" in "${TMPDIR:-/tmp}"*) rm -rf "$SALTMARSH_GCLOUD_DIR" ;; *) echo "not a temp dir, not deleting" ;; esac
unset SALTMARSH_GCLOUD_DIR CLOUDSDK_CONFIG GOOGLE_CLOUD_PROJECT PROJECT_ID
```

If you skipped the separate config and logged in over your existing ADC, run `gcloud auth application-default login` again with your own account to restore it.

If you added an IAM binding to an existing project instead, remove exactly that binding with `gcloud projects remove-iam-policy-binding`, and do not disable the API there.

## How this was checked

- Unit tests with mocked Google clients: backoff growth and cap, jitter bounds, fallback on 429, no retry on 400/403/404, total deadline (late success and late failure rejected), Retry-After in both forms, result fields, and the demo endpoint.
- A real google-genai client over a mock HTTP transport, to count the requests one attempt sends.
- `ruff check` and `compileall`.
- Terraform validation does not apply: this folder has no Terraform.
- A test that the APIs in `config.py` match the enable step above.
- Not run on a live Google Cloud project. SDK names and parameters were checked against the current docs on 2026-11-20; sources are in `FACTS.md`.
