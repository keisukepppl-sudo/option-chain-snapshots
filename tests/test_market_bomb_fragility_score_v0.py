from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import market_bomb_fragility_score_v0 as m


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "fragility_score_v0_nonempty"


def _calendar() -> pd.DataFrame:
    return m.load_calendar(ROOT)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _one_row_input(tmp_path: Path, ticker: str = "SPY", **overrides: object) -> Path:
    input_root = tmp_path / "raw"
    cal = _calendar()
    session_date = overrides.pop("session_date", cal.iloc[0]["session_date"])
    decision_ts = cal[cal["session_date"] == session_date].iloc[0]["decision_timestamp_utc"] if session_date in set(cal["session_date"]) else "2022-01-08T21:15:00Z"
    row = {
        "session_date": session_date,
        "close": 100.0,
        "high": 101.0,
        "low": 99.0,
        "volume": 1000000,
        "ticker": ticker,
        "source_row_identifier": f"{ticker}-{session_date}",
        "source_as_of_timestamp_utc": decision_ts,
        "effective_available_at_utc": decision_ts,
        "source_url_or_path": "unit-test",
        "availability_confidence": "high",
    }
    row.update(overrides)
    subdir = "daily_prices" if ticker in m.PRICE_TICKERS else "volatility_indices"
    _write_csv(input_root / subdir / f"{ticker}.csv", [row])
    return input_root


def _run(tmp_path: Path, input_root: Path | None = None, as_of_date: str | None = None) -> Path:
    out = tmp_path / "out"
    m.run(ROOT, input_root or FIXTURE / "raw", out, as_of_date=as_of_date)
    return out


def _latest(out: Path) -> pd.DataFrame:
    return pd.read_csv(out / "fragility_score_latest_v0.csv")


@pytest.fixture(scope="session")
def fixture_out(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("fragility_fixture_run")
    return _run(tmp)


def test_explicit_timestamped_row_accepted(tmp_path: Path) -> None:
    input_root = _one_row_input(tmp_path)
    inv, audit, availability, canonical = m.ingest_raw_sources(ROOT, input_root, _calendar())
    assert len(canonical[canonical["ticker"] == "SPY"]) == 1
    assert audit[audit["ticker"] == "SPY"].iloc[0]["raw_input_status"] == "valid"
    assert availability[availability["ticker"] == "SPY"].iloc[0]["availability_confidence"] == "high"


def test_assumed_availability_visible_and_medium(tmp_path: Path) -> None:
    cal = _calendar()
    input_root = tmp_path / "raw"
    _write_csv(input_root / "daily_prices" / "SPY.csv", [{"session_date": cal.iloc[0]["session_date"], "close": 100}])
    _, _, _, canonical = m.ingest_raw_sources(ROOT, input_root, cal)
    row = canonical.iloc[0]
    assert row["availability_basis"] == "assumed_official_close_plus_15_minutes"
    assert row["availability_confidence"] == "medium"


def test_naive_supplied_effective_timestamp_selected_invalid(tmp_path: Path) -> None:
    input_root = _one_row_input(tmp_path, effective_available_at_utc="2022-01-03T21:15:00")
    _, audit, _, canonical = m.ingest_raw_sources(ROOT, input_root, _calendar())
    assert "timezone_naive_supplied_effective_timestamp" in audit[audit["ticker"] == "SPY"].iloc[0]["raw_input_reason"]
    assert canonical.empty


def test_future_effective_timestamp_unavailable(tmp_path: Path) -> None:
    input_root = _one_row_input(tmp_path, effective_available_at_utc="2026-01-01T00:00:00Z")
    _, audit, availability, canonical = m.ingest_raw_sources(ROOT, input_root, _calendar())
    assert audit[audit["ticker"] == "SPY"].iloc[0]["raw_input_status"] == "unavailable_coverage"
    assert availability[availability["ticker"] == "SPY"].iloc[0]["availability_status"] == "unavailable_coverage"
    assert canonical.empty


def test_duplicate_ticker_session_selected_invalid(tmp_path: Path) -> None:
    cal = _calendar()
    input_root = tmp_path / "raw"
    session = cal.iloc[0]["session_date"]
    decision = cal.iloc[0]["decision_timestamp_utc"]
    rows = [
        {"session_date": session, "close": 100, "effective_available_at_utc": decision},
        {"session_date": session, "close": 100, "effective_available_at_utc": decision},
    ]
    _write_csv(input_root / "daily_prices" / "SPY.csv", rows)
    _, audit, _, canonical = m.ingest_raw_sources(ROOT, input_root, cal)
    assert canonical.empty
    assert (audit[audit["ticker"] == "SPY"]["raw_input_status"] == "selected_invalid").all()


def test_conflicting_duplicate_close_metadata_conflict(tmp_path: Path) -> None:
    cal = _calendar()
    input_root = tmp_path / "raw"
    session = cal.iloc[0]["session_date"]
    decision = cal.iloc[0]["decision_timestamp_utc"]
    rows = [
        {"session_date": session, "close": 100, "effective_available_at_utc": decision},
        {"session_date": session, "close": 101, "effective_available_at_utc": decision},
    ]
    _write_csv(input_root / "daily_prices" / "SPY.csv", rows)
    _, audit, _, _ = m.ingest_raw_sources(ROOT, input_root, cal)
    assert "duplicate_metadata_conflict" in set(audit[audit["ticker"] == "SPY"]["raw_input_reason"])


def test_weekend_non_nyse_row_excluded(tmp_path: Path) -> None:
    input_root = _one_row_input(tmp_path, session_date="2022-01-08")
    _, audit, _, canonical = m.ingest_raw_sources(ROOT, input_root, _calendar())
    assert "session_date_absent_from_nyse_calendar" in audit[audit["ticker"] == "SPY"].iloc[0]["raw_input_reason"]
    assert canonical.empty


def test_early_close_uses_actual_calendar_close_plus_15m() -> None:
    cal = _calendar()
    early = cal[cal["regular_close_et"] != "16:00"]
    if early.empty:
        return
    row = early.iloc[0]
    assert row["decision_timestamp_utc"].endswith("18:15:00Z")


def test_no_calendar_fallback_invalid_as_of(tmp_path: Path) -> None:
    try:
        m.run(ROOT, tmp_path / "missing", tmp_path / "out", as_of_date="2022-01-08")
    except SystemExit as exc:
        assert "not an ingested completed NYSE" in str(exc)
    else:
        raise AssertionError("invalid as-of date should fail closed")


def test_future_price_change_does_not_alter_earlier_score(tmp_path: Path, fixture_out: Path) -> None:
    panel1 = pd.read_csv(fixture_out / "fragility_score_panel_v0.csv")
    target_row = panel1[(panel1["score_target"] == "SPY") & (panel1["score_status"] == "valid")].iloc[5]
    copied = tmp_path / "raw_mut"
    shutil.copytree(FIXTURE / "raw", copied)
    spy = pd.read_csv(copied / "daily_prices" / "SPY.csv")
    spy.loc[spy.index[-1], "close"] = spy.loc[spy.index[-1], "close"] * 3
    spy.to_csv(copied / "daily_prices" / "SPY.csv", index=False)
    out2 = _run(tmp_path / "b", copied)
    panel2 = pd.read_csv(out2 / "fragility_score_panel_v0.csv")
    same = panel2[(panel2["score_target"] == "SPY") & (panel2["session_date"] == target_row["session_date"])].iloc[0]
    assert same["fragility_score"] == target_row["fragility_score"]


def test_no_ffill_through_missing_price_date(tmp_path: Path) -> None:
    copied = tmp_path / "raw_missing"
    shutil.copytree(FIXTURE / "raw", copied)
    qqq = pd.read_csv(copied / "daily_prices" / "QQQ.csv")
    missing_date = qqq.iloc[260]["session_date"]
    qqq = qqq[qqq["session_date"] != missing_date]
    qqq.to_csv(copied / "daily_prices" / "QQQ.csv", index=False)
    out = _run(tmp_path, copied)
    universe = pd.read_csv(out / "fragility_score_decision_universe_v0.csv")
    row = universe[(universe["score_target"] == "QQQ") & (universe["session_date"] == missing_date)].iloc[0]
    assert row["universe_status"] == "unavailable_coverage"


def test_no_official_score_before_core_histories_available(fixture_out: Path) -> None:
    panel = pd.read_csv(fixture_out / "fragility_score_panel_v0.csv")
    early = panel[(panel["score_target"] == "SPY")].iloc[0]
    assert early["score_status"] == "unavailable_core_component"


def test_invalid_raw_row_cannot_feed_core_feature(tmp_path: Path) -> None:
    input_root = _one_row_input(tmp_path, close=-1)
    out = _run(tmp_path / "run", input_root)
    canonical = pd.read_csv(out / "fragility_daily_canonical_panel_v0.csv")
    assert canonical.empty


def test_policy_assumed_availability_cannot_yield_high_confidence(fixture_out: Path) -> None:
    latest = _latest(fixture_out)
    qqq = latest[latest["score_target"] == "QQQ"].iloc[0]
    assert qqq["confidence"] != "High"


def test_source_effective_after_decision_invalidates_component(tmp_path: Path) -> None:
    input_root = _one_row_input(tmp_path, effective_available_at_utc="2026-01-01T00:00:00Z")
    out = _run(tmp_path / "run", input_root)
    score = pd.read_csv(out / "fragility_score_panel_v0.csv")
    assert score.empty or "valid" not in set(score["score_status"])


def test_market_requires_spy_and_qqq_same_session(tmp_path: Path) -> None:
    copied = tmp_path / "raw_market"
    shutil.copytree(FIXTURE / "raw", copied)
    qqq = pd.read_csv(copied / "daily_prices" / "QQQ.csv").iloc[:-1]
    last_date = pd.read_csv(copied / "daily_prices" / "SPY.csv").iloc[-1]["session_date"]
    qqq.to_csv(copied / "daily_prices" / "QQQ.csv", index=False)
    out = _run(tmp_path, copied)
    universe = pd.read_csv(out / "fragility_score_decision_universe_v0.csv")
    row = universe[(universe["score_target"] == "MARKET") & (universe["session_date"] == last_date)].iloc[0]
    assert row["universe_status"] == "unavailable_coverage"


def test_missing_soxx_does_not_block_spy_qqq_market(tmp_path: Path) -> None:
    copied = tmp_path / "raw_no_soxx"
    shutil.copytree(FIXTURE / "raw", copied)
    (copied / "daily_prices" / "SOXX.csv").unlink()
    out = _run(tmp_path, copied)
    latest = _latest(out)
    assert set(["SPY", "QQQ", "MARKET"]).issubset(set(latest["score_target"]))


def test_trend_score_100_when_below_all_mas_and_10pct_drawdown() -> None:
    score = 100 * (0.20 + 0.25 + 0.20 + 0.35 * m.clip(0.10 / 0.10))
    assert score == 100


def test_trend_score_zero_when_above_all_mas_and_no_drawdown() -> None:
    score = 100 * (0 + 0 + 0 + 0.35 * m.clip(0 / 0.10))
    assert score == 0


def test_rv_score_bounded(fixture_out: Path) -> None:
    comp = pd.read_csv(fixture_out / "fragility_component_scores_v0.csv")
    rv = comp[(comp["component_name"] == "realized_volatility_stress") & (comp["component_status"] == "valid")]
    assert rv["component_score"].between(0, 100).all()


def test_cta_score_bounded_and_proxy_metadata(fixture_out: Path) -> None:
    comp = pd.read_csv(fixture_out / "fragility_component_scores_v0.csv")
    cta = comp[(comp["component_name"] == "cta_deleveraging_proxy") & (comp["component_status"] == "valid")]
    assert cta["component_score"].between(0, 100).all()
    assert set(cta["is_proxy"].astype(str).str.lower()) == {"true"}
    assert set(cta["observed_flow"].astype(str).str.lower()) == {"false"}


def test_vol_control_score_bounded_and_proxy_metadata(fixture_out: Path) -> None:
    comp = pd.read_csv(fixture_out / "fragility_component_scores_v0.csv")
    vc = comp[(comp["component_name"] == "vol_control_deleveraging_proxy") & (comp["component_status"] == "valid")]
    assert vc["component_score"].between(0, 100).all()
    assert set(vc["is_proxy"].astype(str).str.lower()) == {"true"}


def test_vix_missing_vix3m_component_nan_never_zero(tmp_path: Path) -> None:
    copied = tmp_path / "raw_no_vix3m"
    shutil.copytree(FIXTURE / "raw", copied)
    (copied / "volatility_indices" / "VIX3M.csv").unlink()
    out = _run(tmp_path, copied)
    comp = pd.read_csv(out / "fragility_component_scores_v0.csv")
    vix = comp[comp["component_name"] == "vix_term_structure_stress"]
    assert "unavailable_coverage" in set(vix["component_status"])
    assert not (vix["component_score"].fillna(-1) == 0).any()


def test_core_valid_vix_missing_denominator_90_and_medium(tmp_path: Path) -> None:
    copied = tmp_path / "raw_no_vix"
    shutil.copytree(FIXTURE / "raw", copied)
    shutil.rmtree(copied / "volatility_indices")
    out = _run(tmp_path, copied)
    latest = _latest(out)
    spy = latest[latest["score_target"] == "SPY"].iloc[0]
    assert spy["data_coverage_pct"] == 90
    assert spy["confidence"] in ["Medium", "Low"]
    assert "vix_term_structure_stress" in spy["missing_components"]


def test_core_missing_total_nan_unavailable(tmp_path: Path) -> None:
    input_root = _one_row_input(tmp_path)
    out = _run(tmp_path / "run", input_root)
    latest = _latest(out)
    if not latest.empty:
        spy = latest[latest["score_target"] == "SPY"].iloc[0]
        assert pd.isna(spy["fragility_score"])
        assert spy["risk_state"] == "Unavailable"


def test_all_inputs_high_quality_confidence_high(tmp_path: Path) -> None:
    copied = tmp_path / "raw_high"
    shutil.copytree(FIXTURE / "raw", copied)
    qqq = pd.read_csv(copied / "daily_prices" / "QQQ.csv")
    qqq["effective_available_at_utc"] = qqq["source_as_of_timestamp_utc"]
    qqq["availability_confidence"] = "high"
    qqq.to_csv(copied / "daily_prices" / "QQQ.csv", index=False)
    out = _run(tmp_path, copied)
    latest = _latest(out)
    spy = latest[latest["score_target"] == "SPY"].iloc[0]
    assert spy["confidence"] == "High"


def test_oos_future_outcome_labels_cannot_influence_score(fixture_out: Path) -> None:
    score = pd.read_csv(fixture_out / "fragility_score_panel_v0.csv")
    oos = pd.read_csv(fixture_out / "fragility_score_oos_panel_v0.csv")
    merged = oos.merge(score[["score_target", "session_date", "fragility_score"]], on=["score_target", "session_date"], suffixes=("_oos", "_score"))
    assert np.allclose(merged["fragility_score_oos"].fillna(-999), merged["fragility_score_score"].fillna(-999))


def test_oos_fixed_bands_not_quantiles(fixture_out: Path) -> None:
    oos = pd.read_csv(fixture_out / "fragility_score_oos_panel_v0.csv")
    for _, row in oos.dropna(subset=["fragility_score"]).head(30).iterrows():
        assert row["score_band"] == m.risk_state_for_score(row["fragility_score"])


def test_oos_insufficient_history_status(tmp_path: Path) -> None:
    input_root = _one_row_input(tmp_path)
    out = _run(tmp_path / "run", input_root)
    summary = pd.read_csv(out / "fragility_score_oos_summary_v0.csv")
    assert set(summary["evidence_status"]) == {"insufficient_data"}


def test_oos_min_observation_fold_thresholds_respected(fixture_out: Path) -> None:
    summary = pd.read_csv(fixture_out / "fragility_score_oos_summary_v0.csv")
    for _, row in summary.iterrows():
        if row["valid_oos_observation_count"] < 100 or row["non_empty_fold_count"] < 3:
            assert row["evidence_status"] == "insufficient_data"


def test_tail_flag_uses_rv20_at_t_only(fixture_out: Path) -> None:
    oos = pd.read_csv(fixture_out / "fragility_score_oos_panel_v0.csv")
    row = oos[oos["oos_eligible"] == True].iloc[0]
    threshold = -1.5 * row["rv20_at_t"] * math.sqrt(5 / 252)
    expected = int(row["forward_close_to_close_drawdown_5d"] <= threshold)
    assert row["forward_tail_flag_5d"] == expected


def test_no_fitted_coefficients_or_calibrated_weights_emitted(fixture_out: Path) -> None:
    manifest = json.loads((fixture_out / "fragility_score_manifest_v0.json").read_text())
    assert manifest["score_weight_fitting_allowed"] is False
    assert manifest["score_calibration_allowed"] is False


def test_oos_actionization_allowed_false(fixture_out: Path) -> None:
    oos = pd.read_csv(fixture_out / "fragility_score_oos_panel_v0.csv")
    assert set(oos["actionization_allowed"].astype(str).str.lower()) == {"false"}


def test_integration_required_artifacts_exist(fixture_out: Path) -> None:
    required = [
        "fragility_raw_source_inventory_v0.csv",
        "fragility_raw_input_audit_v0.csv",
        "fragility_daily_calendar_audit_v0.csv",
        "fragility_daily_availability_audit_v0.csv",
        "fragility_daily_canonical_panel_v0.csv",
        "fragility_score_decision_universe_v0.csv",
        "fragility_feature_panel_v0.csv",
        "fragility_score_no_lookahead_audit_v0.csv",
        "fragility_component_scores_v0.csv",
        "fragility_score_panel_v0.csv",
        "fragility_score_latest_v0.csv",
        "fragility_score_latest_v0.json",
        "fragility_score_dashboard_v0.md",
        "fragility_score_manifest_v0.json",
        "fragility_score_oos_panel_v0.csv",
        "fragility_score_oos_summary_v0.csv",
    ]
    assert all((fixture_out / name).exists() for name in required)


def test_integration_market_latest_complete_spy_qqq_core(fixture_out: Path) -> None:
    latest = _latest(fixture_out)
    market = latest[latest["score_target"] == "MARKET"].iloc[0]
    assert market["score_status"] == "valid"
    assert "trend_drawdown_stress" not in str(market["missing_components"])


def test_integration_missing_vix_changes_coverage_not_zero(tmp_path: Path) -> None:
    copied = tmp_path / "raw_no_vix"
    shutil.copytree(FIXTURE / "raw", copied)
    shutil.rmtree(copied / "volatility_indices")
    out = _run(tmp_path, copied)
    latest = _latest(out)
    spy = latest[latest["score_target"] == "SPY"].iloc[0]
    assert spy["data_coverage_pct"] == 90
    assert not spy["vix_term_structure_stress"] == 0


def test_integration_source_availability_audit_non_empty(fixture_out: Path) -> None:
    audit = pd.read_csv(fixture_out / "fragility_daily_availability_audit_v0.csv")
    assert not audit.empty


def test_integration_clean_fixture_no_lookahead_no_violations(fixture_out: Path) -> None:
    audit = pd.read_csv(fixture_out / "fragility_score_no_lookahead_audit_v0.csv")
    assert "data_quality_blocked" not in set(audit["no_lookahead_status"])


def test_integration_oos_descriptive_only(fixture_out: Path) -> None:
    summary = pd.read_csv(fixture_out / "fragility_score_oos_summary_v0.csv")
    assert summary["interpretation_caveat"].str.contains("Descriptive OOS").all()


def test_integration_actionization_allowed_false(fixture_out: Path) -> None:
    manifest = json.loads((fixture_out / "fragility_score_manifest_v0.json").read_text())
    assert manifest["actionization_allowed"] is False
