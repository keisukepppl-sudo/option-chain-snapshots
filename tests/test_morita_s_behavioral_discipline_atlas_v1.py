from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.morita_long_call_completion_research import engine as e


def path_row(idx: int, high: float, close: float, low: float, open_: float | None = None, under_low: float = 90.0) -> dict[str, object]:
    return {
        "session_index": idx,
        "date": f"2024-01-{idx + 1:02d}",
        "open": 100.0,
        "high": 110.0,
        "low": under_low,
        "close": 100.0,
        "net_return_open_pct": close if open_ is None else open_,
        "net_return_high_pct": high,
        "net_return_close_pct": close,
        "net_return_low_pct": low,
    }


def modeled(rows: list[dict[str, object]], first100: int | str = "", first125: int | str = "", breakout_low: float = 80.0) -> e.ModeledPath:
    record = {
        "status": "eligible",
        "signal_id": "s1",
        "ticker": "AAA",
        "signal_decision_date": "2024-01-01",
        "entry_date": "2024-01-02",
        "theme": "Test",
        "breakout_day_low": breakout_low,
        "path_session_count": len(rows),
        "terminal_date": "2024-01-31",
        "terminal_reason": "max_holding_30_sessions",
        "terminal_net_return_pct": rows[-1]["net_return_close_pct"],
        "first_hit_100_date": "2024-01-05" if first100 != "" else "",
        "first_hit_100_session": first100,
        "first_hit_125_date": "2024-01-06" if first125 != "" else "",
        "first_hit_125_session": first125,
    }
    return e.ModeledPath(record=record, path=rows)


def test_no_network_provider_api_code_exists() -> None:
    text = "\n".join(
        [
            (REPO_ROOT / "src" / "morita_long_call_completion_research" / "engine.py").read_text(encoding="utf-8"),
            (REPO_ROOT / "scripts" / "build_morita_s_behavioral_discipline_atlas_v1.py").read_text(encoding="utf-8"),
        ]
    )
    forbidden = ["requests", "urllib", "yfinance", "download(", "api_key"]
    assert not any(token in text for token in forbidden)


def test_behavioral_variants_share_identical_entry_and_terminal_inputs() -> None:
    mp = modeled([path_row(1, 10, 0, -5), path_row(2, 130, 20, -10), path_row(3, 90, 40, -20)], first125=2)
    returns = e.behavioral_returns(mp)
    assert set(returns) >= set(e.BEHAVIORAL_POLICIES)
    assert returns["GREED_IGNORE_TP125_HOLD_TO_INDEPENDENT_TERMINAL"]["return_pct"] == 40
    assert returns["BASELINE_TP125"]["return_pct"] == 125.0


def test_tp125_target_priority_beats_end_of_day_panic_stop() -> None:
    mp = modeled([path_row(1, 130, -60, -80), path_row(2, 20, 10, -20)], first125=1)
    returns = e.behavioral_returns(mp)
    assert returns["PANIC_OPTION_STOP_25_NEXT_OPEN"]["return_pct"] == 125.0
    assert returns["PANIC_OPTION_STOP_25_NEXT_OPEN"]["exit_reason"] == "tp125_priority"


def test_panic_stop_uses_close_trigger_and_next_open_value() -> None:
    mp = modeled([path_row(1, 90, -30, -80), path_row(2, 20, 5, -50, open_=-12)])
    returns = e.behavioral_returns(mp)
    assert returns["PANIC_OPTION_STOP_25_NEXT_OPEN"]["return_pct"] == -12
    assert returns["PANIC_OPTION_STOP_25_NEXT_OPEN"]["exit_session"] == 2


def test_missing_next_open_is_reported_not_substituted() -> None:
    mp = modeled([path_row(1, 90, -30, -80)])
    returns = e.behavioral_returns(mp)
    assert returns["PANIC_OPTION_STOP_25_NEXT_OPEN"]["status"] == "unavailable_next_open"
    assert returns["PANIC_OPTION_STOP_25_NEXT_OPEN"]["return_pct"] == ""


def test_breakout_low_same_day_collision_is_ambiguous_and_excluded() -> None:
    mp = modeled([path_row(1, 130, 10, -20, under_low=75)], first125=1, breakout_low=80)
    returns = e.behavioral_returns(mp)
    assert returns["BREAKOUT_LOW_RISK_ALERT_TO_EXIT_NEXT_OPEN"]["status"] == "ambiguous_same_day_stop_tp"
    assert returns["BREAKOUT_LOW_RISK_ALERT_TO_EXIT_NEXT_OPEN"]["return_pct"] == ""


def test_low_diagnostic_does_not_change_policy_exit() -> None:
    mp = modeled([path_row(1, 40, 20, -99), path_row(2, 140, 50, -99)], first125=2)
    returns = e.behavioral_returns(mp)
    assert returns["BASELINE_TP125"]["return_pct"] == 125.0
    assert min(row["net_return_low_pct"] for row in mp.path) == -99


def test_pain_atlas_and_post125_statistics_are_correct() -> None:
    mp = modeled([path_row(1, 10, -5, -25), path_row(2, 130, 20, -40), path_row(3, 110, 80, -20)], first125=2)
    pain = {row["cohort"]: row for row in e.pain_atlas([mp])}
    assert pain["TP125_winners_pre_target"]["MAE_low_worst"] == -25
    post = e.post_125_hold_summary([mp])[0]
    assert post["terminal_below_125_rate"] == 1.0
    assert post["post_125_drawdown_worst"] == -105.0


def test_paired_damage_label_criteria_are_fixed() -> None:
    baseline = {"PF": 2.0, "mean": 25.0, "DD_proxy": -100.0}
    worse = {"N": 100, "PF": 1.7, "mean": 19.0, "DD_proxy": -90.0}
    better = {"N": 100, "PF": 2.2, "mean": 30.0, "DD_proxy": -103.0}
    assert e.label_behavioral_variant("FEAR_TP100", baseline, worse, False, 100) == "materially_worse_than_baseline"
    assert e.label_behavioral_variant("FEAR_TP100", baseline, better, False, 100) == "appears_better_under_fixed_iv_model"
    assert e.label_behavioral_variant("FEAR_TP100", baseline, better, False, 200) == "insufficient_variant_coverage"


def test_manifest_check_rejects_missing_changed_extra_outputs(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    for name in e.BEHAVIORAL_REQUIRED_FILES:
        if name != "behavioral_discipline_content_manifest.json":
            (out / name).write_text("x\n", encoding="utf-8")
    from src.morita_single_call_reference import s_single_call_reference_engine as ref

    ref.build_manifest(out, "behavioral_discipline_content_manifest.json", e.BEHAVIORAL_REQUIRED_FILES)
    assert e.verify_behavioral_manifest(out)["verified"] is True
    (out / "extra.csv").write_text("x\n", encoding="utf-8")
    assert e.verify_behavioral_manifest(out)["extra"] == ["extra.csv"]


def test_cli_rejects_parameter_overrides() -> None:
    from scripts.build_morita_s_behavioral_discipline_atlas_v1 import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--run", "--iv", "0.8"])

