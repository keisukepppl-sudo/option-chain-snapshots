from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import market_bomb_phase3_2_cta_vol_proxy as p32


def price_frame(values, start="2026-01-01"):
    return pd.DataFrame(
        {
            "date": pd.bdate_range(start, periods=len(values)),
            "close": values,
            "adjusted_close": values,
        }
    )


def test_rolling_features_use_prior_history_not_future():
    df = p32.add_common_price_features(price_frame(list(range(100, 230))))
    assert pd.isna(df.loc[18, "realized_vol_20d"])
    assert pd.notna(df.loc[20, "realized_vol_20d"])
    expected = df.loc[20, "adjusted_close"] / df.loc[0, "adjusted_close"] - 1
    assert df.loc[20, "return_20d_pct"] == expected


def test_eod_feature_not_joined_to_same_day_decision():
    prices = {"QQQ": price_frame(np.linspace(100, 140, 260)), "SPY": price_frame(np.linspace(100, 130, 260)), "SOXX": price_frame(np.linspace(100, 160, 260)), "TLT": price_frame(np.linspace(100, 95, 260)), "HYG": price_frame(np.linspace(100, 102, 260))}
    cta = p32.build_cta_proxy_history(prices)
    decision = pd.Timestamp("2026-01-29T20:00:00Z")
    row, status, _ = p32.latest_feature(cta, "QQQ", decision)
    assert status != "joined" or pd.Timestamp(row["feature_as_of_timestamp_utc"]) < decision


def test_latest_prior_feature_is_selected_and_old_feature_rejected():
    cta = pd.DataFrame(
        [
            {"asset": "QQQ", "feature_as_of_timestamp_utc": "2026-01-01T21:00:00Z", "effective_available_at_utc": "2026-01-02T14:30:00Z"},
            {"asset": "QQQ", "feature_as_of_timestamp_utc": "2026-01-05T21:00:00Z", "effective_available_at_utc": "2026-01-06T14:30:00Z"},
        ]
    )
    row, status, _ = p32.latest_feature(cta, "QQQ", pd.Timestamp("2026-01-06T15:00:00Z"))
    assert status == "joined"
    assert row["feature_as_of_timestamp_utc"] == "2026-01-05T21:00:00Z"
    row, status, reason = p32.latest_feature(cta, "QQQ", pd.Timestamp("2026-01-10T15:00:00Z"), max_age_hours=24)
    assert row is None
    assert status == "feature_too_old"


def test_cta_rules_and_deleveraging_definition():
    rising = price_frame(np.linspace(100, 200, 260))
    hist = p32.build_cta_proxy_history({"QQQ": rising, "SPY": rising, "SOXX": rising, "TLT": rising, "HYG": rising})
    qqq = hist[hist["asset"].eq("QQQ")].tail(1).iloc[0]
    assert qqq["cta_trend_state"] == "long_bias"
    assert qqq["cta_normalized_exposure_proxy"] == 1.0
    falling = hist[hist["asset"].eq("QQQ")].copy()
    assert falling["cta_deleveraging_proxy"].isin([True, False]).all()


def test_vol_control_exposure_clip_state_and_targets():
    values = list(np.linspace(100, 120, 80)) + list(np.linspace(120, 80, 80))
    prices = {"QQQ": price_frame(values), "SPY": price_frame(values), "SOXX": price_frame(values)}
    hist = p32.build_vol_control_proxy_history(prices)
    assert set(hist["target_vol"].dropna().round(2)) == {0.10, 0.12, 0.15}
    assert hist["target_exposure_capped"].dropna().between(0, 1).all()
    assert set(hist["vol_control_state"].dropna()).issubset({"re_risking", "stable", "deleveraging", "unavailable"})


def test_strategy_buckets_are_not_mixed_and_small_sample_is_insufficient():
    df = pd.DataFrame(
        [
            {"strategy_bucket": "S_breakout_momentum", "cta_trend_state": "long_bias", "cta_deleveraging_proxy": False, "vol_control_state": "stable", "underlying_return_5d": 0.02, "modelled_option_pnl_pct": 1.0},
            {"strategy_bucket": "AB_institutional_pullback", "cta_trend_state": "long_bias", "cta_deleveraging_proxy": False, "vol_control_state": "stable", "underlying_return_5d": -0.01, "modelled_option_pnl_pct": -0.6},
        ]
    )
    out = p32.summarize_groups(df)
    assert set(out["strategy_bucket"]) == {"S_breakout_momentum", "AB_institutional_pullback"}
    assert set(out["evidence_verdict"]) == {"insufficient_data"}


def test_join_audit_separates_analysis_modes_and_pnl_fields(tmp_path: Path):
    sig_dir = tmp_path / "morita_signal_history"
    sig_dir.mkdir()
    pd.DataFrame(
        [
            {"ticker": "NVDA", "alert_rank": "S", "timestamp_utc": "2026-02-10T15:00:00Z", "modelled_option_pnl_pct": 2.0},
            {"ticker": "MU", "alert_rank": "A", "timestamp_utc": "2026-02-11T15:00:00Z", "observed_option_pnl_pct": -0.6},
        ]
    ).to_csv(sig_dir / "signals.csv", index=False)
    units = p32.load_analysis_units(tmp_path)
    assert set(units["strategy_bucket"]) == {"S_breakout_momentum", "AB_institutional_pullback"}
    assert "observed_option_pnl_pct" in units.columns
    assert "modelled_option_pnl_pct" in units.columns


def test_run_writes_required_outputs_with_local_prices(tmp_path: Path, monkeypatch):
    price_dir = tmp_path / "market_bomb_history" / "price_history"
    price_dir.mkdir(parents=True)
    for asset in sorted(set(p32.CTA_ASSETS + p32.VOL_ASSETS)):
        price_frame(np.linspace(100, 150, 260)).to_csv(price_dir / f"{asset}_daily_price_history.csv", index=False)
    outputs = p32.run(tmp_path, refresh_price_history=False)
    for path in outputs.values():
        assert path.exists()
    assert (tmp_path / "market_bomb_config" / "cta_proxy_rules_v1.json").exists()
    assert (tmp_path / "market_bomb_config" / "vol_control_proxy_rules_v1.json").exists()
    quality = pd.read_csv(tmp_path / "market_bomb_history" / "cta_vol_proxy_quality_audit.csv")
    assert "rows" in quality.columns
