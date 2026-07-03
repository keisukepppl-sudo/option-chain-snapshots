# Morita Bot Baseline Tail Intake v1

This intake is a narrow, authorized Yahoo Finance daily OHLCV tail extension for the existing local Russell 1000 history.

Allowed request window is `2026-06-01` through `2026-07-02` inclusive, with `interval=1d`, `auto_adjust=False`, and `actions=False`.

The original pickle is never overwritten. Dates through `2026-06-12` come from the existing local history. Dates after `2026-06-12` come from the authorized provider tail and are labeled `raw_unadjusted_provider_tail`.

The resulting input is local, ignored, research-only, and not point-in-time universe eligible.
