# Morita Bot v1 Remaining Work Closure — Status Handoff

Generated: 2026-07-20 UTC

## Executive decision

`MORITA_BOT_V1_MANUAL_LIVE_READY = false`

The production breakout scanner and its notification heartbeat have live execution evidence. Short and absorption remain research/shadow-only, and the unified state machine cannot be promoted because the historical point-in-time inputs required by the three priority backtests are not present in the repository.

No broker order path was enabled or changed.

## Current status by track

| Track | Status | Evidence | Remaining blocker |
|---|---|---|---|
| Breakout scan and notification | `REPORTED_LIVE_CURRENT_RUNTIME_UNVERIFIED` | PR #2 merged the Cloud Run path; PR #3 / commit `ed7fb34` merged fixed JST checkpoints. The prior deployment handoff records 100% Cloud Run traffic and an enabled five-minute Scheduler. GitHub Actions run `29717801400` independently proves the fallback heartbeat path | This workspace has no authenticated `gcloud`, so current service traffic, Scheduler enabled state, and recent Cloud Run logs cannot be queried independently |
| Short v3.5.3 historical claim | `REJECTED_BY_EVIDENCE` | `outputs/research_only/morita_short_v3_5_3_claim_audit/20260714T092817Z/` | Existing edge fails concentration gates; a different strategy requires a new, separately sealed evaluation |
| First absorption reversal | `COMPLETE_SHADOW_ONLY` | `outputs/morita_first_absorption_reversal_v1/backtest_report.md` | 24 candidates, 0 CLEAN primary rows; no sealed PIT event/fundamental source and no historical option chain |
| Unified Flow v3.8 | `BLOCKED_DATA` | `outputs/research_only/morita_unified_flow_v3_8_pit_band_recovery/20260713T182910Z/` | 0 valid `V_t`, 0 stable `A`, 0 usable bands; official PIT guidance/capital-structure/reference-rate fields are missing |
| Historical S/A+ replay v1.3 | `BLOCKED_DATA_PARTIAL_RECOVERY` | 72 scanner snapshots were inventoried; 128 raw observations produced a 27-row recovered calendar covering 8 decision dates and 9 tickers | The original frozen 2026 calendar plus the 2022–2025 daily feature and historical-universe panels are absent |
| Three priority backtests | `BLOCKED_DATA` | Definitions are preserved in `docs/morita_bot_v1_remaining_work_closure_instruction_v1.md` | Recovered scanner snapshots do not contain the complete PIT daily/M15 panel needed for state transition, S-group + anchor absorption, or weakest-S vs former-leader selection |

## Work completed in this pass

1. Merged the current production `main` history with the latest research history on local branch `work/morita-v1-closure-20260720` without pushing or changing remote state.
2. Recovered all 72 available nontrivial scanner snapshots from 2026-06-14 through 2026-07-07 and inspected their provenance and schema.
3. Built `morita_2026_scanner_artifact_recovery_v1`: 128 raw observations, 27 deduplicated decision rows, 8 decision dates, 9 tickers, S=15 and A=12. Every row retains its source artifact ID, file path, and SHA-256.
4. Confirmed that the recovered artifacts contain scanner candidates and some trade-log rows, but do not contain the complete intraday/PIT feature set needed to run the three requested backtests honestly.
5. Fixed historical replay v1.3 so empty outputs retain stable schemas, recovered data is visible as partial evidence, and missing signal/Short sources return `BLOCKED` rather than false reproduction failures.
6. Added regression tests for artifact fallback, deduplication, provenance, fail-closed guardrails, and missing Short source handling.
7. Ran 119 targeted regression tests across recovery, historical replay, PIT/M15 recovery, Short audits, absorption, Unified Flow, and Cloud Run checkpoints: all passed.
8. Added the integrated closure instruction at `docs/morita_bot_v1_remaining_work_closure_instruction_v1.md`.

## Evidence notes

### Short v3.5.3

The S+A Open-to-D1 baseline has PF 1.32541 and median return +0.476%, but excluding the top episode lowers PF to 0.921; excluding the top three lowers PF to 0.652. All independent acceptance gates fail. The correct action is rejection of this historical edge claim, not production promotion.

### Absorption

The existing study has 24 candidate rows and no CLEAN primary rows. Its underlying-only diagnostic baseline has PF 1.45096, but median return is -0.1776% and top-five-removed PF is 0.377. The result is not adoption-ready.

### Unified Flow

The v3.8 run preserves the output schema but all states are `BAND_UNAVAILABLE`. The prior absorption labels are diagnostic daily proxies and must not be presented as valid PIT bands.

### Notification

The 2026-07-20 fallback scanner run processed approximately 1,007 symbols and produced no candidates. A `NO_SIGNAL`-equivalent heartbeat was delivered. The Cloud Run deployment is recorded in the prior operational handoff, while this pass independently verified the merged runtime code and fixed-JST rollout but could not query the live Google Cloud control plane.

## Remaining work, in priority order

1. Recover or supply the original frozen 2026 signal calendar and the sealed 2022–2025 daily/M15 PIT panels. The GitHub artifact recovery is partial evidence only; do not synthesize missing features.
2. Run the three priority backtests with event-level clustering and issue separate verdicts for state transition, absorption confirmation, and Short target selection.
3. From an authenticated Google Cloud session, capture a current read-only receipt for service traffic, `morita-bot-every-5m`, and recent on-time checkpoint logs.

## User action

No user action is required to inspect or continue the repository work. A user-only action will be needed only if the missing historical datasets exist outside this repository or if current Google Cloud runtime evidence must be queried from the user's authenticated project.
