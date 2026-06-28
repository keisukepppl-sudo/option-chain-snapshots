from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

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


def write_nyse_calendar(root: Path, rows=None):
    cfg = root / "market_bomb_config"
    cfg.mkdir(parents=True, exist_ok=True)
    default_rows = [
        {"session_date": "2025-11-28", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
        {"session_date": "2025-12-31", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
        {"session_date": "2026-01-02", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
        {"session_date": "2026-01-05", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
        {"session_date": "2026-01-16", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
        {"session_date": "2026-06-18", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
        {"session_date": "2026-06-19", "is_regular_session": False, "regular_open_et": "", "regular_close_et": "", "is_early_close": False},
        {"session_date": "2026-06-22", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
    ]
    data = rows or default_rows
    df = pd.DataFrame(data)
    df["session_date"] = pd.to_datetime(df["session_date"]).dt.date.astype(str)
    full = pd.DataFrame({"session_date": pd.date_range(df["session_date"].min(), df["session_date"].max(), freq="D").date.astype(str)})
    df = full.merge(df, on="session_date", how="left")
    df["is_regular_session"] = df["is_regular_session"].fillna(False)
    df["is_early_close"] = df["is_early_close"].fillna(False)
    df["regular_open_et"] = df["regular_open_et"].fillna("")
    df["regular_close_et"] = df["regular_close_et"].fillna("")
    df["calendar_source"] = "unit_test_calendar"
    df["calendar_version"] = "nyse_regular_sessions_v1"
    df["source_retrieved_at_utc"] = "2026-06-27T00:00:00Z"
    calendar_path = cfg / "nyse_regular_sessions_v1.csv"
    df.to_csv(calendar_path, index=False)
    (cfg / "nyse_regular_sessions_metadata_v1.json").write_text(
        "{"
        '"calendar_version":"nyse_regular_sessions_v1",'
        '"source_name":"unit_test_calendar",'
        '"source_url_or_identifier":"unit_test",'
        '"source_retrieved_at_utc":"2026-06-27T00:00:00Z",'
        f'"source_file_sha256":"{m.hash_file(calendar_path)}",'
        '"generation_method":"unit_test_fixture",'
        f'"coverage_start":"{df["session_date"].min()}",'
        f'"coverage_end":"{df["session_date"].max()}",'
        '"holiday_policy":"all non-regular days explicitly present",'
        '"early_close_policy":"excluded_from_primary_intraday_or_handled_explicitly"'
        "}",
        encoding="utf-8",
    )


def write_expiry_intraday_rules(root: Path, verified=True, method="first_regular_session_bar_open"):
    cfg = root / "market_bomb_config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "market_impact_expiry_intraday_rules_v1.json").write_text(
        "{"
        '"version":"market_impact_expiry_intraday_rules_v1",'
        '"bar_timestamp_convention":"bar_end",'
        f'"regular_session_open_price_method":"{method}",'
        '"regular_session_open_bar_timestamp_et":"09:35",'
        '"regular_session_close_bar_timestamp_et":"16:00",'
        '"bar_interval_minutes":5,'
        f'"provider_bar_semantics_verified":{str(bool(verified)).lower()},'
        '"provider_bar_semantics_source":"unit_test",'
        '"provider_bar_semantics_verified_at_utc":"2026-06-27T00:00:00Z",'
        '"daily_ohlc_proxy_outcome_is_primary":false'
        "}",
        encoding="utf-8",
    )
    (cfg / "expiry_schedule_availability_rules_v1.json").write_text(
        "{"
        '"version":"expiry_schedule_availability_rules_v1",'
        '"rule_id":"us_equity_options_standard_monthly_expiry_v1",'
        '"source_identifier":"unit_test_expiry_schedule",'
        '"rule_known_effective_at_utc":"2025-01-01T00:00:00Z",'
        '"holiday_adjustment_source":"unit_test_calendar",'
        '"rule_revision_hash":"unit_test_rule_hash"'
        "}",
        encoding="utf-8",
    )


def write_expiry_friday_classification(root: Path, day="2026-01-16", group="monthly_expiry_non_quarterly"):
    cfg = root / "market_bomb_config"
    cfg.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{
        "session_date": day,
        "market": "US",
        "is_regular_session": True,
        "is_early_close": False,
        "classification_status": "available_complete",
        "classification_basis": "unit_test",
        "classification_complete": True,
        "comparison_group": group,
        "is_expiry_session": group != "non_expiry_friday",
        "expiry_type": "monthly" if "monthly" in group else "",
        "monthly_expiry_flag": group != "non_expiry_friday",
        "quarterly_expiry_flag": "quarterly" in group or "triple" in group,
        "triple_witching_flag": "triple" in group,
        "holiday_adjusted_flag": False,
        "schedule_source_identifier": "unit_test_expiry_schedule",
        "schedule_rule_version": "expiry_schedule_availability_rules_v1",
        "schedule_rule_revision_hash": "unit_test_rule_hash",
        "classification_effective_available_at_utc": "2025-01-01T00:00:00Z",
        "schedule_published_at_utc": "2025-01-01T00:00:00Z",
        "source_hash_or_revision": "unit_test_rule_hash",
    }]).to_csv(cfg / "expiry_friday_classification_v1.csv", index=False)


def write_expiry_intraday_bars(root: Path, ticker="QQQ", day="2026-01-16"):
    bars_dir = root / "market_bomb_history" / "intraday_bars"
    bars_dir.mkdir(parents=True, exist_ok=True)
    day_date = pd.Timestamp(day).date()
    pd.DataFrame(
        [
            {"timestamp_utc": pd.Timestamp.combine(day_date, pd.Timestamp("09:30").time()).tz_localize("America/New_York").tz_convert("UTC").isoformat(), "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 100},
            {"timestamp_utc": pd.Timestamp.combine(day_date, pd.Timestamp("09:35").time()).tz_localize("America/New_York").tz_convert("UTC").isoformat(), "open": 100, "high": 102, "low": 99, "close": 101, "volume": 100},
            {"timestamp_utc": pd.Timestamp.combine(day_date, pd.Timestamp("10:00").time()).tz_localize("America/New_York").tz_convert("UTC").isoformat(), "open": 100.5, "high": 104, "low": 98, "close": 102, "volume": 100},
            {"timestamp_utc": pd.Timestamp.combine(day_date, pd.Timestamp("16:00").time()).tz_localize("America/New_York").tz_convert("UTC").isoformat(), "open": 102, "high": 103, "low": 101, "close": 103, "volume": 100},
        ]
    ).to_csv(bars_dir / f"{ticker}_5m.csv", index=False)


def write_cta_vol_history(root: Path):
    hist = root / "market_bomb_history"
    hist.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"asset": "QQQ", "feature_as_of_timestamp_utc": "2026-01-02T21:00:00Z", "effective_available_at_utc": "2026-01-02T21:00:00Z", "cta_exposure_change_1d": 0.1, "cta_trend_state": "long", "quality_flag": "high"},
        {"asset": "QQQ", "feature_as_of_timestamp_utc": "2026-01-05T21:00:00Z", "effective_available_at_utc": "2026-01-05T21:00:00Z", "cta_exposure_change_1d": -0.2, "cta_trend_state": "short", "quality_flag": "high"},
    ]).to_csv(hist / "cta_proxy_history.csv", index=False)
    pd.DataFrame([
        {"asset": "QQQ", "target_vol": 0.10, "feature_as_of_timestamp_utc": "2026-01-05T21:00:00Z", "effective_available_at_utc": "2026-01-05T21:00:00Z", "vol_control_exposure_change_1d": 0.5, "vol_control_state": "wrong_vol", "quality_flag": "high"},
        {"asset": "QQQ", "target_vol": 0.12, "feature_as_of_timestamp_utc": "2026-01-05T21:00:00Z", "effective_available_at_utc": "2026-01-05T21:00:00Z", "vol_control_exposure_change_1d": -0.3, "vol_control_state": "target_vol_12", "quality_flag": "high"},
    ]).to_csv(hist / "vol_control_proxy_history.csv", index=False)


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


def test_cta_vol_panel_retains_distinct_family_selection_metadata(tmp_path: Path):
    write_cta_vol_history(tmp_path)
    outcomes = pd.DataFrame([{"target_market": "QQQ", "decision_date": "2026-01-05", "decision_timestamp_utc": "2026-01-05T21:00:00Z"}])
    panel, _, _ = m.build_cta_vol_feature_outcome_panel(tmp_path, outcomes, m.rules(tmp_path))
    assert not panel.empty
    row = panel.iloc[0]
    assert row["cta_selected_source_row_identifier"] != ""
    assert row["vol_selected_source_row_identifier"] != ""
    assert row["cta_selected_source_content_hash"] != row["vol_selected_source_content_hash"]
    assert row["vol_target_vol_requested"] == 0.12
    assert row["vol_control_state"] == "target_vol_12"


def test_cta_vol_selector_parity_detects_real_mismatch(tmp_path: Path):
    write_cta_vol_history(tmp_path)
    outcomes = pd.DataFrame([{"target_market": "QQQ", "decision_date": "2026-01-05", "decision_timestamp_utc": "2026-01-05T21:00:00Z"}])
    panel, _, _ = m.build_cta_vol_feature_outcome_panel(tmp_path, outcomes, m.rules(tmp_path))
    panel.loc[panel.index[0], "cta_selected_source_content_hash"] = "tampered"
    parity = m.build_cta_vol_selector_parity_audit(tmp_path, panel, m.rules(tmp_path))
    cta_only = parity[(parity["model_scope"].eq("CTA_only")) & (parity["required_source_family"].eq("CTA"))].iloc[0]
    vol_only = parity[(parity["model_scope"].eq("Vol_only")) & (parity["required_source_family"].eq("VolControl"))].iloc[0]
    assert cta_only["selection_parity_status"] == "mismatch"
    assert vol_only["selection_parity_status"] == "matched"


def test_missing_cta_history_is_unavailable_coverage_not_selected_invalid(tmp_path: Path):
    selected = m.select_latest_clean_feature(
        family="CTA",
        target="QQQ",
        decision_timestamp_utc="2026-01-05T21:00:00Z",
        target_vol=None,
        source_rows=pd.DataFrame(),
    )
    assert selected["selection_status"] == "unavailable_coverage"
    assert selected["availability_state"] == "coverage_not_started"


def test_market_level_spec_keeps_leveraged_out_of_eod_and_cta_out_of_intraday():
    spec = m.market_level_model_spec()
    assert all("aggregate_pressure_usd" not in model["features"] for model in spec["eod_models"].values())
    assert all("cta_exposure_change_proxy" not in model["features"] for model in spec["intraday_models"].values())
    assert spec["actionization_gate"] is False


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
    write_nyse_calendar(tmp_path)
    write_expiry_intraday_rules(tmp_path, verified=True)
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
            {"ticker": "QQQ", "effective_available_at_utc": "2026-01-05T14:00:00Z", "feature_as_of_timestamp_utc": "2026-01-05T14:00:00Z", "raw_chain_present": False, "raw_chain_quality": "high", "data_type": "reconstructed_from_raw_chain", "dealer_position_observed": False, "gamma_flip_state": "local_flip_found", "gamma_flip_distance_pct": 0.02, "net_gex_proxy": 1.0},
            {"ticker": "QQQ", "effective_available_at_utc": "2026-01-05T14:00:00Z", "feature_as_of_timestamp_utc": "2026-01-05T14:00:00Z", "raw_chain_present": True, "raw_chain_quality": "high", "data_type": "reconstructed_from_raw_chain", "dealer_position_observed": False, "gamma_flip_state": "no_local_flip", "net_gex_proxy": 1.0},
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
            {"ticker": "QQQ", "effective_available_at_utc": "2026-01-05T14:00:00Z", "feature_as_of_timestamp_utc": "2026-01-05T14:00:00Z", "raw_chain_present": True, "raw_chain_quality": "high", "data_type": "reconstructed_from_raw_chain", "dealer_position_observed": False, "gamma_flip_state": "no_local_flip", "net_gex_proxy": 1.0}
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
    write_nyse_calendar(tmp_path)
    write_expiry_intraday_rules(tmp_path, verified=True)
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
    write_nyse_calendar(tmp_path, [
        {"session_date": d.date().isoformat(), "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False}
        for d in pd.bdate_range("2025-11-28", periods=24)
    ])
    write_expiry_intraday_rules(tmp_path, verified=True)
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
    calendar = pd.DataFrame(
        [
            {"session_date": "2026-06-18", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
            {"session_date": "2026-06-19", "is_regular_session": False, "regular_open_et": "", "regular_close_et": "", "is_early_close": False},
            {"session_date": "2026-06-22", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
        ]
    )
    prev = m.previous_regular_session_close_utc(pd.Timestamp("2026-06-22"), calendar)
    assert prev.tz_convert("America/New_York").date().isoformat() == "2026-06-18"


def test_expiry_calendar_and_gamma_conditioned_are_separate(tmp_path: Path):
    write_nyse_calendar(tmp_path)
    write_expiry_intraday_rules(tmp_path, verified=True)
    write_expiry_friday_classification(tmp_path)
    write_expiry_intraday_bars(tmp_path)
    cfg = tmp_path / "market_bomb_config"
    cfg.mkdir(exist_ok=True)
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
    calendar, conditioned, post, audit, outcome_audit, calendar_availability = m.build_dealer_gamma_expiry_event_panel(tmp_path, outcomes, m.rules(tmp_path))
    assert not calendar.empty
    assert not conditioned.empty
    assert set(calendar["feature_family"]) == {"ExpiryCalendar"}
    assert set(conditioned["feature_family"]) == {"DealerGammaExpiryConditioned"}
    assert "selected_snapshot_asof_utc" in conditioned.columns
    assert "expiry_session_return_first_regular_bar_open_to_close" in calendar.columns
    assert not post.empty
    assert not calendar_availability.empty


def test_expiry_rejects_gamma_snapshot_after_0930(tmp_path: Path):
    write_nyse_calendar(tmp_path)
    write_expiry_intraday_rules(tmp_path, verified=True)
    write_expiry_friday_classification(tmp_path)
    write_expiry_intraday_bars(tmp_path)
    cfg = tmp_path / "market_bomb_config"
    cfg.mkdir(exist_ok=True)
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
    _, conditioned, _, audit, _, _ = m.build_dealer_gamma_expiry_event_panel(tmp_path, outcomes, m.rules(tmp_path))
    assert conditioned.empty
    assert "no_strict_prior_gamma_snapshot" in set(audit.get("availability_failure_reason", pd.Series(dtype=str)).astype(str))


def test_nyse_calendar_coverage_missing_makes_session_unavailable():
    calendar = pd.DataFrame([{"session_date": "2026-01-05", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False}])
    session = m.get_nyse_session("2026-01-06", calendar)
    assert session["availability_status"] == "unavailable"
    assert session["availability_failure_reason"] == "nyse_calendar_coverage_missing"


def test_early_close_excluded_from_leveraged_and_expiry_primary(tmp_path: Path):
    write_nyse_calendar(tmp_path, [
        {"session_date": "2026-11-25", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
        {"session_date": "2026-11-27", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "13:00", "is_early_close": True},
    ])
    hist = tmp_path / "market_bomb_history"
    hist.mkdir(parents=True)
    pd.DataFrame(
        [
            {"ticker": t, "effective_available_at_utc": "2026-11-25T21:00:00Z", "as_of_timestamp_utc": "2026-11-25T21:00:00Z", "net_assets_usd": 100.0, "aum_value_type": "net_assets_usd"}
            for t in ["TQQQ", "SQQQ", "QLD", "QID"]
        ]
    ).to_csv(hist / "leveraged_etf_aum_history.csv", index=False)
    write_expiry_intraday_rules(tmp_path, verified=True)
    write_expiry_intraday_bars(tmp_path, day="2026-11-27")
    panel, lev_audit = m.build_leveraged_etf_panel(tmp_path, m.rules(tmp_path))
    outcome, expiry_audit = m.build_expiry_intraday_outcome(tmp_path, "QQQ", "2026-11-27", "non_expiry_friday", m.load_nyse_calendar(tmp_path), m.rules(tmp_path))
    assert panel.empty
    assert "early_close_session_excluded_from_primary" in set(lev_audit["availability_failure_reason"])
    assert outcome is None
    assert expiry_audit["outcome_availability_failure_reason"] == "early_close_session_excluded_from_primary"


def test_expiry_primary_requires_exact_open_and_close_bars(tmp_path: Path):
    write_nyse_calendar(tmp_path)
    write_expiry_intraday_rules(tmp_path, verified=True)
    bars_dir = tmp_path / "market_bomb_history" / "intraday_bars"
    bars_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {"timestamp_utc": "2026-01-16T15:00:00Z", "open": 100, "high": 100, "low": 100, "close": 100, "volume": 100},
            {"timestamp_utc": "2026-01-16T21:00:00Z", "open": 101, "high": 101, "low": 101, "close": 101, "volume": 100},
        ]
    ).to_csv(bars_dir / "QQQ_5m.csv", index=False)
    outcome, audit = m.build_expiry_intraday_outcome(tmp_path, "QQQ", "2026-01-16", "monthly_expiry_non_quarterly", m.load_nyse_calendar(tmp_path), m.rules(tmp_path))
    assert outcome is None
    assert audit["outcome_availability_failure_reason"] == "expiry_exact_first_regular_bar_missing"


def test_expiry_intraday_range_uses_only_0930_to_close_window(tmp_path: Path):
    write_nyse_calendar(tmp_path)
    write_expiry_intraday_rules(tmp_path, verified=True)
    bars_dir = tmp_path / "market_bomb_history" / "intraday_bars"
    bars_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {"timestamp_utc": "2026-01-16T14:00:00Z", "open": 100, "high": 999, "low": 1, "close": 100, "volume": 100},
            {"timestamp_utc": "2026-01-16T14:30:00Z", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 100},
            {"timestamp_utc": "2026-01-16T14:35:00Z", "open": 100, "high": 101, "low": 99, "close": 101, "volume": 100},
            {"timestamp_utc": "2026-01-16T16:00:00Z", "open": 100, "high": 104, "low": 98, "close": 102, "volume": 100},
            {"timestamp_utc": "2026-01-16T21:00:00Z", "open": 102, "high": 103, "low": 101, "close": 103, "volume": 100},
        ]
    ).to_csv(bars_dir / "QQQ_5m.csv", index=False)
    outcome, audit = m.build_expiry_intraday_outcome(tmp_path, "QQQ", "2026-01-16", "monthly_expiry_non_quarterly", m.load_nyse_calendar(tmp_path), m.rules(tmp_path))
    assert outcome is not None
    assert np.isclose(outcome["expiry_session_high_low_range_pct"], (104 - 98) / 100)


def test_expiry_provider_semantics_unverified_blocks_primary(tmp_path: Path):
    write_nyse_calendar(tmp_path)
    write_expiry_intraday_rules(tmp_path, verified=False)
    write_expiry_intraday_bars(tmp_path)
    outcome, audit = m.build_expiry_intraday_outcome(tmp_path, "QQQ", "2026-01-16", "monthly_expiry_non_quarterly", m.load_nyse_calendar(tmp_path), m.rules(tmp_path))
    assert outcome is None
    assert audit["outcome_availability_failure_reason"] == "provider_bar_semantics_unverified"


def test_leveraged_etf_completed_bar_labels_are_saved(tmp_path: Path):
    write_nyse_calendar(tmp_path, [
        {"session_date": "2026-01-15", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
        {"session_date": "2026-01-16", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
    ])
    write_expiry_intraday_rules(tmp_path, verified=True)
    hist = tmp_path / "market_bomb_history"
    hist.mkdir(parents=True)
    pd.DataFrame(
        [
            {"ticker": t, "effective_available_at_utc": "2026-01-15T21:00:00Z", "as_of_timestamp_utc": "2026-01-15T21:00:00Z", "net_assets_usd": 100.0, "aum_value_type": "net_assets_usd"}
            for t in ["TQQQ", "SQQQ", "QLD", "QID"]
        ]
    ).to_csv(hist / "leveraged_etf_aum_history.csv", index=False)
    bars_dir = hist / "intraday_bars"
    bars_dir.mkdir()
    pd.DataFrame(
        [
            {"timestamp_utc": "2026-01-16T14:30:00Z", "open": 100, "high": 100, "low": 100, "close": 100, "volume": 100, "prior_regular_session_close": 100},
            {"timestamp_utc": "2026-01-16T20:30:00Z", "open": 101, "high": 101, "low": 101, "close": 101, "volume": 100, "prior_regular_session_close": 100},
            {"timestamp_utc": "2026-01-16T21:00:00Z", "open": 102, "high": 102, "low": 102, "close": 102, "volume": 100, "prior_regular_session_close": 100},
        ]
    ).to_csv(bars_dir / "QQQ_5m.csv", index=False)
    _, audit = m.build_leveraged_etf_panel(tmp_path, m.rules(tmp_path))
    available = audit[audit["availability_status"].astype(str).eq("available")]
    assert not available.empty
    assert set(available["decision_price_method"]) == {"completed_bar_close"}
    assert set(available["close_price_method"]) == {"completed_regular_close_bar_close"}


def test_expiry_group_sufficiency_is_group_specific():
    panel = pd.DataFrame(
        [{"target_market": "QQQ", "decision_timestamp_utc": f"2026-01-{i+1:02d}T14:30:00Z", "comparison_group": "triple_witching", "y": 0.1} for i in range(2)]
        + [{"target_market": "QQQ", "decision_timestamp_utc": f"2026-02-{i+1:02d}T14:30:00Z", "comparison_group": "non_expiry_friday", "y": 0.1} for i in range(10)]
    )
    audit = m.build_expiry_group_sample_sufficiency_audit(panel, feature_family="ExpiryCalendar", outcomes=["y"], min_oos_rows=5, min_test_months=1)
    triple = audit[audit["comparison_group"].eq("triple_witching")].iloc[0]
    ref = audit[audit["comparison_group"].eq("non_expiry_friday")].iloc[0]
    assert triple["research_execution_gate"] == "insufficient_data"
    assert ref["research_execution_gate"] == "passed"


def test_raw_candidate_future_row_does_not_block_when_clean_replacement_exists():
    rows = pd.DataFrame(
        [
            {"target_market": "QQQ", "feature_as_of_timestamp_utc": "2026-01-16T13:00:00Z", "effective_available_at_utc": "2026-01-16T13:00:00Z", "quality_grade": "high"},
            {"target_market": "QQQ", "feature_as_of_timestamp_utc": "2026-01-16T15:00:00Z", "effective_available_at_utc": "2026-01-16T15:00:00Z", "quality_grade": "high"},
        ]
    )
    audit = m.audit_raw_feature_candidates(rows, "DealerGamma", "QQQ", "2026-01-16T14:30:00Z", 96)
    assert audit["excluded_future_timestamp_count"] == 1
    assert audit["module_gate_recommendation"] == "evaluate"


def test_raw_candidate_missing_only_blocks_module():
    rows = pd.DataFrame([{"target_market": "QQQ", "feature_as_of_timestamp_utc": "", "effective_available_at_utc": "", "quality_grade": "high"}])
    audit = m.audit_raw_feature_candidates(rows, "DealerGamma", "QQQ", "2026-01-16T14:30:00Z", 96)
    assert audit["module_gate_recommendation"] == "data_quality_blocked"
    assert audit["excluded_missing_timestamp_count"] > 0


def test_calendar_metadata_hash_mismatch_blocks_primary(tmp_path: Path):
    write_nyse_calendar(tmp_path)
    write_expiry_intraday_rules(tmp_path, verified=True)
    write_expiry_intraday_bars(tmp_path)
    metadata = tmp_path / "market_bomb_config" / "nyse_regular_sessions_metadata_v1.json"
    metadata.write_text(metadata.read_text(encoding="utf-8").replace(m.hash_file(tmp_path / "market_bomb_config" / "nyse_regular_sessions_v1.csv"), "bad_hash"), encoding="utf-8")
    outcome, audit = m.build_expiry_intraday_outcome(tmp_path, "QQQ", "2026-01-16", "monthly_expiry_non_quarterly", m.load_nyse_calendar(tmp_path), m.rules(tmp_path))
    assert outcome is None
    assert audit["outcome_availability_failure_reason"].startswith("nyse_calendar_provenance_validation_failed")


def test_expiry_group_contrast_uses_actual_walk_forward_predictions():
    rows = []
    for month, base_day in [(1, 10), (2, 10), (3, 10), (4, 10)]:
        for group, y in [("triple_witching", 0.03), ("non_expiry_friday", 0.01)]:
            rows.append({
                "target_market": "QQQ",
                "decision_timestamp_utc": f"2026-{month:02d}-{base_day:02d}T14:30:00Z",
                "comparison_group": group,
                "expiry_session_high_low_range_pct": y,
                "prior_return_1d": 0.0,
                "event_group_indicator": 1.0 if group == "triple_witching" else 0.0,
            })
    panel = pd.DataFrame(rows)
    cfg = m.rules(Path("."))
    cfg["walk_forward"]["minimum_train_observations"] = 2
    result, folds, preds = m.run_expiry_group_contrast_oos(
        panel,
        module="ExpiryCalendar",
        feature_family="ExpiryCalendar",
        feature_name="calendar_group_contrast",
        feature_cols=["event_group_indicator"],
        outcomes=["expiry_session_high_low_range_pct"],
        baseline_cols=["prior_return_1d"],
        cfg=cfg,
        min_oos_rows_per_group=2,
        min_test_months_per_group=2,
    )
    assert not preds.empty
    assert result.loc[0, "sample_count_oos"] == len(preds)
    assert result.loc[0, "event_group_oos_row_count"] == 3
    assert result.loc[0, "reference_group_oos_row_count"] == 3
    triple_folds = folds[folds["event_group"].eq("triple_witching")]
    assert set(triple_folds["fold_status"]) == {"insufficient_train", "tested"}


def test_expiry_group_contrast_fold_requires_both_groups_in_test():
    panel = pd.DataFrame([
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-10T14:30:00Z", "comparison_group": "triple_witching", "y": 0.1, "event_group_indicator": 1.0},
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-17T14:30:00Z", "comparison_group": "non_expiry_friday", "y": 0.0, "event_group_indicator": 0.0},
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-02-10T14:30:00Z", "comparison_group": "triple_witching", "y": 0.1, "event_group_indicator": 1.0},
    ])
    cfg = m.rules(Path("."))
    cfg["walk_forward"]["minimum_train_observations"] = 2
    _, folds, preds = m.run_expiry_group_contrast_oos(
        panel,
        module="ExpiryCalendar",
        feature_family="ExpiryCalendar",
        feature_name="calendar_group_contrast",
        feature_cols=["event_group_indicator"],
        outcomes=["y"],
        baseline_cols=[],
        cfg=cfg,
        min_oos_rows_per_group=1,
        min_test_months_per_group=1,
    )
    assert preds.empty
    assert "missing_reference_group_in_test" in set(folds["fold_status"])


def test_source_candidate_audit_preserves_future_row_when_clean_selected():
    raw = pd.DataFrame([
        {"asset": "QQQ", "feature_as_of_timestamp_utc": "2026-01-01T10:00:00Z", "effective_available_at_utc": "2026-01-01T10:00:00Z", "quality_flag": "high"},
        {"asset": "QQQ", "feature_as_of_timestamp_utc": "2026-01-02T22:00:00Z", "effective_available_at_utc": "2026-01-02T22:00:00Z", "quality_flag": "high"},
    ])
    audit = m.audit_source_feature_candidates(raw, "CTA", "CTA", "QQQ", "2026-01-02T20:00:00Z", 96, {"target_col": "asset", "feature_as_of_col": "feature_as_of_timestamp_utc", "effective_available_col": "effective_available_at_utc", "quality_col": "quality_flag", "target_alias": "QQQ"}, {"allowed_quality": ["high"]})
    summary = m.summarize_source_feature_candidate_audit(audit)
    assert int(audit["selected_for_panel"].sum()) == 1
    assert summary.loc[0, "module_gate_recommendation"] == "evaluate"
    assert summary.loc[0, "excluded_future_timestamp_count"] == 1


def test_calendar_availability_does_not_fallback_to_decision_time(tmp_path: Path):
    cfg = tmp_path / "market_bomb_config"
    cfg.mkdir()
    pd.DataFrame([{"date": "2026-01-16", "market": "US", "expiry_type": "monthly", "calendar_source_effective_at_utc": "2026-01-16T16:00:00Z", "availability_basis": "validated_calendar_export"}]).to_csv(cfg / "options_expiry_calendar_v1.csv", index=False)
    write_expiry_intraday_rules(tmp_path, verified=True)
    expiry = m.load_expiry_calendar(tmp_path)
    decision_ts = pd.Timestamp("2026-01-16T14:30:00Z")
    audit = m.resolve_calendar_availability(tmp_path, expiry, "2026-01-16", decision_ts, "monthly_expiry_non_quarterly")
    assert audit["availability_status"] == "unavailable"
    assert audit["availability_failure_reason"] == "calendar_effective_availability_after_decision"
    assert audit["effective_available_at_utc"] != decision_ts.isoformat()


def test_nyse_calendar_internal_gap_fails(tmp_path: Path):
    write_nyse_calendar(tmp_path, [
        {"session_date": "2026-01-01", "is_regular_session": False, "regular_open_et": "", "regular_close_et": "", "is_early_close": False},
        {"session_date": "2026-01-03", "is_regular_session": False, "regular_open_et": "", "regular_close_et": "", "is_early_close": False},
    ])
    calendar_path = tmp_path / "market_bomb_config" / "nyse_regular_sessions_v1.csv"
    df = pd.read_csv(calendar_path)
    df = df[df["session_date"].astype(str).ne("2026-01-02")]
    df.to_csv(calendar_path, index=False)
    metadata = tmp_path / "market_bomb_config" / "nyse_regular_sessions_metadata_v1.json"
    import json
    meta = json.loads(metadata.read_text(encoding="utf-8"))
    meta["source_file_sha256"] = m.hash_file(calendar_path)
    metadata.write_text(json.dumps(meta), encoding="utf-8")
    result = m.validate_nyse_calendar_provenance(tmp_path, m.load_nyse_calendar(tmp_path))
    assert result["reason"] == "nyse_calendar_internal_date_gap"


def test_nyse_calendar_placeholder_source_fails(tmp_path: Path):
    write_nyse_calendar(tmp_path)
    metadata = tmp_path / "market_bomb_config" / "nyse_regular_sessions_metadata_v1.json"
    text = metadata.read_text(encoding="utf-8").replace('"source_name":"unit_test_calendar"', '"source_name":"official_or_primary_calendar_source"')
    metadata.write_text(text, encoding="utf-8")
    result = m.validate_nyse_calendar_provenance(tmp_path, m.load_nyse_calendar(tmp_path))
    assert result["reason"] == "nyse_calendar_placeholder_source_identifier"


def test_nyse_early_close_at_1600_fails(tmp_path: Path):
    write_nyse_calendar(tmp_path, [{"session_date": "2026-01-02", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": True}])
    result = m.validate_nyse_calendar_provenance(tmp_path, m.load_nyse_calendar(tmp_path))
    assert result["reason"] == "nyse_calendar_early_close_close_not_early"


def test_missing_expiry_classification_does_not_create_non_expiry_reference():
    group = m.expiry_comparison_group(pd.Timestamp("2026-01-16"), pd.DataFrame(), pd.DataFrame(), pd.Timestamp("2026-01-16T14:30:00Z"))
    assert group == "unavailable_incomplete_schedule"


def test_group_contrast_baseline_excludes_expiry_flags():
    panel = pd.DataFrame([
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-16T14:30:00Z", "comparison_group": "triple_witching", "y": 0.1, "event_group_indicator": 1, "monthly_expiry_flag": 1, "quarterly_expiry_flag": 1, "triple_witching_flag": 1, "prior_return_1d": 0.0},
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-23T14:30:00Z", "comparison_group": "non_expiry_friday", "y": 0.0, "event_group_indicator": 0, "monthly_expiry_flag": 0, "quarterly_expiry_flag": 0, "triple_witching_flag": 0, "prior_return_1d": 0.0},
    ])
    cfg = m.rules(Path("."))
    cfg["walk_forward"]["minimum_train_observations"] = 1
    result, _, _ = m.run_expiry_group_contrast_oos(panel, module="ExpiryCalendar", feature_family="ExpiryCalendar", feature_name="calendar_group_contrast", feature_cols=["event_group_indicator"], outcomes=["y"], baseline_cols=["prior_return_1d", "monthly_expiry_flag", "quarterly_expiry_flag", "triple_witching_flag"], cfg=cfg, min_oos_rows_per_group=1, min_test_months_per_group=1)
    assert "monthly_expiry_flag" not in ",".join(result.get("baseline_feature_columns", pd.Series(dtype=str)).astype(str))


def test_coverage_not_started_is_not_data_quality_blocked():
    audit = pd.DataFrame([
        {"module": "CTA", "feature_family": "CTA", "target_market": "QQQ", "decision_timestamp_utc": "2026-01-01T20:00:00Z", "effective_available_at_utc": "2026-01-02T20:00:00Z", "candidate_eligibility_status": "excluded", "candidate_exclusion_reason": "effective_after_decision", "selected_for_panel": False}
    ])
    summary = m.summarize_source_feature_candidate_audit(audit)
    assert summary.loc[0, "decision_level_availability_state"] == "coverage_not_started"
    assert summary.loc[0, "module_gate_recommendation"] == "insufficient_data"


def test_missing_timestamp_without_clean_replacement_blocks_scope():
    audit = pd.DataFrame([
        {"module": "CTA", "feature_family": "CTA", "target_market": "QQQ", "decision_timestamp_utc": "2026-01-01T20:00:00Z", "effective_available_at_utc": "", "candidate_eligibility_status": "excluded", "candidate_exclusion_reason": "effective_available_timestamp_missing;feature_age_missing", "selected_for_panel": False}
    ])
    summary = m.summarize_source_feature_candidate_audit(audit)
    assert summary.loc[0, "module_gate_recommendation"] == "data_quality_blocked"


def test_expiry_classification_provenance_detects_missing_friday(tmp_path: Path):
    write_nyse_calendar(tmp_path, [
        {"session_date": "2026-01-02", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
        {"session_date": "2026-01-09", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
    ])
    cfg = tmp_path / "market_bomb_config"
    pd.DataFrame([{"date": "2026-01-16", "market": "US", "expiry_type": "monthly", "monthly_expiry_flag": True, "quarterly_expiry_flag": False, "triple_witching_flag": False, "holiday_adjusted_flag": False}]).to_csv(cfg / "options_expiry_calendar_v1.csv", index=False)
    write_expiry_intraday_rules(tmp_path, verified=True)
    write_expiry_friday_classification(tmp_path, day="2026-01-02", group="non_expiry_friday")
    import json
    for path_name in ["options_expiry_calendar_metadata_v1.json", "expiry_friday_classification_metadata_v1.json"]:
        meta_path = cfg / path_name
        meta = {
            "calendar_source_file_sha256": m.hash_file(cfg / "options_expiry_calendar_v1.csv"),
            "schedule_rules_file_sha256": m.hash_file(cfg / "expiry_schedule_availability_rules_v1.json"),
            "classification_calendar_file_sha256": m.hash_file(cfg / "expiry_friday_classification_v1.csv"),
            "source_identifier": "unit_test_source",
            "source_retrieved_at_utc": "2026-01-01T00:00:00Z",
            "generation_method": "unit_test_generation",
            "coverage_start": "2026-01-02",
            "coverage_end": "2026-01-09",
        }
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
    result = m.validate_expiry_classification_provenance(tmp_path, m.load_expiry_friday_classification(tmp_path), m.load_nyse_calendar(tmp_path))
    assert result["reason"] == "expiry_classification_coverage_incomplete"


def test_expiry_historical_availability_uses_event_day_0930_not_close(tmp_path: Path):
    write_nyse_calendar(tmp_path)
    write_expiry_intraday_rules(tmp_path, verified=True)
    write_expiry_friday_classification(tmp_path)
    cfg = tmp_path / "market_bomb_config"
    path = cfg / "expiry_friday_classification_v1.csv"
    df = pd.read_csv(path)
    df["classification_effective_available_at_utc"] = "2026-01-16T17:00:00Z"
    df.to_csv(path, index=False)
    audit = m.build_expiry_classification_historical_availability_audit(
        tmp_path,
        m.load_expiry_friday_classification(tmp_path),
        m.load_nyse_calendar(tmp_path),
        pd.DataFrame([{"target_market": "QQQ", "decision_date": "2026-01-16", "decision_timestamp_utc": "2026-01-16T21:00:00Z"}]),
    )
    row = audit[audit["session_date"].astype(str).eq("2026-01-16")].iloc[0]
    assert row["decision_time_policy"] == "expiry_event_decision_0930_et_v1"
    assert row["historically_available_at_decision"] is False or row["historically_available_at_decision"] == False
    assert row["eligibility_failure_reason"] == "classification_effective_availability_after_decision"


def test_leveraged_etf_input_candidate_audit_has_aum_and_exact_bars(tmp_path: Path):
    write_nyse_calendar(tmp_path, [
        {"session_date": "2026-01-15", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
        {"session_date": "2026-01-16", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
    ])
    hist = tmp_path / "market_bomb_history"
    hist.mkdir(parents=True)
    pd.DataFrame([
        {"ticker": t, "effective_available_at_utc": "2026-01-15T21:00:00Z", "as_of_timestamp_utc": "2026-01-15T21:00:00Z", "net_assets_usd": 100.0, "aum_value_type": "net_assets_usd"}
        for t in ["TQQQ", "SQQQ", "QLD", "QID"]
    ]).to_csv(hist / "leveraged_etf_aum_history.csv", index=False)
    bars_dir = hist / "intraday_bars"
    bars_dir.mkdir()
    pd.DataFrame([
        {"timestamp_utc": "2026-01-16T14:30:00Z", "open": 100, "high": 100, "low": 100, "close": 100, "volume": 100, "prior_regular_session_close": 100},
        {"timestamp_utc": "2026-01-16T20:25:00Z", "open": 100, "high": 100, "low": 100, "close": 100, "volume": 100, "prior_regular_session_close": 100},
        {"timestamp_utc": "2026-01-16T20:30:00Z", "open": 101, "high": 101, "low": 101, "close": 101, "volume": 100, "prior_regular_session_close": 100},
        {"timestamp_utc": "2026-01-16T21:00:00Z", "open": 102, "high": 102, "low": 102, "close": 102, "volume": 100, "prior_regular_session_close": 100},
    ]).to_csv(bars_dir / "QQQ_5m.csv", index=False)
    universe, _ = m.build_market_level_intraday_universe_with_gate(tmp_path, m.rules(tmp_path))
    candidate, _, universe, _ = m.build_leveraged_etf_input_candidate_audits(tmp_path, m.rules(tmp_path), universe)
    assert {"aum", "decision_bar_1530", "close_bar_1600"}.issubset(set(candidate["input_component"]))
    assert "2026-01-16T20:25:00Z" not in set(candidate.get("actual_bar_timestamp_utc", pd.Series(dtype=str)).astype(str))
    assert not universe.empty


def test_aum_primary_eligibility_is_bool_contract_not_source_label(tmp_path: Path):
    hist = tmp_path / "market_bomb_history"
    hist.mkdir(parents=True)
    aum = pd.DataFrame([{
        "ticker": "TQQQ",
        "effective_available_at_utc": "2026-01-15T21:00:00Z",
        "as_of_timestamp_utc": "2026-01-15T21:00:00Z",
        "net_assets_usd": 100.0,
        "aum_value_type": "net_assets_usd",
    }])
    record = m.prior_available_aum_record(aum, "TQQQ", pd.Timestamp("2026-01-16T20:30:00Z"), pd.Timestamp("2026-01-15T21:00:00Z"))
    assert record["aum_source"] == "previous_available_net_assets_usd"
    assert record["primary_eligible"] is True
    assert record["selection_status"] == "selected_clean"


def test_date_only_and_surrogate_aum_are_not_primary():
    decision = pd.Timestamp("2026-01-16T20:30:00Z")
    prior_close = pd.Timestamp("2026-01-15T21:00:00Z")
    date_only = pd.DataFrame([{"ticker": "TQQQ", "date": "2026-01-15", "net_assets_usd": 100.0}])
    surrogate = pd.DataFrame([{
        "ticker": "TQQQ",
        "effective_available_at_utc": "2026-01-15T21:00:00Z",
        "as_of_timestamp_utc": "2026-01-15T21:00:00Z",
        "shares_outstanding": 10.0,
        "prior_close": 20.0,
        "aum_value_type": "shares_outstanding_x_price",
    }])
    assert m.prior_available_aum_record(date_only, "TQQQ", decision, prior_close)["primary_eligible"] is False
    surrogate_record = m.prior_available_aum_record(surrogate, "TQQQ", decision, prior_close)
    assert surrogate_record["primary_eligible"] is False
    assert surrogate_record["analysis_mode"] == "imputed_surrogate_exploratory"


def test_leveraged_provider_semantics_unverified_blocks_primary_panel(tmp_path: Path):
    write_nyse_calendar(tmp_path)
    write_expiry_intraday_rules(tmp_path, verified=False)
    hist = tmp_path / "market_bomb_history"
    hist.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"ticker": t, "effective_available_at_utc": "2026-01-02T21:00:00Z", "as_of_timestamp_utc": "2026-01-02T21:00:00Z", "net_assets_usd": 100.0, "aum_value_type": "net_assets_usd"}
        for t in ["TQQQ", "SQQQ", "QLD", "QID"]
    ]).to_csv(hist / "leveraged_etf_aum_history.csv", index=False)
    bars_dir = hist / "intraday_bars"
    bars_dir.mkdir()
    pd.DataFrame([
        {"timestamp_utc": "2026-01-05T14:30:00Z", "close": 100, "volume": 100, "prior_regular_session_close": 100},
        {"timestamp_utc": "2026-01-05T20:30:00Z", "close": 101, "volume": 100},
        {"timestamp_utc": "2026-01-05T21:00:00Z", "close": 102, "volume": 100},
    ]).to_csv(bars_dir / "QQQ_5m.csv", index=False)
    panel, audit = m.build_leveraged_etf_panel(tmp_path, m.rules(tmp_path))
    assert panel.empty
    assert "provider_bar_semantics_unverified" in set(audit["availability_failure_reason"].astype(str))


def test_leveraged_provider_semantics_missing_blocks_primary_panel(tmp_path: Path):
    write_nyse_calendar(tmp_path)
    hist = tmp_path / "market_bomb_history"
    hist.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"ticker": t, "effective_available_at_utc": "2026-01-02T21:00:00Z", "as_of_timestamp_utc": "2026-01-02T21:00:00Z", "net_assets_usd": 100.0, "aum_value_type": "net_assets_usd"}
        for t in ["TQQQ", "SQQQ", "QLD", "QID"]
    ]).to_csv(hist / "leveraged_etf_aum_history.csv", index=False)
    bars_dir = hist / "intraday_bars"
    bars_dir.mkdir()
    pd.DataFrame([
        {"timestamp_utc": "2026-01-05T14:30:00Z", "close": 100, "volume": 100, "prior_regular_session_close": 100},
        {"timestamp_utc": "2026-01-05T20:30:00Z", "close": 101, "volume": 100},
        {"timestamp_utc": "2026-01-05T21:00:00Z", "close": 102, "volume": 100},
    ]).to_csv(bars_dir / "QQQ_5m.csv", index=False)
    panel, audit = m.build_leveraged_etf_panel(tmp_path, m.rules(tmp_path))
    assert panel.empty
    assert "provider_bar_semantics_unverified" in set(audit["availability_failure_reason"].astype(str))


def test_leveraged_volume_reference_minimum_blocks_primary_panel(tmp_path: Path):
    write_nyse_calendar(tmp_path)
    write_expiry_intraday_rules(tmp_path, verified=True)
    cfg = tmp_path / "market_bomb_config"
    (cfg / "market_impact_backtest_rules_v1.json").write_text(
        '{"targets":["QQQ"],"primary_decision_bar_et":"15:30","primary_close_bar_et":"16:00","bar_timestamp_convention":"bar_end","minimum_samples":{"leveraged_etf_volume_reference_min_sessions":20}}',
        encoding="utf-8",
    )
    hist = tmp_path / "market_bomb_history"
    hist.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"ticker": t, "effective_available_at_utc": "2026-01-02T21:00:00Z", "as_of_timestamp_utc": "2026-01-02T21:00:00Z", "net_assets_usd": 100.0, "aum_value_type": "net_assets_usd"}
        for t in ["TQQQ", "SQQQ", "QLD", "QID"]
    ]).to_csv(hist / "leveraged_etf_aum_history.csv", index=False)
    bars_dir = hist / "intraday_bars"
    bars_dir.mkdir()
    pd.DataFrame([
        {"timestamp_utc": "2026-01-05T14:30:00Z", "close": 100, "volume": 100, "prior_regular_session_close": 100},
        {"timestamp_utc": "2026-01-05T20:30:00Z", "close": 101, "volume": 100},
        {"timestamp_utc": "2026-01-05T21:00:00Z", "close": 102, "volume": 100},
    ]).to_csv(bars_dir / "QQQ_5m.csv", index=False)
    panel, audit = m.build_leveraged_etf_panel(tmp_path, m.rules(tmp_path))
    assert panel.empty
    assert "volume_reference_insufficient" in set(audit["availability_failure_reason"].astype(str))


def test_strict_rth_volume_reference_excludes_pre_post_and_early_close(tmp_path: Path):
    write_nyse_calendar(tmp_path, [
        {"session_date": "2026-01-02", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "13:00", "is_early_close": True},
        {"session_date": "2026-01-05", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
        {"session_date": "2026-01-06", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
    ])
    cal = m.load_nyse_calendar(tmp_path)
    rows = []
    for ts, vol in [
        ("2026-01-05T13:00:00Z", 999),
        ("2026-01-05T14:30:00Z", 100),
        ("2026-01-05T20:30:00Z", 100),
        ("2026-01-05T22:00:00Z", 999),
        ("2026-01-06T13:00:00Z", 999),
        ("2026-01-06T14:30:00Z", 200),
        ("2026-01-06T20:30:00Z", 200),
        ("2026-01-06T22:00:00Z", 999),
    ]:
        rows.append({"timestamp_utc": ts, "volume": vol})
    ref = m.strict_rth_volume_reference(pd.DataFrame(rows), "2026-01-06", pd.Timestamp("15:30").time(), cal, window=1, min_valid_sessions=1)
    assert ref["rth_volume_reference_status"] == "eligible"
    assert ref["rth_volume_reference_excluded_premarket_rows"] == 1
    assert ref["rth_volume_reference_excluded_postmarket_rows"] == 1
    assert "2026-01-05" in ref["rth_volume_reference_session_dates"]


def test_oos_no_predictions_has_null_pvalue_not_run():
    panel = pd.DataFrame({"target_market": ["QQQ"], "decision_timestamp_utc": ["2026-01-05T21:00:00Z"], "x": [1.0], "y": [0.1]})
    cfg = m.rules(Path("."))
    cfg["walk_forward"]["minimum_train_observations"] = 252
    result, _ = m.run_oos_comparison(panel, module="X", test_family="unit", feature_sets={"x": ["x"]}, outcomes=["y"], baseline_cols=[], cfg=cfg, min_oos_rows=2, min_test_months=1)
    assert pd.isna(result.loc[0, "raw_p_value"])
    assert pd.isna(result.loc[0, "adjusted_p_value"])
    assert result.loc[0, "p_value_status"] == "not_run"


def test_module_quality_block_only_blocks_offending_module():
    audit = pd.DataFrame(
        [
            {"module": "LeveragedETF", "no_lookahead_passed": False, "violation_reason": "feature_asof_after_decision"},
            {"module": "CTA_Vol", "no_lookahead_passed": True, "violation_reason": ""},
        ]
    )
    blocked = m.quality_blocked_modules(audit)
    lev = pd.DataFrame([{"module": "LeveragedETF", "research_execution_gate": "insufficient_data", "evidence_verdict": "insufficient_data"}])
    cta = pd.DataFrame([{"module": "CTA_Vol", "research_execution_gate": "insufficient_data", "evidence_verdict": "insufficient_data"}])
    lev2 = m.apply_data_quality_block(lev, "LeveragedETF", blocked)
    cta2 = m.apply_data_quality_block(cta, "CTA_Vol", blocked)
    assert lev2.loc[0, "research_execution_gate"] == "data_quality_blocked"
    assert cta2.loc[0, "research_execution_gate"] == "insufficient_data"


def test_v118_cta_latest_low_quality_is_skipped_for_earlier_clean():
    rows = pd.DataFrame([
        {"asset": "QQQ", "feature_as_of_timestamp_utc": "2026-01-05T20:00:00Z", "effective_available_at_utc": "2026-01-05T20:00:00Z", "cta_exposure_change_1d": 1.0, "quality_flag": "high"},
        {"asset": "QQQ", "feature_as_of_timestamp_utc": "2026-01-05T21:00:00Z", "effective_available_at_utc": "2026-01-05T21:00:00Z", "cta_exposure_change_1d": -9.0, "quality_flag": "low"},
    ])
    selected = m.select_latest_clean_feature(family="CTA", target="QQQ", decision_timestamp_utc="2026-01-05T21:30:00Z", target_vol=None, source_rows=rows)
    assert selected["selection_status"] == "selected"
    assert selected["selected_source_quality_value"] == "high"
    assert selected["row"]["cta_exposure_change_1d"] == 1.0


def test_v118_vol_latest_low_quality_target_vol_is_skipped_for_earlier_clean():
    rows = pd.DataFrame([
        {"asset": "QQQ", "target_vol": 0.12, "feature_as_of_timestamp_utc": "2026-01-05T20:00:00Z", "effective_available_at_utc": "2026-01-05T20:00:00Z", "vol_control_exposure_change_1d": 2.0, "quality_flag": "medium"},
        {"asset": "QQQ", "target_vol": 0.12, "feature_as_of_timestamp_utc": "2026-01-05T21:00:00Z", "effective_available_at_utc": "2026-01-05T21:00:00Z", "vol_control_exposure_change_1d": -5.0, "quality_flag": "bad"},
        {"asset": "QQQ", "target_vol": 0.10, "feature_as_of_timestamp_utc": "2026-01-05T21:10:00Z", "effective_available_at_utc": "2026-01-05T21:10:00Z", "vol_control_exposure_change_1d": 99.0, "quality_flag": "high"},
    ])
    selected = m.select_latest_clean_feature(family="VolControl", target="QQQ", decision_timestamp_utc="2026-01-05T21:30:00Z", target_vol=0.12, source_rows=rows)
    assert selected["selection_status"] == "selected"
    assert selected["row"]["vol_control_exposure_change_1d"] == 2.0


def test_v118_required_quality_field_missing_is_selected_invalid():
    rows = pd.DataFrame([
        {"asset": "QQQ", "feature_as_of_timestamp_utc": "2026-01-05T20:00:00Z", "effective_available_at_utc": "2026-01-05T20:00:00Z", "cta_exposure_change_1d": 1.0},
    ])
    selected = m.select_latest_clean_feature(family="CTA", target="QQQ", decision_timestamp_utc="2026-01-05T21:30:00Z", target_vol=None, source_rows=rows)
    assert selected["selection_status"] == "selected_invalid"
    assert "required_quality_field_missing" in selected["invalid_reason"]


def test_v118_strict_rth_reference_uses_most_recent_valid_sessions():
    rows = []
    sessions = []
    for i, day in enumerate(pd.date_range("2026-01-02", periods=6, freq="B")):
        d = day.date()
        sessions.append({"session_date": d.isoformat(), "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False})
        volume = [10, 20, 30, 40, 50, 100][i]
        rows.append({"timestamp_utc": pd.Timestamp.combine(d, pd.Timestamp("15:30").time()).tz_localize("America/New_York").tz_convert("UTC"), "volume": volume})
    ref = m.strict_rth_volume_reference(pd.DataFrame(rows), "2026-01-09", pd.Timestamp("15:30").time(), pd.DataFrame(sessions), window=2, min_valid_sessions=2)
    assert ref["rth_volume_reference_session_dates"] == "2026-01-07;2026-01-08"
    assert np.isclose(ref["volume_ratio"], 100 / 45)


def test_v118_local_flip_alone_does_not_create_negative_gamma(tmp_path: Path):
    cfg = tmp_path / "market_bomb_config"
    cfg.mkdir()
    (cfg / "dealer_gamma_observed_rules_v1.json").write_text('{"sign_convention":"positive_net_gex_proxy_means_long_gamma_proxy_not_dealer_inventory"}', encoding="utf-8")
    pd.DataFrame([
        {"ticker": "QQQ", "feature_as_of_timestamp_utc": "2026-01-05T20:00:00Z", "effective_available_at_utc": "2026-01-05T20:00:00Z", "raw_chain_present": True, "raw_chain_quality": "high", "data_type": "reconstructed_from_raw_chain", "dealer_position_observed": False, "gamma_flip_state": "local_flip_found", "gamma_flip_distance_pct": 0.02, "net_gex_proxy": 10.0},
    ]).to_csv(tmp_path / "dealer_gamma_proxy_history.csv", index=False)
    outcomes = pd.DataFrame([{"target_market": "QQQ", "decision_date": "2026-01-05", "decision_timestamp_utc": "2026-01-05T21:00:00Z"}])
    panel, _ = m.build_dealer_gamma_panel(tmp_path, outcomes, m.rules(tmp_path))
    assert panel.iloc[0]["local_flip_found_flag"] == 1
    assert panel.iloc[0]["negative_gamma_proxy_indicator"] == 0


def test_v118_invalid_cta_blocks_only_dependent_scope_and_target():
    panel = pd.DataFrame([
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-05T21:00:00Z", "model_clock": "EOD", "cta_selection_status": "selected_invalid", "cta_primary_eligible": False, "cta_invalid_reason": "required_quality_field_missing", "vol_selection_status": "selected", "vol_primary_eligible": True},
        {"target_market": "SPY", "decision_timestamp_utc": "2026-01-05T21:00:00Z", "model_clock": "EOD", "cta_selection_status": "selected", "cta_primary_eligible": True, "vol_selection_status": "selected", "vol_primary_eligible": True},
    ])
    provenance = m.build_market_level_component_provenance_status(
        market_level_panel=panel,
        cta_vol_selector_parity=_matched_cta_vol_parity(("QQQ", "SPY")),
        leveraged_selector_parity=pd.DataFrame(),
        leveraged_primary_integrity=pd.DataFrame(),
        dealer_eod_panel=pd.DataFrame(),
        dealer_intraday_selection=pd.DataFrame(),
    )
    integrity = m.build_market_level_model_scope_integrity(panel, provenance)
    qqq_b1 = integrity[(integrity["target_market"] == "QQQ") & (integrity["model_scope"] == "B1")]
    qqq_b2 = integrity[(integrity["target_market"] == "QQQ") & (integrity["model_scope"] == "B2")]
    spy_b1 = integrity[(integrity["target_market"] == "SPY") & (integrity["model_scope"] == "B1")]
    assert set(qqq_b1["scope_integrity_status"]) == {"selected_invalid"}
    assert set(qqq_b2["scope_integrity_status"]) == {"valid"}
    assert set(spy_b1["scope_integrity_status"]) == {"valid"}


def test_v118_c1_survives_missing_intraday_gamma_but_c2_does_not():
    panel = pd.DataFrame([
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-05T20:30:00Z", "model_clock": "INTRADAY", "aggregate_pressure_usd": 100.0, "leveraged_etf_primary_input_gate": "eligible_primary"},
    ])
    provenance = m.build_market_level_component_provenance_status(
        market_level_panel=panel,
        cta_vol_selector_parity=pd.DataFrame(),
        leveraged_selector_parity=pd.DataFrame([{"target_market": "QQQ", "decision_timestamp_utc": "2026-01-05T20:30:00Z", "selection_parity_status": "matched", "required_source_family": "aum:TQQQ"}]),
        leveraged_primary_integrity=pd.DataFrame([{"target_market": "QQQ", "decision_timestamp_utc": "2026-01-05T20:30:00Z", "leveraged_etf_primary_input_gate": "eligible_primary"}]),
        dealer_eod_panel=pd.DataFrame(),
        dealer_intraday_selection=pd.DataFrame(),
    )
    integrity = m.build_market_level_model_scope_integrity(panel, provenance)
    assert set(integrity[integrity["model_scope"] == "C1"]["scope_integrity_status"]) == {"valid"}
    assert set(integrity[integrity["model_scope"] == "C2"]["scope_integrity_status"]) == {"unavailable_coverage"}


def test_v118_paired_oos_uses_identical_parent_and_augmented_rows():
    n = 380
    dates = pd.bdate_range("2024-01-01", periods=n)
    frame = pd.DataFrame({
        "target_market": "QQQ",
        "decision_timestamp_utc": [pd.Timestamp(d).tz_localize("America/New_York").tz_convert("UTC").isoformat() for d in dates],
        "baseline": np.linspace(0, 1, n),
        "feature": np.linspace(1, 2, n),
        "outcome": np.linspace(0, 1, n) + 0.1,
    })
    cfg = {"walk_forward": {"minimum_train_observations": 252}, "statistical": {"ridge_alpha": 1.0}}
    preds, _, coefs = m.market_level_paired_walk_forward(frame, "outcome", "B0", "B1", "EOD", ["baseline"], [], ["feature"], cfg)
    assert not preds.empty
    assert preds["parent_pred"].notna().all()
    assert preds["augmented_pred"].notna().all()
    assert set(coefs["fold_status"]) == {"tested"}


def _v119_base_market_panel(clock="EOD", target="QQQ"):
    return pd.DataFrame([{
        "target_market": target,
        "decision_timestamp_utc": "2026-01-05T21:00:00Z" if clock == "EOD" else "2026-01-05T20:30:00Z",
        "decision_date": "2026-01-05",
        "model_clock": clock,
        "cta_selection_status": "selected",
        "cta_availability_state": "valid",
        "cta_primary_eligible": True,
        "cta_selected_source_row_identifier": "cta1",
        "cta_selected_source_content_hash": "ctah",
        "cta_selected_source_effective_available_at_utc": "2026-01-05T20:00:00Z",
        "vol_selection_status": "selected",
        "vol_availability_state": "valid",
        "vol_primary_eligible": True,
        "vol_selected_source_row_identifier": "vol1",
        "vol_selected_source_content_hash": "volh",
        "vol_selected_source_effective_available_at_utc": "2026-01-05T20:00:00Z",
        "aggregate_pressure_usd": 0.0,
        "leveraged_etf_primary_input_gate": "eligible_primary",
        "next_session_return": 0.0,
    }])


def _matched_cta_vol_parity(targets=("QQQ",), decision="2026-01-05T21:00:00Z"):
    return pd.DataFrame([
        {"target_market": target, "decision_timestamp_utc": decision, "required_source_family": family, "selection_parity_status": "matched"}
        for target in targets
        for family in ["CTA", "VolControl"]
    ])


def _matched_gamma_parity(target="QQQ", decision="2026-01-05T21:00:00Z", family="DealerGammaEOD", context="EOD_CLOSE", row_id="g1", content_hash="gh"):
    return pd.DataFrame([{
        "target_market": target,
        "decision_timestamp_utc": decision,
        "selector_context": context,
        "required_source_family": family,
        "actual_selection_status": "selected",
        "fresh_selection_status": "selected",
        "actual_selected_source_row_identifier": row_id,
        "fresh_selected_source_row_identifier": row_id,
        "actual_selected_source_content_hash": content_hash,
        "fresh_selected_source_content_hash": content_hash,
        "actual_selected_source_effective_available_at_utc": "2026-01-05T20:00:00Z",
        "fresh_selected_source_effective_available_at_utc": "2026-01-05T20:00:00Z",
        "actual_primary_eligible": True,
        "fresh_primary_eligible": True,
        "selection_parity_status": "matched",
        "selection_parity_failure_reason": "",
    }])


def test_v119_cta_parity_mismatch_affects_only_dependent_scopes_and_target():
    panel = pd.concat([_v119_base_market_panel("EOD", "QQQ"), _v119_base_market_panel("EOD", "SPY")], ignore_index=True)
    parity = pd.concat([_matched_cta_vol_parity(("QQQ", "SPY")), pd.DataFrame([
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-05T21:00:00Z", "required_source_family": "CTA", "selection_parity_status": "mismatch"},
    ])], ignore_index=True)
    provenance = m.build_market_level_component_provenance_status(
        market_level_panel=panel,
        cta_vol_selector_parity=parity,
        leveraged_selector_parity=pd.DataFrame(),
        leveraged_primary_integrity=pd.DataFrame(),
        dealer_eod_panel=pd.DataFrame(),
        dealer_intraday_selection=pd.DataFrame(),
    )
    integrity = m.build_market_level_model_scope_integrity(panel, provenance)
    qqq = integrity[integrity["target_market"].eq("QQQ")]
    spy = integrity[integrity["target_market"].eq("SPY")]
    assert set(qqq[qqq["model_scope"].isin(["B1", "B3", "B4", "B5"])]["scope_integrity_status"]) == {"selected_invalid"}
    assert set(qqq[qqq["model_scope"].isin(["B0", "B2"])]["scope_integrity_status"]) == {"valid"}
    assert set(spy[spy["model_scope"].eq("B1")]["scope_integrity_status"]) == {"valid"}


def test_v119_vol_parity_mismatch_affects_b2_b3_b4_b5_not_b1():
    panel = _v119_base_market_panel("EOD", "QQQ")
    parity = pd.concat([_matched_cta_vol_parity(("QQQ",)), pd.DataFrame([
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-05T21:00:00Z", "required_source_family": "VolControl", "selection_parity_status": "mismatch"},
    ])], ignore_index=True)
    provenance = m.build_market_level_component_provenance_status(
        market_level_panel=panel,
        cta_vol_selector_parity=parity,
        leveraged_selector_parity=pd.DataFrame(),
        leveraged_primary_integrity=pd.DataFrame(),
        dealer_eod_panel=pd.DataFrame(),
        dealer_intraday_selection=pd.DataFrame(),
    )
    integrity = m.build_market_level_model_scope_integrity(panel, provenance)
    assert set(integrity[integrity["model_scope"].isin(["B2", "B3", "B4", "B5"])]["scope_integrity_status"]) == {"selected_invalid"}
    assert set(integrity[integrity["model_scope"].isin(["B0", "B1"])]["scope_integrity_status"]) == {"valid"}


def test_v119_leveraged_parity_mismatch_affects_c1_c2_c3_only():
    panel = _v119_base_market_panel("INTRADAY", "QQQ")
    parity = pd.DataFrame([
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-05T20:30:00Z", "selection_parity_status": "mismatch", "required_source_family": "aum:TQQQ"},
    ])
    primary = pd.DataFrame([
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-05T20:30:00Z", "leveraged_etf_primary_input_gate": "eligible_primary"},
    ])
    provenance = m.build_market_level_component_provenance_status(
        market_level_panel=panel,
        cta_vol_selector_parity=pd.DataFrame(),
        leveraged_selector_parity=parity,
        leveraged_primary_integrity=primary,
        dealer_eod_panel=pd.DataFrame(),
        dealer_intraday_selection=pd.DataFrame(),
    )
    integrity = m.build_market_level_model_scope_integrity(panel, provenance)
    assert set(integrity[integrity["model_scope"].eq("C0")]["scope_integrity_status"]) == {"valid"}
    assert set(integrity[integrity["model_scope"].isin(["C1", "C2", "C3"])]["scope_integrity_status"]) == {"selected_invalid"}


def test_v119_leveraged_coverage_gap_is_unavailable_not_selected_invalid():
    panel = _v119_base_market_panel("INTRADAY", "QQQ")
    panel["leveraged_etf_primary_input_gate"] = "insufficient_data"
    provenance = m.build_market_level_component_provenance_status(
        market_level_panel=panel,
        cta_vol_selector_parity=pd.DataFrame(),
        leveraged_selector_parity=pd.DataFrame(),
        leveraged_primary_integrity=pd.DataFrame(),
        dealer_eod_panel=pd.DataFrame(),
        dealer_intraday_selection=pd.DataFrame(),
    )
    integrity = m.build_market_level_model_scope_integrity(panel, provenance)
    assert set(integrity[integrity["model_scope"].isin(["C1", "C2", "C3"])]["scope_integrity_status"]) == {"unavailable_coverage"}


def test_v119_cta_vol_row_is_retained_when_both_unavailable(tmp_path: Path):
    outcomes = pd.DataFrame([{"target_market": "QQQ", "decision_date": "2026-01-05", "decision_timestamp_utc": "2026-01-05T21:00:00Z"}])
    panel, _, _ = m.build_cta_vol_feature_outcome_panel(tmp_path, outcomes, m.rules(tmp_path))
    assert len(panel) == 1
    assert panel.iloc[0]["cta_selection_status"] == "unavailable_coverage"
    assert panel.iloc[0]["vol_selection_status"] == "unavailable_coverage"


def test_v119_cta_selected_invalid_and_vol_unavailable_are_preserved(tmp_path: Path):
    hist = tmp_path / "market_bomb_history"
    hist.mkdir(parents=True)
    pd.DataFrame([{"asset": "QQQ", "feature_as_of_timestamp_utc": "2026-01-05T20:00:00Z", "effective_available_at_utc": "2026-01-05T20:00:00Z", "cta_exposure_change_1d": 1.0}]).to_csv(hist / "cta_proxy_history.csv", index=False)
    outcomes = pd.DataFrame([{"target_market": "QQQ", "decision_date": "2026-01-05", "decision_timestamp_utc": "2026-01-05T21:00:00Z"}])
    panel, _, _ = m.build_cta_vol_feature_outcome_panel(tmp_path, outcomes, m.rules(tmp_path))
    assert panel.iloc[0]["cta_selection_status"] == "selected_invalid"
    assert panel.iloc[0]["vol_selection_status"] == "unavailable_coverage"


def test_v119_intraday_gamma_rejects_observed_dealer_position(tmp_path: Path):
    pd.DataFrame([{
        "ticker": "QQQ",
        "feature_as_of_timestamp_utc": "2026-01-05T20:00:00Z",
        "effective_available_at_utc": "2026-01-05T20:00:00Z",
        "raw_chain_present": True,
        "raw_chain_quality": "high",
        "data_type": "reconstructed_from_raw_chain",
        "dealer_position_observed": True,
        "gamma_flip_state": "no_local_flip",
        "net_gex_proxy": -1.0,
    }]).to_csv(tmp_path / "dealer_gamma_proxy_history.csv", index=False)
    lev = pd.DataFrame([{"target_market": "QQQ", "decision_timestamp_utc": "2026-01-05T20:30:00Z"}])
    audit = m.build_dealer_gamma_intraday_selection_audit(tmp_path, lev, m.rules(tmp_path))
    assert audit.iloc[0]["selection_status"] == "selected_invalid"
    assert audit.iloc[0]["invalid_reason"] == "dealer_position_observed_true"


def test_v119_unverified_sign_policy_blocks_b4_b5_not_b1_b2():
    panel = _v119_base_market_panel("EOD", "QQQ")
    dealer = pd.DataFrame([{
        "target_market": "QQQ",
        "decision_timestamp_utc": "2026-01-05T21:00:00Z",
        "dealer_gamma_selection_status": "selected",
        "net_gex_proxy": -1.0,
        "negative_gamma_proxy_indicator": np.nan,
        "selected_source_row_identifier": "g1",
        "selected_source_content_hash": "gh",
        "selected_source_effective_available_at_utc": "2026-01-05T20:00:00Z",
    }])
    provenance = m.build_market_level_component_provenance_status(
        market_level_panel=panel,
        cta_vol_selector_parity=_matched_cta_vol_parity(("QQQ",)),
        leveraged_selector_parity=pd.DataFrame(),
        leveraged_primary_integrity=pd.DataFrame(),
        dealer_eod_panel=dealer,
        dealer_intraday_selection=pd.DataFrame(),
        dealer_gamma_source_parity=_matched_gamma_parity(),
    )
    integrity = m.build_market_level_model_scope_integrity(panel, provenance)
    assert set(integrity[integrity["model_scope"].isin(["B4", "B5"])]["scope_integrity_status"]) == {"unavailable_coverage"}
    assert set(integrity[integrity["model_scope"].isin(["B0", "B1", "B2", "B3"])]["scope_integrity_status"]) == {"valid"}


def test_v119_oos_counts_one_invalid_decision_once_for_multiple_invalid_components():
    panel = _v119_base_market_panel("EOD", "QQQ")
    panel["prior_return_1d"] = 0.0
    panel["prior_return_5d"] = 0.0
    panel["prior_realized_vol_20d"] = 0.1
    panel["distance_from_20d_moving_average"] = 0.0
    panel["weekday"] = 0
    panel["month_end_flag"] = 0
    panel["monthly_expiry_flag"] = 0
    panel["quarterly_expiry_flag"] = 0
    panel["triple_witching_flag"] = 0
    integrity = pd.DataFrame([
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-05T21:00:00Z", "model_clock": "EOD", "model_scope": "B3", "required_component": "CTA", "scope_integrity_status": "selected_invalid"},
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-05T21:00:00Z", "model_clock": "EOD", "model_scope": "B3", "required_component": "VolControl", "scope_integrity_status": "selected_invalid"},
    ])
    _, _, _, metrics, _, _, _ = m.run_market_level_oos_backtest(panel, integrity, {"walk_forward": {"minimum_train_observations": 252}}, {"daily": [], "intraday": []})
    row = metrics[(metrics["target_market"] == "QQQ") & (metrics["model_scope"] == "B3") & (metrics["outcome"] == "next_session_return")].iloc[0]
    assert row["selected_invalid_exclusion_count"] == 1


def _gamma_rows(rows):
    base = {
        "ticker": "QQQ",
        "feature_as_of_timestamp_utc": "2026-01-05T19:00:00Z",
        "effective_available_at_utc": "2026-01-05T19:00:00Z",
        "raw_chain_present": True,
        "raw_chain_quality": "high",
        "data_type": "reconstructed_from_raw_chain",
        "dealer_position_observed": False,
        "gamma_flip_state": "no_local_flip",
        "net_gex_proxy": -1.0,
    }
    return pd.DataFrame([base | row for row in rows])


@pytest.mark.parametrize("context", ["EOD_CLOSE", "INTRADAY_1530", "EXPIRY_0930"])
def test_v110_gamma_selector_newer_invalid_does_not_poison_earlier_clean(context):
    rows = _gamma_rows([
        {"effective_available_at_utc": "2026-01-05T18:00:00Z", "feature_as_of_timestamp_utc": "2026-01-05T18:00:00Z", "net_gex_proxy": 0.0},
        {"effective_available_at_utc": "2026-01-05T20:00:00Z", "feature_as_of_timestamp_utc": "2026-01-05T20:00:00Z", "dealer_position_observed": True, "net_gex_proxy": 99.0},
    ])
    selected = m.select_latest_clean_dealer_gamma(target_market="QQQ", decision_timestamp_utc="2026-01-05T20:30:00Z", source_rows=rows, selector_context=context, config=m.rules(Path(".")))
    assert selected["selection_status"] == "selected"
    assert selected["primary_eligible"] is True
    assert selected["row"]["net_gex_proxy"] == 0.0


@pytest.mark.parametrize("context", ["EOD_CLOSE", "INTRADAY_1530", "EXPIRY_0930"])
def test_v110_gamma_selector_older_invalid_allows_newer_clean(context):
    rows = _gamma_rows([
        {"effective_available_at_utc": "2026-01-05T18:00:00Z", "feature_as_of_timestamp_utc": "2026-01-05T18:00:00Z", "data_type": "dealer_inventory_observed"},
        {"effective_available_at_utc": "2026-01-05T20:00:00Z", "feature_as_of_timestamp_utc": "2026-01-05T20:00:00Z", "net_gex_proxy": -2.0},
    ])
    selected = m.select_latest_clean_dealer_gamma(target_market="QQQ", decision_timestamp_utc="2026-01-05T20:30:00Z", source_rows=rows, selector_context=context, config=m.rules(Path(".")))
    assert selected["selection_status"] == "selected"
    assert selected["row"]["net_gex_proxy"] == -2.0


@pytest.mark.parametrize(
    "row_override,expected_status,expected_reason",
    [
        ({"dealer_position_observed": True}, "selected_invalid", "dealer_position_observed_true"),
        ({"data_type": "dealer_position_file"}, "selected_invalid", "dealer_gamma_data_type_invalid"),
        ({"raw_chain_present": False}, "selected_invalid", "raw_chain_evidence_missing"),
        ({"raw_chain_quality": "low"}, "selected_invalid", "dealer_gamma_quality_invalid"),
        ({"effective_available_at_utc": "2026-01-06T20:00:00Z", "feature_as_of_timestamp_utc": "2026-01-06T20:00:00Z"}, "unavailable_coverage", "coverage_not_started"),
    ],
)
def test_v110_gamma_selector_invalid_and_future_states(row_override, expected_status, expected_reason):
    selected = m.select_latest_clean_dealer_gamma(
        target_market="QQQ",
        decision_timestamp_utc="2026-01-05T20:30:00Z",
        source_rows=_gamma_rows([row_override]),
        selector_context="EOD_CLOSE",
        config=m.rules(Path(".")),
    )
    assert selected["selection_status"] == expected_status
    assert expected_reason in selected["invalid_reason"]


def test_v110_gamma_selector_no_history_before_decision_is_unavailable():
    selected = m.select_latest_clean_dealer_gamma(
        target_market="SPY",
        decision_timestamp_utc="2026-01-05T20:30:00Z",
        source_rows=_gamma_rows([{}]),
        selector_context="EOD_CLOSE",
        config=m.rules(Path(".")),
    )
    assert selected["selection_status"] == "unavailable_coverage"
    assert selected["invalid_reason"] == "no_target_history"


def test_v110_gamma_selector_valid_zero_net_gex_is_selected():
    selected = m.select_latest_clean_dealer_gamma(
        target_market="QQQ",
        decision_timestamp_utc="2026-01-05T20:30:00Z",
        source_rows=_gamma_rows([{"net_gex_proxy": 0.0}]),
        selector_context="EOD_CLOSE",
        config=m.rules(Path(".")),
    )
    assert selected["selection_status"] == "selected"
    assert selected["row"]["net_gex_proxy"] == 0.0


def test_v110_missing_cta_parity_is_audit_missing_and_blocks_dependent_scopes():
    panel = _v119_base_market_panel("EOD", "QQQ")
    provenance = m.build_market_level_component_provenance_status(
        market_level_panel=panel,
        cta_vol_selector_parity=_matched_cta_vol_parity(("QQQ",)).query("required_source_family == 'VolControl'"),
        leveraged_selector_parity=pd.DataFrame(),
        leveraged_primary_integrity=pd.DataFrame(),
        dealer_eod_panel=pd.DataFrame(),
        dealer_intraday_selection=pd.DataFrame(),
    )
    cta = provenance[provenance["required_component"].eq("CTA")].iloc[0]
    assert cta["source_parity_status"] == "audit_missing"
    assert cta["integrity_reason"] == "required_parity_audit_missing"
    integrity = m.build_market_level_model_scope_integrity(panel, provenance)
    assert set(integrity[integrity["model_scope"].isin(["B1", "B3", "B4", "B5"])]["scope_integrity_status"]) == {"selected_invalid"}
    assert set(integrity[integrity["model_scope"].isin(["B0", "B2"])]["scope_integrity_status"]) == {"valid"}


def test_v110_missing_leveraged_parity_blocks_c1_c2_c3_not_c0():
    panel = _v119_base_market_panel("INTRADAY", "QQQ")
    provenance = m.build_market_level_component_provenance_status(
        market_level_panel=panel,
        cta_vol_selector_parity=pd.DataFrame(),
        leveraged_selector_parity=pd.DataFrame(),
        leveraged_primary_integrity=pd.DataFrame([{"target_market": "QQQ", "decision_timestamp_utc": "2026-01-05T20:30:00Z", "leveraged_etf_primary_input_gate": "eligible_primary"}]),
        dealer_eod_panel=pd.DataFrame(),
        dealer_intraday_selection=pd.DataFrame(),
    )
    lev = provenance[provenance["required_component"].eq("LeveragedETF")].iloc[0]
    assert lev["source_parity_status"] == "audit_missing"
    integrity = m.build_market_level_model_scope_integrity(panel, provenance)
    assert set(integrity[integrity["model_scope"].eq("C0")]["scope_integrity_status"]) == {"valid"}
    assert set(integrity[integrity["model_scope"].isin(["C1", "C2", "C3"])]["scope_integrity_status"]) == {"selected_invalid"}


def test_v110_dealer_gamma_parity_matched_and_mismatch(tmp_path: Path):
    rows = _gamma_rows([{"effective_available_at_utc": "2026-01-05T20:00:00Z", "feature_as_of_timestamp_utc": "2026-01-05T20:00:00Z"}])
    rows.to_csv(tmp_path / "dealer_gamma_proxy_history.csv", index=False)
    outcomes = pd.DataFrame([{"target_market": "QQQ", "decision_date": "2026-01-05", "decision_timestamp_utc": "2026-01-05T20:30:00Z"}])
    audit = m.build_dealer_gamma_eod_selection_audit(tmp_path, outcomes, m.rules(tmp_path))
    _, _, lineage, _ = m.build_dealer_gamma_panel_with_actual_lineage(tmp_path, outcomes, m.rules(tmp_path), audit)
    parity = m.build_dealer_gamma_source_selection_parity_audit(tmp_path, lineage, pd.DataFrame(), m.rules(tmp_path))
    assert parity.iloc[0]["selection_parity_status"] == "matched"
    changed = lineage.copy()
    changed.loc[0, "actual_feature_payload_hash"] = "wrong"
    mismatch = m.build_dealer_gamma_source_selection_parity_audit(tmp_path, changed, pd.DataFrame(), m.rules(tmp_path))
    assert mismatch.iloc[0]["selection_parity_status"] == "mismatch"


def test_v110_missing_dealer_gamma_parity_blocks_gamma_and_sign_scopes():
    panel = _v119_base_market_panel("EOD", "QQQ")
    dealer = pd.DataFrame([{
        "target_market": "QQQ",
        "decision_timestamp_utc": "2026-01-05T21:00:00Z",
        "selection_status": "selected",
        "availability_state": "valid",
        "primary_eligible": True,
        "dealer_gamma_selection_status": "selected",
        "dealer_gamma_availability_state": "valid",
        "negative_gamma_proxy_indicator": 1,
        "selected_source_row_identifier": "g1",
        "selected_source_content_hash": "gh",
        "selected_source_effective_available_at_utc": "2026-01-05T20:00:00Z",
    }])
    provenance = m.build_market_level_component_provenance_status(
        market_level_panel=panel,
        cta_vol_selector_parity=_matched_cta_vol_parity(("QQQ",)),
        leveraged_selector_parity=pd.DataFrame(),
        leveraged_primary_integrity=pd.DataFrame(),
        dealer_eod_panel=dealer,
        dealer_intraday_selection=pd.DataFrame(),
    )
    gamma = provenance[provenance["required_component"].eq("DealerGammaEOD")].iloc[0]
    sign = provenance[provenance["required_component"].eq("DealerGammaSignEOD")].iloc[0]
    assert gamma["source_parity_status"] == "audit_missing"
    assert sign["integrity_status"] == "selected_invalid"


def test_v110_oos_reconciliation_separates_all_exclusion_buckets():
    panel = pd.DataFrame([
        _v119_base_market_panel("EOD", "QQQ").iloc[0].to_dict() | {"decision_timestamp_utc": "2026-01-05T21:00:00Z", "next_session_return": 0.1, "prior_return_1d": 0.0},
        _v119_base_market_panel("EOD", "QQQ").iloc[0].to_dict() | {"decision_timestamp_utc": "2026-01-06T21:00:00Z", "next_session_return": np.nan, "prior_return_1d": 0.0},
        _v119_base_market_panel("EOD", "QQQ").iloc[0].to_dict() | {"decision_timestamp_utc": "2026-01-07T21:00:00Z", "next_session_return": 0.1, "prior_return_1d": np.nan},
        _v119_base_market_panel("EOD", "QQQ").iloc[0].to_dict() | {"decision_timestamp_utc": "2026-01-08T21:00:00Z", "next_session_return": 0.1, "prior_return_1d": 0.0},
    ])
    for col, value in {
        "prior_return_5d": 0.0,
        "prior_realized_vol_20d": 0.1,
        "distance_from_20d_moving_average": 0.0,
        "weekday": 0,
        "month_end_flag": 0,
        "monthly_expiry_flag": 0,
        "quarterly_expiry_flag": 0,
        "triple_witching_flag": 0,
    }.items():
        panel[col] = panel.get(col, value)
    integrity = pd.DataFrame([
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-05T21:00:00Z", "model_clock": "EOD", "model_scope": "B0", "required_component": "baseline", "scope_integrity_status": "selected_invalid"},
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-06T21:00:00Z", "model_clock": "EOD", "model_scope": "B0", "required_component": "baseline", "scope_integrity_status": "unavailable_coverage"},
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-07T21:00:00Z", "model_clock": "EOD", "model_scope": "B0", "required_component": "baseline", "scope_integrity_status": "valid"},
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-08T21:00:00Z", "model_clock": "EOD", "model_scope": "B0", "required_component": "baseline", "scope_integrity_status": "valid"},
    ])
    _, _, _, metrics, _, _, _ = m.run_market_level_oos_backtest(panel, integrity, {"walk_forward": {"minimum_train_observations": 252}}, {"daily": ["prior_return_1d"], "intraday": []})
    row = metrics[(metrics["target_market"] == "QQQ") & (metrics["model_scope"] == "B0") & (metrics["outcome"] == "next_session_return")].iloc[0]
    assert row["selected_invalid_exclusion_count"] == 1
    assert row["scope_unavailable_coverage_exclusion_count"] == 1
    assert row["feature_numeric_unavailable_exclusion_count"] == 1
    assert row["valid_included_decision_count"] == 1
    assert row["reconciliation_gap"] == 0
    assert row["reconciliation_status"] == "matched"


def test_v111_eod_gamma_selection_audit_keeps_all_daily_decisions(tmp_path: Path):
    rows = _gamma_rows([{"target_market": "QQQ", "ticker": "QQQ"}])
    rows.to_csv(tmp_path / "dealer_gamma_proxy_history.csv", index=False)
    outcomes = pd.DataFrame([
        {"target_market": "QQQ", "decision_date": "2026-01-05", "decision_timestamp_utc": "2026-01-05T20:30:00Z"},
        {"target_market": "SPY", "decision_date": "2026-01-05", "decision_timestamp_utc": "2026-01-05T20:30:00Z"},
    ])
    audit = m.build_dealer_gamma_eod_selection_audit(tmp_path, outcomes, m.rules(tmp_path))
    assert len(audit) == 2
    assert set(audit["target_market"]) == {"QQQ", "SPY"}
    assert audit[audit["target_market"].eq("SPY")].iloc[0]["selection_status"] == "unavailable_coverage"


def test_v111_gamma_payload_contract_rejects_missing_net_gex_and_local_flip_distance():
    missing_net = _gamma_rows([{}]).drop(columns=["net_gex_proxy"])
    selected = m.select_latest_clean_dealer_gamma(target_market="QQQ", decision_timestamp_utc="2026-01-05T20:30:00Z", source_rows=missing_net, selector_context="EOD_CLOSE", config=m.rules(Path(".")))
    assert selected["selection_status"] == "selected_invalid"
    assert "net_gex_proxy" in selected["invalid_reason"]
    local_missing_distance = _gamma_rows([{"gamma_flip_state": "local_flip_found"}])
    selected = m.select_latest_clean_dealer_gamma(target_market="QQQ", decision_timestamp_utc="2026-01-05T20:30:00Z", source_rows=local_missing_distance, selector_context="EOD_CLOSE", config=m.rules(Path(".")))
    assert selected["selection_status"] == "selected_invalid"
    assert selected["invalid_reason"] == "gamma_flip_distance_required_for_local_flip"


def test_v111_gamma_sign_uses_derived_not_applicable_not_matched():
    panel = _v119_base_market_panel("EOD", "QQQ")
    dealer = pd.DataFrame([{
        "target_market": "QQQ",
        "decision_timestamp_utc": "2026-01-05T21:00:00Z",
        "selection_status": "selected",
        "availability_state": "valid",
        "primary_eligible": True,
        "negative_gamma_proxy_indicator": 1,
        "selected_source_row_identifier": "g1",
        "selected_source_content_hash": "gh",
        "selected_source_effective_available_at_utc": "2026-01-05T20:00:00Z",
    }])
    provenance = m.build_market_level_component_provenance_status(
        market_level_panel=panel,
        cta_vol_selector_parity=_matched_cta_vol_parity(("QQQ",)),
        leveraged_selector_parity=pd.DataFrame(),
        leveraged_primary_integrity=pd.DataFrame(),
        dealer_eod_panel=dealer,
        dealer_intraday_selection=pd.DataFrame(),
        dealer_gamma_source_parity=_matched_gamma_parity(),
    )
    sign = provenance[provenance["required_component"].eq("DealerGammaSignEOD")].iloc[0]
    assert sign["source_parity_status"] == "not_applicable"
    assert sign["provenance_evidence_type"] == "derived_from_base_component"
    assert sign["provenance_dependency_component"] == "DealerGammaEOD"


def test_v111_intraday_universe_keeps_missing_outcome_day_beyond_eligible_panel(tmp_path: Path):
    write_nyse_calendar(tmp_path, [
        {"session_date": "2026-01-05", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
        {"session_date": "2026-01-06", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
    ])
    bars_dir = tmp_path / "market_bomb_history" / "intraday_bars"
    bars_dir.mkdir(parents=True)
    pd.DataFrame([
        {"timestamp_utc": "2026-01-05T20:30:00Z", "close": 100, "high": 100, "low": 100},
        {"timestamp_utc": "2026-01-05T21:00:00Z", "close": 101, "high": 101, "low": 100},
        {"timestamp_utc": "2026-01-06T20:30:00Z", "close": 100, "high": 100, "low": 100},
    ]).to_csv(bars_dir / "QQQ_5m.csv", index=False)
    cfg = m.rules(tmp_path)
    cfg["targets"] = ["QQQ"]
    universe = m.build_market_level_intraday_decision_universe(tmp_path, cfg)
    assert len(universe) == 2
    assert "outcome_unavailable" in set(universe["intraday_outcome_availability_status"])


def test_v112_eod_actual_feature_lineage_drives_parity(tmp_path: Path):
    rows = _gamma_rows([{"source_row_identifier": "gamma-row-1", "net_gex_proxy": -2.0}])
    rows.to_csv(tmp_path / "dealer_gamma_proxy_history.csv", index=False)
    daily = pd.DataFrame([{
        "target_market": "QQQ",
        "decision_date": "2026-01-05",
        "decision_timestamp_utc": "2026-01-05T20:30:00Z",
    }])
    selection = m.build_dealer_gamma_eod_selection_audit(tmp_path, daily, m.rules(tmp_path))
    _, _, lineage, hydration = m.build_dealer_gamma_panel_with_actual_lineage(tmp_path, daily, m.rules(tmp_path), selection)
    assert lineage.iloc[0]["actual_feature_row_present"] is True or lineage.iloc[0]["actual_feature_row_present"] == True
    assert lineage.iloc[0]["actual_selected_source_row_identifier"] == "gamma-row-1"
    assert hydration.iloc[0]["hydration_status"] == "hydrated"
    parity = m.build_dealer_gamma_source_selection_parity_audit(tmp_path, lineage, pd.DataFrame(), m.rules(tmp_path))
    assert parity.iloc[0]["selection_parity_status"] == "matched"

    missing = lineage.copy()
    missing["actual_feature_row_present"] = False
    missing["actual_feature_hydration_failure_reason"] = "unit_test_missing_lineage"
    parity_missing = m.build_dealer_gamma_source_selection_parity_audit(tmp_path, missing, pd.DataFrame(), m.rules(tmp_path))
    assert parity_missing.iloc[0]["selection_parity_status"] == "audit_missing"


def test_v112_intraday_universe_does_not_synthesize_business_days_without_calendar(tmp_path: Path):
    bars_dir = tmp_path / "market_bomb_history" / "intraday_bars"
    bars_dir.mkdir(parents=True)
    pd.DataFrame([
        {"timestamp_utc": "2026-01-05T20:30:00Z", "close": 100, "high": 100, "low": 100},
        {"timestamp_utc": "2026-01-05T21:00:00Z", "close": 101, "high": 101, "low": 100},
    ]).to_csv(bars_dir / "QQQ_5m.csv", index=False)
    cfg = m.rules(tmp_path)
    cfg["targets"] = ["QQQ"]
    universe, gate = m.build_market_level_intraday_universe_with_gate(tmp_path, cfg)
    assert universe.empty
    assert gate.iloc[0]["universe_generation_status"] == "selected_invalid"
    assert "nyse_calendar" in gate.iloc[0]["universe_generation_reason"]


def test_v112_leveraged_input_audit_iterates_full_intraday_universe(tmp_path: Path):
    write_nyse_calendar(tmp_path, [
        {"session_date": "2026-01-15", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
        {"session_date": "2026-01-16", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
    ])
    write_expiry_intraday_rules(tmp_path, verified=True)
    hist = tmp_path / "market_bomb_history"
    hist.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"ticker": t, "effective_available_at_utc": "2026-01-14T21:00:00Z", "as_of_timestamp_utc": "2026-01-14T21:00:00Z", "net_assets_usd": 100.0, "aum_value_type": "net_assets_usd"}
        for t in ["TQQQ", "SQQQ"]
    ]).to_csv(hist / "leveraged_etf_aum_history.csv", index=False)
    bars_dir = hist / "intraday_bars"
    bars_dir.mkdir(exist_ok=True)
    pd.DataFrame([
        {"timestamp_utc": "2026-01-16T20:30:00Z", "open": 100, "high": 100, "low": 100, "close": 100, "volume": 100, "prior_regular_session_close": 100},
        {"timestamp_utc": "2026-01-16T21:00:00Z", "open": 102, "high": 102, "low": 102, "close": 102, "volume": 100, "prior_regular_session_close": 100},
    ]).to_csv(bars_dir / "QQQ_5m.csv", index=False)
    universe = pd.DataFrame([
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-15T20:30:00Z"},
        {"target_market": "QQQ", "decision_timestamp_utc": "2026-01-16T20:30:00Z"},
    ])
    candidate, _, _, _ = m.build_leveraged_etf_input_candidate_audits(tmp_path, m.rules(tmp_path), universe)
    day15 = candidate[candidate["decision_timestamp_utc"].astype(str).eq("2026-01-15T20:30:00+00:00")]
    assert not day15.empty
    assert "decision_bar_1530" in set(day15["input_component"])
    assert day15[day15["input_component"].eq("decision_bar_1530")].iloc[0]["primary_eligible"] is False or day15[day15["input_component"].eq("decision_bar_1530")].iloc[0]["primary_eligible"] == False


def test_v113_leveraged_input_audit_requires_explicit_intraday_universe(tmp_path: Path):
    with pytest.raises(ValueError, match="intraday_decision_universe is required"):
        m.build_leveraged_etf_input_candidate_audits(tmp_path, m.rules(tmp_path))


def test_v113_leveraged_parity_does_not_self_match_without_panel_manifest(tmp_path: Path):
    write_nyse_calendar(tmp_path, [
        {"session_date": "2026-01-15", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
        {"session_date": "2026-01-16", "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False},
    ])
    write_expiry_intraday_rules(tmp_path, verified=True)
    hist = tmp_path / "market_bomb_history"
    hist.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"ticker": t, "effective_available_at_utc": "2026-01-15T21:00:00Z", "as_of_timestamp_utc": "2026-01-15T21:00:00Z", "net_assets_usd": 100.0, "aum_value_type": "net_assets_usd"}
        for t in ["TQQQ", "SQQQ", "QLD", "QID"]
    ]).to_csv(hist / "leveraged_etf_aum_history.csv", index=False)
    bars_dir = hist / "intraday_bars"
    bars_dir.mkdir(exist_ok=True)
    pd.DataFrame([
        {"timestamp_utc": "2026-01-16T14:30:00Z", "open": 100, "high": 100, "low": 100, "close": 100, "volume": 100, "prior_regular_session_close": 100},
        {"timestamp_utc": "2026-01-16T20:30:00Z", "open": 101, "high": 101, "low": 101, "close": 101, "volume": 100, "prior_regular_session_close": 100},
        {"timestamp_utc": "2026-01-16T21:00:00Z", "open": 102, "high": 102, "low": 102, "close": 102, "volume": 100, "prior_regular_session_close": 100},
    ]).to_csv(bars_dir / "QQQ_5m.csv", index=False)
    universe = pd.DataFrame([{"target_market": "QQQ", "decision_timestamp_utc": "2026-01-16T20:30:00Z"}])
    _, _, _, parity = m.build_leveraged_etf_input_candidate_audits(tmp_path, m.rules(tmp_path), universe)
    assert "matched" not in set(parity["selection_parity_status"])
    assert "audit_missing" in set(parity["selection_parity_status"])


def test_v113_target_clock_gate_blocks_oos_metrics_even_with_valid_bucket():
    panel = _v119_base_market_panel("EOD", "QQQ")
    panel["prior_return_1d"] = 0.0
    integrity = pd.DataFrame([{
        "target_market": "QQQ",
        "decision_timestamp_utc": "2026-01-05T21:00:00Z",
        "model_clock": "EOD",
        "model_scope": "B0",
        "required_component": "baseline",
        "scope_integrity_status": "valid",
    }])
    bucket = pd.DataFrame([{
        "target_market": "QQQ",
        "decision_timestamp_utc": "2026-01-05T21:00:00Z",
        "model_clock": "EOD",
        "model_scope": "B0",
        "outcome": "next_session_return",
        "bucket": "valid_included",
    }])
    gate = pd.DataFrame([{
        "target_market": "QQQ",
        "model_clock": "EOD",
        "model_scope": "B0",
        "outcome": "next_session_return",
        "target_clock_gate_status": "selected_invalid",
        "target_clock_gate_reason": "unit_test_invalid_calendar",
        "candidate_decision_count": 1,
        "universe_gate_selected_invalid_count": 1,
        "universe_gate_unavailable_coverage_count": 0,
    }])
    _, _, _, metrics, _, _, _ = m.run_market_level_oos_backtest(
        panel,
        integrity,
        {"walk_forward": {"minimum_train_observations": 252}},
        {"daily": ["prior_return_1d"], "intraday": []},
        bucket,
        gate,
    )
    row = metrics[(metrics["target_market"] == "QQQ") & (metrics["model_scope"] == "B0") & (metrics["outcome"] == "next_session_return")].iloc[0]
    assert row["result_status"] == "data_quality_blocked"
    assert row["universe_gate_selected_invalid_count"] == 1
    assert row["target_clock_gate_reason"] == "unit_test_invalid_calendar"


def test_v113_run_nonempty_actual_lineage_parity_and_bucket_fixture(tmp_path: Path):
    sessions = [
        {"session_date": d.date().isoformat(), "is_regular_session": True, "regular_open_et": "09:30", "regular_close_et": "16:00", "is_early_close": False}
        for d in pd.bdate_range("2026-01-01", "2026-03-31")
    ]
    write_nyse_calendar(tmp_path, sessions)
    write_expiry_intraday_rules(tmp_path, verified=True)
    cfg_dir = tmp_path / "market_bomb_config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "dealer_gamma_observed_rules_v1.json").write_text(
        '{"sign_convention":"positive_net_gex_proxy_means_long_gamma_proxy_not_dealer_inventory"}',
        encoding="utf-8",
    )
    for t in ["QQQ", "SPY", "SOXX", "SMH"]:
        write_price(tmp_path, t, np.linspace(100, 150, 80))
    hist = tmp_path / "market_bomb_history"
    hist.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"source_row_identifier": "gamma-row-1", "ticker": "QQQ", "effective_available_at_utc": "2026-01-29T20:00:00Z", "feature_as_of_timestamp_utc": "2026-01-29T20:00:00Z", "raw_chain_present": True, "raw_chain_quality": "high", "data_type": "reconstructed_from_raw_chain", "dealer_position_observed": False, "gamma_flip_state": "no_local_flip", "net_gex_proxy": 0.0},
    ]).to_csv(tmp_path / "dealer_gamma_proxy_history.csv", index=False)
    pd.DataFrame([
        {"ticker": t, "effective_available_at_utc": "2026-01-28T21:00:00Z", "as_of_timestamp_utc": "2026-01-28T21:00:00Z", "net_assets_usd": 100.0, "aum_value_type": "net_assets_usd"}
        for t in ["TQQQ", "SQQQ"]
    ]).to_csv(hist / "leveraged_etf_aum_history.csv", index=False)
    bars_dir = hist / "intraday_bars"
    bars_dir.mkdir(exist_ok=True)
    pd.DataFrame([
        {"timestamp_utc": "2026-01-29T14:30:00Z", "open": 100, "high": 100, "low": 100, "close": 100, "volume": 100, "prior_regular_session_close": 100},
        {"timestamp_utc": "2026-01-29T20:30:00Z", "open": 101, "high": 101, "low": 101, "close": 101, "volume": 100, "prior_regular_session_close": 100},
        {"timestamp_utc": "2026-01-29T21:00:00Z", "open": 102, "high": 102, "low": 102, "close": 102, "volume": 100, "prior_regular_session_close": 100},
    ]).to_csv(bars_dir / "QQQ_5m.csv", index=False)

    m.run(tmp_path, run_cta_vol_analysis=False)
    out = tmp_path / "market_bomb_market_impact"
    lineage = pd.read_csv(out / "dealer_gamma_eod_actual_feature_lineage_v1.csv")
    parity = pd.read_csv(out / "dealer_gamma_source_selection_parity_audit_v1.csv")
    buckets = pd.read_csv(out / "market_level_decision_bucket_audit_v1.csv")
    metrics = pd.read_csv(out / "market_level_oos_metrics_v1.csv")
    manifest = pd.read_json(out / "analysis_manifest.json", typ="series")
    assert not lineage.empty
    assert "matched" in set(lineage["lineage_status"])
    assert "matched" in set(parity["selection_parity_status"])
    assert not buckets.empty
    assert not metrics.empty
    assert metrics["reconciliation_gap"].fillna(0).eq(0).all()
    assert manifest["actionization_allowed"] is False
    assert manifest["market_level_oos"]["calendar_fallback_allowed"] is False
    assert manifest["market_level_oos"]["leveraged_self_match_allowed"] is False


def test_v112_expiry_gamma_selection_uses_canonical_context():
    raw = _gamma_rows([{"source_row_identifier": "expiry-gamma-1", "net_gex_proxy": -3.0}])
    selected, audit = m.select_strict_gamma_snapshot_for_event(raw, "QQQ", pd.Timestamp("2026-01-05T20:30:00Z", tz="UTC"), m.rules(Path(".")))
    assert selected is not None
    assert audit["selector_context"] == "EXPIRY_0930"
    assert audit["selection_status"] == "selected"
    assert audit["selected_source_row_identifier"] == "expiry-gamma-1"


def test_v111_decision_bucket_audit_assigns_exactly_one_bucket():
    panel = _v119_base_market_panel("EOD", "QQQ")
    panel["prior_return_1d"] = np.nan
    integrity = pd.DataFrame([{"target_market": "QQQ", "decision_timestamp_utc": "2026-01-05T21:00:00Z", "model_clock": "EOD", "model_scope": "B0", "required_component": "baseline", "scope_integrity_status": "valid"}])
    buckets = m.build_market_level_decision_bucket_audit(panel, integrity, {"daily": ["prior_return_1d"], "intraday": []})
    row = buckets[(buckets["target_market"].eq("QQQ")) & (buckets["model_scope"].eq("B0")) & (buckets["outcome"].eq("next_session_return"))].iloc[0]
    assert row["bucket"] == "feature_numeric_unavailable"
    assert buckets.groupby(["target_market", "decision_timestamp_utc", "model_clock", "model_scope", "outcome"]).size().max() == 1
