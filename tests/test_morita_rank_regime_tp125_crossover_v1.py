from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_morita_rank_regime_tp125_crossover_v1.py"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.build_morita_rank_regime_tp125_crossover_v1 as study


def thresholds() -> dict[str, float]:
    return {
        "D_high_cutoff": study.EXPECTED_D_HIGH_CUTOFF,
        "L_high_cutoff": study.EXPECTED_L_HIGH_CUTOFF,
    }


def test_regime_classification_matches_three_state_policy() -> None:
    th = thresholds()
    assert study.classify_regime(0.05, 0.99, th)["regime_state"] == "NORMAL"
    assert study.classify_regime(0.12, 0.00, th)["regime_state"] == "HIGH_DISPERSION"
    assert study.classify_regime(0.12, 0.03, th)["regime_state"] == "NARROW_LEADERSHIP"
    assert study.classify_regime(None, 0.03, th)["regime_state"] == "REGIME_UNAVAILABLE"


def test_profit_factor_and_loss_metrics_are_option_return_based() -> None:
    returns = pd.Series([125.0, -50.0, 25.0, -25.0])
    assert study.profit_factor(returns) == pytest.approx(2.0)
    assert study.mean_loss(returns) == pytest.approx(-37.5)
    assert study.median_loss(returns) == pytest.approx(-37.5)
    assert math.isinf(study.profit_factor(pd.Series([1.0, 2.0])))


def test_nonempty_treats_nan_as_empty_tp_marker() -> None:
    assert not study.nonempty(float("nan"))
    assert not study.nonempty("")
    assert study.nonempty("2026-01-02")


def test_cell_summary_includes_empty_cells_and_sparse_flags() -> None:
    trades = pd.DataFrame(
        [
            {
                "period_id": "primary_2024_2026_completed_confirmation_interval",
                "cell": "A_NORMAL",
                "rank": "A",
                "regime_state": "NORMAL",
                "ticker": "AAA",
                "theme": "Software",
                "tp125_hit": True,
                "modeled_exit_option_return_pct": 125.0,
                "min_net_return_close_pct": -10.0,
                "modeled_underlying_MAE_pct": -2.0,
                "breakout_low_breach_before_exit": False,
                "day10_plus5_success": True,
                "timeout_10_sessions_under_threshold": False,
            }
        ]
    )
    summary = study.build_cell_summary(trades)
    assert set(summary["cell"]) == set(study.CELLS)
    row = summary[summary["cell"] == "A_NORMAL"].iloc[0]
    assert row["trade_count"] == 1
    assert row["tp125_hit_rate"] == pytest.approx(1.0)
    assert row["sample_flag"] == "SPARSE_SAMPLE"


def test_required_primary_label_precedence() -> None:
    spec = {
        "primary_period": {"period_id": "primary_2024_2026_completed_confirmation_interval"},
        "sample_gates": {"primary_comparison_min_per_side": 10},
        "tp125_floor": {"floor_hit_rate": 0.35, "preferred_hit_rate": 0.40},
    }
    summary = pd.DataFrame(
        [
            {
                "period_id": "primary_2024_2026_completed_confirmation_interval",
                "cell": "A_NORMAL",
                "trade_count": 9,
                "tp125_hit_rate": 1.0,
                "profit_factor": 2.0,
            },
            {
                "period_id": "primary_2024_2026_completed_confirmation_interval",
                "cell": "S_NARROW_LEADERSHIP",
                "trade_count": 20,
                "tp125_hit_rate": 0.20,
                "profit_factor": 0.5,
            },
        ]
    )
    assert study.primary_label(summary, spec)["primary_label"] == "INSUFFICIENT_PRIMARY_SAMPLE"
    summary.loc[summary["cell"] == "A_NORMAL", "trade_count"] = 10
    summary.loc[summary["cell"] == "A_NORMAL", "tp125_hit_rate"] = 0.30
    assert study.primary_label(summary, spec)["primary_label"] == "A_NORMAL_TP125_NOT_ESTABLISHED"
    summary.loc[summary["cell"] == "A_NORMAL", "tp125_hit_rate"] = 0.37
    assert study.primary_label(summary, spec)["primary_label"] == "A_NORMAL_MEETS_TP125_FLOOR"
    summary.loc[summary["cell"] == "A_NORMAL", "tp125_hit_rate"] = 0.42
    assert study.primary_label(summary, spec)["primary_label"] == "A_NORMAL_POTENTIAL_RANK_REGIME_CROSSOVER"


def test_2023_is_descriptive_only_in_period_comparison() -> None:
    summary = pd.DataFrame(
        [
            {"period_id": "primary_2024_2026_completed_confirmation_interval", "cell": "A_NORMAL", "trade_count": 10, "tp125_hit_rate": 0.4, "profit_factor": 1.2},
            {"period_id": "descriptive_2023_rs_warmup_frozen_threshold", "cell": "A_NORMAL", "trade_count": 8, "tp125_hit_rate": 0.6, "profit_factor": 2.2},
            {"period_id": "combined_2023_2026_descriptive", "cell": "A_NORMAL", "trade_count": 18, "tp125_hit_rate": 0.5, "profit_factor": 1.6},
        ]
    )
    period = study.build_period_comparison(summary)
    row = period[period["cell"] == "A_NORMAL"].iloc[0]
    assert row["period_pooling_status"] == "combined_row_descriptive_only_not_used_for_primary_label"
    assert row["descriptive_2023_trades"] == 8


def test_script_cli_help_is_available() -> None:
    result = subprocess.run([sys.executable, str(SCRIPT_PATH), "--help"], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    assert result.returncode == 0
    assert "run" in result.stdout
    assert "verify" in result.stdout
