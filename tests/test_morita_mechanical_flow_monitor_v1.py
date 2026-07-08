from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import build_morita_mechanical_flow_monitor_v1 as flow


def _write_policy(path: Path, override: dict | None = None) -> None:
    payload = {
        "policy_version": "morita_mechanical_flow_monitor_v1",
        "mode": "research_logging_only",
        "research_only": True,
        "no_signal_filtering": True,
        "no_auto_execution": True,
        "broker_execution_enabled": False,
        "auto_trade_action_enabled": False,
        "pushover_emergency_enabled": False,
        "rank_change_allowed": False,
        "sizing_change_allowed": False,
        "notification_change_allowed": False,
    }
    if override:
        payload.update(override)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_mechanical_flow_logs_available_metrics_without_creating_signals(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    root = tmp_path / "daily_flow_outputs"
    day = root / "2026-07-08"
    day.mkdir(parents=True)
    _write_policy(policy)
    pd.DataFrame(
        [
            {
                "date": "2026-07-08",
                "ticker": "QQQ",
                "cta_score": 4,
                "cta_flow_proxy": 123.0,
                "cta_regime": "CTA_LONG",
            }
        ]
    ).to_csv(day / "cta_signals.csv", index=False)
    pd.DataFrame(
        [
            {
                "date": "2026-07-08",
                "ticker": "QQQ",
                "vol_control_exposure_proxy": 0.8,
                "vol_control_flow_proxy": -10.0,
                "regime": "VOL_CONTROL_SELL",
            }
        ]
    ).to_csv(day / "vol_control_proxy.csv", index=False)

    receipt = flow.build_monitor(tmp_path / "out", policy, root)

    assert receipt["run_status"] == "mechanical_flow_context_logged"
    context = pd.read_csv(tmp_path / "out" / "mechanical_flow_daily_context.csv")
    assert {"cta_trend_following_proxy", "volatility_control_proxy"}.issubset(set(context["metric_family"]))
    assert set(context["research_only"].astype(str).str.lower()) == {"true"}
    assert set(context["no_signal_filtering"].astype(str).str.lower()) == {"true"}
    assert set(context["no_auto_execution"].astype(str).str.lower()) == {"true"}
    assert "signal" not in context.columns
    assert flow.verify_output_manifest(tmp_path / "out")


def test_missing_metrics_are_unavailable_not_fabricated_and_manifest_is_strict(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    root = tmp_path / "daily_flow_outputs"
    (root / "2026-07-08").mkdir(parents=True)
    _write_policy(policy)

    flow.build_monitor(tmp_path / "out", policy, root)
    availability = pd.read_csv(tmp_path / "out" / "mechanical_flow_metric_availability.csv")
    assert (availability["metric_available"].astype(str).str.lower() == "false").any()
    missing = availability[availability["metric_available"].astype(str).str.lower() == "false"]
    assert set(missing["unavailable_reason"]) == {"no_existing_source_file_found"}

    (tmp_path / "out" / "unexpected.csv").write_text("x\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="mechanical_flow_manifest_file_set_mismatch"):
        flow.verify_output_manifest(tmp_path / "out")


def test_mechanical_flow_policy_rejects_rank_sizing_notification_or_execution_changes(tmp_path: Path) -> None:
    for key, value in [
        ("rank_change_allowed", True),
        ("sizing_change_allowed", True),
        ("notification_change_allowed", True),
        ("broker_execution_enabled", True),
        ("auto_trade_action_enabled", True),
    ]:
        policy = tmp_path / f"{key}.json"
        _write_policy(policy, {key: value})
        with pytest.raises(SystemExit, match="mechanical_flow_policy_safety_flag_mismatch"):
            flow.load_policy(policy)
