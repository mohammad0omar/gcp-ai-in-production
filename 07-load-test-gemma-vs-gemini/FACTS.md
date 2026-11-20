# Facts and sources

Format: claim | URL | date checked.

- Cloud Run GPU types: `nvidia-rtx-pro-6000` (96 GB) and `nvidia-l4` (24 GB); one GPU per instance | https://docs.cloud.google.com/run/docs/configuring/services/gpu | 2026-11-20
- RTX PRO 6000 regions: asia-southeast1, asia-south2, europe-west4, us-central1; L4 includes europe-west1 | https://docs.cloud.google.com/run/docs/configuring/services/gpu | 2026-11-20
- Minimums: RTX PRO 6000 20 CPU and 80Gi; L4 4 CPU and 16Gi (recommended 8 and 32Gi) | https://docs.cloud.google.com/run/docs/configuring/services/gpu | 2026-11-20
- Flags `--gpu 1`, `--gpu-type`, `--no-gpu-zonal-redundancy`, `--no-cpu-throttling`, `--max-instances` (must not exceed regional GPU quota); GPU services use instance-based billing | https://docs.cloud.google.com/run/docs/configuring/services/gpu | 2026-11-20
- Default quota on first deploy: 3,000 milliGPU (RTX PRO 6000) or 3 GPUs (L4), zonal redundancy off | https://docs.cloud.google.com/run/docs/configuring/services/gpu | 2026-11-20
- Gemma 4 on Cloud Run with vLLM: image `us-docker.pkg.dev/vertex-ai/vertex-vision-model-garden-dockers/pytorch-vllm-serve:gemma4`, models `google/gemma-4-E2B-it` and `google/gemma-4-E4B-it`, `gcloud beta run deploy` with the flags in deploy/deploy_gemma.sh, OpenAI-compatible `/v1/chat/completions`, test with `gcloud run services proxy` | https://docs.cloud.google.com/run/docs/run-gemma-on-cloud-run.md.txt | 2026-11-20
- Cloud Run instance-based prices (Tier 1): RTX PRO 6000 no zonal redundancy 0.00036522 per second; L4 no zonal redundancy 0.0001867 per second; vCPU 0.000018 per second; GiB 0.000002 per second | https://cloud.google.com/run/pricing | 2026-11-20
- Gemini 3.8 Flash global standard output: 3.75 per 1M tokens through 2026-12-31, then 7.50 from 2027-01-01; output includes reasoning; non-global endpoints cost more (so location is fixed to global) | https://cloud.google.com/vertex-ai/generative-ai/pricing | 2026-11-20
- Gemini model id `gemini-3.8-flash`, location `global` | https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-8-flash | 2026-11-20
- `google-genai` 3.6.1: `Client(vertexai=True, project, location, http_options)`, `models.generate_content_stream(model, contents, config)`, usage fields `candidates_token_count` and `thoughts_token_count`; checked by introspection | https://googleapis.github.io/python-genai/ | 2026-11-20
- Locust 2.47.0: `events.request.fire(request_type, name, response_time (ms), response_length, exception, context)`; one request event per completion, `EventHook` for custom events; checked by importing the locustfile and reading the signature, Locust was not run | https://docs.locust.io/en/stable/api.html | 2026-11-20
- vLLM streams `/v1/chat/completions` as `data: {json}` lines ending `data: [DONE]`; `stream_options.include_usage` adds a final usage chunk | https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html | 2026-11-20
- `gcloud beta run deploy` flags `--max` (service-level cap, changeable without a revision), `--max-instances` (per revision), `--invoker-iam-check`, `--service-account`; Cloud Run can briefly exceed a cap | https://docs.cloud.google.com/sdk/gcloud/reference/beta/run/deploy | 2026-11-20
- Service-level vs revision max instances | https://docs.cloud.google.com/run/docs/configuring/max-instances | 2026-11-20
- Default runtime identity is the Compute Engine default service account unless `--service-account` is set | https://docs.cloud.google.com/run/docs/securing/service-identity | 2026-11-20
- `gcloud run services delete`, `gcloud iam service-accounts create` and `delete`, `gcloud run services proxy` | https://docs.cloud.google.com/sdk/gcloud/reference/run/services/delete | 2026-11-20
- `gcloud auth application-default revoke`, `gcloud services disable` | https://docs.cloud.google.com/sdk/gcloud/reference/auth/application-default/revoke | 2026-11-20
- google-genai 3.6.1 accepts `Client(enterprise=True, ...)` (`vertexai` is a legacy alias), `ThinkingConfig(thinking_level=...)` with levels MINIMAL, LOW, MEDIUM, HIGH, XHIGH, `HttpRetryOptions(attempts=1)`, `Client.close()`; checked by introspection | https://googleapis.github.io/python-genai/ | 2026-11-20

## Not verified

- That Gemini 3.8 Flash accepts thinking level `LOW` (the SDK enum does; the model page was not re-read for the allowed levels). Set `THINKING_LEVEL` if the API rejects it.

- The vLLM stream and `stream_options` behaviour of the Gemma 4 image was not fetched from the vLLM page in this session; it is standard OpenAI-compatible behaviour. Confirm with one curl before a long run.
- Whether `google/gemma-4-E4B-it` needs an `HF_TOKEN` in your project. The guide calls it optional.
- Cloud Run price tier of your region: the numbers are the first column (Tier 1) of the pricing table.
- Per-chunk token counts are not available from Gemini; tokens per second uses the final usage count over the first-to-last chunk span.
- Nothing here ran against a live project.
