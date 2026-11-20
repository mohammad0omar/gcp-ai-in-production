# 04 Model upgrade pipeline

Larkspur Travel is a trip-planning app. Its FastAPI service on Cloud Run has one Gemini endpoint, `POST /summarize`, that turns a pasted itinerary into JSON (destination, days, highlights, budget level). Their current model, `gemini-3.7-flash`, retires on 2027-01-28, so they need to move to `gemini-3.8-flash` without a bad release reaching every user.

**Run only one pipeline per service at a time.** Cloud Run has one traffic split and one `candidate` tag per service, and the checks in this pipeline are guards, not a lock. Overlapping runs can overwrite each other's split or rollback. Start upgrades from one trigger that runs one build at a time.

```text
gcloud builds submit (Cloud Build)
  test             unit tests
  eval-candidate   score the candidate model on 12 golden cases, fail under 0.9
  build, push      container image
  deploy-candidate new Cloud Run revision, tagged "candidate", 0% traffic, MODEL_ID=candidate
  canary-10        10% of traffic to the candidate revision
  watch            read the candidate's 5xx rate from Cloud Monitoring for N minutes
  promote          100% to the latest revision
  (watch fails)    100% back to the previous revision, build fails
```

## Why model ids are pinned versions, not aliases

`config.py` pins `gemini-3.7-flash` and `gemini-3.8-flash`. The Vertex AI model pages and the model versions page list only version ids with release and retirement dates. We found no auto-updating alias (a "latest" id that moves) described in the current docs (checked 2026-11-20, see `FACTS.md`). Even if you use one elsewhere, a moving id would change your answers with no deploy, no eval and no canary. A pinned id changes only when this pipeline changes it, and it retires on a date you can read: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions

## Steps

You need a billable project, `gcloud` and Python 3.12. These steps change your project. Run them yourself. Replace `YOUR_PROJECT_ID` and set the variables once:

```bash
export PROJECT_ID=YOUR_PROJECT_ID REGION=europe-west1
export BUILD_SA=larkspur-build RUNTIME_SA=larkspur-runtime BUCKET=$PROJECT_ID-larkspur-build
gcloud config set project $PROJECT_ID
```

1. Enable the APIs:
   ```bash
   gcloud services enable aiplatform.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com monitoring.googleapis.com run.googleapis.com
   ```
2. Create two service accounts, so the app that serves requests holds no deploy rights: `gcloud iam service-accounts create $BUILD_SA` and `gcloud iam service-accounts create $RUNTIME_SA`. Their emails are `$BUILD_SA@$PROJECT_ID.iam.gserviceaccount.com` and `$RUNTIME_SA@...`.
3. Create the image repository and one bucket for build source and baseline logs:
   ```bash
   gcloud artifacts repositories create larkspur --repository-format=docker --location=$REGION
   gcloud storage buckets create gs://$BUCKET --location=$REGION
   ```
4. Grant the runtime account only what the app needs: `gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$RUNTIME_SA@$PROJECT_ID.iam.gserviceaccount.com --role=roles/aiplatform.user`.
5. Grant the build account its project-level roles, and its access to the bucket and the repository. `roles/logging.logWriter` lets it write build logs, `roles/aiplatform.user` lets the eval call Gemini, `roles/monitoring.viewer` lets the watch read metrics:
   ```bash
   BUILD_MEMBER=serviceAccount:$BUILD_SA@$PROJECT_ID.iam.gserviceaccount.com
   for role in roles/logging.logWriter roles/aiplatform.user roles/monitoring.viewer; do
     gcloud projects add-iam-policy-binding $PROJECT_ID --member=$BUILD_MEMBER --role=$role
   done
   gcloud storage buckets add-iam-policy-binding gs://$BUCKET --member=$BUILD_MEMBER --role=roles/storage.objectAdmin
   gcloud artifacts repositories add-iam-policy-binding larkspur --location=$REGION --member=$BUILD_MEMBER --role=roles/artifactregistry.writer
   ```
6. Let the build account act as the runtime account (needed to deploy a revision that runs as it), and let you act as both accounts (the runtime one for the manual baseline deploy in step 7, the build one to submit builds with it):
   ```bash
   gcloud iam service-accounts add-iam-policy-binding $RUNTIME_SA@$PROJECT_ID.iam.gserviceaccount.com --member=$BUILD_MEMBER --role=roles/iam.serviceAccountUser
   gcloud iam service-accounts add-iam-policy-binding $BUILD_SA@$PROJECT_ID.iam.gserviceaccount.com --member=user:YOUR_EMAIL --role=roles/iam.serviceAccountUser
   gcloud iam service-accounts add-iam-policy-binding $RUNTIME_SA@$PROJECT_ID.iam.gserviceaccount.com --member=user:YOUR_EMAIL --role=roles/iam.serviceAccountUser
   ```
7. Deploy the baseline once, by hand, on the current model, so there is a revision to roll back to. The service needs authentication (no `--allow-unauthenticated`):
   ```bash
   IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/larkspur/itinerary-summariser:baseline
   gcloud builds submit --tag $IMAGE \
     --service-account=projects/$PROJECT_ID/serviceAccounts/$BUILD_SA@$PROJECT_ID.iam.gserviceaccount.com \
     --gcs-source-staging-dir=gs://$BUCKET/source --gcs-log-dir=gs://$BUCKET/logs .
   gcloud run deploy itinerary-summariser --region $REGION --image $IMAGE \
     --service-account=$RUNTIME_SA@$PROJECT_ID.iam.gserviceaccount.com \
     --set-env-vars MODEL_ID=gemini-3.7-flash,GOOGLE_CLOUD_PROJECT=$PROJECT_ID
   ```
   Now that the service exists, give the build account Cloud Run Developer on that one service only:
   `gcloud run services add-iam-policy-binding itinerary-summariser --region $REGION --member=$BUILD_MEMBER --role=roles/run.developer`.
   Give yourself `roles/run.invoker` on the service the same way, so you can send test requests.
8. Run the upgrade. Pass `_REGION` explicitly: `--region` on `builds submit` only picks where Cloud Build runs, not where Cloud Run is. Gemini calls use location `global` (`GEMINI_LOCATION` in `config.py`), which the model pages list for both model ids.
   ```bash
   gcloud builds submit --config cloudbuild.yaml --region $REGION \
     --service-account=projects/$PROJECT_ID/serviceAccounts/$BUILD_SA@$PROJECT_ID.iam.gserviceaccount.com \
     --gcs-source-staging-dir=gs://$BUCKET/source \
     --substitutions=_CANDIDATE_MODEL=gemini-3.8-flash,_REGION=$REGION .
   ```
   Other substitutions: `_EVAL_THRESHOLD` (0.9), `_WATCH_MINUTES` (10), `_MAX_ERROR_RATE` (0.02). The build validates all of them first.
9. While the `watch` step runs (about 13 minutes: the watch plus 3 minutes for metrics to arrive), send the candidate at least 20 requests. The tag URL (it points to the candidate while only this run exists) is the service URL with `candidate---` in front of the host:
   ```bash
   URL=$(gcloud run services describe itinerary-summariser --region $REGION --format='value(status.url)')
   CANDIDATE_URL=${URL/https:\/\//https://candidate---}
   for i in $(seq 1 30); do
     curl -s -o /dev/null -w "%{http_code}\n" -X POST "$CANDIDATE_URL/summarize" \
       -H "Authorization: Bearer $(gcloud auth print-identity-token)" -H "Content-Type: application/json" \
       -d '{"text": "Rome 3 days: Colosseum, Vatican museums, Trastevere dinner. Three-star hotel."}'
     sleep 5
   done
   ```

Run the eval alone any time. It needs the dependencies and local Application Default Credentials:
```bash
pip install -r app/requirements.txt
gcloud auth application-default login
GOOGLE_CLOUD_PROJECT=$PROJECT_ID python eval/run_eval.py --model gemini-3.8-flash --golden eval/golden.jsonl --threshold 0.9
```

## Production choices and limits

- The eval scores exact fields plus a schema check, so a model that "improves" the prose but breaks the JSON fails before any user sees it.
- Gemini calls have a 30 s timeout and 3 attempts. A failed call scores 0 in the eval and returns a clean 503 or 504 from the app. We leave the sampling settings at the model default; Google recommends that for Gemini 3.
- The candidate gets no traffic until the eval passes, then 10%, then a watch window of `_WATCH_MINUTES` plus 3 minutes, counted from the traffic shift. The window starts when traffic moves, so installs do not shorten it. It fails on a 5xx rate over the limit once there are 20 requests, fails closed with fewer than 20, and fails if the final read of Cloud Monitoring fails (an earlier healthy read never rescues it).
- A bad model answer returns 502, which counts as an error in the watch.
- Rollback is its own step. It restores the revision saved before the deploy and checks the split is back at 100%. If the command or the check fails, the log says `ROLLBACK FAILED` and the build fails.
- **Limit: one pipeline run per service at a time.** Cloud Run has one traffic split per service, and the `candidate` tag points to one revision. Two overlapping runs would overwrite each other's tag and split, and one could promote a revision the other never watched. So every step after the deploy names the exact revision (`--to-revisions REVISION=10`, never a tag or `--to-latest`). The deploy step refuses to start unless one revision serves 100%, and promote refuses unless the service still has exactly the 90/10 split this run set. That is a guard, not a lock: two builds started in the same second could still race, so start upgrades from one trigger that runs one build at a time.
- **Limit: a cancelled or timed-out build can leave 10% on the candidate.** The build has a 5400 s timeout and every step before the watch has its own shorter timeout, so the time left for the rollback is known. `_WATCH_MINUTES` is capped at 30, the watcher has a hard limit of the watch time plus 5 minutes, and a failed or timed-out watch still reaches the rollback step, so a timeout before rollback is unlikely. After a cancel, roll back by hand:
  `gcloud run services update-traffic itinerary-summariser --region $REGION --to-revisions PREVIOUS_REVISION=100` (find it with `gcloud run revisions list --service itinerary-summariser --region $REGION`).

## Clean up

```bash
gcloud run services delete itinerary-summariser --region $REGION
gcloud artifacts repositories delete larkspur --location=$REGION
gcloud storage rm -r gs://$BUCKET      # source archives and baseline build logs; the upgrade logs go to Cloud Logging
gcloud iam service-accounts delete $BUILD_SA@$PROJECT_ID.iam.gserviceaccount.com
gcloud iam service-accounts delete $RUNTIME_SA@$PROJECT_ID.iam.gserviceaccount.com
for role in roles/logging.logWriter roles/aiplatform.user roles/monitoring.viewer; do
  gcloud projects remove-iam-policy-binding $PROJECT_ID --member=$BUILD_MEMBER --role=$role
done
gcloud projects remove-iam-policy-binding $PROJECT_ID --member=serviceAccount:$RUNTIME_SA@$PROJECT_ID.iam.gserviceaccount.com --role=roles/aiplatform.user
```
Deleting a service account removes its bindings on the bucket and repository, which are deleted anyway. Also remove your own `roles/run.invoker` on the service (it goes with the service) and your `roles/iam.serviceAccountUser` grant (it goes with the build account). Upgrade build logs stay in Cloud Logging and are removed by the `_Default` bucket's retention period (30 days unless you changed it). APIs can stay enabled.

## What this costs

Gemini tokens (the eval runs 12 short calls per upgrade, plus canary traffic), Cloud Run, Cloud Build minutes, Artifact Registry and Cloud Storage storage, Cloud Logging, and Cloud Monitoring reads. See the current prices and do your own estimate:
- https://cloud.google.com/vertex-ai/generative-ai/pricing
- https://cloud.google.com/run/pricing
- https://cloud.google.com/build/pricing
- https://cloud.google.com/artifact-registry/pricing
- https://cloud.google.com/products/observability/pricing

## How this was checked

Unit tests with every Google client mocked (eval scoring and exit codes, canary watch with a fake clock and a mocked Monitoring client, the Cloud Build rollout shell steps run against a fake `gcloud`, input validation, app), `ruff`, and a compile check. Nothing here was run against a live Google Cloud project. Check the gcloud commands on a test project first. Sources are in `FACTS.md`.
