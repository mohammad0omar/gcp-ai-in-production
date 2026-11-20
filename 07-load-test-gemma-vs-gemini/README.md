# 07 Load test Gemma vs Gemini

Coral Desk tags support tickets with a category and an urgency, about 2 million tickets a month. The team asks one question: is it cheaper to host Gemma 4 with vLLM on a Cloud Run GPU, or to call Gemini? This folder measures both on the same prompt and does the money maths from a price file.

```text
Locust -> GemmaUser  -> gcloud proxy -> Cloud Run (vLLM, 1 GPU) /v1/chat/completions (streaming)
       -> GeminiUser -> Gemini via google-genai, ADC, no API key                    (streaming)
each request -> one Locust request event + one custom stream_metrics event
              -> TTFT, tokens per second, token counts -> results/records-<time>.csv (new file per run)
report.py + prices.toml -> p50/p95 TTFT, aggregate throughput, cost per 1M output tokens, break-even
```

A request only counts as a success when its stream finished properly (Gemma: `[DONE]` plus usage, no error payload; Gemini: finish reason STOP or MAX_TOKENS), showed visible text and reported token usage. Each side makes one attempt per request; there are no retries.

## Steps

These steps rent a GPU. Run them yourself, in a dedicated project you can bill and later delete, not a shared one. You need `gcloud`, `uv`, and your own account with `roles/run.admin`, `roles/iam.serviceAccountAdmin` (or an existing `coral-gemma-runtime` account) and `roles/iam.serviceAccountUser` on it.

1. Pick the project: `gcloud config set project YOUR_PROJECT_ID`.
2. Enable the APIs, once:
   ```bash
   gcloud services enable run.googleapis.com aiplatform.googleapis.com iam.googleapis.com
   ```
3. Check your GPU quota for `nvidia-rtx-pro-6000` in the region (new projects get 3). Check the region on the [Cloud Run GPU page](https://docs.cloud.google.com/run/docs/configuring/services/gpu). Region, service name, model and the instance cap all come from `config.py`; the scripts read them from there.
4. Deploy Gemma. Cost starts here. The script refuses a cap above 3, creates a service account with no project roles for the container (a marker file in `deploy/` records its email and uniqueId, so a later account with the same name never matches; if an account with that name already exists and the script did not make it, the script stops and asks you to delete it or use another project), and keeps the service private. Keep `MAX_INSTANCES` at 1 for this benchmark: the report gives per-instance numbers and works out how many instances a volume needs:
   ```bash
   PROJECT=YOUR_PROJECT_ID bash deploy/deploy_gemma.sh
   ```
   The first start loads the model and can take several minutes. `--max-instances` caps one revision and `--max` caps the service, but Cloud Run can briefly exceed a cap while scaling, so do not leave it running.
5. Open a private tunnel in a second terminal. Your account needs `roles/run.invoker` on the service:
   ```bash
   gcloud run services proxy coral-gemma-loadtest --project YOUR_PROJECT_ID --region us-central1 --port=9090
   ```
6. Run the Gemma side. Run at least 5 minutes so ramp-up is a small part of the window:
   ```bash
   uv sync
   uv run locust -f loadtest/locustfile.py GemmaUser --headless -u 8 -r 1 -t 5m --stop-timeout 70
   ```
7. Delete the GPU service now, before the Gemini run. The same command works after an interrupted run:
   ```bash
   PROJECT=YOUR_PROJECT_ID bash deploy/delete_gemma.sh
   ```
8. Run the Gemini side with your own credentials (`gcloud auth application-default login`; the account needs `roles/aiplatform.user`). The run uses thinking level `LOW` (config.py, env `THINKING_LEVEL`); the model default is `MEDIUM`. State the level in your post:
   ```bash
   GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID uv run locust -f loadtest/locustfile.py GeminiUser --headless -u 8 -r 1 -t 5m --stop-timeout 70
   ```
9. Read the numbers from the ONE Gemma file and the ONE Gemini file of this comparison (name them, do not glob; the report refuses two files for the same side). The report takes the average billed output tokens per request from the Gemini file (pass `--output-tokens` to override). Give the share of time an always-on GPU would be busy in production, and the date whose Gemini price you want:
   ```bash
   uv run python report.py results/records-GEMMA_RUN.csv results/records-GEMINI_RUN.csv --utilisation 0.6 --pricing-date 2027-04-13
   ```

Safe test habits: keep the first run to a few minutes, set a budget alert, delete the service the moment the Gemma run ends, and use a new records file per comparison (the locustfile makes one per run).

## What the report calculates

- Gemma throughput is the output tokens of requests that start inside a steady window, divided by the window length. Only requests that start and end inside the window count, so no token is credited from outside it. Failures inside the window count as time with no tokens. The default window drops the first and last 10 percent of the test; set your own with `--steady-window START END` (seconds from test start). It is a busy-GPU number for one instance.
- Utilisation is the share of an always-on instance's time that is busy in production. Idle time is counted once, there. Cost per 1M tokens is the instance hour price divided by throughput times utilisation.
- Break-even is where one always-on instance costs the same per day as Gemini for the same output tokens. The report also prints how many requests one instance can serve, using Gemma's own measured output tokens per request (not Gemini's billed count), and how many instances the break-even volume needs. One instance is the limit; extra instances add cost and capacity together.
- It is output tokens only. Input tokens, networking and engineering time are not included.
- Tokens per second is an approximate streaming rate (a chunk can hold several tokens, and first-chunk tokens are counted). Gemini decode speed uses visible tokens; cost uses billed tokens, which include thinking tokens.
- Gemini price depends on the date (3.75 until 2026-12-31, 7.50 from 2027-01-01 for output on the `global` endpoint). Pass `--pricing-date`.

## Clean up

```bash
PROJECT=YOUR_PROJECT_ID bash deploy/delete_gemma.sh
gcloud run services list --project YOUR_PROJECT_ID   # confirm coral-gemma-loadtest is gone
```

This deletes the Cloud Run service, and the `coral-gemma-runtime` service account only if `deploy_gemma.sh` created it (the marker file `deploy/.created_service_account`). An account the script did not create is never deleted or attached. The account is removed even when the service delete fails. If you changed `REGION` or `SERVICE`, pass the same values. Stop the proxy with Ctrl-C. Delete `results/` if you do not want the numbers. Restore credentials you changed: `gcloud auth application-default revoke` removes the ADC login from step 8. If you enabled the APIs only for this test, you can turn them off with `gcloud services disable run.googleapis.com aiplatform.googleapis.com iam.googleapis.com`; leave them on if anything else uses them.

## What this costs

- Cloud Run GPU, CPU and memory, billed per second while the instance lives: https://cloud.google.com/run/pricing
- Gemini tokens: https://cloud.google.com/vertex-ai/generative-ai/pricing

Every price the report uses is in `prices.toml` with its source URL and date checked. Update the file, not the code. No total is promised: it depends on how long you leave the service up.

## Read the numbers honestly

The result depends on your prompt and answer sizes. This folder uses one short ticket prompt and 128 output tokens at most. Longer prompts raise TTFT and lower GPU throughput; longer answers raise cost on both sides. Concurrency (8 users here) changes throughput and TTFT; test at the load you expect. The break-even assumes one always-on instance and the `global` Gemini endpoint.

## How this was checked

Unit tests with mocks, nothing is deployed and no Google client is called: timing maths from fixed timestamps; stream validation with fake Gemma and Gemini streams (success, truncation, in-stream error, blocked or empty Gemini answer); break-even maths with fixed inputs, the capacity check and input validation; prices read from `prices.toml` (changing the file changes the result); the deploy script flags and its use of `config.py`; the APIs in README and config. `ruff` and compile checks pass. The shell scripts and the Locust file were not run on a live project.
