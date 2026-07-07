from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import scripts.build_morita_regime_sizing_overlay_v1 as overlay


def policy() -> dict:
    return overlay.load_policy()


def thresholds() -> dict:
    return {
        "D_high_cutoff": overlay.EXPECTED_D_HIGH_CUTOFF,
        "L_high_cutoff": overlay.EXPECTED_L_HIGH_CUTOFF,
        "threshold_source": "synthetic_threshold_source",
        "threshold_manifest_hash": "synthetic_manifest_hash",
    }


def daily_state() -> pd.DataFrame:
    rows = []
    for date, d_value, l_value in [
        ("2026-01-02", 0.08, 0.00),
        ("2026-01-05", 0.12, 0.00),
        ("2026-01-06", 0.12, 0.03),
        ("2026-01-07", 0.08, 0.03),
    ]:
        cls = overlay.classify_regime(d_value, l_value, thresholds())
        rows.append(
            {
                "regime_observation_date": date,
                "regime_data_asof_timestamp": f"{date}T20:00:00Z",
                "D_value": d_value,
                "L_value": l_value,
                "D_high_cutoff": thresholds()["D_high_cutoff"],
                "L_high_cutoff": thresholds()["L_high_cutoff"],
                "threshold_source": "synthetic_threshold_source",
                "threshold_manifest_hash": "synthetic_manifest_hash",
                **cls,
            }
        )
    return pd.DataFrame(rows)


def patch_synthetic_sources(monkeypatch: pytest.MonkeyPatch, prior: pd.DataFrame | None = None) -> None:
    monkeypatch.setattr(overlay, "load_thresholds", lambda *args, **kwargs: thresholds())
    monkeypatch.setattr(overlay, "build_regime_daily_state", lambda *args, **kwargs: daily_state())
    monkeypatch.setattr(overlay, "load_prior_recommendations", lambda *args, **kwargs: prior if prior is not None else pd.DataFrame())
    monkeypatch.setattr(overlay, "verify_source_artifacts", lambda: {"synthetic": {"status": "passed"}})


def s_row(date: str = "2026-01-06") -> dict:
    return {
        "ticker": "TEST",
        "alert_rank": "S",
        "breakout_date": date,
        "production_adjusted_score": 55,
        "legacy_50pct_exception_eligible": False,
    }


def test_regime_classifier_and_l_high_only_normal() -> None:
    th = thresholds()
    assert overlay.classify_regime(0.08, 0.00, th)["regime_state"] == "NORMAL"
    assert overlay.classify_regime(0.12, 0.00, th)["regime_state"] == "HIGH_DISPERSION"
    assert overlay.classify_regime(0.12, 0.03, th)["regime_state"] == "NARROW_LEADERSHIP"
    assert overlay.classify_regime(0.08, 0.03, th)["regime_state"] == "NORMAL"
    assert overlay.classify_regime(None, 0.03, th)["regime_state"] == "REGIME_UNAVAILABLE_CONSERVATIVE"


def test_sizing_policy_targets_and_legacy_exception() -> None:
    p = policy()
    normal = overlay.apply_sizing_policy("NORMAL", p, legacy_50pct_exception_eligible=False)
    assert normal["suggested_max_premium_pct"] == pytest.approx(0.30)
    assert normal["sleeve_capacity_status"] == "NO_ROLLING_CAP"
    legacy = overlay.apply_sizing_policy("NORMAL", p, legacy_50pct_exception_eligible=True)
    assert legacy["suggested_max_premium_pct"] == pytest.approx(0.50)
    assert legacy["legacy_50pct_exception_allowed"] is True
    high = overlay.apply_sizing_policy("HIGH_DISPERSION", p, legacy_50pct_exception_eligible=True)
    assert high["suggested_max_premium_pct"] == pytest.approx(0.20)
    assert high["legacy_50pct_exception_allowed"] is False
    narrow = overlay.apply_sizing_policy("NARROW_LEADERSHIP", p)
    assert narrow["suggested_max_premium_pct"] == pytest.approx(0.15)
    unavailable = overlay.apply_sizing_policy("REGIME_UNAVAILABLE_CONSERVATIVE", p)
    assert unavailable["suggested_max_premium_pct"] == pytest.approx(0.20)


def test_remaining_sleeve_capacity_caps_without_suppressing() -> None:
    p = policy()
    partial = overlay.apply_sizing_policy("NARROW_LEADERSHIP", p, current_rolling_recommendation_pct=0.20)
    assert partial["suggested_max_premium_pct"] == pytest.approx(0.10)
    assert partial["sleeve_capacity_status"] == "PARTIALLY_AVAILABLE"
    exhausted = overlay.apply_sizing_policy("NARROW_LEADERSHIP", p, current_rolling_recommendation_pct=0.31)
    assert exhausted["suggested_max_premium_pct"] == pytest.approx(0.0)
    assert exhausted["sleeve_capacity_status"] == "EXHAUSTED"


def test_threshold_loader_verifies_expected_values(tmp_path: Path) -> None:
    good = tmp_path / "cutoffs.csv"
    pd.DataFrame(
        [
            {"metric": overlay.D_METRIC, "p33": 0.01, "p67": overlay.EXPECTED_D_HIGH_CUTOFF},
            {"metric": overlay.L_METRIC, "p33": 0.01, "p67": overlay.EXPECTED_L_HIGH_CUTOFF},
        ]
    ).to_csv(good, index=False)
    assert overlay.load_thresholds(good)["D_high_cutoff"] == pytest.approx(overlay.EXPECTED_D_HIGH_CUTOFF)
    bad = tmp_path / "bad.csv"
    pd.DataFrame(
        [
            {"metric": overlay.D_METRIC, "p33": 0.01, "p67": 0.20},
            {"metric": overlay.L_METRIC, "p33": 0.01, "p67": overlay.EXPECTED_L_HIGH_CUTOFF},
        ]
    ).to_csv(bad, index=False)
    with pytest.raises(ValueError, match="D_high_cutoff_failed_verification"):
        overlay.load_thresholds(bad)


def test_exact_date_join_and_missing_state_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_synthetic_sources(monkeypatch)
    state = daily_state()
    decision = overlay.decision_from_signal(
        s_row("2026-01-06"),
        daily_state=state,
        policy=policy(),
        prior_recommendations=pd.DataFrame(),
    )
    assert decision["regime_observation_date"] == "2026-01-06"
    assert decision["regime_state"] == "NARROW_LEADERSHIP"
    missing = overlay.decision_from_signal(
        s_row("2026-01-08"),
        daily_state=state,
        policy=policy(),
        prior_recommendations=pd.DataFrame(),
    )
    assert missing["regime_state"] == "REGIME_UNAVAILABLE_CONSERVATIVE"
    assert missing["data_availability_status"] == "UNAVAILABLE_OR_FAILED_VALIDATION"


def test_rolling_window_uses_current_plus_previous_nine_sessions() -> None:
    dates = pd.DataFrame({"regime_observation_date": [f"2026-01-{day:02d}" for day in range(1, 16)]})
    window = overlay.rolling_decision_dates(dates, "2026-01-15", 10)
    assert window == [f"2026-01-{day:02d}" for day in range(6, 16)]


def test_recommendation_only_and_confirmed_execution_sources() -> None:
    window = ["2026-01-02", "2026-01-05", "2026-01-06"]
    prior = pd.DataFrame(
        [
            {"signal_id": "a", "rank": "S", "signal_decision_date": "2026-01-02", "suggested_max_premium_pct": 0.20},
            {"signal_id": "b", "rank": "A", "signal_decision_date": "2026-01-05", "suggested_max_premium_pct": 0.20},
        ]
    )
    assert overlay.recommendation_rolling_total(prior, window) == pytest.approx(0.20)
    total, source = overlay.confirmed_execution_rolling_total(None, window)
    assert total == pytest.approx(0.0)
    assert source == "RECOMMENDATION_ONLY"
    ledger = pd.DataFrame(
        [
            {"rank": "S", "execution_status": "filled", "entry_decision_date": "2026-01-05", "initial_premium_pct": 0.15},
            {"rank": "S", "execution_status": "missed", "entry_decision_date": "2026-01-06", "initial_premium_pct": 0.15},
        ]
    )
    total, source = overlay.confirmed_execution_rolling_total(ledger, window)
    assert total == pytest.approx(0.15)
    assert source == "CONFIRMED_EXECUTION"


def test_enrich_s_only_and_ab_only_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_synthetic_sources(monkeypatch)
    ab = pd.DataFrame([{"ticker": "AB", "alert_rank": "A", "breakout_date": "2026-01-06"}])
    enriched_ab = overlay.enrich_s_candidates(ab, write_logs=False)
    assert list(enriched_ab.columns) == list(ab.columns)
    mixed = pd.DataFrame([s_row("2026-01-06"), {"ticker": "AB", "alert_rank": "A", "breakout_date": "2026-01-06"}])
    enriched = overlay.enrich_s_candidates(mixed, write_logs=False)
    assert "regime_overlay_regime_state" in enriched.columns
    assert enriched.loc[0, "regime_overlay_regime_state"] in {
        "NORMAL",
        "HIGH_DISPERSION",
        "NARROW_LEADERSHIP",
        "REGIME_UNAVAILABLE_CONSERVATIVE",
    }
    assert pd.isna(enriched.loc[1, "regime_overlay_regime_state"])


def test_notification_block_required_fields_and_non_s_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_synthetic_sources(monkeypatch)
    block = overlay.notification_overlay_block(s_row("2026-01-06"))
    assert "Regime sizing overlay" in block
    assert "Suggested" in block
    assert "Rolling 10-session S sleeve" in block
    assert "50% exception" in block
    assert "Budget source" in block
    assert "Policy: morita_regime_sizing_overlay_v1" in block
    assert "buy now" not in block.lower()
    assert overlay.notification_overlay_block({"ticker": "AB", "alert_rank": "A"}) == ""


def test_output_manifest_rejects_missing_and_unexpected_files(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        overlay.create_manifest(tmp_path)
    for name in overlay.REQUIRED_OUTPUTS:
        (tmp_path / name).write_text("x\n", encoding="utf-8")
    (tmp_path / "unexpected.csv").write_text("x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected_output_files"):
        overlay.create_manifest(tmp_path)


def test_no_broker_or_account_language_in_overlay_source() -> None:
    source = Path(overlay.__file__).read_text(encoding="utf-8").lower()
    forbidden = ["place_order", "buying_power", "account_id", "webull_order", "submit_order"]
    assert not any(token in source for token in forbidden)
