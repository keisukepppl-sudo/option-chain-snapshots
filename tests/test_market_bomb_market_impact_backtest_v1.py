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
    write_nyse_calendar(tmp_path)
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
    write_nyse_calendar(tmp_path)
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
    candidate, _, universe, _ = m.build_leveraged_etf_input_candidate_audits(tmp_path, m.rules(tmp_path))
    assert {"aum", "decision_bar_1530", "close_bar_1600"}.issubset(set(candidate["input_component"]))
    assert "2026-01-16T20:25:00Z" not in set(candidate.get("actual_bar_timestamp_utc", pd.Series(dtype=str)).astype(str))
    assert not universe.empty


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
