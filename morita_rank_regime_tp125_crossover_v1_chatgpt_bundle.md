# Morita Rank x Regime TP125 Crossover Study v1

## Conclusion
- Primary label: `A_NORMAL_TP125_NOT_ESTABLISHED`
- Primary window: `2024-01-08` to `2026-06-16`.
- A_NORMAL trades: `206`, TP125 hit rate `0.277`, PF `1.808`.
- S_NARROW_LEADERSHIP trades: `47`, TP125 hit rate `0.340`, PF `1.815`.
- 2023 rows are descriptive only and are not pooled into the primary label.
- This is a synthetic fixed-IV reference model, not historical option-fill reconstruction and not a live execution estimate.

## Primary Cell Summary
| cell | trade_count | tp125_hit_rate | profit_factor | median_option_return_pct | p10_option_return_pct | day10_plus5_success_rate | breakout_low_breach_rate | sample_flag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S_NORMAL | 179 | 0.4246 | 2.2947 | 26.3673 | -88.3252 | 0.6480 | 0.5363 |  |
| S_HIGH_DISPERSION | 75 | 0.3067 | 1.2247 | -26.1404 | -93.0267 | 0.5600 | 0.6133 |  |
| S_NARROW_LEADERSHIP | 47 | 0.3404 | 1.8148 | -15.8005 | -68.9938 | 0.3617 | 0.6809 |  |
| A_NORMAL | 206 | 0.2767 | 1.8079 | -6.1151 | -75.1359 | 0.4854 | 0.6408 |  |
| A_HIGH_DISPERSION | 85 | 0.2824 | 1.3873 | -19.6874 | -75.8255 | 0.4353 | 0.6941 |  |
| A_NARROW_LEADERSHIP | 53 | 0.2830 | 1.5547 | -9.3348 | -82.2719 | 0.4340 | 0.7736 |  |

## Required Comparisons
| comparison_id | left_trade_count | right_trade_count | left_tp125_hit_rate | right_tp125_hit_rate | left_profit_factor | right_profit_factor | sample_status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PRIMARY_A_NORMAL_vs_S_NARROW_LEADERSHIP | 206 | 47 | 0.2767 | 0.3404 | 1.8079 | 1.8148 | OK |
| A_NORMAL_vs_S_HIGH_DISPERSION | 206 | 75 | 0.2767 | 0.3067 | 1.8079 | 1.2247 | OK |
| A_NORMAL_vs_S_NORMAL | 206 | 179 | 0.2767 | 0.4246 | 1.8079 | 2.2947 | OK |
| A_HIGH_DISPERSION_vs_S_HIGH_DISPERSION | 85 | 75 | 0.2824 | 0.3067 | 1.3873 | 1.2247 | OK |
| A_NARROW_LEADERSHIP_vs_S_NARROW_LEADERSHIP | 53 | 47 | 0.2830 | 0.3404 | 1.5547 | 1.8148 | OK |

## Reconciliation
| period_id | bucket | count | primary_denominator |
| --- | --- | --- | --- |
| primary_2024_2026_completed_confirmation_interval | source_rank_S_or_A_complete_rows | 659 | True |
| primary_2024_2026_completed_confirmation_interval | eligible_trade_rows | 645 | True |
| primary_2024_2026_completed_confirmation_interval | excluded_missing_regime_state | 0 | False |
| primary_2024_2026_completed_confirmation_interval | excluded_missing_or_invalid_option_model | 14 | False |
| primary_2024_2026_completed_confirmation_interval | duplicate_signal_id_rows | 0 | False |
| primary_2024_2026_completed_confirmation_interval | duplicate_ticker_date_rank_rows | 0 | False |
| primary_2024_2026_completed_confirmation_interval | eligible_rank_A | 344 | False |
| primary_2024_2026_completed_confirmation_interval | eligible_rank_S | 301 | False |
| primary_2024_2026_completed_confirmation_interval | eligible_regime_NORMAL | 385 | False |
| primary_2024_2026_completed_confirmation_interval | eligible_regime_HIGH_DISPERSION | 160 | False |
| primary_2024_2026_completed_confirmation_interval | eligible_regime_NARROW_LEADERSHIP | 100 | False |

## Guardrails
- Existing production rank, current source panels, and inherited realized-dispersion thresholds are used without threshold retuning.
- The option contract is the same fixed-IV 60DTE Delta0.6 single-call reference engine used for S; TP125 semantics are verified against existing S reference output.
- No notification, order, sizing, or live-bot behavior is changed.


---

## Source Artifact Lineage
```json
{
  "actionization_allowed": false,
  "artifact_version": "morita_rank_regime_tp125_crossover_v1",
  "bot_rerun_or_rule_change": false,
  "created_at_utc": "2026-07-08T12:55:17Z",
  "git_head_at_run": "8f3ba8a84950e256840aa8deff219fbec82d9840",
  "new_market_data_downloaded": false,
  "research_only": true,
  "sources": {
    "baseline_panel": {
      "path": "market_bomb_history/morita_bot_historical_baseline_v1/historical_runs/morita_baseline_20260703T123912Z_4994e3744ffa/morita_bot_baseline_panel.csv",
      "sha256": "9850a085bccdfe2e4af39d644085035439dedec22149b95a55c4808e4a7a9d0d"
    },
    "baseline_receipt": {
      "path": "market_bomb_history/morita_bot_historical_baseline_v1/historical_runs/morita_baseline_20260703T123912Z_4994e3744ffa/baseline_receipt.json",
      "sha256": "883db50e2c8a73b7ab608d1a6c7752670043125b9875dcdbcfde51e7eeb8c250"
    },
    "baseline_source_manifest": {
      "path": "market_bomb_history/morita_bot_historical_baseline_v1/historical_runs/morita_baseline_20260703T123912Z_4994e3744ffa/source_content_manifest.json",
      "sha256": "25727b33c0e306c7c48ab5d8198cccd386d9d7b8428ca2bd3377c95b565284c7"
    },
    "dispersion_metric_implementation": {
      "path": "scripts/build_morita_realized_dispersion_quick_screen_v1.py",
      "sha256": "cc7381008b2d85920cafc3df553d7eec706742a1863d93d06b188fffb386fd27"
    },
    "frozen_2023_receipt": {
      "path": "outputs/morita_narrow_leadership_2023_frozen_replication_v2/replication_receipt.json",
      "sha256": "2f06998fe5dd920818ae0e31927f217ced08dee6cb883e80710d7f88a980c481"
    },
    "narrow_leadership_receipt": {
      "path": "outputs/morita_narrow_leadership_confirmation/narrow_leadership_receipt.json",
      "sha256": "3b32acf432e4d6353c7507be3919fe64879964f0dd8337e4837d7d696abb4221"
    },
    "option_reference_engine": {
      "path": "src/morita_single_call_reference/s_single_call_reference_engine.py",
      "sha256": "d70a43159d958031c09a7376827e61cd07cccc5957f6567be55307604d8a0f02"
    },
    "realized_dispersion_context": {
      "path": "outputs/morita_realized_dispersion_quick_screen/realized_dispersion_signal_context_panel.csv",
      "sha256": "e52a8b6daec93a9d5b722f91c9d80d80533022db65a99d75298ad0990e630921"
    },
    "realized_dispersion_daily_panel": {
      "path": "outputs/morita_realized_dispersion_quick_screen/realized_dispersion_daily_panel.csv",
      "sha256": "d1a38f2abc2dba9029898822a20b32bd37d2c5bca8ad4c69008b6a7848910917"
    },
    "realized_dispersion_manifest": {
      "path": "outputs/morita_realized_dispersion_quick_screen/realized_dispersion_content_manifest.json",
      "sha256": "68f848090e3e5857110f7f597214d62d445ada118492129d74a46f1f9b10eac5"
    },
    "rs_warmup_2023_manifest": {
      "path": "outputs/morita_2023_rs_warmup_retest_v1/rs_warmup_retest_content_manifest.json",
      "sha256": "85fdc3b198d90c21f87f3bc971d634c933cd5aadbefb8b7b28a340373600e351"
    },
    "rs_warmup_2023_panel": {
      "path": "outputs/morita_2023_rs_warmup_retest_v1/morita_2023_signal_panel.csv",
      "sha256": "99d9d32a0e168af17424d6c16c081888895e4dd044ae01cef91f6ff56d24c288"
    },
    "study_spec": {
      "path": "config/morita_rank_regime_tp125_crossover_v1/study_spec.json",
      "sha256": "a0fe90b755221aa2faf2313201da601d1b6467f56fa79f02974d6b0a4105e6af"
    }
  }
}
```

## Threshold Inheritance
```json
{
  "D_high_cutoff": 0.1076297441118458,
  "D_low_cutoff": 0.0907138950199848,
  "D_metric_name": "broad_russell1000_cross_sectional_dispersion_20d",
  "L_high_cutoff": 0.0211600633543862,
  "L_low_cutoff": -0.0099227766667306,
  "L_metric_name": "broad_russell1000_qqq_minus_eqw_return_20d",
  "classification": {
    "HIGH_DISPERSION": "D_value >= D_high_cutoff and L_value < L_high_cutoff",
    "NARROW_LEADERSHIP": "D_value >= D_high_cutoff and L_value >= L_high_cutoff",
    "NORMAL": "D_value < D_high_cutoff regardless L_value"
  },
  "no_threshold_reestimation": true,
  "threshold_source": "outputs/morita_realized_dispersion_quick_screen/realized_dispersion_state_cutoffs.csv",
  "threshold_source_manifest": "outputs/morita_realized_dispersion_quick_screen/realized_dispersion_content_manifest.json",
  "threshold_source_manifest_sha256": "68f848090e3e5857110f7f597214d62d445ada118492129d74a46f1f9b10eac5",
  "threshold_source_sha256": "9eeea4426a5ff858c1fd69adb40e26c4954a49baabd849246a0abe3a244ec91c",
  "verification_status": "passed"
}
```

## Option Contract Lineage
```json
{
  "assumptions": {
    "annualized_implied_volatility": 0.6,
    "continuous_dividend_yield": 0.0,
    "entry_markup": 0.05,
    "exit_haircut": 0.05,
    "initial_calendar_dte": 60,
    "max_holding_sessions": 30,
    "model_id": "morita_s_single_call_fixed_iv_reference_v1",
    "option_side": "call",
    "progress_gate_horizon_sessions": 10,
    "progress_gate_underlying_return": 0.05,
    "risk_free_rate": 0.0,
    "target_entry_delta": 0.6
  },
  "contract_id": "morita_s_single_call_fixed_iv_reference_v1",
  "engine_module": "src/morita_single_call_reference/s_single_call_reference_engine.py",
  "engine_sha256": "d70a43159d958031c09a7376827e61cd07cccc5957f6567be55307604d8a0f02",
  "model_spec": "config/morita_s_single_call_reference_v1/fixed_iv_reference_model_spec.json",
  "model_spec_sha256": "1c271b94e3a1d7e6338bcc156b37ae46b3d1ec69d4c764c2e6543a1896e73797",
  "not_historical_option_fill_reconstruction": true,
  "not_live_execution_estimate": true,
  "primary_S_overlap_checked": 301,
  "reference_output_dir": "outputs/morita_s_single_call_reference_v1",
  "reference_terminal_summary_sha256": "81e08b89b282974ce68d45d7de6c1cc88bb21573746d6d4c046b8e361dde9a6e",
  "synthetic_fixed_iv_reference_model": true,
  "tp125_semantics_verified_against_existing_S_reference": true
}
```

## Primary Label JSON
```json
{
  "A_NORMAL_profit_factor": 1.8079305639827195,
  "A_NORMAL_tp125_hit_rate": 0.2766990291262136,
  "A_NORMAL_trade_count": 206,
  "S_NARROW_LEADERSHIP_profit_factor": 1.8147647282399164,
  "S_NARROW_LEADERSHIP_tp125_hit_rate": 0.3404255319148936,
  "S_NARROW_LEADERSHIP_trade_count": 47,
  "actionization_allowed": false,
  "artifact_version": "morita_rank_regime_tp125_crossover_v1",
  "label_rules_fixed_in_spec": true,
  "period_id": "primary_2024_2026_completed_confirmation_interval",
  "primary_label": "A_NORMAL_TP125_NOT_ESTABLISHED",
  "primary_label_uses_2023": false,
  "primary_question": "Can A_NORMAL beat S_NARROW_LEADERSHIP on standardized TP125 single-call reference?",
  "research_only": true
}
```
