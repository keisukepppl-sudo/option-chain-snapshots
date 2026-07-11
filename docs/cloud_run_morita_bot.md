# Morita Bot on Cloud Run

## What this deploys

- Private Cloud Run service: `morita-bot-tick`
- One Cloud Scheduler job, every 5 minutes during the relevant UTC window
- Cloud Storage state/cache bucket
- Secret Manager entries for Pushover and optional Discord
- Separate runtime and scheduler service accounts

The service converts UTC to `America/New_York`, so U.S. daylight-saving changes are automatic.

## Runtime behavior

| ET window | Action |
|---|---|
| 08:15–09:50 | Build the daily RS98 candidate cache once |
| 10:00–10:14 | Send S+A status once |
| 11:30–11:44 | Send S+A status once |
| 12:00–12:14 | Send S+A status and save the execution baseline |
| 15:15–15:40 | Check every five minutes; Emergency only for a current S absent from the noon S+A baseline |

Each checkpoint uses only complete 5-minute bars whose start timestamp is strictly before the decision cutoff. A run starting at 12:03 therefore still uses the 11:55–12:00 bar as its final eligible bar, not the 12:00–12:05 bar.

Cloud Storage uses separate `shadow` and `live` state paths. Shadow testing therefore does not suppress the next live notification.

## Prerequisites

1. Create or select a Google Cloud project.
2. Enable billing for that project.
3. Install the current Google Cloud CLI.
4. Run `gcloud auth login`.
5. Clone this repository and check out the Cloud Run branch/merged commit.

## Deploy in shadow mode

From the repository root:

```bash
export PROJECT_ID="your-project-id"
export PUSHOVER_APP_TOKEN="your-token"
export PUSHOVER_USER_KEY="your-user-key"
# Optional:
export STOCK="your-discord-webhook"

DRY_RUN=true bash deploy/bootstrap_gcp.sh
```

The default region is `us-central1`. Override it with `REGION=...` if needed.

The script creates resources idempotently, builds the container, deploys a private service, and creates the authenticated Scheduler target. It does not place brokerage orders.

## Manual shadow test

Get the service URL:

```bash
SERVICE_URL="$(gcloud run services describe morita-bot-tick \
  --region=us-central1 --format='value(status.url)')"
TOKEN="$(gcloud auth print-identity-token)"
```

Force a precompute run for a real NYSE trading date:

```bash
curl -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${SERVICE_URL}/tick" \
  -d '{"force_action":"PRECOMPUTE","mock_time_et":"2026-07-10T08:30:00-04:00"}'
```

Then force a 12:00 shadow scan:

```bash
curl -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${SERVICE_URL}/tick" \
  -d '{"force_action":"12:00","mock_time_et":"2026-07-10T12:05:00-04:00"}'
```

Use a date for which Yahoo intraday data is still available. Five-minute history is limited by the upstream provider.

## Enable live notifications

After shadow output is correct:

```bash
gcloud run services update morita-bot-tick \
  --region=us-central1 \
  --update-env-vars=DRY_RUN=false,ALLOW_TEST_OVERRIDES=false
```

The live state path is separate, so the first live checkpoint is not suppressed by shadow state.

## Operational checks

View service logs:

```bash
gcloud run services logs read morita-bot-tick \
  --region=us-central1 \
  --limit=100
```

Run the Scheduler immediately:

```bash
gcloud scheduler jobs run morita-bot-every-5m \
  --location=us-central1
```

Inspect state and outputs:

```bash
gcloud storage ls --recursive "gs://${PROJECT_ID}-morita-bot-state/**"
```

## Failure behavior

- Low intraday-data coverage returns HTTP 500. The checkpoint is not marked complete, so the next five-minute Scheduler call retries it.
- Pushover failure also prevents completion from being saved.
- Duplicate or overlapping calls are serialized by a Cloud Storage lock and by Cloud Run `max-instances=1`, `concurrency=1`.
- If the 12:00 baseline is missing, the wake path fails safe: every current eligible S is wake-eligible, and the alert explicitly warns that the noon baseline is missing.
- NYSE holidays are skipped. On early-close sessions, the 15:15–15:40 wake window is skipped.

## Cutover

Keep GitHub Actions available only as a manual fallback. After at least several shadow sessions match the existing scanner, enable live Cloud Run notifications. Do not run both scheduled paths live, or duplicate alerts can occur.
