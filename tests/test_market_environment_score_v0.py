from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import market_environment_score_v0 as score


def sample_snapshot() -> pd.DataFrame:
    rows = []

    def add(name, value, state="neutral", quality="observed", proxy=False):
        rows.append(
            {
                "market_snapshot_id": "mb_test",
                "timestamp_utc": "2026-06-26T01:00:00+00:00",
                "collected_at_utc": "2026-06-26T01:00:00+00:00",
                "source_available_at_utc": "2026-06-26T01:00:00+00:00",
                "metric_name": name,
                "metric_value": value,
                "metric_state": state,
                "quality_flag": quality,
                "is_proxy": proxy,
            }
        )

    for ticker in ["QQQ", "SOXX"]:
        add(f"{ticker}.close_vs_20ema_pct", 1.0)
        add(f"{ticker}.close_vs_50dma_pct", 2.0)
        add(f"{ticker}.20EMA_slope_5d_pct", 0.2)
        add(f"{ticker}.50DMA_slope_5d_pct", 0.3)
        add(f"{ticker}.20d_realized_vol", 0.20)
        add(f"{ticker}.dealer_gamma_state", "Positive Gamma", "proxy_only", "observed", True)
        add(f"{ticker}.spot_vs_gamma_flip_pct", -0.5, "neutral", "observed", True)
        add(f"{ticker}.0dte_share", 0.05, "neutral", "observed", True)
        add(f"{ticker}.pinning_score", 0.2, "neutral", "observed", True)
    add("VIX.20d_percentile", 0.3)
    add("VIX.1d_change_pct", -1.0)
    add("is_month_end_window", False)
    add("is_quarter_end_window", False)
    add("is_pension_rebalance_window", False)
    add("TQQQ.estimated_rebalance_notional", 600_000_000, "proxy_only", "observed", True)
    add("SQQQ.estimated_rebalance_notional", 0, "proxy_only", "observed", True)
    add("SOXL.estimated_rebalance_notional", 100_000_000, "proxy_only", "observed", True)
    add("SOXS.estimated_rebalance_notional", 0, "proxy_only", "observed", True)
    add("QQQ.estimated_cta_pressure", "long_bias", "proxy_only", "observed", True)
    add("QQQ.target_vol_12pct.vol_control_pressure_proxy", 0.1, "proxy_only", "observed", True)
    add("deleveraging_pressure_proxy", 0, "proxy_only", "observed", True)
    add("correlation_shock_flag", False, "proxy_only", "observed", True)
    return pd.DataFrame(rows)


def test_market_score_is_between_zero_and_hundred_and_separates_proxy():
    result = score.calculate_market_environment_score(sample_snapshot(), pd.Timestamp("2026-06-26T01:30:00Z"))
    assert result["market_environment_score_v0"] is not None
    assert 0 <= result["market_environment_score_v0"] <= 100
    assert result["market_environment_score_observed_v0"] is not None
    assert result["market_environment_score_proxy_augmented_v0"] is not None
    assert result["market_score_confidence"] in {"medium", "low"}


def test_unavailable_components_reduce_coverage_not_score_zero():
    snap = sample_snapshot()
    snap = snap[~snap["metric_name"].str.startswith("VIX")]
    result = score.calculate_market_environment_score(snap, pd.Timestamp("2026-06-26T01:30:00Z"))
    assert result["market_score_coverage_pct"] < 100
    assert "Volatility Regime" in result["market_score_unavailable_components"]


def test_coverage_below_sixty_makes_standard_score_unavailable():
    snap = sample_snapshot()
    snap = snap[snap["metric_name"].isin(["QQQ.close_vs_20ema_pct"])]
    result = score.calculate_market_environment_score(snap, pd.Timestamp("2026-06-26T01:30:00Z"))
    assert result["market_environment_score_v0"] is None
    assert result["market_score_confidence"] == "low"


def test_stale_gex_snapshot_is_not_used():
    snap = sample_snapshot()
    component = score.dealer_component(snap, pd.Timestamp("2026-06-28T02:00:00Z"))
    assert component["available_points"] == 0
    assert component["details"]["stale"] is True


def test_execution_score_unavailable_without_option_quote():
    option_context = pd.DataFrame(
        [
            {
                "option_snapshot_id": "opt_test",
                "decision_id": "dec_test",
                "snapshot_timestamp_utc": "2026-06-26T01:00:00+00:00",
                "collected_at_utc": "2026-06-26T01:00:00+00:00",
                "candidate_label": "target_delta_060",
            }
        ]
    )
    out = score.calculate_execution_scores(option_context)
    assert pd.isna(out.loc[0, "execution_score_v0"])
    assert out.loc[0, "execution_score_confidence"] == "low"


def test_deployment_and_dealer_audits_are_written(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("MARKET_ENV_GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("MORITA_GITHUB_REPOSITORY", raising=False)
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "daily_scan.yml").write_text('on:\n  schedule:\n    - cron: "0 1 * * 1-5"\n', encoding="utf-8")
    snap_dir = tmp_path / "market_bomb_snapshots" / "2026-06-26"
    snap_dir.mkdir(parents=True)
    sample_snapshot().to_csv(snap_dir / "market_bomb_snapshot_20260626_0100.csv", index=False)
    option_dir = tmp_path / "option_chain_snapshots" / "2026-06-26"
    option_dir.mkdir(parents=True)
    (option_dir / "QQQ_20260626_0630_jst.json").write_text(
        """
{
  "ticker": "QQQ",
  "option_chain_as_of_timestamp_utc": "2026-06-25T21:30:00Z",
  "underlying_quote_timestamp_utc": "2026-06-25T21:30:00Z",
  "option_quote_timestamp_utc": "2026-06-25T21:30:00Z",
  "underlyingPrice": 500,
  "calls": [{"strike": 500, "expiration": "2026-09-18", "bid": 10, "ask": 11, "openInterest": 1000, "impliedVolatility": 0.4}],
  "puts": [{"strike": 500, "expiration": "2026-09-18", "bid": 9, "ask": 10, "openInterest": 900, "impliedVolatility": 0.42}]
}
""",
        encoding="utf-8",
    )
    outputs = score.run(tmp_path)
    assert outputs["deployment_audit_csv"].exists()
    assert outputs["dealer_coverage_csv"].exists()
    assert outputs["score_history_csv"].exists()
    assert outputs["execution_history_csv"].exists()
    coverage = pd.read_csv(outputs["dealer_coverage_csv"])
    qqq = coverage[coverage["ticker"].eq("QQQ")].iloc[0]
    assert qqq["after_close_count"] == 1
    assert qqq["strict_entry_usable_count"] == 0
    assert qqq["prior_session_context_usable_count"] == 1
    assert qqq["historical_reconstructed_usable_count"] == 1
    assert qqq["input_completeness_rate"] > 0.8
    detail = pd.read_csv(tmp_path / "dealer_gamma_history" / "dealer_gamma_snapshot_file_audit.csv")
    assert "underlying_quote_timestamp_utc" in detail.columns
    assert "economic_quality" in detail.columns
    backfill = pd.read_csv(tmp_path / "dealer_gamma_history" / "dealer_gamma_proxy_history.csv")
    assert len(backfill) == 1
    assert backfill.loc[0, "data_type"] == "reconstructed"
    assert backfill.loc[0, "is_proxy"] == True
    assert backfill.loc[0, "sign_convention"] == score.DEALER_GAMMA_SIGN_CONVENTION
    assert backfill.loc[0, "dealer_gamma_proxy_assumption"] == score.DEALER_GAMMA_PROXY_ASSUMPTION
    assert backfill.loc[0, "dealer_position_observed"] == False
    assert (tmp_path / "dealer_gamma_history" / "dealer_gamma_quality_rules_v2.json").exists()
    assert (tmp_path / "dealer_gamma_history" / "dealer_gamma_root_diagnostics.csv").exists()
    assert "raw_chain_quality" in backfill.columns
    assert "net_gex_proxy_quality" in backfill.columns
    assert "gamma_flip_proxy_quality" in backfill.columns
    assert list((tmp_path / "dealer_gamma_history").glob("dealer_gamma_manual_validation_QQQ_*.md"))
    manual = list((tmp_path / "dealer_gamma_history").glob("dealer_gamma_manual_validation_QQQ_*.md"))[0].read_text(encoding="utf-8")
    assert "Contract-Level Gamma Examples" in manual


def test_0630_jst_after_close_snapshot_is_not_strict_entry_but_is_context():
    ts = pd.Timestamp("2026-06-25T21:30:00Z")
    flags = score.snapshot_usability(ts, raw_complete=True, gex_success=True)
    assert flags["us_session_phase"] == "after_close"
    assert flags["strict_entry_usable"] is False
    assert flags["prior_session_context_usable"] is True
    assert flags["historical_reconstructed_usable"] is True


def test_0630_jst_is_after_close_in_winter_too():
    ts = pd.Timestamp("2026-01-05T21:30:00Z")
    assert score.classify_us_session(ts) == "after_close"
    assert score.session_subtype(score.classify_us_session(ts)) == "post_close"


def test_strict_entry_requires_decision_available_and_fresh():
    assert score.strict_entry_usable_for_decision(
        "2026-06-26T13:00:00Z",
        "2026-06-26T13:00:00Z",
        "2026-06-26T12:00:00Z",
        "2026-06-26T13:30:00Z",
        "medium",
        "same_session_pre_open",
    )
    assert not score.strict_entry_usable_for_decision(
        "2026-06-26T14:00:00Z",
        "2026-06-26T14:00:00Z",
        "2026-06-26T12:00:00Z",
        "2026-06-26T13:30:00Z",
        "medium",
        "same_session_pre_open",
    )
    assert not score.strict_entry_usable_for_decision(
        "2026-06-26T13:00:00Z",
        "2026-06-26T13:00:00Z",
        "2026-06-25T12:00:00Z",
        "2026-06-26T13:30:00Z",
        "medium",
        "same_session_pre_open",
    )


def test_deployment_audit_uses_github_main_api_when_available(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setattr(
        score,
        "github_main_tree",
        lambda repo: {
            ".github/workflows/daily_scan.yml": {"type": "blob"},
            "market_environment_score_v0.py": {"type": "blob"},
        },
    )
    monkeypatch.setattr(score, "github_file_text", lambda repo, path: 'on:\n  schedule:\n    - cron: "0 1 * * 1-5"\n')
    monkeypatch.setattr(score, "github_workflow_runs", lambda repo, workflow_path=None: {"latest_successful_run": "url", "workflow_execution_success_rate": 1.0, "started_at": "2026-06-26T01:00:00Z", "completed_at": "2026-06-26T01:01:00Z"})
    out = score.deployment_audit(tmp_path)
    daily = out[out["component"].eq("daily_scan_workflow")].iloc[0]
    assert daily["source_basis"] == "github_main_api"
    assert bool(daily["main_branch_checked"]) is True
    assert bool(daily["exists_on_main"]) is True
    assert bool(daily["local_exists"]) is False


def test_api_unavailable_does_not_guess_exists_on_main(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "daily_scan.yml").write_text("name: local only\n", encoding="utf-8")
    out = score.deployment_audit(tmp_path)
    daily = out[out["component"].eq("daily_scan_workflow")].iloc[0]
    assert daily["source_basis"] == "local_fallback_repo_unresolved_or_api_unavailable"
    assert bool(daily["main_branch_checked"]) is False
    assert pd.isna(daily["exists_on_main"]) or daily["exists_on_main"] == ""
    assert bool(daily["local_exists"]) is True


def test_dealer_gamma_sign_convention_and_assumption():
    rows = [
        {"call_put_flag": "call", "strike": 500, "expiration": "2026-09-18", "open_interest": 1000, "implied_volatility": 0.4, "contract_multiplier": 100},
        {"call_put_flag": "put", "strike": 500, "expiration": "2026-09-18", "open_interest": 500, "implied_volatility": 0.4, "contract_multiplier": 100},
    ]
    out = score.calculate_gex_proxy_metrics(rows, 500, pd.Timestamp("2026-06-25T21:30:00Z"))
    assert out["call_gamma_open_interest_proxy"] > 0
    assert out["put_gamma_open_interest_proxy"] > 0
    assert out["net_gamma_open_interest_proxy"] == pytest.approx(out["call_gamma_open_interest_proxy"] - out["put_gamma_open_interest_proxy"], rel=1e-6)
    assert out["dealer_gamma_proxy"] == pytest.approx(-out["net_gamma_open_interest_proxy"], rel=1e-6)
    assert out["sign_convention"] == score.DEALER_GAMMA_SIGN_CONVENTION
    assert pd.isna(score.dealer_gamma_proxy_from_net_gamma(123.0, ""))


def test_gamma_flip_quality_guard_rejects_far_root():
    quality, warning, failure = score.gamma_flip_quality(-0.755)
    assert quality == "unusable"
    assert warning == "far_from_spot"
    assert failure == "far_root_rejected"


def test_no_local_flip_is_normal_status_not_raw_failure():
    rows = [
        {"call_put_flag": "call", "strike": 500, "expiration": "2026-09-18", "open_interest": 1000, "implied_volatility": 0.4, "contract_multiplier": 100},
        {"call_put_flag": "call", "strike": 520, "expiration": "2026-09-18", "open_interest": 900, "implied_volatility": 0.42, "contract_multiplier": 100},
    ]
    metrics = score.calculate_gex_proxy_metrics(rows, 500, pd.Timestamp("2026-06-25T21:30:00Z"))
    assert metrics["gamma_flip_status"] == "no_local_flip"
    assert metrics["gamma_flip_proxy_quality"] == "unavailable"
    assert pd.isna(metrics["gamma_flip_proxy"])


def test_local_gamma_flip_selects_nearest_root(monkeypatch):
    values = {
        80.0: -1.0,
        90.0: 1.0,
        100.0: 2.0,
        110.0: -2.0,
        120.0: -1.0,
    }

    def fake_grid(low, high, size):
        return pd.Series([80.0, 90.0, 100.0, 110.0, 120.0]).to_numpy()

    monkeypatch.setattr(score.np, "linspace", fake_grid)
    monkeypatch.setattr(score, "aggregate_gamma_proxy_at_price", lambda rows, spot, as_of: values[spot])
    metrics, diagnostics = score.local_gamma_flip_search([{"dummy": True}], 100, pd.Timestamp("2026-06-25T21:30:00Z"))
    assert metrics["gamma_flip_root_count"] == 2
    assert metrics["gamma_flip_selected_root"] == 105.0
    assert metrics["gamma_flip_selection_reason"] == "nearest_to_spot"
    assert diagnostics


def test_corrupted_raw_chain_does_not_crash_and_duplicate_is_detected(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    option_dir = tmp_path / "option_chain_snapshots"
    option_dir.mkdir()
    (option_dir / "QQQ_20260626_0630_a.json").write_text("{broken", encoding="utf-8")
    (option_dir / "QQQ_20260626_0630_b.json").write_text("{broken", encoding="utf-8")
    coverage = score.dealer_gamma_coverage_audit(tmp_path)
    qqq = coverage[coverage["ticker"].eq("QQQ")].iloc[0]
    assert qqq["corrupted_or_incomplete_snapshot_count"] == 2
    assert qqq["duplicate_snapshot_count"] == 1
