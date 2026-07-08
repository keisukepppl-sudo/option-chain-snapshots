# Morita Material Spike Put Vertical Research v1

## Purpose

This module studies whether failed material-spike breakouts can be expressed as bearish put vertical research candidates.

The target pattern is a small-cap or smaller mid-cap MRLN-style move: news or theme-driven gap, volume surge, failure to keep making highs, then gradual fade. Large-cap or institutionally supported MRVL-style moves are separated through market-cap, price, catalyst-strength, and theme buckets.

This is research-only. It does not change production notifications, ranks, orders, sizing, or existing Morita Bot behavior.

## Inputs

`scripts/build_morita_material_spike_put_vertical_research_v1.py` takes:

- `--baseline-panel`: existing Morita initial-breakout candidate panel
- `--price-panel`: OHLCV forward path panel

Entry decisions use only fields available at entry time:

- OHLCV through the failure confirmation date
- rank and score columns from the baseline panel
- theme
- market cap
- catalyst label or fixed proxy

## Material Proxy

`CANDIDATE_MATERIAL_SPIKE` if any of:

- `gap_pct >= 8%`
- `signal_date_return >= 10%`
- `volume_multiple >= 3.0`
- `breakout_excess_pct >= 5%`

`CANDIDATE_EXTREME_MATERIAL_SPIKE` if any of:

- `gap_pct >= 15%`
- `signal_date_return >= 20%`
- `volume_multiple >= 5.0`

## Buckets

Market cap:

- `MICRO_LT_300M`
- `SMALL_300M_2B`
- `SMALL_MID_2B_10B`
- `MID_10B_20B`
- `LARGE_GT_20B`

Price:

- `5_10`
- `10_20`
- `20_50`
- `GT_50`

Catalyst strength:

- `FUNDAMENTAL_STRONG`
- `PR_WEAK`
- `UNKNOWN`

Volume multiple buckets are fixed as:

- `1.2-2`
- `2-3`
- `3-5`
- `>5`

## Failure Entry Rules

D0 is the material-spike breakout date. Entries are evaluated from D1 through D5 only. Each rule is logged independently at its first occurrence, then the hypothetical put vertical entry is next session open.

- F1: no D0-high close update and close below D0 close
- F2: close below breakout level / prior high
- F3: close below D0 midpoint and volume less than 60% of D0 volume
- F4: close below previous day low and D0 high not updated
- F5: two consecutive lower highs and lower closes

## Synthetic Put Vertical Reference

If historical option fills are unavailable, the module uses a synthetic fixed-IV reference. It is explicitly labeled:

`synthetic_fixed_iv_not_historical_option_fill_reconstruction`

Base structure:

- 35 calendar DTE policy default, representing the requested 30 to 45 DTE range
- buy put delta `-0.35`
- sell put delta `-0.20`
- entry markup `5%`
- exit haircut `5%`
- IV scenarios `60%`, `80%`, `100%`
- IV crush scenarios `0`, `-10`, `-20` vol points

Exit policies:

- `PV_5D_TP50_STOP50`
- `PV_10D_TP75_STOP50`
- `PV_10D_TP100_STOP60`
- `PV_15D_TP100_STOP60`

## Outputs

Runtime outputs are ignored under `outputs/morita_material_spike_put_vertical_v1/`:

- `material_spike_candidate_panel.csv`
- `material_spike_failure_entry_log.csv`
- `material_spike_underlying_outcomes.csv`
- `material_spike_put_vertical_reference.csv`
- `material_spike_bucket_summary.csv`
- `material_spike_source_lineage.json`
- `material_spike_receipt.json`
- `material_spike_content_manifest.json`
- `material_spike_summary.md`
