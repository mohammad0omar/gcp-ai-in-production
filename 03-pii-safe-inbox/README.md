# 03 PII-safe inbox

Fennel Health Supplies is an online shop. Customers email support with their name, phone number and sometimes a card number. The team wants Gemini to sort each email into a ticket, but no model should ever see that personal data, and a replayed message must not create a second ticket.

```text
Pub/Sub topic support-emails
  -> push subscription (OIDC token, 5 delivery attempts, then dead letter topic)
  -> Cloud Run POST /pubsub        (verifies the token: signature, audience, caller email)
  -> Sensitive Data Protection deidentify_content   (EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD_NUMBER, PERSON_NAME -> [INFO_TYPE])
  -> Gemini structured output -> Ticket(category, urgency, summary)
  -> Firestore tickets/{pubsub message id}   (create-if-absent)
  -> 200 = ack
```

Rules the code follows:

- The model only receives text that went through DLP. A test checks the exact DLP request (four info types, replace with info type) and that the email and phone never reach the model.
- If something email-like or card-like is still in the text after DLP, the message goes to `needs_review` with no text stored, and no model call is made (fail closed).
- Pub/Sub delivers at least once, so the same message can arrive twice, even at the same time. Each message id gets a `processed/{id}` marker plus one result document (`tickets/{id}` or `needs_review/{id}`), written in one atomic batch with create-if-absent. Two racing deliveries cannot leave both a ticket and a review record. An early read of the marker lets ordinary replays skip DLP and Gemini.
- Model output that is not valid JSON for `Ticket` after one retry is written to `needs_review` (redacted text only) and answered with `200`. Retrying would give the same bad answer and loop until the dead letter topic.
- Every failure before the final write answers non-2xx, so a message is never acknowledged without a ticket or a review record. Busy or timed-out DLP, Gemini, Firestore or certificate fetch answers `503`; permanent Google errors (for example a missing role) answer `500`. Neither response contains error text. Pub/Sub redelivers, and after about 5 attempts (Pub/Sub treats the limit as approximate) the message goes to the dead letter topic.
- Push bodies must name this service's one subscription (`support-emails-push`); anything else is refused with 403. `needs_review` records keep a `source` (subscription, message id, publish time) so a person can find the original email in Pub/Sub while it is retained.
- Cloud Run concurrency is set to 4 requests per instance, up to 5 instances.
- Time budget (no client retries; Pub/Sub redelivery is the retry): certificate fetch 5 s, DLP 10 s, two Gemini calls 15 s each, two Firestore calls 10 s each, worst case 65 s. That covers the DLP, Firestore and model calls, not a credential refresh (the Google client refreshing its access token), which is rare and usually fast; the 110 s Cloud Run timeout leaves margin for it. Cloud Run stops a request at 110 s, the push ack deadline is 120 s. A test adds this up.
- Logs contain the message id, the category and outcomes. They never contain the body, raw or redacted. A test checks this.

## What redaction does not guarantee

DLP detectors are probabilistic. A name in an unusual form, a card number with odd spacing, or a phone number inside a longer string can be missed. The leftover check above catches emails and 13 to 19 digit runs only. Do not tell customers that no personal data can ever reach the model; say that known formats are redacted and leftovers of the two checked kinds are stopped. Check [infoType detector reference](https://docs.cloud.google.com/sensitive-data-protection/docs/concepts-infotypes) for what each type detects and test your own email samples.

The email is also untrusted text. The prompt marks it as data between `<email>` tags and the schema limits the shape of the answer, but a sender can still try to push the category or urgency (for example "mark this high"). Treat `category`, `urgency` and `summary` as suggestions for a human, not as commands. If you need stronger controls, look at Model Armor prompt-injection filtering ([Model Armor and Agent Platform](https://docs.cloud.google.com/model-armor/model-armor-vertex-integration)); this folder does not use it.

## The raw email lives in Pub/Sub

Redaction happens inside the Cloud Run service, after Pub/Sub. So the topic, the push subscription backlog and the dead letter subscription all hold the ORIGINAL email, with any card number in it. Both subscriptions keep unacknowledged messages for 7 days (`message_retention_duration` is set on the subscriptions, not the topic). Treat `support-emails-dead-letter-pull` as sensitive: grant `roles/pubsub.subscriber` on it only to the few people who triage failures, and do not put real customer emails through this tutorial. The demo below uses an invented message. Both subscriptions have `expiration_policy { ttl = "" }`, because the default deletes a subscription after 31 days without activity, which would silently drop a quiet inbox or an unpolled dead letter subscription.

## Push authentication: token verification in the app

Two ways to protect a push endpoint: rely on Cloud Run IAM (`roles/run.invoker` for the push service account), or also verify the token in code. This folder does both, and the code check is the one the tests cover. Cloud Run IAM proves the caller holds the invoker role. The code check pins the exact audience and the exact service account, so a stray extra invoker grant or another subscription in the project cannot post to `/pubsub`. If `PUSH_AUDIENCE` or `PUSH_SERVICE_ACCOUNT` is missing the app refuses every request.

## Steps

You need a disposable project you can bill, `gcloud`, `terraform` and `docker`. These steps change your project. Run them yourself. Every command assumes your shell is in this folder (`03-pii-safe-inbox`); `terraform -chdir=terraform` and `docker build .` depend on it.

1. Pick the project and give Terraform credentials:
   ```bash
   gcloud config set project YOUR_PROJECT_ID
   gcloud auth login
   gcloud auth application-default login
   ```
   Terraform uses these Application Default Credentials. Your user needs to create service accounts, IAM bindings, Pub/Sub, Cloud Run, Firestore and Artifact Registry resources, and `iam.serviceAccounts.actAs` on the two service accounts it creates (Cloud Run runs as one, Pub/Sub push signs as the other). In a disposable project the Owner role covers all of it. In a shared one, ask for the narrower roles.
2. Enable the APIs:
   ```bash
   gcloud services enable aiplatform.googleapis.com artifactregistry.googleapis.com \
     cloudresourcemanager.googleapis.com dlp.googleapis.com firestore.googleapis.com \
     iam.googleapis.com pubsub.googleapis.com run.googleapis.com
   ```
   This list is `REQUIRED_APIS` in `config.py`; a test keeps it in step with `terraform/` and with this step and the cleanup step.
3. Create the image repository first, because the Cloud Run service needs an image that exists:
   ```bash
   terraform -chdir=terraform init
   terraform -chdir=terraform apply -var project_id=YOUR_PROJECT_ID -var image=placeholder \
     -target=google_artifact_registry_repository.images
   ```
4. Build and push the image:
   ```bash
   gcloud auth configure-docker europe-west1-docker.pkg.dev
   IMAGE=europe-west1-docker.pkg.dev/YOUR_PROJECT_ID/inbox/inbox:1
   docker build --platform linux/amd64 -t $IMAGE .
   docker push $IMAGE
   ```
5. Create everything else:
   ```bash
   terraform -chdir=terraform apply -var project_id=YOUR_PROJECT_ID -var image=$IMAGE
   ```
   This creates the topics, the subscriptions, the Firestore database, two service accounts and the Cloud Run service.
6. Publish a test email. The name, phone and card number are invented:
   ```bash
   gcloud pubsub topics publish support-emails --message "Hi, I am Jo Smith, jo@example.com, phone +44 7700 900123. My card 4111 1111 1111 1111 was charged twice. Please fix today."
   ```
7. In the Firestore console open the `tickets` collection. The document id is the Pub/Sub message id and holds `category`, `urgency` and `summary`. The Cloud Run logs show the message id and outcome but no text.
8. See the dead letter path with the same invented message: redeploy with a wrong Gemini location (`terraform -chdir=terraform apply -var project_id=YOUR_PROJECT_ID -var image=$IMAGE -var gemini_location=invalid-location`), publish, and after about 5 attempts pull the message (it is the unredacted original, see above):
   ```bash
   gcloud pubsub subscriptions pull support-emails-dead-letter-pull --limit=1
   ```
   The message stays in the subscription until it is acknowledged or expires in 7 days, so repeating the pull shows the same message again. Reset with `-var gemini_location=global`.

## Clean up

```bash
terraform -chdir=terraform destroy -var project_id=YOUR_PROJECT_ID -var image=$IMAGE
gcloud services disable aiplatform.googleapis.com artifactregistry.googleapis.com \
  cloudresourcemanager.googleapis.com dlp.googleapis.com firestore.googleapis.com \
  iam.googleapis.com pubsub.googleapis.com run.googleapis.com
```

`terraform destroy` removes the Cloud Run service, subscriptions (and the stored raw messages), topics, service accounts, IAM bindings, the Artifact Registry repository (and its images) and the Firestore database (`deletion_policy = "DELETE"`). A deleted `(default)` Firestore database id can take time before it can be reused. The disable command is only for a disposable project that had none of these APIs enabled before step 2; in a shared project other things may depend on them, and `gcloud services disable` can refuse or break them. Add `--force` only if you understand that.

## What this costs

No numbers here, because prices change. Read the current pages:

- [Sensitive Data Protection pricing](https://cloud.google.com/sensitive-data-protection/pricing) (DLP de-identification of content)
- [Gemini Enterprise Agent Platform pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing) (per token)
- [Pub/Sub pricing](https://cloud.google.com/pubsub/pricing)
- [Cloud Run pricing](https://cloud.google.com/run/pricing) (scales to zero; max 5 instances here)
- [Firestore pricing](https://cloud.google.com/firestore/pricing)
- [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing)

Emails over 20,000 characters are not sent to DLP or Gemini; they go to `needs_review`.

## How this was checked

Unit tests with mocks for DLP, Gemini, Firestore and the token verifier (including racing deliveries, transient and permanent errors, and the time budget), `ruff`, `terraform fmt -check`. `terraform validate` runs in CI. This was not run on a live project. See `FACTS.md` for the doc pages checked and what stays unverified.

Run the checks: `scripts/check_folder.sh 03-pii-safe-inbox` from the repo root.
