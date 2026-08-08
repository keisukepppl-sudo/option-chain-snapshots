#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import time
import warnings
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from discord_alert import send_discord_alert
from scanner.pipeline import scan_universe
from scanner.pushover_notify import pushover_enabled, send_pushover_emergency
from scanner.utils import DEFAULT_THRESHOLDS, Thresholds


BENCHMARK = "QQQ"
BLACKROCK_IWB_PORTFOLIO_ID = "239707"
CHUNK_SIZE = 80
INTRADAY_DIGEST_SCHEDULES = {
    "30 14 * * 1-5",
    "30 15 * * 1-5",
    "30 16 * * 1-5",
    "30 17 * * 1-5",
    "30 18 * * 1-5",
    "30 19 * * 1-5",
}
PUSHOVER_EMERGENCY_SCHEDULE = "30 19 * * 1-5"  # 04:30 JST only.
POST_MARKET_REVIEW_SCHEDULE = "0 2 * * 1-5"
POST_CLOSE_SCHEDULE = "0 22 * * 1-5"

YFINANCE_SYMBOL_MAP = {
    "BRKB": "BRK-B",
    "BFA": "BF-A",
    "BFB": "BF-B",
    "HEIA": "HEI-A",
    "LENB": "LEN-B",
    "MOGA": "MOG-A",
    "UHALB": "UHAL-B",
}

SEMICONDUCTOR_TICKERS = {
    "NVDA", "AMD", "AVGO", "ARM", "AMAT", "LRCX", "KLAC", "ASML", "TSM", "QCOM", "MRVL", "MCHP",
    "ON", "LSCC", "ENTG", "TER", "COHR", "ALAB", "ACMR", "AEHR", "SMTC", "MPWR", "MU", "WDC", "STX",
}
AI_INFRA_TICKERS = {"NVDA", "AMD", "AVGO", "SMCI", "DELL", "HPE", "VRT", "ETN", "ANET", "MRVL", "CIEN", "MU", "PWR", "EME"}
SPACE_TICKERS = {"RKLB", "ASTS", "LUNR", "RDW", "IRDM", "SPIR", "PL"}
BIOTECH_KEYWORDS = ["BIO", "BIOTECH", "THERAPEUTICS", "PHARMA", "PHARMACEUTICAL", "GENE", "ONCOLOGY", "MEDICINE"]
HEALTHCARE_SECTORS = {"Health Care", "Healthcare", "Biotech"}


def today_str() -> str:
    return pd.Timestamp.today(tz="Asia/Tokyo").strftime("%Y-%m-%d")


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("config root must be a mapping")
        return data
    except ImportError:
        return json.loads(path.read_text(encoding="utf-8"))


def production_config(config: dict[str, Any]) -> dict[str, Any]:
    notify = config.get("notify", {})
    return notify.get("production", {}) or notify.get("production_momentum", {}) or {}


def strict_notification_config(config: dict[str, Any]) -> dict[str, Any]:
    raw = production_config(config).get("strict_notification_gate", {}) or {}
    return dict(raw) if isinstance(raw, dict) else {}


def benchmark_regime_fields(benchmark_history: pd.DataFrame) -> dict[str, Any]:
    raw_close = (
        benchmark_history["Close"]
        if isinstance(benchmark_history, pd.DataFrame) and "Close" in benchmark_history.columns
        else pd.Series(dtype="float64")
    )
    close = pd.to_numeric(raw_close, errors="coerce").dropna()
    if len(close) < 20:
        return {
            "qqq_close": math.nan,
            "qqq_20ema": math.nan,
            "qqq_above_20ema": False,
        }
    qqq_close = float(close.iloc[-1])
    qqq_20ema = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    return {
        "qqq_close": qqq_close,
        "qqq_20ema": qqq_20ema,
        "qqq_above_20ema": bool(qqq_close > qqq_20ema),
    }


def thresholds_from_config(config: dict[str, Any]) -> Thresholds:
    raw = dict(asdict(DEFAULT_THRESHOLDS))
    raw.update(config.get("thresholds", {}))
    if config.get("notify", {}).get("mode") == "production_momentum":
        raw["min_market_cap"] = 0
        raw["min_avg_volume_50d"] = 0
        raw["min_price"] = 0
    return Thresholds(**raw)


def clean_ticker(ticker: str) -> str:
    symbol = str(ticker).strip().upper().replace(".", "-")
    return YFINANCE_SYMBOL_MAP.get(symbol, symbol)


def parse_blackrock_holdings(portfolio_id: str) -> pd.DataFrame:
    import requests
    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

    url = (
        "https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document"
        f"?appType=PRODUCT_PAGE&appSubType=ISHARES&targetSite=us-ishares&locale=en_US&portfolioId={portfolio_id}"
        "&component=fundDownload&userType=individual"
    )
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 options momentum scanner"}, timeout=90)
    response.raise_for_status()
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
    soup = BeautifulSoup(response.text, "html.parser")
    parsed_rows: list[list[str]] = []
    for row in soup.find_all(["ss:row", "row"]):
        values = []
        for cell in row.find_all(["ss:cell", "cell"]):
            data = cell.find(["ss:data", "data"])
            values.append(data.get_text(strip=True) if data else "")
        parsed_rows.append(values)
    header_idx = None
    for idx, row in enumerate(parsed_rows):
        if row[:4] == ["Ticker", "Name", "Sector", "Asset Class"]:
            header_idx = idx
            break
    if header_idx is None:
        raise RuntimeError("Could not locate BlackRock holdings header")
    header = parsed_rows[header_idx]
    holdings: list[dict[str, Any]] = []
    for row in parsed_rows[header_idx + 1 :]:
        if len(row) < 4:
            continue
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        rec = dict(zip(header, row[: len(header)]))
        if rec.get("Asset Class") != "Equity" or rec.get("Location") not in {"United States", ""}:
            continue
        symbol = clean_ticker(rec.get("Ticker", ""))
        if not symbol or symbol == "--" or " " in symbol:
            continue
        holdings.append({"ticker": symbol, "name": rec.get("Name", ""), "sector": rec.get("Sector", "")})
    return pd.DataFrame(holdings).drop_duplicates("ticker").sort_values("ticker")


def load_russell1000_tickers(cache_path: Path | None = None) -> list[str]:
    if cache_path and cache_path.exists():
        raw = pd.read_csv(cache_path)
        return sorted(set(raw["ticker"].astype(str).map(clean_ticker).tolist()))
    holdings = parse_blackrock_holdings(BLACKROCK_IWB_PORTFOLIO_ID)
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        holdings.to_csv(cache_path, index=False)
    return sorted(set(holdings["ticker"].tolist()))


def load_company_metadata(cache_path: Path | None = None) -> dict[str, dict[str, str]]:
    if not cache_path or not cache_path.exists():
        return {}
    raw = pd.read_csv(cache_path)
    name_col = "name" if "name" in raw.columns else "Name" if "Name" in raw.columns else None
    sector_col = "sector" if "sector" in raw.columns else "Sector" if "Sector" in raw.columns else None
    meta: dict[str, dict[str, str]] = {}
    for _, row in raw.iterrows():
        ticker = clean_ticker(row.get("ticker", ""))
        if ticker:
            meta[ticker] = {"name": str(row.get(name_col, "")) if name_col else "", "sector": str(row.get(sector_col, "")) if sector_col else ""}
    return meta


def fetch_histories(tickers: list[str], period: str) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    histories: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), CHUNK_SIZE):
        chunk = tickers[i : i + CHUNK_SIZE]
        print(f"Downloading price history {i + 1}-{i + len(chunk)} / {len(tickers)}", flush=True)
        raw = yf.download(chunk, period=period, auto_adjust=False, progress=False, threads=True, group_by="ticker", timeout=45)
        if raw is None or raw.empty:
            continue
        if isinstance(raw.index, pd.DatetimeIndex) and raw.index.tz is not None:
            raw.index = raw.index.tz_localize(None)
        for ticker in chunk:
            try:
                df = raw[ticker].copy() if isinstance(raw.columns, pd.MultiIndex) else raw.copy()
            except Exception:
                continue
            cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            if len(cols) == 5 and len(df.dropna(subset=["Close"])) >= 60:
                histories[ticker] = df[cols].dropna()
        time.sleep(0.2)
    return histories


def fetch_market_caps(tickers: list[str]) -> dict[str, float]:
    import yfinance as yf

    market_caps: dict[str, float] = {}
    for idx, ticker in enumerate(sorted(set(tickers)), start=1):
        if idx % 50 == 1:
            print(f"Fetching market caps {idx}-{min(idx + 49, len(tickers))} / {len(tickers)}", flush=True)
        try:
            fast = yf.Ticker(ticker).fast_info or {}
            cap = fast.get("marketCap", fast.get("market_cap"))
            if cap:
                market_caps[ticker] = float(cap)
        except Exception:
            pass
        time.sleep(0.03)
    return market_caps


def session_fraction_from_timestamp(timestamp: pd.Timestamp) -> float:
    ts = pd.Timestamp(timestamp)
    ts = ts.tz_localize("America/New_York") if ts.tzinfo is None else ts.tz_convert("America/New_York")
    start = ts.normalize() + pd.Timedelta(hours=9, minutes=30)
    end = ts.normalize() + pd.Timedelta(hours=16)
    if ts <= start:
        return 0.05
    if ts >= end:
        return 1.0
    return float(max(0.05, min(1.0, (ts - start).total_seconds() / (end - start).total_seconds())))


def expected_cumulative_volume_fraction(timestamp: pd.Timestamp) -> float:
    """Approximate the regular-session cumulative volume curve.

    The old scanner divided volume by elapsed clock time. That materially
    overstates relative volume near the open because U.S. equity volume is
    U-shaped. This fixed, monotone profile keeps candidate generation
    deterministic while making the actionable-notification RVOL comparable
    across decision times.
    """

    ts = pd.Timestamp(timestamp)
    ts = ts.tz_localize("America/New_York") if ts.tzinfo is None else ts.tz_convert("America/New_York")
    start = ts.normalize() + pd.Timedelta(hours=9, minutes=30)
    minutes = float((ts - start).total_seconds() / 60.0)
    profile = [
        (0.0, 0.0),
        (5.0, 0.05),
        (30.0, 0.17),
        (60.0, 0.26),
        (90.0, 0.34),
        (150.0, 0.47),
        (210.0, 0.59),
        (270.0, 0.72),
        (330.0, 0.85),
        (390.0, 1.0),
    ]
    if minutes <= 0:
        return 0.05
    if minutes >= 390:
        return 1.0
    for (left_minute, left_fraction), (right_minute, right_fraction) in zip(profile, profile[1:]):
        if left_minute <= minutes <= right_minute:
            width = right_minute - left_minute
            weight = (minutes - left_minute) / width if width else 0.0
            return float(left_fraction + weight * (right_fraction - left_fraction))
    return 1.0


def fetch_intraday_snapshots(tickers: list[str], interval: str = "5m") -> dict[str, dict[str, Any]]:
    import yfinance as yf

    snapshots: dict[str, dict[str, Any]] = {}
    unique = sorted(set(tickers))
    for i in range(0, len(unique), CHUNK_SIZE):
        chunk = unique[i : i + CHUNK_SIZE]
        print(f"Downloading intraday latest {i + 1}-{i + len(chunk)} / {len(unique)}", flush=True)
        try:
            raw = yf.download(chunk, period="5d", interval=interval, auto_adjust=False, progress=False, threads=True, group_by="ticker", timeout=45)
        except Exception:
            continue
        if raw is None or raw.empty:
            continue
        for ticker in chunk:
            try:
                df = raw[ticker].copy() if isinstance(raw.columns, pd.MultiIndex) else raw.copy()
            except Exception:
                continue
            cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            if len(cols) != 5:
                continue
            df = df[cols].dropna(subset=["Close"])
            if df.empty:
                continue
            idx = pd.to_datetime(df.index)
            idx = idx.tz_localize("America/New_York") if idx.tz is None else idx.tz_convert("America/New_York")
            df = df.copy()
            df.index = idx
            latest_ts = pd.Timestamp(df.index[-1])
            today = df[df.index.date == latest_ts.date()]
            if today.empty:
                continue
            latest = today.iloc[-1]
            today_volume = today["Volume"].fillna(0)
            vwap_denominator = float(today_volume.sum())
            recent_closes = today["Close"].dropna().astype(float).tail(2)
            completed_through = latest_ts + pd.Timedelta(minutes=5)
            intraday_vwap = (
                float((today["Close"].astype(float) * today_volume).sum() / vwap_denominator)
                if vwap_denominator > 0
                else math.nan
            )
            snapshots[ticker] = {
                "latest_price": float(latest["Close"]),
                "intraday_open": float(today["Open"].dropna().iloc[0]) if not today["Open"].dropna().empty else math.nan,
                "intraday_high": float(today["High"].max()),
                "intraday_volume": vwap_denominator,
                "intraday_vwap": intraday_vwap,
                "latest_price_date": latest_ts.date().isoformat(),
                "latest_price_time": latest_ts.isoformat(),
                "session_fraction": session_fraction_from_timestamp(latest_ts),
                "expected_volume_fraction": expected_cumulative_volume_fraction(completed_through),
                "confirmation_bar_count": int(len(recent_closes)),
                "recent_close_min": float(recent_closes.min()) if not recent_closes.empty else math.nan,
            }
        time.sleep(0.2)
    return snapshots


def market_cap_bucket(value: Any) -> str:
    if value is None or pd.isna(value):
        return "Unknown"
    v = float(value)
    if v < 2_000_000_000:
        return "<2B"
    if v < 20_000_000_000:
        return "2B-20B"
    if v < 50_000_000_000:
        return "20B-50B"
    if v < 200_000_000_000:
        return "50B-200B"
    return "200B+"


def classify_theme(ticker: str, name: str = "", sector: str = "") -> str:
    symbol = clean_ticker(ticker)
    blob = f"{symbol} {name} {sector}".upper()
    if symbol in SEMICONDUCTOR_TICKERS or "SEMICONDUCTOR" in blob or "CHIP" in blob:
        return "Semiconductor"
    if symbol in AI_INFRA_TICKERS or "DATA CENTER" in blob or "SERVER" in blob or "AI INFRASTRUCTURE" in blob:
        return "AI Infrastructure"
    if symbol in SPACE_TICKERS or "SPACE" in blob or "ROCKET" in blob or "SATELLITE" in blob:
        return "Space"
    if any(keyword in blob for keyword in BIOTECH_KEYWORDS):
        return "Biotech"
    if sector in HEALTHCARE_SECTORS:
        return "Healthcare"
    if "SOFTWARE" in blob or "CLOUD" in blob:
        return "Cloud Software"
    return sector or "Other"


def format_number(value: Any) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    value = float(value)
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    return f"{value:,.0f}"


def format_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value) * 100:.1f}%"


def breakout_metrics(
    history: pd.DataFrame,
    intraday: dict[str, Any] | None = None,
    strict_lookback_days: int = 65,
) -> dict[str, Any]:
    df = history.copy().dropna(subset=["Close"])
    if len(df) < 51:
        raise ValueError("not enough price bars")
    historical = df
    if intraday and intraday.get("latest_price_date"):
        latest_date = pd.Timestamp(intraday["latest_price_date"]).date()
        historical = df[pd.to_datetime(df.index).date < latest_date]
        if len(historical) < 51:
            historical = df
    latest_price = float(intraday["latest_price"]) if intraday and pd.notna(intraday.get("latest_price")) else float(df["Close"].iloc[-1])
    open_price = float(intraday["intraday_open"]) if intraday and pd.notna(intraday.get("intraday_open")) else float(df["Open"].iloc[-1])
    prev_close = float(historical["Close"].iloc[-1]) if intraday else float(df["Close"].iloc[-2])
    prior20_high = float(historical["High"].iloc[-20:].max()) if intraday else float(df["High"].iloc[-21:-1].max())
    if intraday:
        prior_strict_high = (
            float(historical["High"].iloc[-strict_lookback_days:].max())
            if len(historical) >= strict_lookback_days
            else math.nan
        )
    else:
        strict_window = df["High"].iloc[-strict_lookback_days - 1 : -1]
        prior_strict_high = float(strict_window.max()) if len(strict_window) >= strict_lookback_days else math.nan
    avg_volume_50d = float(historical["Volume"].iloc[-50:].mean())
    volume = float(intraday["intraday_volume"]) if intraday and pd.notna(intraday.get("intraday_volume")) else float(df["Volume"].iloc[-1])
    fraction = float(intraday.get("session_fraction", 1.0)) if intraday else 1.0
    pace = volume / (avg_volume_50d * fraction) if avg_volume_50d and fraction > 0 else math.nan
    expected_fraction = float(intraday.get("expected_volume_fraction", 1.0)) if intraday else 1.0
    tod_volume_multiple = (
        volume / (avg_volume_50d * expected_fraction)
        if avg_volume_50d and expected_fraction > 0
        else math.nan
    )
    raw_confirmation_bars = intraday.get("confirmation_bar_count", 0) if intraday else 0
    confirmation_bar_count = (
        int(float(raw_confirmation_bars))
        if raw_confirmation_bars is not None and pd.notna(raw_confirmation_bars)
        else 0
    )
    raw_recent_close_min = intraday.get("recent_close_min", math.nan) if intraday else math.nan
    recent_close_min = (
        float(raw_recent_close_min)
        if raw_recent_close_min is not None and pd.notna(raw_recent_close_min)
        else math.nan
    )
    gap_pct = open_price / prev_close - 1.0 if prev_close > 0 else math.nan
    return {
        "latest_price": latest_price,
        "close": latest_price,
        "intraday_high": intraday.get("intraday_high") if intraday else math.nan,
        "intraday_open": open_price,
        "intraday_vwap": intraday.get("intraday_vwap") if intraday else math.nan,
        "prior_20d_high": prior20_high,
        "prior_65d_high": prior_strict_high,
        "strict_breakout_lookback_days": strict_lookback_days,
        "breakout_price": latest_price,
        "breakout_date": intraday.get("latest_price_date") if intraday else pd.Timestamp(df.index[-1]).date().isoformat(),
        "gap_pct": gap_pct,
        "gap_up_pct": gap_pct,
        "volume": volume,
        "avg_volume_50d": avg_volume_50d,
        "volume_multiple": pace if intraday else volume / avg_volume_50d if avg_volume_50d else math.nan,
        "time_adjusted_volume_multiple": tod_volume_multiple,
        "expected_volume_fraction": expected_fraction,
        "confirmation_bar_count": confirmation_bar_count,
        "recent_close_min": recent_close_min,
        "latest_price_time": intraday.get("latest_price_time") if intraday else "",
        "breakout20": bool(latest_price > prior20_high),
        "breakout65": bool(pd.notna(prior_strict_high) and latest_price > prior_strict_high),
        "confirmed_breakout65": bool(
            pd.notna(prior_strict_high)
            and confirmation_bar_count >= 2
            and pd.notna(recent_close_min)
            and recent_close_min > prior_strict_high
        ),
    }


def option_liquidity_for(ticker: str, spot: float, config: dict[str, Any]) -> dict[str, Any]:
    cfg = production_config(config).get("option_liquidity", {})
    if not cfg.get("enabled", True):
        return {"option_liquidity": "skipped", "option_liquidity_ok": True, "option_iv": math.nan, "option_liquidity_reason": "skipped"}
    try:
        import yfinance as yf

        tk = yf.Ticker(ticker)
        today = pd.Timestamp.utcnow().tz_localize(None).normalize()
        expiries = []
        for exp in getattr(tk, "options", []) or []:
            dte = int((pd.to_datetime(exp) - today).days)
            if int(cfg.get("min_dte", 45)) <= dte <= int(cfg.get("max_dte", 100)):
                expiries.append((abs(dte - 60), dte, exp))
        if not expiries:
            return {"option_liquidity": "unavailable", "option_liquidity_ok": False, "option_liquidity_reason": "no 45-100DTE chain", "option_iv": math.nan}
        _, dte, exp = sorted(expiries)[0]
        calls = tk.option_chain(exp).calls.copy()
        if calls.empty:
            return {"option_liquidity": "unavailable", "option_liquidity_ok": False, "option_liquidity_reason": "no calls", "option_iv": math.nan}
        calls["distance"] = (calls["strike"] - spot).abs()
        atm = calls.sort_values("distance").iloc[0]
        bid = float(atm.get("bid", 0) or 0)
        ask = float(atm.get("ask", 0) or 0)
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else 0
        spread = (ask - bid) / mid if mid > 0 else math.inf
        oi = float(atm.get("openInterest", 0) or 0)
        iv = float(atm.get("impliedVolatility", math.nan))
        ok = bid > 0 and ask > 0 and spread <= float(cfg.get("max_spread_pct", 0.35)) and oi >= float(cfg.get("min_open_interest_per_leg", 100))
        return {"option_liquidity": "liquid" if ok else "insufficient", "option_liquidity_ok": bool(ok), "option_liquidity_reason": "ok" if ok else "wide spread or low OI", "option_iv": iv, "option_expiry": exp, "option_dte": dte}
    except Exception as exc:
        return {"option_liquidity": "unavailable", "option_liquidity_ok": False, "option_liquidity_reason": str(exc), "option_iv": math.nan}


def near_intraday_high(row: dict[str, Any], max_distance: float = 0.01) -> bool:
    high = row.get("intraday_high")
    price = row.get("latest_price", row.get("close"))
    if high is None or pd.isna(high):
        return True
    if price is None or pd.isna(price) or float(high) <= 0:
        return False
    return (float(high) - float(price)) / float(high) <= max_distance


def is_healthcare_or_biotech(row: dict[str, Any]) -> bool:
    return str(row.get("theme", "")) in {"Biotech", "Healthcare"} or str(row.get("sector_proxy", "")) in {"Biotech", "Healthcare"}


def is_extreme_iv(row: dict[str, Any], config: dict[str, Any]) -> bool:
    severe = float(production_config(config).get("pushover", {}).get("severe_iv", 1.20))
    return pd.notna(row.get("option_iv")) and float(row["option_iv"]) >= severe


def is_emergency_gap_excluded(row: dict[str, Any], threshold: float = 0.15) -> bool:
    return pd.notna(row.get("gap_pct")) and float(row["gap_pct"]) >= threshold


def gap_pct_value(row: dict[str, Any]) -> float:
    return float(row["gap_pct"]) if pd.notna(row.get("gap_pct")) else math.nan


def is_high_gap_caution(row: dict[str, Any]) -> bool:
    gap = gap_pct_value(row)
    return pd.notna(gap) and 0.15 <= gap < 0.20


def is_extreme_gap(row: dict[str, Any]) -> bool:
    gap = gap_pct_value(row)
    return pd.notna(gap) and gap >= 0.20


def price_above_vwap(row: dict[str, Any]) -> bool:
    price = row.get("latest_price", row.get("close"))
    vwap = row.get("intraday_vwap")
    return pd.notna(price) and pd.notna(vwap) and float(price) > float(vwap)


def not_fading_from_open(row: dict[str, Any]) -> bool:
    price = row.get("latest_price", row.get("close"))
    open_price = row.get("intraday_open")
    return pd.notna(price) and pd.notna(open_price) and float(price) >= float(open_price)


def breakout_still_valid(row: dict[str, Any]) -> bool:
    price = row.get("latest_price", row.get("close"))
    prior = row.get("prior_20d_high")
    return pd.notna(price) and pd.notna(prior) and float(price) > float(prior)


def base_exclusion(row: dict[str, Any], config: dict[str, Any]) -> bool:
    if is_healthcare_or_biotech(row):
        return True
    if is_extreme_iv(row, config):
        return True
    return False


def tier_for(row: dict[str, Any], config: dict[str, Any]) -> str:
    if base_exclusion(row, config) or not bool(row.get("option_liquidity_ok", False)):
        return "C"
    volume = float(row.get("volume_multiple", 0) or 0)
    if volume >= 1.5:
        return "A"
    if volume >= 1.2:
        return "B"
    return "C"


def risk_flags(row: dict[str, Any], config: dict[str, Any]) -> str:
    flags: list[str] = []
    if is_healthcare_or_biotech(row):
        flags.append("Biotech/Healthcare")
    if is_extreme_gap(row):
        flags.append("Gap >= 20%: Emergency excluded")
    elif is_high_gap_caution(row):
        flags.append("HIGH GAP CAUTION: consider smaller size")
    elif pd.notna(row.get("gap_pct")) and float(row["gap_pct"]) > float(production_config(config).get("danger_gap_pct", 0.15)):
        flags.append("Gap > 15%")
    if not bool(row.get("option_liquidity_ok", False)):
        flags.append("Option Liquidity NG")
    if is_extreme_iv(row, config):
        flags.append("Extreme IV")
    if not near_intraday_high(row):
        flags.append("Not near intraday high")
    return ", ".join(flags) if flags else "None"


def select_candidates(results: pd.DataFrame, histories: dict[str, pd.DataFrame], config: dict[str, Any], metadata: dict[str, dict[str, str]], intraday: dict[str, dict[str, Any]]) -> pd.DataFrame:
    prod = production_config(config)
    strict = strict_notification_config(config)
    rows: list[dict[str, Any]] = []
    rs_min = float(prod.get("rs_min", 98))
    volume_min = float(prod.get("s_volume_multiple_min", prod.get("volume_multiple_min", 1.2)))
    strict_lookback_days = int(strict.get("breakout_lookback_days", 65))
    for _, base in results.iterrows():
        ticker = str(base.get("ticker", "")).upper()
        if ticker not in histories:
            continue
        rs = float(base.get("standard_rs_score", math.nan))
        if not pd.notna(rs) or rs < rs_min:
            continue
        try:
            metrics = breakout_metrics(
                histories[ticker],
                intraday.get(ticker),
                strict_lookback_days=strict_lookback_days,
            )
        except Exception:
            continue
        if not metrics["breakout20"] or not pd.notna(metrics.get("volume_multiple")) or float(metrics["volume_multiple"]) < volume_min:
            continue
        meta = metadata.get(ticker, {})
        row = base.to_dict()
        row.update(metrics)
        row["company_name"] = meta.get("name", "")
        row["source_sector"] = meta.get("sector", "")
        row["theme"] = classify_theme(ticker, row["company_name"], row["source_sector"])
        row["sector_proxy"] = row["theme"] if row["theme"] in {"Semiconductor", "AI Infrastructure", "Space", "Biotech", "Healthcare"} else row["source_sector"] or "Unknown"
        row["market_cap_bucket"] = market_cap_bucket(row.get("market_cap"))
        row.update(option_liquidity_for(ticker, float(row["close"]), config))
        row["alert_rank"] = tier_for(row, config)
        row["conviction_tier"] = {"A": "A Tier", "B": "B Tier"}.get(row["alert_rank"], "C Tier")
        row["danger_flags"] = risk_flags(row, config)
        row["research_log_status"] = "pending_20d_performance"
        row["entry_price_for_tracking"] = row.get("close", math.nan)
        row["tracking_horizon_trading_days"] = 20
        try:
            row["tracking_due_date"] = (pd.Timestamp(row["breakout_date"]) + pd.offsets.BDay(20)).date().isoformat()
        except Exception:
            row["tracking_due_date"] = ""
        row["return_20d"] = math.nan
        row["max_gain_20d"] = math.nan
        row["max_drawdown_20d"] = math.nan
        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    order = {"A": 0, "B": 1, "C": 2}
    out["rank_order"] = out["alert_rank"].map(order).fillna(99)
    return out.sort_values(["rank_order", "standard_rs_score", "volume_multiple"], ascending=[True, False, False]).drop(columns=["rank_order"])


def select_alert_candidates(results: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Compatibility wrapper for deterministic notification unit tests."""
    if results.empty:
        return results.copy()
    prod = production_config(config)
    out = results.copy()
    rs_min = float(prod.get("rs_min", 98))
    volume_min = float(prod.get("volume_multiple_min", 1.2))
    truthy = pd.Series(True, index=out.index)
    mask = (
        out.get("trend_passed", truthy).astype(bool)
        & (pd.to_numeric(out.get("standard_rs_score"), errors="coerce") >= rs_min)
        & out.get("breakout_today", truthy).astype(bool)
        & (pd.to_numeric(out.get("volume_multiple"), errors="coerce") >= volume_min)
        & (pd.to_numeric(out.get("close"), errors="coerce") >= float(prod.get("min_price", 0)))
        & (pd.to_numeric(out.get("avg_volume_50d"), errors="coerce") >= float(prod.get("min_avg_volume_50d", 0)))
    )
    out = out[mask].copy()
    if out.empty:
        return out
    out["market_cap_bucket"] = out["market_cap"].map(market_cap_bucket) if "market_cap" in out.columns else "Unknown"
    out["volume_2x_flag"] = pd.to_numeric(out.get("volume_multiple"), errors="coerce") >= float(prod.get("volume_flag_high", 2.0))
    out["alert_rank"] = out.get("rank", "A")
    return out.reset_index(drop=True)


def enrich_option_liquidity(candidates: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Compatibility wrapper for deterministic notification unit tests."""
    out = candidates.copy()
    if out.empty:
        return out
    cfg = production_config(config).get("option_liquidity", {})
    if not cfg.get("enabled", True):
        out["option_liquidity"] = "Skipped"
        out["option_liquidity_ok"] = True
        out["option_liquidity_reason"] = "skipped"
        out["option_iv"] = math.nan
        out["alert_rank"] = "S"
        return out
    enriched = []
    for _, row in out.iterrows():
        data = row.to_dict()
        data.update(option_liquidity_for(str(row.get("ticker", "")), float(row.get("close", math.nan)), config))
        data["alert_rank"] = tier_for(data, config)
        enriched.append(data)
    return pd.DataFrame(enriched)


def save_candidates(candidates: pd.DataFrame, outdir: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "russell1000_momentum_candidates.csv"
    candidates.to_csv(path, index=False)
    return path


def update_research_log_performance(log_root: Path, histories: dict[str, pd.DataFrame], horizon: int = 20) -> None:
    if not log_root.exists():
        return
    for csv_path in log_root.glob("*/russell1000_momentum_candidates.csv"):
        try:
            log = pd.read_csv(csv_path)
        except Exception:
            continue
        if log.empty or "ticker" not in log.columns or "breakout_date" not in log.columns:
            continue
        changed = False
        for col in ["research_log_status", "entry_price_for_tracking", "tracking_horizon_trading_days", "tracking_due_date", "return_20d", "max_gain_20d", "max_drawdown_20d"]:
            if col not in log.columns:
                log[col] = math.nan
        for idx, row in log.iterrows():
            if pd.notna(row.get("return_20d")):
                continue
            ticker = str(row.get("ticker", "")).upper()
            history = histories.get(ticker)
            if history is None or history.empty:
                continue
            try:
                signal_date = pd.Timestamp(row["breakout_date"]).date()
            except Exception:
                continue
            hist = history.copy().dropna(subset=["Close"])
            if hist.empty:
                continue
            hist_dates = pd.Series(pd.to_datetime(hist.index).date, index=hist.index)
            eligible_positions = [i for i, d in enumerate(hist_dates.tolist()) if d >= signal_date]
            if not eligible_positions:
                continue
            entry_idx = eligible_positions[0]
            target_idx = entry_idx + horizon
            if target_idx >= len(hist):
                log.at[idx, "research_log_status"] = "pending_20d_performance"
                changed = True
                continue
            entry_price = float(row.get("entry_price_for_tracking")) if pd.notna(row.get("entry_price_for_tracking")) else float(hist["Close"].iloc[entry_idx])
            target_price = float(hist["Close"].iloc[target_idx])
            window = hist.iloc[entry_idx : target_idx + 1]
            if entry_price <= 0 or window.empty:
                continue
            log.at[idx, "entry_price_for_tracking"] = entry_price
            log.at[idx, "tracking_horizon_trading_days"] = horizon
            log.at[idx, "tracking_due_date"] = pd.Timestamp(hist.index[target_idx]).date().isoformat()
            log.at[idx, "return_20d"] = target_price / entry_price - 1.0
            log.at[idx, "max_gain_20d"] = float(window["High"].max()) / entry_price - 1.0 if "High" in window.columns else math.nan
            log.at[idx, "max_drawdown_20d"] = float(window["Low"].min()) / entry_price - 1.0 if "Low" in window.columns else math.nan
            log.at[idx, "research_log_status"] = "completed_20d_performance"
            changed = True
        if changed:
            log.to_csv(csv_path, index=False)


def schedule_kind(schedule_utc: str) -> str:
    if schedule_utc in INTRADAY_DIGEST_SCHEDULES:
        return "intraday_digest"
    if schedule_utc == POST_MARKET_REVIEW_SCHEDULE:
        return "post_market_review"
    if schedule_utc == POST_CLOSE_SCHEDULE:
        return "post_close"
    return "manual"


def candidate_block(row: pd.Series) -> str:
    price = row.get("latest_price", row.get("close", math.nan))
    prior = row.get("prior_20d_high", math.nan)
    breakout_pct = price / prior - 1.0 if pd.notna(price) and pd.notna(prior) and prior > 0 else math.nan
    rank = row.get("alert_rank", "B")
    action = {"A": "Priority review / 04:30 Emergency eligible", "B": "Monitor / 04:30 Emergency eligible"}.get(rank, "No realtime alert")
    return (
        f"{row.get('ticker')} - {row.get('company_name') or 'N/A'}\n"
        f"Tier: {rank}\n"
        f"Price: {float(price):.2f}\n"
        f"Prior 20D High: {float(prior):.2f}\n"
        f"Breakout %: {format_pct(breakout_pct)}\n"
        f"RS: {float(row.get('standard_rs_score', 0)):.1f}\n"
        f"Volume Pace: {float(row.get('volume_multiple', 0)):.2f}x\n"
        f"Near Intraday High: {'Yes' if near_intraday_high(row.to_dict()) else 'No'}\n"
        f"Above VWAP: {'Yes' if price_above_vwap(row.to_dict()) else 'No'}\n"
        f"Not Fading From Open: {'Yes' if not_fading_from_open(row.to_dict()) else 'No'}\n"
        f"Sector: {row.get('sector_proxy', 'N/A')}\n"
        f"Theme: {row.get('theme', 'N/A')}\n"
        f"Conviction Tier: {row.get('conviction_tier', 'N/A')}\n"
        f"Gap: {format_pct(row.get('gap_pct'))}\n"
        f"Market Cap: {format_number(row.get('market_cap'))} ({row.get('market_cap_bucket', 'Unknown')})\n"
        f"IV: {format_pct(row.get('option_iv'))}\n"
        f"Option Liquidity: {row.get('option_liquidity', 'N/A')} ({row.get('option_liquidity_reason', 'N/A')})\n"
        f"Suggested Vertical: 60DTE ATM/+15% and ATM/+20% Call Vertical\n"
        f"Warning Flags: {row.get('danger_flags', 'None')}\n"
        f"Suggested Action: {action}\n"
        "--------------------------------"
    )


def build_message(candidates: pd.DataFrame, csv_path: Path, schedule_utc: str, limit: int = 10) -> str:
    kind = schedule_kind(schedule_utc)
    visible = candidates[candidates["alert_rank"].isin(["A", "B"])].copy() if not candidates.empty and "alert_rank" in candidates.columns else candidates
    if visible.empty:
        if kind == "intraday_digest":
            return "No intraday breakout candidates"
        if kind == "post_market_review":
            return "Post-Market Breakout Review\n\nNo confirmed close breakouts or next-day candidates."
        return "No signals today"
    if kind == "post_market_review":
        title = "Post-Market Breakout Review"
        subtitle = "Discord only. C tier is excluded. Review earnings, guidance, theme, valuation, IV, and option spread."
    elif kind == "intraday_digest":
        title = "Intraday Breakout Digest"
        subtitle = "Discord: A/B only. C tier hidden. Pushover Emergency: 04:30 JST only."
    else:
        title = "Production Momentum Alert"
        subtitle = "RS98 + intraday breakout + volume pace. Candidate discovery only."
    sections = [title, subtitle]
    shown = 0
    for rank, heading in [("A", "A Tier"), ("B", "B Tier")]:
        group = visible[visible["alert_rank"] == rank].head(max(0, limit - shown))
        if group.empty:
            continue
        sections.append(heading)
        for _, row in group.iterrows():
            sections.append(candidate_block(row))
            shown += 1
        if shown >= limit:
            break
    if len(visible) > shown:
        sections.append(f"... plus {len(visible) - shown} more Discord candidates in `{csv_path}`")
    hidden = len(candidates) - len(visible)
    if hidden > 0:
        sections.append(f"{hidden} C tier candidates saved to CSV/research log only.")
    sections.append("Exit: Day10 underlying +5% not reached -> exit / +125% take profit or Day20")
    sections.append(f"CSV: `{csv_path}`")
    return "\n\n".join(sections)


def build_discord_message(candidates: pd.DataFrame, csv_path: Path, config: dict[str, Any]) -> str:
    """Compatibility wrapper for production momentum notification tests."""
    if candidates.empty:
        return "No signals today"
    lines = [
        "Production Momentum Alert",
        "RS>=98",
        "MarketCap displayed only",
    ]
    for _, row in candidates.head(10).iterrows():
        lines.append(
            f"{row.get('alert_rank', row.get('rank', ''))} | {row.get('ticker', '')} | "
            f"Price {float(row.get('close', row.get('latest_price', 0)) or 0):.2f} | "
            f"RS {float(row.get('standard_rs_score', 0) or 0):.1f} | "
            f"Vol {float(row.get('volume_multiple', 0) or 0):.2f}x | "
            f"MarketCap {row.get('market_cap_bucket', 'Unknown')}"
        )
    if len(candidates) > 10:
        lines.append(f"... plus {len(candidates) - 10} more candidates in `{csv_path}`")
    lines.extend(
        [
            "60DTE ATM/+15%",
            "+125% profit take",
            f"CSV: `{csv_path}`",
        ]
    )
    return "\n".join(lines)


def is_strong_b(row: pd.Series, config: dict[str, Any], ignore_gap: bool = False) -> bool:
    data = row.to_dict()
    return bool(
        row.get("alert_rank") == "B"
        and float(row.get("volume_multiple", 0) or 0) >= 1.2
        and near_intraday_high(data)
        and bool(row.get("option_liquidity_ok", False))
        and not is_healthcare_or_biotech(data)
        and (ignore_gap or not is_emergency_gap_excluded(data))
        and not is_extreme_iv(data, config)
    )


def is_emergency_candidate(row: pd.Series, schedule_utc: str, config: dict[str, Any]) -> bool:
    if schedule_utc != PUSHOVER_EMERGENCY_SCHEDULE:
        return False
    data = row.to_dict()
    if is_extreme_gap(data):
        return False
    return row.get("alert_rank") in {"A", "B"}


def select_pushover_candidates(candidates: pd.DataFrame, schedule_utc: str, config: dict[str, Any]) -> pd.DataFrame:
    if candidates.empty or schedule_utc != PUSHOVER_EMERGENCY_SCHEDULE:
        return candidates.iloc[0:0].copy()
    rows = [row for _, row in candidates.iterrows() if is_emergency_candidate(row, schedule_utc, config)]
    return pd.DataFrame(rows)


def build_pushover_message(candidates: pd.DataFrame, csv_path: Path, limit: int = 8) -> str:
    lines = ["04:30 Breakout Emergency", "Exit: Day10 underlying +5% not reached -> exit / +125% take profit or Day20"]
    for _, row in candidates.head(limit).iterrows():
        size = "A: priority review" if row.get("alert_rank") == "A" else "B: standard review"
        caution = " | HIGH GAP CAUTION: consider smaller size" if is_high_gap_caution(row.to_dict()) else ""
        lines.append(
            f"{row.get('alert_rank')} | {row.get('ticker')} {row.get('company_name') or ''} | Price {float(row.get('latest_price', row.get('close', 0))):.2f} | "
            f"RS {float(row.get('standard_rs_score', 0)):.1f} | Vol {float(row.get('volume_multiple', 0)):.2f}x | "
            f"NearHigh {'Yes' if near_intraday_high(row.to_dict()) else 'No'} | AboveVWAP {'Yes' if price_above_vwap(row.to_dict()) else 'No'} | "
            f"NotFading {'Yes' if not_fading_from_open(row.to_dict()) else 'No'} | Sector {row.get('sector_proxy', 'N/A')} | Theme {row.get('theme', 'N/A')} | "
            f"Gap {format_pct(row.get('gap_pct'))} | IV {format_pct(row.get('option_iv'))} | {size} | Warnings {row.get('danger_flags', 'None')}"
            f"{caution}"
        )
    if len(candidates) > limit:
        lines.append(f"... plus {len(candidates) - limit} more. CSV: {csv_path}")
    else:
        lines.append(f"CSV: {csv_path}")
    return "\n".join(lines)


def run(config: dict[str, Any], outdir: Path, period: str) -> tuple[pd.DataFrame, Path]:
    notify = config.get("notify", {})
    cache_path = Path(notify.get("universe_cache", "cache/russell1000_iwb_holdings.csv"))
    tickers = load_russell1000_tickers(cache_path=cache_path)
    tickers = sorted(set(tickers + [BENCHMARK]))
    histories = fetch_histories(tickers, period=period)
    benchmark = histories.pop(BENCHMARK, None)
    if benchmark is None:
        raise RuntimeError(f"benchmark history missing: {BENCHMARK}")
    market_caps = fetch_market_caps(list(histories))
    thresholds = thresholds_from_config(config)
    results = scan_universe(histories, benchmark, market_caps=market_caps, thresholds=thresholds)
    for key, value in benchmark_regime_fields(benchmark).items():
        results[key] = value
    if notify.get("mode") == "production_momentum":
        metadata = load_company_metadata(cache_path)
        prod = production_config(config)
        rs_min = float(prod.get("rs_min", 98))
        rs_candidates = results[pd.to_numeric(results.get("standard_rs_score"), errors="coerce") >= rs_min].copy()
        intraday = {}
        if prod.get("intraday", {}).get("enabled", True) and not rs_candidates.empty:
            intraday = fetch_intraday_snapshots(rs_candidates["ticker"].astype(str).tolist(), interval=prod.get("intraday", {}).get("interval", "5m"))
        candidates = select_candidates(results, histories, config, metadata, intraday)
    else:
        candidates = results[results.get("rank", "C").isin(["S", "A", "B"])].copy() if "rank" in results.columns else results.iloc[0:0].copy()
    csv_path = save_candidates(candidates, outdir / today_str())
    update_research_log_performance(outdir, histories)
    return candidates, csv_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--outdir", default="scanner_alerts")
    parser.add_argument("--period", default="18mo")
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument("--message-limit", type=int, default=10)
    args = parser.parse_args()

    config = load_config(Path(args.config))
    candidates, csv_path = run(config, Path(args.outdir), period=args.period)
    schedule_utc = os.environ.get("SCANNER_SCHEDULE_UTC", "")
    message = build_message(candidates, csv_path, schedule_utc, limit=args.message_limit)
    print(message)

    if args.no_notify or not config.get("notify", {}).get("enabled", True):
        return
    send_discord_alert(message, env_var=config.get("notify", {}).get("discord_webhook_env", "STOCK"))

    pushover_candidates = select_pushover_candidates(candidates, schedule_utc, config)
    if (
        schedule_utc == PUSHOVER_EMERGENCY_SCHEDULE
        and config.get("notify", {}).get("mode") == "production_momentum"
        and pushover_enabled()
        and os.environ.get("PUSHOVER_APP_TOKEN")
        and os.environ.get("PUSHOVER_USER_KEY")
        and not pushover_candidates.empty
    ):
        send_pushover_emergency(build_pushover_message(pushover_candidates, csv_path), title="04:30 Breakout Alert")


if __name__ == "__main__":
    main()
