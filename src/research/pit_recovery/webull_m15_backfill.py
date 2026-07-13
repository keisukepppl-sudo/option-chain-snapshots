from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import pandas as pd


SCHEMA = [
    "ticker",
    "timestamp_et",
    "timestamp_utc",
    "session_date",
    "bar_interval",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap_if_available",
    "trade_count_if_available",
    "source_name",
    "source_sdk_version",
    "requested_start_utc",
    "requested_end_utc",
    "retrieved_at_utc",
    "adjustment_mode",
    "quality_flag",
]


def event_window_inventory(authoritative_calendar: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for signal in authoritative_calendar:
        ticker = str(signal.get("ticker", "")).upper()
        signal_date = str(signal.get("decision_date", ""))
        rank = str(signal.get("rank", "")).upper()
        if not ticker or not signal_date or rank not in {"S", "A", "B"}:
            continue
        rows.append(
            {
                "signal_id": stable_id(ticker, signal_date, rank),
                "rank": rank,
                "signal_ticker": ticker,
                "signal_date": signal_date,
                "symbols_required": f"SOXX|QQQ|{ticker}",
                "window_start": offset_date(signal_date, -14),
                "window_end": offset_date(signal_date, 14),
                "status": "PENDING_WEBULL_M15_CAPABILITY",
                "checkpoint_key": stable_id(ticker, signal_date, "M15"),
            }
        )
    if not rows:
        rows.append(
            {
                "signal_id": "",
                "rank": "",
                "signal_ticker": "",
                "signal_date": "",
                "symbols_required": "",
                "window_start": "",
                "window_end": "",
                "status": "BLOCKED_NO_AUTHORITATIVE_SIGNAL_CALENDAR",
                "checkpoint_key": "",
            }
        )
    return rows


def quality_audit_from_inventory(inventory: list[dict[str, Any]], webull_status: str) -> list[dict[str, Any]]:
    return [
        {
            "signal_id": row.get("signal_id", ""),
            "status": "NOT_RUN" if row.get("signal_id") else "BLOCKED",
            "quality_flag": "UNADJUSTED_MINUTE_BARS",
            "missing_bars_filled": False,
            "synthetic_intraday_data_used": False,
            "blocker": "" if webull_status == "WEBULL_M15_2022_2025_SUPPORTED" and row.get("signal_id") else "WEBULL_OR_SIGNAL_AUTHORITY_BLOCKED",
        }
        for row in inventory
    ]


def empty_authoritative_signal_m15_dataset() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "quality": "BLOCKED_NO_AUTHORITATIVE_SIGNAL_OR_M15",
                "outcome_label_used_as_entry_feature": False,
                "adjustment_mode": "UNADJUSTED_MINUTE_BARS",
            }
        ]
    )


def join_audit(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "signal_id": row.get("signal_id", ""),
            "join_name": "authoritative_signal_to_m15_event_window",
            "PIT_pass": False,
            "outcome_label_used_as_entry_feature": False,
            "unavailable_reason": row.get("status", "WEBULL_OR_SIGNAL_AUTHORITY_BLOCKED"),
        }
        for row in inventory
    ]


def stable_id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def offset_date(value: str, days: int) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return ""
    return (ts + pd.Timedelta(days=days)).strftime("%Y-%m-%d")


def retrieved_at_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
