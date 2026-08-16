from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


NOTIFICATION_COOLDOWN_TRADING_SESSIONS = 20


def prior_trading_session_dates(
    current_date_et: str,
    cooldown_sessions: int = NOTIFICATION_COOLDOWN_TRADING_SESSIONS,
) -> list[str]:
    """Return prior NYSE sessions that are still inside the notification cooldown.

    A 20-session cooldown means a notification on D0 suppresses the same ticker
    through D19; it becomes eligible again on D20. The current session is handled
    separately by the caller, so only the previous 19 sessions are returned.
    """
    if cooldown_sessions <= 1:
        return []

    import pandas_market_calendars as mcal

    current = pd.Timestamp(current_date_et).normalize()
    # 3x calendar-day lookback comfortably covers weekends/holidays for normal
    # U.S. market calendars while keeping this helper deterministic and cheap.
    lookback_days = max(45, cooldown_sessions * 3)
    calendar = mcal.get_calendar("NYSE")
    schedule = calendar.schedule(
        start_date=(current - pd.Timedelta(days=lookback_days)).date().isoformat(),
        end_date=current.date().isoformat(),
    )
    session_dates = [pd.Timestamp(idx).date().isoformat() for idx in schedule.index]
    prior = [date for date in session_dates if date < current.date().isoformat()]
    return prior[-(cooldown_sessions - 1) :]


def _notification_sent(notification: Any) -> bool:
    return isinstance(notification, dict) and str(notification.get("status", "")).upper() == "SENT"


def _pushover_sent(status: Any) -> bool:
    if status is None:
        return False
    text = str(status).strip().upper()
    return text in {"200", "201", "SENT", "OK", "SUCCESS", "TRUE"}


def successful_notified_tickers(state: dict[str, Any]) -> set[str]:
    """Extract tickers that were actually sent successfully from one day state.

    Supports both the Cloud Run state schema and the legacy ET-slot fallback
    schema. Dry-run/shadow records do not consume the cooldown.
    """
    sent: set[str] = set()

    for slot in (state.get("slots", {}) or {}).values():
        if not isinstance(slot, dict):
            continue
        cloud_sent = _notification_sent(slot.get("notification"))
        legacy_sent = _pushover_sent(slot.get("pushover_status"))
        if not (cloud_sent or legacy_sent):
            continue

        if "notified_s_tickers" in slot or "notified_a_tickers" in slot:
            tickers = list(slot.get("notified_s_tickers", []) or []) + list(slot.get("notified_a_tickers", []) or [])
        else:
            # Backward compatibility: before cooldown support, every stored S/A
            # ticker in a successful checkpoint notification was actually sent.
            tickers = list(slot.get("s_tickers", []) or []) + list(slot.get("a_tickers", []) or [])
        sent.update(str(ticker) for ticker in tickers if str(ticker))

    for key in ("late_s_emergency_sent", "late_emergency_sent"):
        for ticker, record in (state.get(key, {}) or {}).items():
            if not isinstance(record, dict):
                continue
            if _notification_sent(record.get("notification")) or _pushover_sent(record.get("pushover_status")):
                sent.add(str(ticker))

    return sent


def filter_recently_notified(
    candidates: pd.DataFrame,
    blocked_tickers: set[str] | list[str] | tuple[str, ...],
) -> pd.DataFrame:
    """Filter only the user-facing notification population; raw candidates stay intact."""
    if candidates.empty or "ticker" not in candidates.columns:
        return candidates.copy()
    blocked = {str(ticker) for ticker in blocked_tickers}
    if not blocked:
        return candidates.copy()
    tickers = candidates["ticker"].astype(str)
    return candidates[~tickers.isin(blocked)].copy()


def recently_notified_tickers_gcs(
    store: Any,
    current_date_et: str,
    mode: str,
    current_state: dict[str, Any],
    cooldown_sessions: int = NOTIFICATION_COOLDOWN_TRADING_SESSIONS,
) -> set[str]:
    """Collect successful ticker notifications from D0 through D19 in GCS state."""
    blocked = successful_notified_tickers(current_state)
    for date_et in prior_trading_session_dates(current_date_et, cooldown_sessions):
        state, _ = store.read_json(f"state/{mode}/{date_et}.json", {})
        blocked.update(successful_notified_tickers(state))
    return blocked


def recently_notified_tickers_files(
    state_dir: Path,
    current_date_et: str,
    current_state: dict[str, Any],
    cooldown_sessions: int = NOTIFICATION_COOLDOWN_TRADING_SESSIONS,
) -> set[str]:
    """Collect successful ticker notifications from cached ET-slot state files."""
    blocked = successful_notified_tickers(current_state)
    for date_et in prior_trading_session_dates(current_date_et, cooldown_sessions):
        path = Path(state_dir) / f"morita_notification_state_{date_et}.json"
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict):
            blocked.update(successful_notified_tickers(raw))
    return blocked
