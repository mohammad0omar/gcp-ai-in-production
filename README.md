# gcp-ai-in-production

Production patterns for running AI on Google Cloud. Each folder is the code behind one tutorial: small, tested, and written so you can copy it into your own project.

| Folder | What it shows | Status |
| --- | --- | --- |
| [01-keyless-ai-app](01-keyless-ai-app) | Cloud Run + Gemini deployed from GitHub Actions with no service account key and no API key | available |
| 02-resilient-gemini-client | Retries, timeouts and fallbacks for Gemini calls | coming |
| 03-pii-safe-inbox | Keep personal data out of model prompts | coming |
| 04-model-upgrade-pipeline | Move to a new Gemini model with a safety net | coming |
| 05-ai-cost-attribution | Know which feature spends the tokens | coming |
| 06-production-rag-api | A retrieval API you can operate | coming |
| 07-load-test-gemma-vs-gemini | Load test a hosted Gemma against Gemini | coming |
| 08-agent-incident-drill | Practice an incident with an AI agent | coming |

## How this code is checked

- Unit tests with mocked clients (pytest). No test calls Google Cloud.
- `ruff` for lint, `python -m compileall` for syntax.
- `terraform fmt -check`, `terraform init -backend=false` and `terraform validate`.
- Not run on a live project. Read the code, then run it in your own project and read the cost notes first.

Run the checks for one folder:

```bash
scripts/check_folder.sh 01-keyless-ai-app
```

Needs `uv`, and `terraform` for folders that have a `terraform/` directory.

## License

MIT, see [LICENSE](LICENSE).
