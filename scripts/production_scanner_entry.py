from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import pandas as pd

import scanner_notify as sn
from scanner.catalyst_routing import catalyst_route_for


PRE_CLOSE_SCAN_SCHEDULES = {
    "15 19 * * 1-5",
    "25 19 * * 1-5",
    "35 19 * * 1-5",
    "30 19 * * 1-5",
}
FORBIDDEN_NOTIFICATION_PATTERNS = (
    "day10",
    "day20",
    "future",
    "realized",
    "exit_pnl",
    "trade_max_drawdown",
    "exit_reason",
    "forward",
    "follow",
)
REAL_SEND_PUSHOVER_EMERGENCY = sn.send_pushover_emergency
EMERGENCY_CONTEXT: dict[str, Any] = {}


def _safe_float(value: Any, default: float = math.nan) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def forbidden_columns_detected(row: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for col in row:
        lowered = str(col).lower()
        if any(pattern in lowered for pattern in FORBIDDEN_NOTIFICATION_PATTERNS):
            out.append(str(col))
    return sorted(set(out))


def _production_live_score(row: dict[str, Any]) -> float:
    forbidden = [c for c in forbidden_columns_detected(row) if c != "day10_subscore"]
    conviction = _safe_float(row.get("conviction_score"), math.nan)
    day10_subscore = _safe_float(row.get("day10_subscore"), 0.0)
    if pd.notna(conviction) and not forbidden:
        return max(0.0, conviction - day10_subscore)

    rs = _safe_float(row.get("standard_rs_score", row.get("rs")), 0.0)
    volume = _safe_float(row.get("volume_multiple"), 0.0)
    price = _safe_float(row.get("latest_price", row.get("close")), math.nan)
    prior_high = _safe_float(row.get("prior_20d_high"), math.nan)
    accumulation = _safe_float(row.get("accumulation_score"), math.nan)
    theme = str(row.get("theme", ""))
    sector = str(row.get("sector_proxy", row.get("source_sector", "")))
    bucket = str(row.get("market_cap_bucket", "Unknown"))

    score = 0.0
    if rs >= 99.5:
        score += 25
    elif rs >= 99:
        score += 22
    elif rs >= 98:
        score += 20
    else:
        score += max(0.0, min(20.0, (rs - 90.0) / 8.0 * 20.0))

    if volume >= 3.0:
        score += 15
    elif volume >= 2.0:
        score += 13
    elif volume >= 1.5:
        score += 10
    elif volume >= 1.2:
        score += 7

    if pd.notna(price) and pd.notna(prior_high) and prior_high > 0 and price > prior_high:
        excess = price / prior_high - 1.0
        if excess >= 0.10:
            score += 15
        elif excess >= 0.05:
            score += 12
        elif excess >= 0.02:
            score += 9
        else:
            score += 7

    score += 5 if pd.isna(accumulation) else max(0.0, min(10.0, accumulation / 100.0 * 10.0))
    if theme in {"Semiconductor", "AI Infrastructure", "Space", "Cloud Software"}:
        score += 5
    elif "Technology" in sector or "Software" in sector:
        score += 3
    else:
        score += 2

    if bucket in {"50B-200B", "200B+"}:
        score += 5
    elif bucket in {"20B-50B", "2B-20B"}:
        score += 3
    elif bucket == "<2B":
        score += 1
    return max(0.0, score)


def _rank(score: float) -> str:
    if score >= 50:
        return "S"
    if score >= 40:
        return "A"
    if score >= 30:
        return "B"
    if score >= 25:
        return "C"
    return "D"


def _size(rank: str) -> str:
    return {"S": "60%", "A": "50%", "B": "40%", "C": "30%", "D": "no trade"}.get(rank, "no trade")


def _is_healthcare_or_biotech(row: dict[str, Any]) -> bool:
    theme = str(row.get("theme", ""))
    sector = str(row.get("sector_proxy", row.get("source_sector", "")))
    return theme in {"Biotech", "Healthcare"} or sector in {"Biotech", "Healthcare", "Health Care"}


def _exclusion_reason(row: dict[str, Any]) -> str:
    if _is_healthcare_or_biotech(row):
        return "excluded_biotech_healthcare"
    gap = _safe_float(row.get("gap_pct"), math.nan)
    if pd.notna(gap) and gap >= 0.10:
        return "excluded_gap_ge_10"
    price = _safe_float(row.get("latest_price", row.get("close")), math.nan)
    if pd.notna(price) and price < 5:
        return "excluded_price_lt_5"
    if _safe_float(row.get("production_adjusted_score"), 0) < 25:
        return "excluded_production_adjusted_score_lt_25"
    return ""


def _catalyst_routing_config() -> dict[str, Any]:
    path = Path(os.environ.get("SCANNER_CONFIG_PATH", "config.yaml"))
    try:
        config = sn.load_config(path)
        routing = sn.production_config(config).get("catalyst_routing", {}) or {}
        return dict(routing) if isinstance(routing, dict) else {}
    except Exception:
        return {}


def _not_evaluated_catalyst(reason: str) -> dict[str, Any]:
    return {
        "catalyst_type": "NOT_EVALUATED",
        "catalyst_confidence": "not_evaluated",
        "catalyst_source": "",
        "catalyst_headline": "",
        "catalyst_timestamp_utc": "",
        "catalyst_url": "",
        "catalyst_fetch_status": reason,
        "action_route": "DISCORD_ONLY",
        "action_reason": reason,
    }


def _scan_time_token() -> str:
    return pd.Timestamp.now(tz="Asia/Tokyo").strftime("%Y%m%d_%H%M")


def _state_path(csv_path: Path) -> Path:
    day = pd.Timestamp.now(tz="Asia/Tokyo").strftime("%Y%m%d")
    return csv_path.parent / f"notification_sent_state_{day}.json"


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"sent": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"sent": {}}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _rank_value(rank: str) -> int:
    return {"S": 4, "A": 3, "B": 2, "C": 1, "D": 0}.get(str(rank), 0)


def _needs_emergency(row: pd.Series, state: dict[str, Any]) -> bool:
    ticker = str(row.get("ticker", ""))
    existing = state.get("sent", {}).get(ticker)
    if not existing:
        return True
    if not existing.get("emergency_sent") or str(existing.get("pushover_response_status", "")).startswith("ERROR"):
        return True
    if _rank_value(str(row.get("alert_rank"))) > _rank_value(str(existing.get("rank"))):
        return True
    old_score = _safe_float(existing.get("production_adjusted_score"), -999)
    new_score = _safe_float(row.get("production_adjusted_score"), -999)
    return new_score >= old_score + 5


def _record_emergency(candidates: pd.DataFrame, status: Any, sent: bool) -> None:
    path = EMERGENCY_CONTEXT.get("state_path")
    state = EMERGENCY_CONTEXT.get("state")
    if not path or not state:
        return
    sent_map = state.setdefault("sent", {})
    for _, row in candidates.iterrows():
        ticker = str(row.get("ticker", ""))
        sent_map[ticker] = {
            "ticker": ticker,
            "rank": row.get("alert_rank"),
            "production_adjusted_score": _safe_float(row.get("production_adjusted_score"), 0.0),
            "scan_time_jst": pd.Timestamp.now(tz="Asia/Tokyo").isoformat(),
            "pushover_priority": 2,
            "emergency_sent": bool(sent),
            "pushover_response_status": status,
        }
    _save_state(path, state)


def _visible(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return candidates
    return candidates[(candidates["exclusion_reason"].fillna("") == "") & candidates["alert_rank"].isin(["S", "A", "B", "C"])].copy()


def _patched_select_candidates(*args: Any, **kwargs: Any) -> pd.DataFrame:
    out = ORIGINAL_SELECT_CANDIDATES(*args, **kwargs)
    if out.empty:
        return out
    routing_config = _catalyst_routing_config()
    rows = []
    for _, original in out.iterrows():
        row = original.to_dict()
        live = _production_live_score(row)
        penalty = -5.0 if _safe_float(row.get("volume_multiple"), 0) < 1.5 else 0.0
        adjusted = max(0.0, live + penalty)
        rank = _rank(adjusted)
        row["production_live_score"] = live
        row["production_adjusted_score"] = adjusted
        row["live_score"] = live
        row["adjusted_score"] = adjusted
        row["volume_penalty"] = penalty
        row["alert_rank"] = rank
        row["production_rank"] = rank
        row["raw_suggested_size"] = _size(rank)
        row["conviction_tier"] = f"{rank} Tier"
        row["exclusion_reason"] = _exclusion_reason(row)
        row["option_liquidity_warning"] = "" if bool(row.get("option_liquidity_ok", False)) else str(row.get("option_liquidity_reason", "Option liquidity warning"))

        if row["exclusion_reason"] == "" and rank in {"S", "A", "B"}:
            row.update(catalyst_route_for(str(row.get("ticker", "")), routing_config))
        else:
            reason = row["exclusion_reason"] or f"rank_{rank}_not_actionable"
            row.update(_not_evaluated_catalyst(reason))

        row["suggested_size"] = (
            "WATCH_ONLY"
            if row.get("action_route") == "NEWS_SPIKE_WATCH_ONLY"
            else row["raw_suggested_size"]
        )
        rows.append(row)
    scored = pd.DataFrame(rows)
    order = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
    scored["rank_order"] = scored["alert_rank"].map(order).fillna(99)
    return scored.sort_values(["rank_order", "production_adjusted_score"], ascending=[True, False]).drop(columns=["rank_order"])


def _patched_save_candidates(candidates: pd.DataFrame, outdir: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    legacy = ORIGINAL_SAVE_CANDIDATES(candidates, outdir)
    token = _scan_time_token()
    daily = outdir / f"daily_scan_log_{token}.csv"
    notified = outdir / f"notified_candidates_{token}.csv"
    excluded = outdir / f"excluded_candidates_{token}.csv"
    candidates.to_csv(daily, index=False)
    _visible(candidates).to_csv(notified, index=False)
    if candidates.empty:
        candidates.to_csv(excluded, index=False)
    else:
        candidates[(candidates["exclusion_reason"].fillna("") != "") | (candidates["alert_rank"] == "D")].to_csv(excluded, index=False)
    return legacy


def _patched_schedule_kind(schedule_utc: str) -> str:
    if schedule_utc == "30 13 * * 1-5":
        return "intraday_2230"
    if schedule_utc == "0 14 * * 1-5":
        return "intraday_2300"
    if schedule_utc in PRE_CLOSE_SCAN_SCHEDULES:
        return "pre_close_0430"
    return ORIGINAL_SCHEDULE_KIND(schedule_utc)


def _patched_candidate_block(row: pd.Series) -> str:
    price = row.get("latest_price", row.get("close", math.nan))
    action = row.get("action_route") or (
        "WAKE_AND_CHECK" if row.get("alert_rank") in {"S", "A", "B"} else "DISCORD_ONLY"
    )
    headline = str(row.get("catalyst_headline", "") or "")
    catalyst_line = (
        f"catalyst: {row.get('catalyst_type', 'UNKNOWN')} / "
        f"confidence: {row.get('catalyst_confidence', 'unknown')} / "
        f"source: {row.get('catalyst_source', '') or 'N/A'}\n"
    )
    headline_line = f"catalyst_headline: {headline}\n" if headline else ""
    return (
        f"[{row.get('alert_rank')} BREAKOUT] {row.get('ticker')} - {row.get('company_name') or 'N/A'}\n"
        f"production_live_score: {float(row.get('production_live_score', 0)):.1f} / "
        f"production_adjusted_score: {float(row.get('production_adjusted_score', 0)):.1f} / rank {row.get('alert_rank')}\n"
        f"volume penalty: {float(row.get('volume_penalty', 0)):.0f} / suggested size: {row.get('suggested_size', 'N/A')} "
        f"(raw: {row.get('raw_suggested_size', 'N/A')})\n"
        f"gap: {sn.format_pct(row.get('gap_pct'))} / volume: {float(row.get('volume_multiple', 0)):.2f}x / price: {float(price):.2f}\n"
        f"sector: {row.get('sector_proxy', 'N/A')} / theme: {row.get('theme', 'N/A')}\n"
        f"{catalyst_line}"
        f"{headline_line}"
        f"option_liquidity_warning: {row.get('option_liquidity_warning', '') or 'None'}\n"
        f"exclusion_reason: {row.get('exclusion_reason', '') or 'None'}\n"
        f"action: {action} / reason: {row.get('action_reason', '') or 'None'}\n"
        f"scan_time_jst: {pd.Timestamp.now(tz='Asia/Tokyo').isoformat()}\n"
        "--------------------------------"
    )


def _patched_build_message(candidates: pd.DataFrame, csv_path: Path, schedule_utc: str, limit: int = 10) -> str:
    visible = _visible(candidates)
    if visible.empty:
        return "No signals today"
    title = {
        "intraday_2230": "22:30 JST Breakout Check",
        "intraday_2300": "23:00 JST Breakout Check",
        "pre_close_0430": "04:30 JST Pre-Close Breakout Check",
    }.get(_patched_schedule_kind(schedule_utc), "Production Momentum Alert")
    sections = [
        title,
        "RS98 + 20-day breakout + volume pace. Candidate discovery only.",
        "NEWS_SPIKE_WATCH_ONLY = contract/partnership/customer-win/order headline; no immediate call entry.",
    ]
    shown = 0
    for rank in ["S", "A", "B", "C"]:
        group = visible[visible["alert_rank"] == rank].head(max(0, limit - shown))
        if group.empty:
            continue
        sections.append(f"{rank} Tier")
        for _, row in group.iterrows():
            sections.append(_patched_candidate_block(row))
            shown += 1
        if shown >= limit:
            break
    sections.append("Exit: Day10 underlying +5% not reached -> exit / +125% take profit or Day20")
    sections.append(f"CSV: `{csv_path}`")
    return "\n\n".join(sections)


def _patched_select_pushover_candidates(candidates: pd.DataFrame, schedule_utc: str, config: dict[str, Any]) -> pd.DataFrame:
    if schedule_utc not in PRE_CLOSE_SCAN_SCHEDULES or candidates.empty:
        return candidates.iloc[0:0].copy()

    routing = sn.production_config(config).get("catalyst_routing", {}) or {}
    routes = candidates.get(
        "action_route",
        pd.Series("STANDARD_BREAKOUT_REVIEW", index=candidates.index, dtype="object"),
    )
    base = candidates[
        (candidates["exclusion_reason"].fillna("") == "")
        & candidates["alert_rank"].isin(["S", "A", "B"])
        & (
            (routes != "NEWS_SPIKE_WATCH_ONLY")
            | (not bool(routing.get("suppress_pushover_emergency", True)))
        )
    ].copy()
    state_path = _state_path(Path("scanner_alerts") / sn.today_str() / "russell1000_momentum_candidates.csv")
    state = _load_state(state_path)
    sendable = pd.DataFrame([row for _, row in base.iterrows() if _needs_emergency(row, state)])
    EMERGENCY_CONTEXT.clear()
    EMERGENCY_CONTEXT.update({"state_path": state_path, "state": state, "candidates": sendable})
    return sendable


def _patched_build_pushover_message(candidates: pd.DataFrame, csv_path: Path, limit: int = 8) -> str:
    lines = [
        "04:30 Breakout Emergency",
        f"scan_time_jst={pd.Timestamp.now(tz='Asia/Tokyo').isoformat()}",
        "Exit: Day10 underlying +5% not reached -> exit / +125% take profit or Day20",
    ]
    for _, row in candidates.head(limit).iterrows():
        lines.append(
            f"{row.get('alert_rank')} | {row.get('ticker')} {row.get('company_name') or ''} | "
            f"Price {float(row.get('latest_price', row.get('close', 0))):.2f} | "
            f"RS {float(row.get('standard_rs_score', 0)):.1f} | Vol {float(row.get('volume_multiple', 0)):.2f}x | "
            f"Score {float(row.get('production_adjusted_score', 0)):.1f} | Size {row.get('suggested_size', 'N/A')} | "
            f"Catalyst {row.get('catalyst_type', 'UNKNOWN')} ({row.get('catalyst_confidence', 'unknown')}) | "
            f"Sector {row.get('sector_proxy', 'N/A')} | Theme {row.get('theme', 'N/A')} | "
            f"Gap {sn.format_pct(row.get('gap_pct'))} | IV {sn.format_pct(row.get('option_iv'))} | "
            f"Warnings {row.get('danger_flags', 'None')}"
        )
    lines.append(f"CSV: {csv_path}")
    return "\n".join(lines)


def _patched_send_pushover_emergency(message: str, title: str = "04:30 Breakout Alert", **kwargs: Any) -> dict[str, Any]:
    candidates = EMERGENCY_CONTEXT.get("candidates", pd.DataFrame())
    try:
        result = REAL_SEND_PUSHOVER_EMERGENCY(message, title=title, **kwargs)
        _record_emergency(candidates, result.get("status_code"), True)
        return result
    except Exception as exc:
        _record_emergency(candidates, f"ERROR: {exc}", False)
        raise


ORIGINAL_SELECT_CANDIDATES = sn.select_candidates
ORIGINAL_SAVE_CANDIDATES = sn.save_candidates
ORIGINAL_SCHEDULE_KIND = sn.schedule_kind

sn.PUSHOVER_EMERGENCY_SCHEDULE = "30 19 * * 1-5"
sn.schedule_kind = _patched_schedule_kind
sn.select_candidates = _patched_select_candidates
sn.save_candidates = _patched_save_candidates
sn.candidate_block = _patched_candidate_block
sn.build_message = _patched_build_message
sn.select_pushover_candidates = _patched_select_pushover_candidates
sn.build_pushover_message = _patched_build_pushover_message
sn.send_pushover_emergency = _patched_send_pushover_emergency


def main() -> None:
    schedule = os.environ.get("SCANNER_SCHEDULE_UTC", "")
    if schedule in {"15 19 * * 1-5", "25 19 * * 1-5", "35 19 * * 1-5"}:
        os.environ["SCANNER_SCHEDULE_UTC"] = "30 19 * * 1-5"
    sn.main()


if __name__ == "__main__":
    main()
