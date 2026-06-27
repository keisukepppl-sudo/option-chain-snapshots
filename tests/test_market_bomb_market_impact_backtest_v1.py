from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import market_bomb_market_impact_backtest_v1 as m


def price_frame(values, start="2026-01-01"):
    n = len(values)
    return pd.DataFrame(
        {
            "date": pd.bdate_range(start, periods=n),
            "open": np.array(values) * 0.99,
            "high": np.array(values) * 1.02,
            "low": np.array(values) * 0.98,
            "close": values,
            "adjusted_close": values,
            "volume": np.linspace(1000000, 2000000, n),
        }
    )


def write_price(root: Path, ticker: str, values):
    d = root / "market_bomb_history" / "price_history"
    d.mkdir(parents=True, exist_ok=True)
    price_frame(values).to_csv(d / f"{ticker}_daily_price_history.csv", index=False)


def test_cta_vol_feature_after_decision_is_not_joined():
    features = pd.DataFrame(
        [
            {
                "asset": "QQQ",
                "feature_as_of_timestamp_utc": "2026-01-02T21:00:00Z",
                "effective_available_at_utc": "2026-01-03T14:30:00Z",
            }
        ]
    )
    row, status, reason = m.latest_available_feature(features, "QQQ", pd.Timestamp("2026-01-02T20:00:00Z"))
    assert row is None
    assert status == "unavailable"
    assert reason == "no_temporally_available_feature"


def test_daily_outcome_starts_after_decision_timestamp():
    outcomes = m.build_daily_outcomes({"QQQ": price_frame(np.linspace(100, 130, 30))})
    assert not outcomes.empty
    decision = pd.to_datetime(outcomes.loc[0, "decision_timestamp_utc"], utc=True)
    start = pd.to_datetime(outcomes.loc[0, "outcome_start_timestamp_utc"], utc=True)
    assert start > decision


def test_walk_forward_manifest_never_uses_random_split():
    manifest = m.build_walk_forward_manifest(300, m.rules(Path(".")))
    assert manifest["method"] == "expanding_window"
    assert manifest["random_split_used"] is False


def test_primary_and_robustness_are_separated_in_summary():
    panel = pd.DataFrame(
        {
            "target_market": ["QQQ"] * 40,
            "feature": np.linspace(-1, 1, 40),
            "outcome": np.linspace(-0.02, 0.02, 40),
        }
    )
    primary = m.summarize_association(panel, "test", "outcome", "feature", "primary")
    robust = m.summarize_association(panel, "test", "outcome", "feature", "robustness")
    assert set(primary["primary_or_robustness"]) == {"primary"}
    assert set(robust["primary_or_robustness"]) == {"robustness"}


def test_leveraged_etf_formula_long_and_inverse_signs():
    assert m.leveraged_pressure(3.0, 100.0, 0.02) == 12.0
    assert m.leveraged_pressure(-3.0, 100.0, 0.02) == 24.0
    assert m.leveraged_pressure(-3.0, 100.0, -0.02) == -24.0


def test_aum_missing_is_unavailable_not_zero():
    value, reason, proxy = m.prior_available_aum(pd.DataFrame(), "TQQQ", pd.Timestamp("2026-01-05T20:30:00Z"))
    assert pd.isna(value)
    assert reason == "aum_history_missing"
    assert proxy is False


def test_leveraged_pressure_uses_1530_return_not_close_to_close(tmp_path: Path):
    aum = tmp_path / "market_bomb_history"
    aum.mkdir(parents=True)
    pd.DataFrame(
        [
            {"ticker": "TQQQ", "effective_available_at_utc": "2026-01-02T21:00:00Z", "net_assets_usd": 100.0},
            {"ticker": "SQQQ", "effective_available_at_utc": "2026-01-02T21:00:00Z", "net_assets_usd": 100.0},
            {"ticker": "QLD", "effective_available_at_utc": "2026-01-02T21:00:00Z", "net_assets_usd": 100.0},
            {"ticker": "QID", "effective_available_at_utc": "2026-01-02T21:00:00Z", "net_assets_usd": 100.0},
        ]
    ).to_csv(aum / "leveraged_etf_aum_history.csv", index=False)
    bars_dir = tmp_path / "market_bomb_history" / "intraday_bars"
    bars_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {"timestamp_utc": "2026-01-05T14:30:00Z", "open": 100, "high": 100, "low": 100, "close": 100, "volume": 100, "prior_regular_session_close": 100},
            {"timestamp_utc": "2026-01-05T20:30:00Z", "open": 101, "high": 101, "low": 101, "close": 101, "volume": 100},
            {"timestamp_utc": "2026-01-05T21:00:00Z", "open": 110, "high": 110, "low": 110, "close": 110, "volume": 100},
        ]
    ).to_csv(bars_dir / "QQQ_5m.csv", index=False)
    panel, _ = m.build_leveraged_etf_panel(tmp_path, m.rules(tmp_path))
    assert not panel.empty
    assert np.isclose(panel.loc[0, "return_prior_close_to_1530"], 0.01)
    assert not np.isclose(panel.loc[0, "return_prior_close_to_1530"], 0.10)


def test_intraday_missing_day_is_excluded_from_leveraged_panel(tmp_path: Path):
    bars_dir = tmp_path / "market_bomb_history" / "intraday_bars"
    bars_dir.mkdir(parents=True)
    pd.DataFrame([{"timestamp_utc": "2026-01-05T14:30:00Z", "close": 100, "prior_regular_session_close": 100}]).to_csv(bars_dir / "QQQ_5m.csv", index=False)
    panel, audit = m.build_leveraged_etf_panel(tmp_path, m.rules(tmp_path))
    assert panel.empty
    assert "unavailable" in set(audit["availability_status"])


def test_dealer_primary_requires_observed_raw_chain(tmp_path: Path):
    pd.DataFrame(
        [
            {"ticker": "QQQ", "effective_available_at_utc": "2026-01-05T14:00:00Z", "raw_chain_present": False, "raw_chain_quality": "high", "gamma_flip_state": "local_flip_found"},
            {"ticker": "QQQ", "effective_available_at_utc": "2026-01-05T14:00:00Z", "raw_chain_present": True, "raw_chain_quality": "high", "gamma_flip_state": "no_local_flip", "net_gex_proxy": 1.0},
        ]
    ).to_csv(tmp_path / "dealer_gamma_proxy_history.csv", index=False)
    outcomes = pd.DataFrame(
        [
            {
                "target_market": "QQQ",
                "decision_timestamp_utc": "2026-01-05T21:00:00Z",
                "next_session_high_low_range_pct": 0.02,
            }
        ]
    )
    panel, _ = m.build_dealer_gamma_panel(tmp_path, outcomes)
    assert len(panel) == 1
    assert panel.loc[0, "gamma_flip_state"] == "no_local_flip"
    assert panel.loc[0, "dealer_position_observed"] is False or panel.loc[0, "dealer_position_observed"] == False
    assert "sign_convention" in panel.columns


def test_no_local_flip_is_not_imputed_to_zero_or_spot(tmp_path: Path):
    pd.DataFrame(
        [
            {"ticker": "QQQ", "effective_available_at_utc": "2026-01-05T14:00:00Z", "raw_chain_present": True, "raw_chain_quality": "high", "gamma_flip_state": "no_local_flip"}
        ]
    ).to_csv(tmp_path / "dealer_gamma_proxy_history.csv", index=False)
    outcomes = pd.DataFrame([{"target_market": "QQQ", "decision_timestamp_utc": "2026-01-05T21:00:00Z"}])
    panel, _ = m.build_dealer_gamma_panel(tmp_path, outcomes)
    assert panel.loc[0, "gamma_flip_state"] == "no_local_flip"
    assert pd.isna(panel.loc[0, "gamma_flip_distance_pct"])


def test_expiry_calendar_holiday_adjusted_rows_are_audited(tmp_path: Path):
    cfg = tmp_path / "market_bomb_config"
    cfg.mkdir()
    pd.DataFrame(
        [
            {"date": "2026-06-18", "market": "US", "expiry_type": "quarterly", "holiday_adjusted_flag": True}
        ]
    ).to_csv(cfg / "options_expiry_calendar_v1.csv", index=False)
    for t in ["QQQ", "SPY", "SOXX", "SMH"]:
        write_price(tmp_path, t, np.linspace(100, 130, 40))
    outputs = m.run(tmp_path, run_cta_vol_analysis=False, run_leveraged_etf_analysis=False, run_dealer_observed_analysis=False)
    expiry = pd.read_csv(tmp_path / "market_bomb_market_impact" / "dealer_gamma_expiry_event_study.csv")
    assert "holiday_adjusted_audited" in expiry.columns
    assert outputs["gate"].exists()


def test_adjusted_p_value_and_insufficient_sample_are_preserved():
    panel = pd.DataFrame({"target_market": ["QQQ"] * 2, "x": [1, 2], "y": [0.1, 0.2]})
    summary = m.summarize_association(panel, "fam", "y", "x")
    assert "adjusted_p_value" in summary.columns
    assert summary.loc[0, "evidence_verdict"] == "insufficient_data"


def test_run_writes_outputs_and_actionization_false(tmp_path: Path):
    for t in ["QQQ", "SPY", "SOXX", "SMH"]:
        write_price(tmp_path, t, np.linspace(100, 150, 80))
    outputs = m.run(tmp_path)
    for path in outputs.values():
        assert path.exists()
    gate = (tmp_path / "market_impact_backtest_gate_audit.md").read_text(encoding="utf-8")
    assert "actionization_gate: `false`" in gate
    manifest = pd.read_json(tmp_path / "market_bomb_market_impact" / "analysis_manifest.json", typ="series")
    assert manifest["actionization_allowed"] is False


def test_empty_feature_join_makes_no_lookahead_not_run_and_data_gate_insufficient(tmp_path: Path):
    m.run(tmp_path, run_cta_vol_analysis=False, run_leveraged_etf_analysis=False, run_dealer_observed_analysis=False)
    gate = (tmp_path / "market_impact_backtest_gate_audit.md").read_text(encoding="utf-8")
    assert "market_impact_data_gate: `insufficient_data`" in gate
    assert "no_lookahead_status: `not_run`" in gate


def test_expanding_oos_uses_previous_months_only_with_train_scaler():
    dates = pd.bdate_range("2025-01-01", periods=90)
    panel = pd.DataFrame(
        {
            "target_market": ["QQQ"] * len(dates),
            "decision_timestamp_utc": [m.et_close_utc(d).isoformat() for d in dates],
            "baseline": np.linspace(0, 1, len(dates)),
            "feature": np.linspace(1, 2, len(dates)),
            "outcome": np.linspace(0, 0.1, len(dates)),
        }
    )
    cfg = m.rules(Path("."))
    cfg["walk_forward"]["minimum_train_observations"] = 20
    result, folds = m.run_oos_comparison(
        panel,
        module="Test",
        test_family="unit",
        feature_sets={"feature_set": ["feature"]},
        outcomes=["outcome"],
        baseline_cols=["baseline"],
        cfg=cfg,
        min_oos_rows=1,
        min_test_months=1,
    )
    tested = folds[folds["fold_status"].eq("tested")]
    assert not result.empty
    assert not tested.empty
    assert tested["sample_count_train"].min() >= 20
    assert result.loc[0, "evidence_engine"] == "expanding_window_oos_ridge"


def test_prior_available_aum_rejects_date_only_same_day_primary():
    aum = pd.DataFrame([{"ticker": "TQQQ", "date": "2026-01-05", "net_assets_usd": 100.0}])
    value, reason, proxy = m.prior_available_aum(aum, "TQQQ", pd.Timestamp("2026-01-05T20:30:00Z"), pd.Timestamp("2026-01-02T21:00:00Z"))
    assert pd.isna(value)
    assert reason == "date_only_aum_not_primary"
    assert proxy is False


def test_no_lookahead_audit_fails_effective_after_decision():
    join = pd.DataFrame(
        [
            {
                "module": "X",
                "feature_family": "X",
                "target_market": "QQQ",
                "decision_timestamp_utc": "2026-01-05T20:30:00Z",
                "feature_as_of_timestamp_utc": "2026-01-05T20:00:00Z",
                "effective_available_at_utc": "2026-01-05T21:00:00Z",
            }
        ]
    )
    audit, status = m.build_no_lookahead_audit(join)
    assert status == "failed"
    assert audit.loc[0, "no_lookahead_passed"] is False or audit.loc[0, "no_lookahead_passed"] == False


def test_no_lookahead_audit_fails_missing_required_timestamps_and_age():
    join = pd.DataFrame([{"module": "X", "feature_family": "X", "target_market": "QQQ", "decision_timestamp_utc": "2026-01-05T20:30:00Z"}])
    audit, status = m.build_no_lookahead_audit(join)
    assert status == "failed"
    assert "missing_required_timestamp:feature_asof_timestamp_missing" in audit.loc[0, "violation_reason"]
    assert "effective_available_timestamp_missing" in audit.loc[0, "violation_reason"]
    assert "feature_age_missing" in audit.loc[0, "violation_reason"]


def test_no_lookahead_audit_fails_feature_age_over_max():
    join = pd.DataFrame(
        [
            {
                "module": "X",
                "feature_family": "X",
                "target_market": "QQQ",
                "decision_timestamp_utc": "2026-01-05T20:30:00Z",
                "feature_as_of_timestamp_utc": "2026-01-05T19:30:00Z",
                "effective_available_at_utc": "2026-01-05T19:30:00Z",
                "feature_age_hours": 100,
                "max_feature_age_hours": 96,
            }
        ]
    )
    audit, status = m.build_no_lookahead_audit(join)
    assert status == "failed"
    assert "feature_age_exceeds_maximum" in audit.loc[0, "violation_reason"]


def test_train_only_encoder_does_not_add_test_only_category():
    train = pd.DataFrame({"state": ["a", "b", "a"]})
    test = pd.DataFrame({"state": ["c"]})
    encoder = m.fit_feature_encoder(train, ["state"])
    train_x, train_unseen = m.transform_feature_encoder(train, encoder)
    test_x, test_unseen = m.transform_feature_encoder(test, encoder)
    assert list(train_x.columns) == ["state=a", "state=b"]
    assert list(test_x.columns) == ["state=a", "state=b"]
    assert test_x.iloc[0].sum() == 0
    assert train_unseen == 0
    assert test_unseen == 1


def test_dealer_state_keeps_no_local_flip_distance_uses_only_local_flip():
    panel = pd.DataFrame(
        [
            {"target_market": "QQQ", "gamma_flip_state": "no_local_flip", "gamma_flip_distance_pct": np.nan, "net_gex_proxy": 1, "pinning_proxy": 0},
            {"target_market": "QQQ", "gamma_flip_state": "local_flip_found", "gamma_flip_distance_pct": 0.03, "net_gex_proxy": 2, "pinning_proxy": 1},
        ]
    )
    state, distance, audit = m.split_dealer_gamma_state_distance(panel)
    assert len(state) == 2
    assert "gamma_flip_distance_pct" not in state.columns
    assert len(distance) == 1
    assert distance.iloc[0]["gamma_flip_state"] == "local_flip_found"
    assert audit.loc[0, "no_local_flip_count"] == 1


def test_exact_1530_and_1600_bars_required_for_leveraged_panel(tmp_path: Path):
    hist = tmp_path / "market_bomb_history"
    hist.mkdir(parents=True)
    pd.DataFrame(
        [
            {"ticker": t, "effective_available_at_utc": "2025-11-28T21:00:00Z", "as_of_timestamp_utc": "2025-11-28T21:00:00Z", "net_assets_usd": 100.0, "aum_value_type": "net_assets_usd"}
            for t in ["TQQQ", "SQQQ", "QLD", "QID"]
        ]
    ).to_csv(hist / "leveraged_etf_aum_history.csv", index=False)
    bars_dir = hist / "intraday_bars"
    bars_dir.mkdir()
    pd.DataFrame(
        [
            {"timestamp_utc": "2026-01-05T14:30:00Z", "close": 100, "volume": 100, "prior_regular_session_close": 100},
            {"timestamp_utc": "2026-01-05T20:25:00Z", "close": 101, "volume": 100},
            {"timestamp_utc": "2026-01-05T21:00:00Z", "close": 102, "high": 102, "low": 101, "volume": 100},
        ]
    ).to_csv(bars_dir / "QQQ_5m.csv", index=False)
    panel, audit = m.build_leveraged_etf_panel(tmp_path, m.rules(tmp_path))
    assert panel.empty
    assert "required_1530_bar_missing" in set(audit["availability_failure_reason"])


def test_leveraged_primary_does_not_use_full_day_volume_denominator(tmp_path: Path):
    hist = tmp_path / "market_bomb_history"
    hist.mkdir(parents=True)
    pd.DataFrame(
        [
            {"ticker": t, "effective_available_at_utc": "2025-11-28T21:00:00Z", "as_of_timestamp_utc": "2025-11-28T21:00:00Z", "net_assets_usd": 100.0, "aum_value_type": "net_assets_usd"}
            for t in ["TQQQ", "SQQQ", "QLD", "QID"]
        ]
    ).to_csv(hist / "leveraged_etf_aum_history.csv", index=False)
    bars_dir = hist / "intraday_bars"
    bars_dir.mkdir()
    rows = []
    for i, day in enumerate(pd.bdate_range("2025-12-01", periods=22)):
        day_date = pd.Timestamp(day).date()
        rows.extend(
            [
                {"timestamp_utc": pd.Timestamp.combine(day_date, pd.Timestamp("09:30").time()).tz_localize("America/New_York").tz_convert("UTC").isoformat(), "close": 100, "volume": 100, "prior_regular_session_close": 100},
                {"timestamp_utc": pd.Timestamp.combine(day_date, pd.Timestamp("15:30").time()).tz_localize("America/New_York").tz_convert("UTC").isoformat(), "close": 101, "high": 101, "low": 101, "volume": 100},
                {"timestamp_utc": pd.Timestamp.combine(day_date, pd.Timestamp("16:00").time()).tz_localize("America/New_York").tz_convert("UTC").isoformat(), "close": 102, "high": 102, "low": 101, "volume": 1000},
            ]
        )
    pd.DataFrame(rows).to_csv(bars_dir / "QQQ_5m.csv", index=False)
    panel, _ = m.build_leveraged_etf_panel(tmp_path, m.rules(tmp_path))
    assert "intraday_volume_share_to_1530" not in panel.columns
    assert "intraday_volume_ratio_vs_prior_20d_same_time" in panel.columns


def test_previous_regular_session_skips_2026_juneteenth():
    prev = m.previous_regular_session_close_utc(pd.Timestamp("2026-06-22"), m.rules(Path(".")))
    assert prev.tz_convert("America/New_York").date().isoformat() == "2026-06-18"


def test_expiry_calendar_and_gamma_conditioned_are_separate(tmp_path: Path):
    cfg = tmp_path / "market_bomb_config"
    cfg.mkdir()
    pd.DataFrame([{"date": "2026-01-16", "market": "US", "expiry_type": "monthly", "holiday_adjusted_flag": False}]).to_csv(cfg / "options_expiry_calendar_v1.csv", index=False)
    outcomes = pd.DataFrame(
        [
            {
                "target_market": "QQQ",
                "decision_date": "2026-01-16",
                "decision_timestamp_utc": "2026-01-15T21:00:00Z",
                "next_session_absolute_return": 0.01,
                "next_session_high_low_range_pct": 0.02,
            }
        ]
    )
    pd.DataFrame(
        [
            {
                "ticker": "QQQ",
                "feature_as_of_timestamp_utc": "2026-01-16T13:00:00Z",
                "effective_available_at_utc": "2026-01-16T13:05:00Z",
                "raw_chain_present": True,
                "raw_chain_quality": "high",
                "data_type": "reconstructed_from_raw_chain",
                "dealer_position_observed": False,
                "gamma_flip_state": "no_local_flip",
                "net_gex_proxy": 1.0,
                "pinning_proxy": 0.2,
            }
        ]
    ).to_csv(tmp_path / "dealer_gamma_proxy_history.csv", index=False)
    calendar, conditioned, audit = m.build_dealer_gamma_expiry_event_panel(tmp_path, outcomes, m.rules(tmp_path))
    assert not calendar.empty
    assert not conditioned.empty
    assert set(calendar["feature_family"]) == {"ExpiryCalendar"}
    assert set(conditioned["feature_family"]) == {"DealerGammaExpiryConditioned"}
    assert "selected_snapshot_asof_utc" in conditioned.columns


def test_expiry_rejects_gamma_snapshot_after_0930(tmp_path: Path):
    cfg = tmp_path / "market_bomb_config"
    cfg.mkdir()
    pd.DataFrame([{"date": "2026-01-16", "market": "US", "expiry_type": "monthly"}]).to_csv(cfg / "options_expiry_calendar_v1.csv", index=False)
    outcomes = pd.DataFrame([{"target_market": "QQQ", "decision_date": "2026-01-16", "decision_timestamp_utc": "2026-01-15T21:00:00Z"}])
    pd.DataFrame(
        [
            {
                "ticker": "QQQ",
                "feature_as_of_timestamp_utc": "2026-01-16T15:00:00Z",
                "effective_available_at_utc": "2026-01-16T15:00:00Z",
                "raw_chain_present": True,
                "raw_chain_quality": "high",
                "data_type": "reconstructed_from_raw_chain",
                "dealer_position_observed": False,
            }
        ]
    ).to_csv(tmp_path / "dealer_gamma_proxy_history.csv", index=False)
    _, conditioned, audit = m.build_dealer_gamma_expiry_event_panel(tmp_path, outcomes, m.rules(tmp_path))
    assert conditioned.empty
    assert "no_strict_prior_gamma_snapshot" in set(audit.get("availability_failure_reason", pd.Series(dtype=str)).astype(str))
