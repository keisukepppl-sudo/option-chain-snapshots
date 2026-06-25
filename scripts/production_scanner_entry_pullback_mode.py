from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import pandas as pd

import scripts.production_scanner_entry as entry
import scripts.production_scanner_entry_0430 as runner

ALL_RANKS = ["S", "A", "B", "C"]
WAKE_RANKS = ["S"]


def _safe_float(value: Any, default: float = math.nan) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _visible(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return candidates
    return candidates[(candidates["exclusion_reason"].fillna("") == "") & candidates["alert_rank"].isin(ALL_RANKS)].copy()


def _rank_counts_all(candidates: pd.DataFrame) -> dict[str, int]:
    counts = {rank: 0 for rank in ALL_RANKS}
    if candidates.empty or "alert_rank" not in candidates.columns:
        return counts
    frame = candidates.copy()
    if "exclusion_reason" in frame.columns:
        frame = frame[frame["exclusion_reason"].fillna("") == ""]
    values = frame["alert_rank"].value_counts(dropna=False).to_dict()
    for rank in ALL_RANKS:
        counts[rank] = int(values.get(rank, 0))
    return counts


def _format_rank_counts_all(counts: dict[str, int]) -> str:
    return " ".join(f"{rank}={int(counts.get(rank, 0))}" for rank in ALL_RANKS)


def _is_priority_pullback(row: pd.Series | dict[str, Any]) -> bool:
    return str(row.get("alert_rank", "")) in {"A", "B"} and _safe_float(row.get("accumulation_score"), -999.0) >= 50


def _candidate_block(row: pd.Series) -> str:
    rank = str(row.get("alert_rank", ""))
    price = _safe_float(row.get("latest_price", row.get("close")), math.nan)
    accum = _safe_float(row.get("accumulation_score"), math.nan)
    accum_text = f"{accum:.1f}" if pd.notna(accum) else "N/A"
    if rank == "S":
        header = f"[S BREAKOUT MOMENTUM] {row.get('ticker')} - {row.get('company_name') or 'N/A'}"
        action = "WAKE_AND_CHECK_BREAKOUT_CALL"
        rule = "S -> check breakout-day Delta0.6/90DTE single call"
    elif rank in {"A", "B"}:
        header = f"[{rank} PULLBACK WATCHLIST] {row.get('ticker')} - {row.get('company_name') or 'N/A'}"
        action = "PULLBACK_WATCHLIST_NO_WAKE"
        rule = "A/B -> wait for low-volume pullback, close > 20EMA, green/prior-high rebound"
    else:
        header = f"[{rank} RESEARCH] {row.get('ticker')} - {row.get('company_name') or 'N/A'}"
        action = "DISCORD_ONLY"
        rule = "Research only"
    return (
        f"{header}\n"
        f"production_adjusted_score: {float(row.get('production_adjusted_score', 0)):.1f} / rank {rank}\n"
        f"RS: {float(row.get('standard_rs_score', 0)):.1f} / accumulation_score: {accum_text} / pullback_priority: {'YES' if _is_priority_pullback(row) else 'NO'}\n"
        f"gap: {entry.sn.format_pct(row.get('gap_pct'))} / volume: {float(row.get('volume_multiple', 0)):.2f}x / price: {price:.2f}\n"
        f"sector: {row.get('sector_proxy', 'N/A')} / theme: {row.get('theme', 'N/A')}\n"
        f"option_liquidity_warning: {row.get('option_liquidity_warning', '') or 'None'}\n"
        f"action: {action}\n"
        f"rule: {rule}\n"
        f"scan_time_jst: {pd.Timestamp.now(tz='Asia/Tokyo').isoformat()}\n"
        "--------------------------------"
    )


def _build_message(candidates: pd.DataFrame, csv_path: Path, schedule_utc: str, limit: int = 10) -> str:
    visible = _visible(candidates)
    if visible.empty:
        return "No signals today"
    title = {
        "30 13 * * 1-5": "22:30 JST Breakout / Pullback Watchlist Check",
        "0 14 * * 1-5": "23:00 JST Breakout / Pullback Watchlist Check",
        "30 19 * * 0-4": "04:30 JST S-Rank Breakout Emergency Check",
        "30 19 * * 1-5": "04:30 JST S-Rank Breakout Emergency Check",
        "15 1 * * 1-5": "10:15 JST Scanner Status / Watchlist Check",
        "0 1 * * 1-5": "10:00 JST Scanner Status / Watchlist Check",
    }.get(schedule_utc, "Production Momentum Alert")
    sections = [
        title,
        "S = wake/check breakout call. A/B = no-wake pullback watchlist; wait for low-volume pullback, close > 20EMA, rebound confirmation.",
    ]
    shown = 0
    s_group = visible[visible["alert_rank"] == "S"].head(limit)
    if not s_group.empty:
        sections.append("S Breakout Momentum Candidates")
        for _, row in s_group.iterrows():
            sections.append(_candidate_block(row))
            shown += 1
    remaining = max(0, limit - shown)
    ab_group = visible[visible["alert_rank"].isin(["A", "B"])].head(remaining)
    if not ab_group.empty:
        sections.append("A/B Pullback Watchlist Candidates")
        for _, row in ab_group.iterrows():
            sections.append(_candidate_block(row))
            shown += 1
    sections.append("A/B Entry: low-volume pullback + close > 20EMA + green/prior-high rebound.")
    sections.append("A/B Suggested option after trigger: Delta0.6 / 90DTE single call; research exit TP +200-300%, SL -60%, max hold 30.")
    sections.append(f"CSV: `{csv_path}`")
    return "\n\n".join(sections)


def _save_candidates(candidates: pd.DataFrame, outdir: Path) -> Path:
    path = runner.REAL_SAVE_CANDIDATES(candidates, outdir)
    token = entry._scan_time_token()
    outdir.mkdir(parents=True, exist_ok=True)
    visible = _visible(candidates)
    visible[visible["alert_rank"] == "S"].to_csv(outdir / f"breakout_momentum_{token}.csv", index=False)
    visible[visible["alert_rank"].isin(["A", "B"])].to_csv(outdir / f"pullback_watchlist_{token}.csv", index=False)
    pd.DataFrame(columns=list(candidates.columns) + ["rebound_confirmation_type", "close_vs_20ema_pct", "pullback_volume_ratio"]).to_csv(outdir / f"pullback_entry_signals_{token}.csv", index=False)
    visible[~visible["alert_rank"].isin(["S", "A", "B"])].to_csv(outdir / f"pullback_rejected_{token}.csv", index=False)
    counts = _rank_counts_all(candidates)
    runner.SCAN_CONTEXT.update({
        "candidates_total": int(len(candidates)),
        "notifiable_candidates": int(counts.get("S", 0)),
        "rank_counts": counts,
        "csv_path": path,
    })
    print(f"candidates count: {len(candidates)}", flush=True)
    print(f"S wake candidates count: {counts.get('S', 0)}", flush=True)
    print(f"A/B pullback watchlist candidates count: {counts.get('A', 0) + counts.get('B', 0)}", flush=True)
    print(f"rank counts: {_format_rank_counts_all(counts)}", flush=True)
    return path


def _select_s_only_pushover_candidates(candidates: pd.DataFrame, schedule_utc: str, config: dict[str, Any]) -> pd.DataFrame:
    if schedule_utc not in runner.PRE_CLOSE_CRONS or candidates.empty:
        print("Pushover skipped: not pre-close schedule or no scanner candidates", flush=True)
        return candidates.iloc[0:0].copy()
    base = candidates[(candidates["exclusion_reason"].fillna("") == "") & (candidates["alert_rank"] == "S")].copy()
    if base.empty:
        print("Pushover skipped: no S-rank breakout emergency candidates", flush=True)
    state_path = entry._state_path(Path("scanner_alerts") / entry.sn.today_str() / "russell1000_momentum_candidates.csv")
    state = entry._load_state(state_path)
    sendable = pd.DataFrame([row for _, row in base.iterrows() if entry._needs_emergency(row, state)])
    entry.EMERGENCY_CONTEXT.clear()
    entry.EMERGENCY_CONTEXT.update({"state_path": state_path, "state": state, "candidates": sendable})
    return sendable


def _build_s_only_pushover_message(candidates: pd.DataFrame, csv_path: Path, limit: int = 8) -> str:
    lines = [
        "04:30 S-Rank Breakout Emergency",
        f"scan_time_jst={pd.Timestamp.now(tz='Asia/Tokyo').isoformat()}",
        "Only S rank wakes. A/B candidates are saved to pullback watchlist.",
        "Review: Delta0.6 / 90DTE single call only after chart, market, earnings, and option liquidity pass.",
    ]
    for _, row in candidates.head(limit).iterrows():
        lines.append(
            f"S | {row.get('ticker')} {row.get('company_name') or ''} | "
            f"Price {float(row.get('latest_price', row.get('close', 0))):.2f} | "
            f"RS {float(row.get('standard_rs_score', 0)):.1f} | Vol {float(row.get('volume_multiple', 0)):.2f}x | "
            f"Score {float(row.get('production_adjusted_score', 0)):.1f} | "
            f"Theme {row.get('theme', 'N/A')} | IV {entry.sn.format_pct(row.get('option_iv'))} | Warnings {row.get('danger_flags', 'None')}"
        )
    lines.append(f"CSV: {csv_path}")
    return "\n".join(lines)


def _completion_message(status: str = "SUCCESS") -> str:
    counts = runner.SCAN_CONTEXT.get("rank_counts") or {rank: 0 for rank in ALL_RANKS}
    schedule_utc = str(runner.SCAN_CONTEXT.get("schedule_utc", ""))
    scheduled_scan_jst = runner._scheduled_scan_jst(schedule_utc)
    s_count = int(counts.get("S", 0))
    ab_count = int(counts.get("A", 0)) + int(counts.get("B", 0))
    today_line = "No S wake candidates found." if s_count == 0 else "S wake candidates found. Check Pushover/Discord."
    return (
        "Russell1000 Scanner\n\n"
        f"{scheduled_scan_jst} JST Scan Complete\n\n"
        f"scheduled_scan_jst: {scheduled_scan_jst}\n"
        f"actual_run_time_jst: {runner._scan_time_text()}\n"
        f"SCANNER_SCHEDULE_UTC: {schedule_utc}\n"
        "notification_sent: YES\n\n"
        f"S Wake Candidates:\n{s_count}\n\n"
        f"A/B Pullback Watchlist Candidates:\n{ab_count}\n\n"
        "Rank Count:\n"
        f"{_format_rank_counts_all(counts)}\n\n"
        f"Today:\n{today_line}\n\n"
        f"Scanner Status:\n{status}\n\n"
        "Market Status:\nscanned successfully"
    )


def apply_patch() -> None:
    runner.EMERGENCY_RANKS = WAKE_RANKS
    runner.EMERGENCY_RANK_SET = set(WAKE_RANKS)
    runner._select_sabcd_pushover_candidates = _select_s_only_pushover_candidates
    runner._completion_message = _completion_message
    entry.sn.build_message = _build_message
    entry.sn.candidate_block = _candidate_block
    entry.sn.save_candidates = _save_candidates
    entry.sn.select_pushover_candidates = _select_s_only_pushover_candidates
    entry.sn.build_pushover_message = _build_s_only_pushover_message


def main() -> None:
    apply_patch()
    runner.main()


if __name__ == "__main__":
    main()
