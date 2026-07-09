# Morita Former Leader Retest Short v1

This is a research-only former leader retest rejection short/put study.

It tests whether former Morita leaders and high-RS breakout names become better downside candidates after:

1. a former leader origin,
2. a primary breakdown below the 20-day SMA and origin close,
3. a bounce into a fixed retest zone,
4. a confirmed rejection,
5. next-session-open hypothetical entry.

The study does not create live short signals, put alerts, broker orders, account access, sizing changes, long S logic changes, or regime sizing overlay changes.

## Source Lineage

- Scanner source: `scripts/production_scanner_entry.py`
- Signal baseline source: formal Morita historical baseline panel plus the 2023 RS warmup retest signal panel
- OHLCV source: `outputs/morita_2023_rs_warmup_retest_v1/input/morita_baseline_2022warmup_2023_2026_v1/sources/daily_ohlcv_merged.csv`
- Regime source: `outputs/morita_realized_dispersion_quick_screen/realized_dispersion_daily_panel.csv`
- Threshold source: `outputs/morita_realized_dispersion_quick_screen/realized_dispersion_state_cutoffs.csv`
- Option model: fixed-IV synthetic Black-Scholes reference, not historical fill reconstruction

The 2022 period requires 2021 OHLCV warmup for 252-session RS. If that warmup is unavailable, the builder marks 2022 as blocked and does not use substitute data.

## Fixed Regimes

- `NORMAL`: D not high
- `HIGH_DISPERSION`: D high and L not high
- `NARROW_LEADERSHIP`: D high and L high
- `HIGH_D_OR_NARROW`: `HIGH_DISPERSION` or `NARROW_LEADERSHIP`

Inherited thresholds are verified before the study runs:

- D high cutoff: `0.1076297441118458`
- L high cutoff: `0.0211600633543862`

## Primary Setup

`FL_RETEST_PRIMARY` requires:

- former leader episode,
- primary breakdown,
- retest-zone touch within fixed tolerance,
- primary rejection trigger,
- next-open hypothetical entry.

Rising-D diagnostics are recorded only as diagnostics and do not create adoption labels.

## Outputs

The builder writes computed research outputs under:

`outputs/morita_former_leader_retest_short_v1/`

It also writes:

`morita_former_leader_retest_short_v1_chatgpt_bundle.md`

The bundle is a Git-safe handoff summary. It does not include raw OHLCV, broker data, credentials, account data, order IDs, or live trade instructions.
