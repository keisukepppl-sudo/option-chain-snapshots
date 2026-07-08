# Morita Material Spike Put Vertical v1 ChatGPT Bundle

## Objective

Evaluate whether failed material-spike breakouts can be captured by bearish put vertical research candidates, with small-cap and smaller mid-cap PR/theme spikes separated from larger-cap fundamental moves.

## Status

Implemented as a research-only module on branch `research/material-spike-put-vertical-v1`.

## Files Added

- `config/morita_material_spike_put_vertical_v1/policy.json`
- `scripts/build_morita_material_spike_put_vertical_research_v1.py`
- `tests/test_morita_material_spike_put_vertical_research_v1.py`
- `docs/morita_material_spike_put_vertical_research_v1.md`

## Inputs

The module consumes:

- existing Morita initial-breakout baseline candidate panel
- OHLCV forward path panel

Entry-time decisions use only OHLCV, rank, score, theme, market cap, and catalyst labels available at or before failure confirmation. Future leakage is disabled by policy and tested.

## Candidate Separation

Small PR/theme spike example bucket:

- `SMALL_300M_2B`
- `10_20`
- `PR_WEAK`
- `CANDIDATE_EXTREME_MATERIAL_SPIKE`

Large fundamental example bucket:

- `LARGE_GT_20B`
- `FUNDAMENTAL_STRONG`

## Failure Rules

F1 through F5 are logged independently so rule comparison is possible. Entry is next session open after each rule's first confirmation in D1 through D5.

## Put Vertical Model

The option model is synthetic fixed-IV only and is not historical option fill reconstruction.

Scenarios:

- IV: `60%`, `80%`, `100%`
- IV crush: `0`, `-10`, `-20` vol points
- Buy put delta: `-0.35`
- Sell put delta: `-0.20`
- Entry markup: `5%`
- Exit haircut: `5%`

## Output Directory

`outputs/morita_material_spike_put_vertical_v1/`

Required outputs are manifest-verified.

## Validation

Focused test:

`python -m pytest tests/test_morita_material_spike_put_vertical_research_v1.py -q --durations=30`

Result at implementation time:

`4 passed`

## Explicit Confirmations

- Research-only.
- No production notification change.
- No rank change.
- No order path.
- No sizing change.
- No existing Morita Bot behavior change.
- No broker/account/order access.
- Synthetic option output is not historical fill reconstruction.
