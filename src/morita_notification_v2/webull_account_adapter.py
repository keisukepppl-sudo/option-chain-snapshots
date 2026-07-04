from __future__ import annotations

from pathlib import Path
from typing import Any

from .notification_state_machine import read_jsonl, utc_now


class ReadOnlyWebullAccountAdapter:
    """Read-only adapter surface. It intentionally has no order-write methods."""

    broker_write_allowed = False

    def __init__(self, positions_path: Path | None = None, orders_path: Path | None = None, fills_path: Path | None = None) -> None:
        self.positions_path = positions_path
        self.orders_path = orders_path
        self.fills_path = fills_path
        self.last_synchronization_timestamp_utc = utc_now()

    def positions(self) -> list[dict[str, Any]]:
        return read_jsonl(self.positions_path) if self.positions_path else []

    def orders(self) -> list[dict[str, Any]]:
        return read_jsonl(self.orders_path) if self.orders_path else []

    def fills(self) -> list[dict[str, Any]]:
        return read_jsonl(self.fills_path) if self.fills_path else []

    def average_entry_price(self, ticker: str) -> float | None:
        matches = [row for row in self.positions() if str(row.get("ticker", "")).upper() == ticker.upper()]
        if not matches:
            return None
        try:
            return float(matches[-1].get("average_entry_price"))
        except Exception:
            return None

    def remaining_quantity(self, ticker: str) -> float | None:
        matches = [row for row in self.positions() if str(row.get("ticker", "")).upper() == ticker.upper()]
        if not matches:
            return None
        try:
            return float(matches[-1].get("remaining_quantity"))
        except Exception:
            return None

    def symbol_mapping(self) -> dict[str, str]:
        return {str(row.get("ticker", "")).upper(): str(row.get("broker_symbol", row.get("ticker", ""))).upper() for row in self.positions()}
