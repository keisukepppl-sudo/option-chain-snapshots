#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
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
    prod = production_config(config)
    if config.get("notify", {}).get("mode") == "production_momentum":
        raw["breakout_lookback_days"] = prod.get("breakout_lookback_days", raw.get("breakout_lookback_days", 20))
        raw["breakout_volume_multiple"] = prod.get("volume_multiple_min", raw["breakout_volume_multiple"])
        raw["min_price"] = prod.get("min_price", raw["min_price"])
        raw["min_avg_volume_50d"] = prod.get("min_avg_volume_50d", raw["min_avg_volume_50d"])
        raw["min_market_cap"] = 0
    return Thresholds(**raw)


def production_config(config: dict[str, Any]) -> dict[str, Any]:
    notify = config.get("notify", {})
    return notify.get("production_momentum", {}) or {}


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


def select_alert_candidates(results: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    if config.get("notify", {}).get("mode") == "production_momentum":
        return select_production_momentum_candidates(results, config)
    return select_legacy_alert_candidates(results, config)


def select_production_momentum_candidates(results: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    prod = production_config(config)
    if results.empty:
        return results.copy()
    required = [
        "ticker",
        "close",
        "pivot",
        "standard_rs_score",
        "breakout_rs_score",
        "breakout_today",
        "volume_multiple",
        "avg_volume_50d",
        "market_cap",
    ]
    missing = [col for col in required if col not in results.columns]
    if missing:
        raise ValueError(f"scanner results missing columns: {', '.join(missing)}")

    rs_min = float(prod.get("rs_min", 98))
    volume_min = float(prod.get("volume_multiple_min", 1.2))
    min_price = float(prod.get("min_price", 5.0))
    min_avg_volume = float(prod.get("min_avg_volume_50d", 500_000))

    mask = (
        (results["standard_rs_score"] >= rs_min)
        & (results["breakout_rs_score"] >= rs_min)
        & (results["breakout_today"].astype(bool))
        & (results["volume_multiple"] >= volume_min)
        & (results["close"] >= min_price)
        & (results["avg_volume_50d"] >= min_avg_volume)
    )
    out = results[mask].copy()
    if out.empty:
        return out

    out["market_cap_bucket"] = out["market_cap"].map(market_cap_bucket)
    out["volume_2x_flag"] = out["volume_multiple"] >= float(prod.get("volume_flag_high", 2.0))
    out["volume_3x_flag"] = out["volume_multiple"] >= float(prod.get("volume_flag_extreme", 3.0))
    out["gap_pct"] = compute_gap_pct(out)
    out["gap_warning"] = out["gap_pct"].abs() >= float(prod.get("gap_warning_pct", 0.15))
    out["market_cap_warning"] = out["market_cap"].isna() | (out["market_cap"] < float(prod.get("market_cap_warning_threshold", 2_000_000_000)))
    out["risk_flags"] = out.apply(lambda r: ", ".join(build_risk_flags(r, prod)) or "None", axis=1)
    out["alert_rank"] = "A"
    out["option_liquidity"] = "Unchecked"
    out["option_liquidity_ok"] = False
    out["iv"] = math.nan
    out["suggested_verticals"] = build_vertical_label(prod)
    out["exit_rule"] = build_exit_rule_label(prod)

    rank_order = {"S": 0, "A": 1}
    out["rank_order"] = out["alert_rank"].map(rank_order).fillna(99)
    return out.sort_values(
        ["rank_order", "standard_rs_score", "volume_multiple"],
        ascending=[True, False, False],
    ).drop(columns=["rank_order"])


def compute_gap_pct(df: pd.DataFrame) -> pd.Series:
    if "open" in df.columns and "prev_close" in df.columns:
        return pd.to_numeric(df["open"], errors="coerce") / pd.to_numeric(df["prev_close"], errors="coerce") - 1.0
    return pd.Series([math.nan] * len(df), index=df.index)


def build_risk_flags(row: pd.Series, prod: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if bool(row.get("gap_warning", False)):
        flags.append("Gap>15%")
    if row.get("market_cap_bucket") in {"<2B", "Unknown"}:
        flags.append("MarketCapCheck")
    if bool(row.get("volume_2x_flag", False)):
        flags.append("Volume>=2x")
    if bool(row.get("volume_3x_flag", False)):
        flags.append("Volume>=3x")
    return flags


def build_vertical_label(prod: dict[str, Any]) -> str:
    pcts = prod.get("vertical_upper_pcts", [0.15, 0.20])
    labels = [f"60DTE ATM/+{int(float(p) * 100)}%" for p in pcts]
    return " | ".join(labels)


def build_exit_rule_label(prod: dict[str, Any]) -> str:
    exits = prod.get("exit_rules", {})
    profit = float(exits.get("profit_take", 1.25))
    days = int(exits.get("time_stop_days", 10))
    gain = float(exits.get("time_stop_underlying_gain", 0.05))
    return f"+{profit * 100:.0f}% profit take; {days}D +{gain * 100:.0f}% underlying time-stop after human theme check"


def enrich_option_liquidity(candidates: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    prod = production_config(config)
    liquidity_cfg = prod.get("option_liquidity", {})
    if candidates.empty or not liquidity_cfg.get("enabled", True):
        if not candidates.empty:
            candidates["option_liquidity_ok"] = True
            candidates["option_liquidity"] = "Skipped"
            candidates["alert_rank"] = "S"
        return candidates

    import yfinance as yf

    rows = []
    for _, row in candidates.iterrows():
        r = row.copy()
        try:
            liq = evaluate_option_liquidity(
                ticker=str(row["ticker"]),
                spot=float(row["close"]),
                yf_module=yf,
                prod=prod,
            )
            for k, v in liq.items():
                r[k] = v
        except Exception as exc:
            r["option_liquidity_ok"] = False
            r["option_liquidity"] = f"Error: {exc}"
        r["alert_rank"] = "S" if bool(r.get("option_liquidity_ok", False)) else "A"
        risk_flags = build_risk_flags(r, prod)
        if not bool(r.get("option_liquidity_ok", False)):
            risk_flags.append("OptionLiquidityWeak")
        iv_val = r.get("iv")
        if iv_val is not None and not pd.isna(iv_val) and float(iv_val) >= float(prod.get("iv_warning_threshold", 1.0)):
            risk_flags.append("IV>100%")
            r["suggested_verticals"] = "60DTE ATM/+15% emphasized | ATM/+20% secondary"
        r["risk_flags"] = ", ".join(risk_flags) or "None"
        rows.append(r)
        time.sleep(0.05)
    out = pd.DataFrame(rows)
    rank_order = {"S": 0, "A": 1}
    out["rank_order"] = out["alert_rank"].map(rank_order).fillna(99)
    return out.sort_values(["rank_order", "standard_rs_score", "volume_multiple"], ascending=[True, False, False]).drop(columns=["rank_order"])


def evaluate_option_liquidity(ticker: str, spot: float, yf_module: Any, prod: dict[str, Any]) -> dict[str, Any]:
    tk = yf_module.Ticker(ticker)
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    expiries = []
    for exp in getattr(tk, "options", []) or []:
        exp_dt = pd.to_datetime(exp)
        dte = int((exp_dt - today).days)
        if int(prod.get("dte_min", 45)) <= dte <= int(prod.get("dte_max", 100)):
            expiries.append((abs(dte - int(prod.get("dte_target", 60))), dte, exp))
    if not expiries:
        return {"option_liquidity_ok": False, "option_liquidity": "No 45-100DTE chain", "iv": math.nan}
    _, dte, exp = sorted(expiries)[0]
    chain = tk.option_chain(exp)
    calls = chain.calls.copy()
    if calls.empty:
        return {"option_liquidity_ok": False, "option_liquidity": "No calls", "iv": math.nan}
    calls["strike_distance"] = (calls["strike"] - spot).abs()
    atm = calls.sort_values("strike_distance").iloc[0]
    bid = float(atm.get("bid", 0) or 0)
    ask = float(atm.get("ask", 0) or 0)
    mid = (bid + ask) / 2 if ask > 0 else 0
    rel_spread = (ask - bid) / mid if mid > 0 else math.inf
    oi = float(atm.get("openInterest", 0) or 0)
    vol = float(atm.get("volume", 0) or 0)
    iv = float(atm.get("impliedVolatility", math.nan))
    cfg = prod.get("option_liquidity", {})
    ok = (
        bid > 0
        and ask > 0
        and rel_spread <= float(cfg.get("max_relative_spread", 0.30))
        and (ask - bid) <= float(cfg.get("max_spread_abs", 1.00))
        and oi >= float(cfg.get("min_open_interest", 50))
        and vol >= float(cfg.get("min_volume", 0))
    )
    label = f"{'OK' if ok else 'Weak'}: {exp} {dte}DTE ATM {atm['strike']:.2f}, spread {rel_spread:.0%}, OI {oi:.0f}, vol {vol:.0f}"
    return {"option_liquidity_ok": bool(ok), "option_liquidity": label, "iv": iv, "option_expiry": exp, "option_dte": dte}


def select_legacy_alert_candidates(results: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
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
    if config.get("notify", {}).get("mode") == "production_momentum":
        return build_production_message(candidates, csv_path, config, limit)

    sections = ["🚨 Daily Scanner Alert"]
    headings = [("S", "🔥 S Rank"), ("A", "🚨 A Rank"), ("B", "⚠️ B Rank")]
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


def build_production_message(candidates: pd.DataFrame, csv_path: Path, config: dict[str, Any], limit: int = 10) -> str:
    prod = production_config(config)
    ref = config.get("notify", {}).get("backtest_reference", {})
    sections = [
        "🚨 Production Momentum Alert",
        f"Rule: RS>={prod.get('rs_min', 98)} | Close > prior {prod.get('breakout_lookback_days', 20)}D High | Volume>={prod.get('volume_multiple_min', 1.2)}x | MarketCap displayed only",
        f"OOS reference: PF {ref.get('test_pf', 'N/A')} | Avg {format_pct(ref.get('test_avg_return'))} | Win {format_pct(ref.get('test_win_rate'))}",
        "Regime: RS98 breadth rising/falling = N/A in this run",
    ]
    headings = [("S", "🔥 S級: Option Liquidity OK"), ("A", "🚨 A級 / Review: Liquidity unchecked or weak")]
    shown = 0
    rank_col = "alert_rank" if "alert_rank" in candidates.columns else "rank"
    for rank, heading in headings:
        group = candidates[candidates[rank_col] == rank].head(max(0, limit - shown))
        if group.empty:
            continue
        sections.append(heading)
        for _, row in group.iterrows():
            sections.append(_format_production_candidate_block(row))
            shown += 1
        if shown >= limit:
            break
    if len(candidates) > shown:
        sections.append(f"... plus {len(candidates) - shown} more signals in `{csv_path}`")
    return "\n\n".join(sections)


def _format_production_candidate_block(row: pd.Series) -> str:
    flags = row.get("risk_flags", "None")
    return (
        "{ticker}\n"
        "Rank: {rank}\n"
        "RS: {rs:.0f} | Breakout RS: {breakout_rs:.0f}\n"
        "Close/Pivot: {close:.2f} / {pivot:.2f}\n"
        "Volume Multiple: {vol_mult:.2f}x | Avg Vol: {avg_vol}\n"
        "Market Cap: {mcap} ({bucket})\n"
        "Gap: {gap}\n"
        "Option Liquidity: {liq}\n"
        "IV: {iv}\n"
        "Suggested: {verticals}\n"
        "Exit: {exit_rule}\n"
        "Flags: {flags}\n"
        "--------------------------------"
    ).format(
        ticker=row["ticker"],
        rank=row.get("alert_rank", row.get("rank", "A")),
        rs=float(row["standard_rs_score"]),
        breakout_rs=float(row["breakout_rs_score"]),
        close=float(row["close"]),
        pivot=float(row["pivot"]),
        vol_mult=float(row["volume_multiple"]),
        avg_vol=format_number(row["avg_volume_50d"]),
        mcap=format_number(row.get("market_cap")),
        bucket=row.get("market_cap_bucket", market_cap_bucket(row.get("market_cap"))),
        gap=format_pct(row.get("gap_pct")),
        liq=row.get("option_liquidity", "Unchecked"),
        iv=format_pct(row.get("iv")),
        verticals=row.get("suggested_verticals", "60DTE ATM/+15% | ATM/+20%"),
        exit_rule=row.get("exit_rule", "+125% profit take"),
        flags=flags,
    )


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
    if notify.get("mode") == "production_momentum":
        candidates = enrich_option_liquidity(candidates, config)
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
