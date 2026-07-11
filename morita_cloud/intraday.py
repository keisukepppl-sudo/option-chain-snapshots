from __future__ import annotations

import math
import time
from typing import Any

import pandas as pd


def _normalize_cutoff(cutoff_et: pd.Timestamp) -> pd.Timestamp:
    cutoff = pd.Timestamp(cutoff_et)
    if cutoff.tzinfo is None:
        return cutoff.tz_localize("America/New_York")
    return cutoff.tz_convert("America/New_York")


def snapshot_from_frame(frame: pd.DataFrame, cutoff_et: pd.Timestamp) -> dict[str, Any] | None:
    if frame is None or frame.empty:
        return None
    required = ["Open", "High", "Low", "Close", "Volume"]
    if any(column not in frame.columns for column in required):
        return None

    cutoff = _normalize_cutoff(cutoff_et)
    data = frame[required].dropna(subset=["Close"]).copy()
    if data.empty:
        return None

    index = pd.to_datetime(data.index)
    if index.tz is None:
        index = index.tz_localize("America/New_York")
    else:
        index = index.tz_convert("America/New_York")
    data.index = index

    # yfinance labels intraday bars by bar start. A bar beginning at the cutoff
    # contains post-cutoff information, so it is deliberately excluded.
    session = data[
        (data.index.date == cutoff.date())
        & (data.index < cutoff)
    ].copy()
    if session.empty:
        return None

    latest = session.iloc[-1]
    volume = session["Volume"].fillna(0).astype(float)
    total_volume = float(volume.sum())
    vwap = (
        float((session["Close"].astype(float) * volume).sum() / total_volume)
        if total_volume > 0
        else math.nan
    )
    market_open = cutoff.normalize() + pd.Timedelta(hours=9, minutes=30)
    market_close = cutoff.normalize() + pd.Timedelta(hours=16)
    elapsed = max(
        0.0,
        min(
            (cutoff - market_open).total_seconds(),
            (market_close - market_open).total_seconds(),
        ),
    )
    session_fraction = max(
        0.05,
        min(1.0, elapsed / (market_close - market_open).total_seconds()),
    )

    latest_ts = pd.Timestamp(session.index[-1])
    return {
        "latest_price": float(latest["Close"]),
        "intraday_open": float(session["Open"].dropna().iloc[0]) if not session["Open"].dropna().empty else math.nan,
        "intraday_high": float(session["High"].max()),
        "intraday_volume": total_volume,
        "intraday_vwap": vwap,
        "latest_price_date": cutoff.date().isoformat(),
        "latest_price_time": latest_ts.isoformat(),
        "session_fraction": session_fraction,
        "decision_cutoff_et": cutoff.isoformat(),
    }


def fetch_intraday_snapshots_at_cutoff(
    tickers: list[str],
    cutoff_et: pd.Timestamp,
    interval: str = "5m",
    chunk_size: int = 80,
) -> dict[str, dict[str, Any]]:
    import yfinance as yf

    snapshots: dict[str, dict[str, Any]] = {}
    unique = sorted(set(str(ticker).upper() for ticker in tickers if ticker))
    for start in range(0, len(unique), chunk_size):
        chunk = unique[start : start + chunk_size]
        print(
            f"Downloading cutoff intraday data {start + 1}-{start + len(chunk)} / {len(unique)} "
            f"cutoff={_normalize_cutoff(cutoff_et).isoformat()}",
            flush=True,
        )
        try:
            raw = yf.download(
                chunk,
                period="5d",
                interval=interval,
                auto_adjust=False,
                progress=False,
                threads=True,
                group_by="ticker",
                timeout=45,
            )
        except Exception as exc:
            print(f"Intraday chunk failed: {exc}", flush=True)
            continue
        if raw is None or raw.empty:
            continue

        for ticker in chunk:
            try:
                frame = raw[ticker].copy() if isinstance(raw.columns, pd.MultiIndex) else raw.copy()
            except Exception:
                continue
            snapshot = snapshot_from_frame(frame, cutoff_et)
            if snapshot is not None:
                snapshots[ticker] = snapshot
        time.sleep(0.1)
    return snapshots
