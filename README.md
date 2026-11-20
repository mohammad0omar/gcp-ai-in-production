# gcp-ai-in-production

Production patterns for running AI on Google Cloud. Each folder is the code behind one tutorial: small, tested, and written so you can copy it into your own project.

| Folder | What it shows | Status |
| --- | --- | --- |
| [01-keyless-ai-app](01-keyless-ai-app) | Cloud Run + Gemini deployed from GitHub Actions with no service account key and no API key | available |
| [02-resilient-gemini-client](02-resilient-gemini-client) | Retries, timeouts and fallbacks for Gemini calls | available |
| [03-pii-safe-inbox](03-pii-safe-inbox) | Keep personal data out of model prompts | available |
| [04-model-upgrade-pipeline](04-model-upgrade-pipeline) | Move to a new Gemini model with a safety net | available |
| [05-ai-cost-attribution](05-ai-cost-attribution) | Know which feature spends the tokens | available |
| [06-production-rag-api](06-production-rag-api) | A retrieval API you can operate | available |
| [07-load-test-gemma-vs-gemini](07-load-test-gemma-vs-gemini) | Load test a hosted Gemma against Gemini | available |
| [08-agent-incident-drill](08-agent-incident-drill) | Practice an incident with an AI agent | available |

## How this code is checked

- Unit tests with mocked clients (pytest). No test calls Google Cloud.
- `ruff` for lint, `python -m compileall` for syntax.
- `terraform fmt -check`, `terraform init -backend=false` and `terraform validate` (validate runs in CI; a local run may skip it when the Terraform registry is unreachable).
- Not run on a live project. Read the code, then run it in your own project and read the cost notes first.

Run the checks for one folder:

```bash
scripts/check_folder.sh 01-keyless-ai-app
```

Needs `uv`, and `terraform` for folders that have a `terraform/` directory.

## License

MIT, see [LICENSE](LICENSE).
