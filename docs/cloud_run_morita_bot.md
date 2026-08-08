# Morita Bot on Cloud Run

## What this deploys

- Private Cloud Run service: `morita-bot-tick`
- One Cloud Scheduler job, every 5 minutes during the relevant UTC window
- Cloud Storage state/cache bucket
- Secret Manager entries for Pushover and optional Discord
- Separate runtime and scheduler service accounts

The user-facing checkpoint slots are fixed in `Asia/Tokyo`, so they do not move when U.S. daylight-saving time changes.

## Runtime behavior

| JST slot | Action |
|---|---|
| 21:00–22:20 | Build the daily RS98 candidate cache once |
| 22:30 | Send the first S+A status after the first regular-session 5-minute bar completes; normally arrives around 22:35 JST |
| 23:00 | Send S+A status once |
| 24:00 | Send S+A status and save the execution baseline |
| 15:15–15:40 ET | Check every five minutes; Emergency only for a current S absent from the 24:00 JST S+A baseline |

Each checkpoint uses only complete 5-minute bars whose start timestamp is strictly before the decision cutoff. The 22:30 slot intentionally executes at 22:35 JST so the first regular-session 5-minute bar is complete and the notification remains within the accepted five-minute delay.

Candidate notifications fail closed unless the row is S/A and passes the shared strict gate: prior 65-session high, time-of-day adjusted RVOL >= 1.5x, two completed 5-minute closes above the pivot, price above VWAP/open and within 1% of the session high, and QQQ above its 20-day EMA. The 22:35 run therefore remains a status checkpoint but cannot emit an actionable candidate from only one completed bar. Failed rows remain in scan output with `notification_gate_reasons` for calibration.

During U.S. standard time, the fixed 22:30 and 23:00 JST slots occur before the NYSE regular session opens. The service still sends an explicit heartbeat stating that S/A cannot yet be evaluated, rather than failing silently or reporting a false zero-candidate scan.

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
  -d '{"force_action":"PRECOMPUTE","mock_time_et":"2026-07-10T08:00:00-04:00"}'
```

Then force the 24:00 JST execution-baseline scan. During U.S. daylight-saving time, 24:00 JST is 11:00 ET:

```bash
curl -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${SERVICE_URL}/tick" \
  -d '{"force_action":"24:00","mock_time_et":"2026-07-10T11:05:00-04:00"}'
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
- Fixed JST slots that occur before the regular session opens send an explicit `market_not_open` heartbeat and are marked complete.
- Pushover failure also prevents completion from being saved.
- Duplicate or overlapping calls are serialized by a Cloud Storage lock and by Cloud Run `max-instances=1`, `concurrency=1`.
- If the 24:00 JST baseline is missing, the wake path fails safe: every current eligible S is wake-eligible, and the alert explicitly warns that the baseline is missing.
- NYSE holidays are skipped. On early-close sessions, the 15:15–15:40 ET wake window is skipped.

## Cutover

Keep GitHub Actions available only as a manual fallback. After shadow output is correct, enable live Cloud Run notifications. Do not run both scheduled paths live, or duplicate alerts can occur.
