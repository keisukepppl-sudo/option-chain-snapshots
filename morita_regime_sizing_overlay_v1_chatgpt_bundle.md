# Morita Regime Sizing Overlay v1 - ChatGPT Handoff Bundle

## Completion Status

- policy_version: `morita_regime_sizing_overlay_v1`
- git_head_at_build: `2561f9eb22edae5d575289fb6c52d5f841884fdf`
- output_manifest_hash: `ca2f26cea3adffd33abb0e2e48d5c4096e2492943308599f96faeb581032d93f`
- mode: notification and logging only

## Verified Source Artifacts

- realized dispersion: `outputs/morita_realized_dispersion_quick_screen`
- narrow leadership confirmation: `outputs/morita_narrow_leadership_confirmation`
- 2023 frozen replication v2: `outputs/morita_narrow_leadership_2023_frozen_replication_v2`
- metric implementation: `scripts/build_morita_realized_dispersion_quick_screen_v1.py`

## Inherited Thresholds

- D = `broad_russell1000_cross_sectional_dispersion_20d` high cutoff `0.1076297441118458`
- L = `broad_russell1000_qqq_minus_eqw_return_20d` high cutoff `0.0211600633543862`
- threshold source: `outputs/morita_realized_dispersion_quick_screen/realized_dispersion_state_cutoffs.csv`
- threshold manifest hash: `68f848090e3e5857110f7f597214d62d445ada118492129d74a46f1f9b10eac5`

## Policy Table

| Regime | Suggested max/base premium | Rolling 10-session new-S cap | 50% exception |
| --- | ---: | ---: | --- |
| NORMAL | 30% base | none | existing-rule-dependent |
| HIGH_DISPERSION | 20% max | 40% | disabled |
| NARROW_LEADERSHIP | 15% max | 30% | disabled |
| REGIME_UNAVAILABLE_CONSERVATIVE | 20% max | 40% | disabled |

## Source Timing Contract

- Join rule: `regime_observation_date == signal_decision_date`.
- Future dates and missing D/L states fail closed to `REGIME_UNAVAILABLE_CONSERVATIVE`.
- No new threshold, universe, provider, or proxy was introduced.

## Notification Examples

S notifications receive a compact `Regime sizing overlay` block. A/B notifications are not modified by the overlay.

```text
Regime sizing overlay
Regime: NARROW_LEADERSHIP
D20: 0.1120 (HIGH; cutoff 0.1076)
QQQ minus EQW 20d: 0.0310 (HIGH; cutoff 0.0212)
Suggested max premium: 15.0%
Rolling 10-session S sleeve: 15.0% / 30.0%
50% exception: DISABLED
Budget source: RECOMMENDATION_ONLY
As-of: YYYY-MM-DD close
Policy: morita_regime_sizing_overlay_v1
```

## Rolling Sleeve Definition

- Window: current decision session plus preceding nine trading decision sessions.
- Confirmed execution ledger is read-only if supplied.
- Without confirmed fills, prior overlay recommendations are used as advisory bookkeeping and labeled `RECOMMENDATION_ONLY`.
- Exhausted capacity never suppresses an S notification; it only lowers displayed suggested maximum to the remaining capacity.

## Forward Review Snapshot

Source: `outputs/morita_regime_sizing_overlay_v1/regime_overlay_forward_review.csv`

| Regime | Complete S outcomes | +5% within 10 sessions | Breakout-low breach | Timeout |
| --- | ---: | ---: | ---: | ---: |
| NORMAL | 179 | 64.8% | 31.3% | 3.9% |
| HIGH_DISPERSION | 77 | 57.1% | 39.0% | 3.9% |
| NARROW_LEADERSHIP | 52 | 42.3% | 55.8% | 1.9% |
| REGIME_UNAVAILABLE_CONSERVATIVE | 0 | N/A | N/A | N/A |

This is a logging-only review. No policy value auto-adjusts from these results.

## Test Results

- Focused: `python -m pytest tests/test_morita_regime_sizing_overlay_v1.py -q --durations=30` -> `11 passed`; pytest cache warning only because `.pytest_cache` is not writable.
- Syntax check: `python -m py_compile scripts/build_morita_regime_sizing_overlay_v1.py scripts/build_morita_regime_sizing_overlay_forward_review_v1.py scripts/production_scanner_entry_pullback_mode.py` -> passed.
- Full: `python -m pytest -q` -> timed out after 904 seconds in this local workspace.
- CI collection coverage: registry updated to include tracked Morita tests, including `tests/test_morita_regime_sizing_overlay_v1.py`.

## Confirmations

- S signal logic did not change.
- A/B notification eligibility did not change.
- No threshold was retuned.
- No broker order was created.
- No broker/account data was fetched.
- No automatic execution exists.
- Forward review is logging-only.
- Policy values do not auto-adjust; changes require manual config edits.
