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
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

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
PUSHOVER_A_SCHEDULES = {"30 17 * * 1-5", "30 19 * * 1-5"}
PUSHOVER_B_SCHEDULES = {"30 19 * * 1-5"}
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


def thresholds_from_config(config: dict[str, Any]) -> Thresholds:
    raw = dict(asdict(DEFAULT_THRESHOLDS))
    raw.update(config.get("thresholds", {}))
    notify = config.get("notify", {})
    if notify.get("mode") == "production_momentum":
        raw["min_market_cap"] = 0
    else:
        filters = notify.get("filters", {})
        raw["min_price"] = filters.get("min_price", raw["min_price"])
        raw["min_avg_volume_50d"] = filters.get("min_avg_volume_50d", raw["min_avg_volume_50d"])
        raw["min_market_cap"] = filters.get("min_market_cap_proxy", raw["min_market_cap"])
    return Thresholds(**raw)


def clean_ticker(ticker: str) -> str:
    symbol = str(ticker).strip().upper().replace(".", "-")
    return YFINANCE_SYMBOL_MAP.get(symbol, symbol)


def parse_blackrock_holdings(portfolio_id: str) -> pd.DataFrame:
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
        if rec.get("Asset Class") != "Equity":
            continue
        if rec.get("Location") not in {"United States", ""}:
            continue
        symbol = clean_ticker(rec.get("Ticker", ""))
        if not symbol or symbol == "--" or " " in symbol:
            continue
        holdings.append(
            {
                "ticker": symbol,
                "name": rec.get("Name", ""),
                "sector": rec.get("Sector", ""),
                "holding_weight_pct": pd.to_numeric(rec.get("Weight (%)"), errors="coerce"),
            }
        )
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
    if "ticker" not in raw.columns:
        return {}
    name_col = "name" if "name" in raw.columns else "Name" if "Name" in raw.columns else None
    sector_col = "sector" if "sector" in raw.columns else "Sector" if "Sector" in raw.columns else None
    out: dict[str, dict[str, str]] = {}
    for _, row in raw.iterrows():
        ticker = clean_ticker(row.get("ticker", ""))
        if not ticker:
            continue
        out[ticker] = {
            "name": str(row.get(name_col, "")) if name_col else "",
            "sector": str(row.get(sector_col, "")) if sector_col else "",
        }
    return out


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
            market_cap = fast.get("marketCap", fast.get("market_cap"))
            if market_cap:
                market_caps[ticker] = float(market_cap)
        except Exception:
            pass
        time.sleep(0.03)
    return market_caps


def session_fraction_from_timestamp(timestamp: pd.Timestamp) -> float:
    ts = pd.Timestamp(timestamp)
    if ts.tzinfo is None:
        ts = ts.tz_localize("America/New_York")
    else:
        ts = ts.tz_convert("America/New_York")
    start = ts.normalize() + pd.Timedelta(hours=9, minutes=30)
    end = ts.normalize() + pd.Timedelta(hours=16)
    if ts <= start:
        return 0.05
    if ts >= end:
        return 1.0
    return float(max(0.05, min(1.0, (ts - start).total_seconds() / (end - start).total_seconds())))


def fetch_intraday_snapshots(tickers: list[str], interval: str = "5m") -> dict[str, dict[str, Any]]:
    import yfinance as yf

    snapshots: dict[str, dict[str, Any]] = {}
    for i in range(0, len(tickers), CHUNK_SIZE):
        chunk = sorted(set(tickers))[i : i + CHUNK_SIZE]
        print(f"Downloading intraday latest {i + 1}-{i + len(chunk)} / {len(set(tickers))}", flush=True)
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
            snapshots[ticker] = {
                "latest_price": float(latest["Close"]),
                "intraday_open": float(today["Open"].dropna().iloc[0]) if not today["Open"].dropna().empty else math.nan,
                "intraday_high": float(today["High"].max()),
                "intraday_volume": float(today["Volume"].fillna(0).sum()),
                "latest_price_date": latest_ts.date().isoformat(),
                "latest_price_time": latest_ts.isoformat(),
                "session_fraction": session_fraction_from_timestamp(latest_ts),
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
    if sector == "Health Care":
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


def format_iv(value: Any) -> str:
    return format_pct(value)


def bool_flag(value: Any) -> str:
    return "Yes" if bool(value) else "No"


def breakout_metrics(history: pd.DataFrame, intraday: dict[str, Any] | None = None) -> dict[str, Any]:
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
    avg_volume_50d = float(historical["Volume"].iloc[-50:].mean())
    volume = float(intraday["intraday_volume"]) if intraday and pd.notna(intraday.get("intraday_volume")) else float(df["Volume"].iloc[-1])
    fraction = float(intraday.get("session_fraction", 1.0)) if intraday else 1.0
    pace = volume / (avg_volume_50d * fraction) if avg_volume_50d and fraction > 0 else math.nan
    return {
        "close": latest_price,
        "latest_price": latest_price,
        "intraday_high": intraday.get("intraday_high") if intraday else math.nan,
        "prior_20d_high": prior20_high,
        "breakout_price": latest_price,
        "breakout_date": intraday.get("latest_price_date") if intraday else pd.Timestamp(df.index[-1]).date().isoformat(),
        "gap_pct": open_price / prev_close - 1.0 if prev_close > 0 else math.nan,
        "volume": volume,
        "avg_volume_50d": avg_volume_50d,
        "volume_multiple": pace if intraday else volume / avg_volume_50d if avg_volume_50d else math.nan,
        "volume_pace_multiple": pace,
        "latest_price_time": intraday.get("latest_price_time") if intraday else "",
        "breakout20": bool(latest_price > prior20_high),
    }


def option_liquidity_for(ticker: str, spot: float, config: dict[str, Any]) -> dict[str, Any]:
    prod = production_config(config)
    cfg = prod.get("option_liquidity", {})
    if not cfg.get("enabled", True):
        return {"option_liquidity": "skipped", "option_liquidity_ok": True, "option_iv": math.nan}
    try:
        import yfinance as yf

        tk = yf.Ticker(ticker)
        today = pd.Timestamp.utcnow().tz_localize(None).normalize()
        expiries = []
        for exp in getattr(tk, "options", []) or []:
            exp_dt = pd.to_datetime(exp)
            dte = int((exp_dt - today).days)
            if int(cfg.get("min_dte", cfg.get("dte_min", 45))) <= dte <= int(cfg.get("max_dte", cfg.get("dte_max", 100))):
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
        ok = bid > 0 and ask > 0 and spread <= float(cfg.get("max_spread_pct", cfg.get("max_relative_spread", 0.35))) and oi >= float(cfg.get("min_open_interest_per_leg", cfg.get("min_open_interest", 100)))
        return {
            "option_liquidity": "liquid" if ok else "insufficient",
            "option_liquidity_ok": bool(ok),
            "option_liquidity_reason": "ok" if ok else "wide spread or low OI",
            "option_iv": iv,
            "option_expiry": exp,
            "option_dte": dte,
        }
    except Exception as exc:
        return {"option_liquidity": "unavailable", "option_liquidity_ok": False, "option_liquidity_reason": str(exc), "option_iv": math.nan}


def danger_flags(row: dict[str, Any], config: dict[str, Any]) -> str:
    prod = production_config(config)
    flags: list[str] = []
    if pd.notna(row.get("gap_pct")) and float(row["gap_pct"]) > float(prod.get("danger_gap_pct", 0.15)):
        flags.append("Gap > 15%")
    if pd.isna(row.get("market_cap")):
        flags.append("Market Cap unknown")
    elif float(row["market_cap"]) < float(prod.get("danger_market_cap", 2_000_000_000)):
        flags.append("Market Cap < 2B")
    if row.get("option_liquidity") in {"insufficient", "unavailable", "not_checked"}:
        flags.append(f"Option Liquidity {row.get('option_liquidity')}")
    if pd.notna(row.get("option_iv")) and float(row["option_iv"]) > float(prod.get("danger_iv", 1.00)):
        flags.append("IV > 100")
    if pd.notna(row.get("gap_pct")) and float(row["gap_pct"]) > float(prod.get("earnings_check_gap_pct", 0.08)):
        flags.append("Earnings check required")
    return ", ".join(flags) if flags else "None"


def select_candidates(results: pd.DataFrame, histories: dict[str, pd.DataFrame], config: dict[str, Any], metadata: dict[str, dict[str, str]], intraday: dict[str, dict[str, Any]]) -> pd.DataFrame:
    prod = production_config(config)
    rows: list[dict[str, Any]] = []
    rs_min = float(prod.get("rs_min", 98))
    vol_min = float(prod.get("s_volume_multiple_min", prod.get("volume_multiple_min", 1.2)))
    for _, base in results.iterrows():
        ticker = str(base.get("ticker", "")).upper()
        if ticker not in histories:
            continue
        rs = float(base.get("standard_rs_score", math.nan))
        if not pd.notna(rs) or rs < rs_min:
            continue
        try:
            metrics = breakout_metrics(histories[ticker], intraday.get(ticker))
        except Exception:
            continue
        if not metrics["breakout20"] or not pd.notna(metrics.get("volume_multiple")) or float(metrics["volume_multiple"]) < vol_min:
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
        row["alert_rank"] = "S" if row.get("option_liquidity_ok") else "A"
        row["conviction_tier"] = "A Tier" if row["alert_rank"] == "S" else "B Tier"
        row["danger_flags"] = danger_flags(row, config)
        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    order = {"S": 0, "A": 1}
    out["rank_order"] = out["alert_rank"].map(order).fillna(99)
    return out.sort_values(["rank_order", "standard_rs_score", "volume_multiple"], ascending=[True, False, False]).drop(columns=["rank_order"])


def save_candidates(candidates: pd.DataFrame, outdir: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "russell1000_momentum_candidates.csv"
    candidates.to_csv(path, index=False)
    return path


def schedule_kind(schedule_utc: str) -> str:
    if schedule_utc in INTRADAY_DIGEST_SCHEDULES:
        return "intraday_digest"
    if schedule_utc == POST_MARKET_REVIEW_SCHEDULE:
        return "post_market_review"
    if schedule_utc == POST_CLOSE_SCHEDULE:
        return "post_close"
    return "manual"


def candidate_block(row: pd.Series, digest: bool = False) -> str:
    price = row.get("latest_price", row.get("close", math.nan))
    prior = row.get("prior_20d_high", math.nan)
    breakout_pct = price / prior - 1.0 if pd.notna(price) and pd.notna(prior) and prior > 0 else math.nan
    action = "Consider immediately / Emergency eligible" if row.get("alert_rank") == "S" else "Monitor / 04:30 confirmation candidate"
    return (
        f"{row.get('ticker')} - {row.get('company_name') or 'N/A'}\n"
        f"Rank: {row.get('alert_rank', 'A')}\n"
        f"Price: {float(price):.2f}\n"
        f"Prior 20D High: {float(prior):.2f}\n"
        f"Breakout %: {format_pct(breakout_pct)}\n"
        f"RS: {float(row.get('standard_rs_score', 0)):.1f}\n"
        f"Volume Pace: {float(row.get('volume_multiple', 0)):.2f}x\n"
        f"Sector: {row.get('sector_proxy', 'N/A')}\n"
        f"Theme: {row.get('theme', 'N/A')}\n"
        f"Conviction Tier: {row.get('conviction_tier', 'N/A')}\n"
        f"Gap: {format_pct(row.get('gap_pct'))}\n"
        f"Market Cap: {format_number(row.get('market_cap'))} ({row.get('market_cap_bucket', 'Unknown')})\n"
        f"IV: {format_iv(row.get('option_iv'))}\n"
        f"Option Liquidity: {row.get('option_liquidity', 'N/A')} ({row.get('option_liquidity_reason', 'N/A')})\n"
        f"Suggested Vertical: 60DTE ATM/+15% and ATM/+20% Call Vertical\n"
        f"Warning Flags: {row.get('danger_flags', 'None')}\n"
        f"Suggested Action: {action}\n"
        "--------------------------------"
    )


def build_message(candidates: pd.DataFrame, csv_path: Path, config: dict[str, Any], schedule_utc: str, limit: int = 10) -> str:
    kind = schedule_kind(schedule_utc)
    if candidates.empty:
        if kind == "intraday_digest":
            return "No intraday breakout candidates"
        if kind == "post_market_review":
            return "Post-Market Breakout Review\n\nNo confirmed close breakouts or next-day candidates."
        return "No signals today"
    if kind == "post_market_review":
        title = "Post-Market Breakout Review"
        subtitle = "Discord only. Review earnings quality, guidance, theme, valuation, IV, and option spreads."
    elif kind == "intraday_digest":
        title = "Intraday Breakout Digest"
        subtitle = "RS98 + latest intraday price > prior 20D high + intraday volume pace >= 1.2x. Discord digest; Pushover only for strict Emergency candidates."
    else:
        title = "Production Momentum Alert"
        subtitle = "RS98 + prior 20D high breakout + volume. Candidate discovery only."
    sections = [title, subtitle]
    shown = 0
    for rank, heading in [("S", "A Tier / Emergency Eligible"), ("A", "B Tier / Monitor")]:
        group = candidates[candidates["alert_rank"] == rank].head(max(0, limit - shown))
        if group.empty:
            continue
        sections.append(heading)
        for _, row in group.iterrows():
            sections.append(candidate_block(row, digest=kind == "intraday_digest"))
            shown += 1
        if shown >= limit:
            break
    if len(candidates) > shown:
        sections.append(f"... plus {len(candidates) - shown} more candidates in `{csv_path}`")
    sections.append("Exit: Day10 +5%未達なら撤退 / +125%利確 or Day20")
    sections.append(f"CSV: `{csv_path}`")
    return "\n\n".join(sections)


def is_emergency_candidate(row: pd.Series, schedule_utc: str, config: dict[str, Any]) -> bool:
    theme = str(row.get("theme", ""))
    sector = str(row.get("sector_proxy", ""))
    if theme in {"Biotech", "Healthcare"} or sector in {"Biotech", "Healthcare"}:
        return False
    if not bool(row.get("option_liquidity_ok", False)):
        return False
    if pd.notna(row.get("option_iv")) and float(row["option_iv"]) >= float(production_config(config).get("pushover", {}).get("severe_iv", 1.20)):
        return False
    if pd.notna(row.get("gap_pct")) and float(row["gap_pct"]) >= 0.20:
        return False
    if schedule_utc in PUSHOVER_A_SCHEDULES and row.get("alert_rank") == "S":
        return True
    if schedule_utc in PUSHOVER_B_SCHEDULES and row.get("alert_rank") == "A" and float(row.get("volume_multiple", 0)) >= 1.5:
        return True
    return False


def select_pushover_candidates(candidates: pd.DataFrame, schedule_utc: str, config: dict[str, Any]) -> pd.DataFrame:
    if candidates.empty or schedule_utc == POST_MARKET_REVIEW_SCHEDULE:
        return candidates.iloc[0:0].copy()
    rows = [row for _, row in candidates.iterrows() if is_emergency_candidate(row, schedule_utc, config)]
    return pd.DataFrame(rows)


def build_pushover_message(candidates: pd.DataFrame, csv_path: Path, limit: int = 8) -> str:
    lines = ["Breakout emergency signal detected", "Exit: Day10 +5%未達なら撤退 / +125%利確 or Day20"]
    for _, row in candidates.head(limit).iterrows():
        lines.append(
            f"{row.get('ticker')} {row.get('company_name') or ''} | Price {float(row.get('latest_price', row.get('close', 0))):.2f} | "
            f"RS {float(row.get('standard_rs_score', 0)):.1f} | Vol {float(row.get('volume_multiple', 0)):.2f}x | "
            f"Sector {row.get('sector_proxy', 'N/A')} | Theme {row.get('theme', 'N/A')} | "
            f"Tier {row.get('conviction_tier', 'N/A')} | Gap {format_pct(row.get('gap_pct'))} | IV {format_iv(row.get('option_iv'))} | "
            f"Vertical 60DTE ATM/+15% and ATM/+20% | Warnings {row.get('danger_flags', 'None')}"
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
        candidates = results.iloc[0:0].copy()
    csv_path = save_candidates(candidates, outdir / today_str())
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
    message = build_message(candidates, csv_path, config, schedule_utc, limit=args.message_limit)
    print(message)

    if args.no_notify or not config.get("notify", {}).get("enabled", True):
        return
    send_discord_alert(message, env_var=config.get("notify", {}).get("discord_webhook_env", "STOCK"))

    pushover_candidates = select_pushover_candidates(candidates, schedule_utc, config)
    if (
        config.get("notify", {}).get("mode") == "production_momentum"
        and pushover_enabled()
        and os.environ.get("PUSHOVER_APP_TOKEN")
        and os.environ.get("PUSHOVER_USER_KEY")
        and not pushover_candidates.empty
    ):
        send_pushover_emergency(build_pushover_message(pushover_candidates, csv_path), title="A\u7d1a Breakout Alert")


if __name__ == "__main__":
    main()
