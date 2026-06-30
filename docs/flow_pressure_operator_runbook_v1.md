# Flow Pressure Operator Runbook v1

This runbook defines the manual real-data workflow for future Flow Pressure phases.

Codex must not fetch provider data, scrape websites, use browser automation, use provider SDKs, add credentials, or commit raw provider exports. Raw provider files stay outside git unless they are synthetic fixtures.

## Manual Workflow

1. Create a staging template.
2. Export provider data manually.
3. Keep raw provider files outside git-managed outputs unless explicitly synthetic.
4. Hash each source file.
5. Populate `source_bundle_manifest.json`.
6. Validate the provider contract.
7. Audit timing availability.
8. Inspect source coverage.
9. Run the QQQ/TQQQ/SQQQ Phase 1 readiness report when the staged family is QQQ.
10. Correct errors only by obtaining a correct export. Do not interpolate, forward-fill, or guess missing values.
11. Stop at readiness unless a separate Phase 2 instruction explicitly authorizes release/study work.

## Required Staging Layout

```text
market_bomb_history/
  flow_pressure_research_v0/
    staging/
      <opaque_staging_id>/
        source_bundle_manifest.json
        sources/
          prices_daily.csv
          leveraged_etf_reference.csv
          leveraged_etf_aum.csv
          vol_control_returns.csv
```

The first real-data study uses `research_timing_class=eod_next_session` and does not require intraday source files.

## Required Readiness Outputs

Future Phase 1 readiness work must emit:

```text
provider_contract_validation_report.json
timing_audit.csv
timing_audit_summary.json
source_coverage_by_instrument.csv
source_coverage_by_dataset.csv
aum_selection_audit.csv
research_timing_eligibility_summary.md
real_data_readiness_report.md
```

For QQQ/TQQQ/SQQQ, run:

```powershell
python market_bomb_flow_pressure_research_v0.py run-qqq-phase1-readiness --staging-id <opaque_staging_id> --decision-time-utc <utc> --research-timing-class eod_next_session
python market_bomb_flow_pressure_research_v0.py verify-qqq-phase1-readiness --staging-id <opaque_staging_id>
```

This writes readiness artifacts under the staging directory and does not create a release.

## Operator Rules

- Use `QQQ/TQQQ/SQQQ` as the required first family.
- Analyze `SOXL/SOXS` only with an explicit valid reference mapping or an explicitly marked proxy.
- Preferred coverage is five complete years; minimum coverage is three complete years.
- Require at least 250 timing-eligible sessions after warm-up for each primary research family.
- AUM/NAV/shares rows must include `available_at_timestamp`, `valid_until_timestamp`, and stable row identity.
- Daily price rows must include real `available_at_timestamp`; the market close timestamp alone is not proof of availability.
- Missing AUM, prices, returns, OI, IV, Greeks, or shares are never forward-filled.
- Provider publication timing controls eligibility.

## Blocked Outcomes

The correct result is allowed to be:

```text
insufficient_coverage
historical_descriptive_only
blocked_by_data_quality
no_reliable_evidence
```

Do not lower coverage, timing, or data-quality standards to force a study result.

Do not run `build-flow-release`, `run-flow-real-data-study`, or `run-flow-statistical-backtest` during Phase 1.

## QQQ Phase 1.1 PIT Readiness

QQQ/TQQQ/SQQQ Phase 1 historical readiness requires a manifest-declared `decision_schedule.csv` and row-level point-in-time audit outputs. Use `run-qqq-phase1-readiness --decision-schedule-file sources/decision_schedule.csv`; do not use a single global decision timestamp for multi-date historical readiness. See `docs/flow_pressure_qqq_phase1_point_in_time_audit_v1.md`.
