#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
from scanner.utils import DEFAULT_THRESHOLDS, Thresholds


BENCHMARK = "QQQ"
BLACKROCK_IWB_PORTFOLIO_ID = "239707"
CHUNK_SIZE = 80

YFINANCE_SYMBOL_MAP = {
    "BRKB": "BRK-B",
    "BFA": "BF-A",
    "BFB": "BF-B",
    "HEIA": "HEI-A",
    "LENB": "LEN-B",
    "MOGA": "MOG-A",
    "UHALB": "UHAL-B",
}


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


def thresholds_from_config(config: dict[str, Any]) -> Thresholds:
    raw = dict(asdict(DEFAULT_THRESHOLDS))
    raw.update(config.get("thresholds", {}))
    notify_filters = config.get("notify", {}).get("filters", {})
    raw["min_price"] = notify_filters.get("min_price", raw["min_price"])
    raw["min_avg_volume_50d"] = notify_filters.get("min_avg_volume_50d", raw["min_avg_volume_50d"])
    raw["min_market_cap"] = notify_filters.get("min_market_cap_proxy", raw["min_market_cap"])
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


def fetch_histories(tickers: list[str], period: str) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    histories: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), CHUNK_SIZE):
        chunk = tickers[i : i + CHUNK_SIZE]
        print(f"Downloading price history {i + 1}-{i + len(chunk)} / {len(tickers)}", flush=True)
        raw = yf.download(
            chunk,
            period=period,
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by="ticker",
            timeout=45,
        )
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
            if len(cols) == 5 and len(df.dropna(subset=["Close"])) >= 260:
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


def select_alert_candidates(results: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    notify = config.get("notify", {})
    rule = notify.get("rule", {})
    filters = notify.get("filters", {})
    if results.empty:
        return results.copy()
    required = [
        "trend_passed",
        "standard_rs_score",
        "breakout_rs_score",
        "accumulation_score",
        "vcp_score",
        "distance_to_pivot",
        "avg_volume_50d",
        "close",
        "market_cap",
    ]
    missing = [col for col in required if col not in results.columns]
    if missing:
        raise ValueError(f"scanner results missing columns: {', '.join(missing)}")

    mask = (
        results["trend_passed"].astype(bool)
        & (results["standard_rs_score"] >= rule.get("standard_rs_min", 95))
        & (results["breakout_rs_score"] >= rule.get("breakout_rs_min", 95))
        & (results["accumulation_score"] >= rule.get("accumulation_min", 30))
        & (results["vcp_score"] >= rule.get("vcp_min", 50))
        & (results["distance_to_pivot"] >= 0)
        & (results["distance_to_pivot"] <= rule.get("distance_to_pivot_max", 0.12))
        & (results["avg_volume_50d"] >= filters.get("min_avg_volume_50d", 2_000_000))
        & (results["close"] >= filters.get("min_price", 10.0))
        & (results["market_cap"] >= filters.get("min_market_cap_proxy", 2_000_000_000))
    )
    out = results[mask].copy()
    reference = notify.get("backtest_reference", {})
    out["backtest_hit_rate_10pct_20d"] = reference.get("hit_rate_10pct_20d")
    out["backtest_hit_rate_15pct_20d"] = reference.get("hit_rate_15pct_20d")
    out["backtest_hit_rate_20pct_20d"] = reference.get("hit_rate_20pct_20d")
    out["backtest_reference_signals"] = reference.get("signals")
    ranks = notify.get("alert_ranks", ["S", "A", "B"])
    out = out[out["rank"].isin(ranks)].copy()
    if out.empty:
        return out
    rank_order = {rank: idx for idx, rank in enumerate(["S", "A", "B"])}
    out["rank_order"] = out["rank"].map(rank_order).fillna(99)
    return out.sort_values(
        ["rank_order", "total_score", "standard_rs_score", "breakout_rs_score"],
        ascending=[True, False, False, False],
    ).drop(columns=["rank_order"])


def save_candidates(candidates: pd.DataFrame, outdir: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "russell1000_momentum_candidates.csv"
    candidates.to_csv(path, index=False)
    return path


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


def build_discord_message(candidates: pd.DataFrame, csv_path: Path, config: dict[str, Any], limit: int = 10) -> str:
    if candidates.empty:
        return "No signals today"

    sections = ["\U0001f6a8 Daily Scanner Alert"]
    headings = [("S", "\U0001f525 S Rank"), ("A", "\U0001f6a8 A Rank"), ("B", "\u26a0\ufe0f B Rank")]
    shown = 0
    for rank, heading in headings:
        group = candidates[candidates["rank"] == rank].head(max(0, limit - shown))
        if group.empty:
            continue
        sections.append(heading)
        for _, row in group.iterrows():
            sections.append(_format_candidate_block(row))
            shown += 1
        if shown >= limit:
            break
    if len(candidates) > shown:
        sections.append(f"... plus {len(candidates) - shown} more signals in `{csv_path}`")
    return "\n\n".join(sections)


def _format_candidate_block(row: pd.Series) -> str:
    return (
        "{ticker}\n"
        "Rank: {rank}\n"
        "Score: {score:.0f}\n\n"
        "RS: {rs:.0f}\n"
        "Breakout RS: {breakout_rs:.0f}\n"
        "Accumulation: {accumulation:.0f}\n"
        "VCP: {vcp:.0f}\n\n"
        "Pivot Distance: {distance}\n\n"
        "Volume: {volume}\n\n"
        "--------------------------------"
    ).format(
        ticker=row["ticker"],
        rank=row["rank"],
        score=float(row["total_score"]),
        rs=float(row["standard_rs_score"]),
        breakout_rs=float(row["breakout_rs_score"]),
        accumulation=float(row["accumulation_score"]),
        vcp=float(row["vcp_score"]),
        distance=format_pct(row["distance_to_pivot"]),
        volume=format_number(row["avg_volume_50d"]),
    )


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
    candidates = select_alert_candidates(results, config)
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
    message = build_discord_message(candidates, csv_path, config, limit=args.message_limit)
    print(message)

    if args.no_notify or not config.get("notify", {}).get("enabled", True):
        return
    send_discord_alert(message, env_var=config.get("notify", {}).get("discord_webhook_env", "STOCK"))


if __name__ == "__main__":
    main()
