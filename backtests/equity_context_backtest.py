#!/usr/bin/env python3
"""
Equity/context and option-proxy backtest for the Russell1000 momentum scanner.

This is intentionally skeptical:
- Uses next-day entry.
- Applies a per-ticker cooldown to reduce repeated overlapping signals.
- Reports bad variants and small sample sizes.
- Clearly labels the option test as a Black-Scholes proxy, not a real option-chain backtest.

The scanner here is a vectorized approximation of the current daily scanner rules.
It is designed for research speed and robustness, not a perfect recreation of every
latest-snapshot module detail.
"""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests


IWB_PORTFOLIO_ID = "239707"
BENCHMARK = "QQQ"


@dataclass
class BacktestConfig:
    period: str = "5y"
    min_price: float = 10.0
    min_avg_volume_50d: float = 2_000_000
    min_market_cap: float = 2_000_000_000
    cooldown_days: int = 20
    max_tickers: int | None = None
    fetch_market_caps: bool = False
    outdir: Path = Path("output/backtests")


def clean_ticker(ticker: str) -> str:
    symbol = str(ticker).strip().upper().replace(".", "-")
    mapping = {
        "BRKB": "BRK-B",
        "BFA": "BF-A",
        "BFB": "BF-B",
        "HEIA": "HEI-A",
        "LENB": "LEN-B",
        "MOGA": "MOG-A",
        "UHALB": "UHAL-B",
    }
    return mapping.get(symbol, symbol)


def parse_iwb_holdings(cache_path: Path) -> pd.DataFrame:
    if cache_path.exists():
        return pd.read_csv(cache_path)

    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
    import warnings

    url = (
        "https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document"
        f"?appType=PRODUCT_PAGE&appSubType=ISHARES&targetSite=us-ishares&locale=en_US&portfolioId={IWB_PORTFOLIO_ID}"
        "&component=fundDownload&userType=individual"
    )
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 momentum-backtest"}, timeout=90)
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

    out = pd.DataFrame(holdings).drop_duplicates("ticker").sort_values("ticker")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(cache_path, index=False)
    return out


def download_ohlcv(tickers: list[str], period: str, chunk_size: int = 80) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    histories: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        print(f"Downloading {i + 1}-{i + len(chunk)} / {len(tickers)}", flush=True)
        raw = yf.download(
            chunk,
            period=period,
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by="ticker",
            timeout=60,
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
            if len(cols) != 5:
                continue
            df = df[cols].dropna(subset=["Close"])
            if len(df) >= 260:
                histories[ticker] = df
        time.sleep(0.2)
    return histories


def fetch_market_caps(tickers: list[str], cache_path: Path) -> dict[str, float]:
    if cache_path.exists():
        raw = pd.read_csv(cache_path)
        return dict(zip(raw["ticker"].astype(str), raw["market_cap"].astype(float)))

    import yfinance as yf

    rows = []
    for idx, ticker in enumerate(tickers, start=1):
        if idx % 50 == 1:
            print(f"Fetching market caps {idx}-{min(idx + 49, len(tickers))} / {len(tickers)}", flush=True)
        cap = np.nan
        try:
            fast = yf.Ticker(ticker).fast_info or {}
            cap = fast.get("marketCap", fast.get("market_cap", np.nan))
        except Exception:
            pass
        rows.append({"ticker": ticker, "market_cap": cap})
        time.sleep(0.03)

    df = pd.DataFrame(rows)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False)
    return dict(zip(df["ticker"].astype(str), pd.to_numeric(df["market_cap"], errors="coerce")))


def make_panel(histories: dict[str, pd.DataFrame], field: str) -> pd.DataFrame:
    return pd.concat({t: df[field] for t, df in histories.items()}, axis=1).sort_index()


def rank_pct(df: pd.DataFrame) -> pd.DataFrame:
    return df.rank(axis=1, pct=True) * 100.0


def rolling_slope_positive(df: pd.DataFrame, window: int) -> pd.DataFrame:
    return (df - df.shift(window)) > 0


def compute_scores(open_: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, volume: pd.DataFrame, benchmark: str, sector_map: dict[str, str]) -> dict[str, pd.DataFrame]:
    daily_ret = close.pct_change()
    sma50 = close.rolling(50).mean()
    sma150 = close.rolling(150).mean()
    sma200 = close.rolling(200).mean()
    high252 = close.rolling(252).max()
    low252 = close.rolling(252).min()
    trend_passed = ((close > sma150) & (close > sma200) & (sma150 > sma200) & (sma200 > sma200.shift(20)) & (sma50 > sma150) & (close >= high252 * 0.75) & (close >= low252 * 1.30))

    ret20 = close / close.shift(20) - 1
    ret63 = close / close.shift(63) - 1
    ret126 = close / close.shift(126) - 1
    standard_rs = rank_pct(ret126)
    breakout_rs = (rank_pct(ret20) * 0.60 + rank_pct(ret63) * 0.40).clip(0, 100)

    qret = daily_ret[benchmark]
    down_mask = qret <= -0.005
    excess = daily_ret.sub(qret, axis=0)
    defensive_raw = excess.where(down_mask, np.nan).rolling(60, min_periods=5).mean()
    defensive_rs = rank_pct(defensive_raw)

    sector_rs = pd.DataFrame(index=close.index, columns=close.columns, dtype=float)
    sectors = pd.Series(sector_map)
    for _, members in sectors.groupby(sectors).groups.items():
        cols = [c for c in members if c in ret63.columns]
        if len(cols) >= 3:
            sector_rs[cols] = rank_pct(ret63[cols])
    sector_rs = sector_rs.fillna(rank_pct(ret63))

    prev_close = close.shift(1)
    tr = pd.concat([(high - low).stack(), (high - prev_close).abs().stack(), (low - prev_close).abs().stack()], axis=1).max(axis=1).unstack()
    atr20_pct = tr.rolling(20).mean() / close
    atr60_pct = tr.rolling(60).mean() / close
    vol5_50 = volume.rolling(5).mean() / volume.rolling(50).mean()
    close_range5 = (high.rolling(5).max() - low.rolling(5).min()) / close
    vcp_score = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    vcp_score += np.where(atr20_pct < atr60_pct * 0.85, 35, np.where(atr20_pct < atr60_pct, 20, 0))
    vcp_score += np.where(vol5_50 < 0.70, 35, np.where(vol5_50 < 0.90, 20, 0))
    vcp_score += np.where(close_range5 < 0.06, 20, np.where(close_range5 < 0.10, 10, 0))
    vcp_score = vcp_score.clip(0, 100)

    pivot = high.rolling(252).max().shift(1)
    distance_to_pivot = (pivot - close) / close
    avg_vol50 = volume.rolling(50).mean()
    clv = ((close - low) / (high - low).replace(0, np.nan)).clip(0, 1)
    down_day = daily_ret < 0
    down_vol_ratio = volume.where(down_day).rolling(20, min_periods=5).mean() / volume.rolling(50).mean()
    up_vol = volume.where(daily_ret > 0).rolling(20, min_periods=5).sum()
    down_vol = volume.where(daily_ret < 0).rolling(20, min_periods=5).sum()
    up_down_vol_ratio = up_vol / down_vol.replace(0, np.nan)
    obv = (np.sign(daily_ret.fillna(0)) * volume).cumsum()
    obv_up20 = rolling_slope_positive(obv, 20)

    accumulation = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    accumulation += np.where(clv.rolling(20).mean() > 0.58, 25, np.where(clv.rolling(20).mean() > 0.50, 15, 0))
    accumulation += np.where(down_vol_ratio < 0.85, 25, np.where(down_vol_ratio < 1.05, 15, 0))
    accumulation += np.where(up_down_vol_ratio > 1.25, 25, np.where(up_down_vol_ratio > 1.0, 15, 0))
    accumulation += np.where(obv_up20, 25, 0)
    accumulation = accumulation.clip(0, 100)

    drawdown60 = close / close.rolling(60).max() - 1
    clv_down = clv.where(down_day).rolling(20, min_periods=5).mean()
    rebound = ((daily_ret.shift(1) < -0.03) & (daily_ret > 0.02) & (volume > volume.shift(1))).rolling(20).sum()
    absorption = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    absorption += np.where(down_vol_ratio < 0.75, 20, np.where(down_vol_ratio < 0.95, 12, 0))
    absorption += np.where(clv_down > 0.62, 20, np.where(clv_down > 0.52, 12, 0))
    absorption += np.where(obv_up20, 20, 0)
    absorption += np.where(drawdown60 > -0.08, 20, np.where(drawdown60 > -0.15, 12, 0))
    absorption += np.where(rebound >= 2, 20, np.where(rebound >= 1, 10, 0))
    absorption = absorption.clip(0, 100)
    rv20 = daily_ret.rolling(20).std() * np.sqrt(252)

    return {"trend_passed": trend_passed, "standard_rs_score": standard_rs, "breakout_rs_score": breakout_rs, "defensive_rs_score": defensive_rs, "sector_rs_score": sector_rs, "vcp_score": vcp_score, "accumulation_score": accumulation, "absorption_score": absorption, "distance_to_pivot": distance_to_pivot, "avg_volume_50d": avg_vol50, "pivot": pivot, "rv20": rv20, "atr20_pct": atr20_pct}


def apply_cooldown(dates: list[pd.Timestamp], cooldown_days: int) -> list[pd.Timestamp]:
    kept = []
    next_ok = None
    for d in sorted(dates):
        if next_ok is None or d > next_ok:
            kept.append(d)
            next_ok = d + pd.tseries.offsets.BDay(cooldown_days)
    return kept


def build_trades(scores: dict[str, pd.DataFrame], open_: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, market_caps: dict[str, float], sector_map: dict[str, str], cfg: BacktestConfig) -> pd.DataFrame:
    cols = [c for c in close.columns if c != BENCHMARK]
    mc = pd.Series({c: market_caps.get(c, np.nan) for c in cols})
    core = (scores["trend_passed"][cols] & (scores["standard_rs_score"][cols] >= 95) & (scores["breakout_rs_score"][cols] >= 95) & (scores["accumulation_score"][cols] >= 30) & (scores["vcp_score"][cols] >= 50) & (scores["distance_to_pivot"][cols] >= 0) & (scores["distance_to_pivot"][cols] <= 0.12) & (scores["avg_volume_50d"][cols] >= cfg.min_avg_volume_50d) & (close[cols] >= cfg.min_price))
    if cfg.fetch_market_caps:
        cap_ok = mc >= cfg.min_market_cap
        core = core & pd.DataFrame([cap_ok] * len(core), index=core.index)

    rows = []
    for ticker in cols:
        signal_dates = list(core.index[core[ticker].fillna(False)])
        signal_dates = apply_cooldown(signal_dates, cfg.cooldown_days)
        for d in signal_dates:
            loc = close.index.get_loc(d)
            if isinstance(loc, slice) or loc + 41 >= len(close.index):
                continue
            entry_date = close.index[loc + 1]
            entry_price = open_.at[entry_date, ticker]
            if not np.isfinite(entry_price) or entry_price <= 0:
                entry_price = close.at[entry_date, ticker]
            if not np.isfinite(entry_price) or entry_price <= 0:
                continue
            future_slice = slice(loc + 1, min(loc + 41, len(close.index) - 1) + 1)
            fut_high = high[ticker].iloc[future_slice]
            fut_low = low[ticker].iloc[future_slice]
            fut_close = close[ticker].iloc[future_slice]
            rec = {"ticker": ticker, "sector": sector_map.get(ticker, ""), "signal_date": d.date().isoformat(), "entry_date": entry_date.date().isoformat(), "entry_price": float(entry_price), "close_on_signal": float(close.at[d, ticker]), "market_cap_current_proxy": market_caps.get(ticker, np.nan)}
            for name in ["standard_rs_score", "breakout_rs_score", "defensive_rs_score", "sector_rs_score", "vcp_score", "accumulation_score", "absorption_score", "distance_to_pivot", "avg_volume_50d", "rv20", "atr20_pct"]:
                rec[name] = float(scores[name].at[d, ticker]) if pd.notna(scores[name].at[d, ticker]) else np.nan
            for n in [5, 10, 20, 40]:
                if len(fut_close) >= n:
                    rec[f"return_{n}d_close"] = float(fut_close.iloc[n - 1] / entry_price - 1)
                    rec[f"mfe_{n}d"] = float(fut_high.iloc[:n].max() / entry_price - 1)
                    rec[f"mae_{n}d"] = float(fut_low.iloc[:n].min() / entry_price - 1)
            if "mfe_20d" in rec:
                rec["hit_10pct_20d"] = rec["mfe_20d"] >= 0.10
                rec["hit_15pct_20d"] = rec["mfe_20d"] >= 0.15
                rec["hit_20pct_20d"] = rec["mfe_20d"] >= 0.20
            rows.append(rec)
    return pd.DataFrame(rows)


def summarize_variant(df: pd.DataFrame, name: str) -> dict[str, Any]:
    out = {"variant": name, "signals": len(df)}
    if df.empty:
        return out
    for hit in ["hit_10pct_20d", "hit_15pct_20d", "hit_20pct_20d"]:
        out[hit] = float(df[hit].mean()) if hit in df else np.nan
    for col in ["return_5d_close", "return_10d_close", "return_20d_close", "return_40d_close", "mae_20d", "mfe_20d"]:
        if col in df:
            out[f"avg_{col}"] = float(df[col].mean())
            out[f"median_{col}"] = float(df[col].median())
            out[f"worst_{col}"] = float(df[col].min())
            out[f"best_{col}"] = float(df[col].max())
    return out


def make_variants(trades: pd.DataFrame) -> pd.DataFrame:
    variants = {
        "core_only": pd.Series(True, index=trades.index),
        "core_absorption_ge_60": trades["absorption_score"] >= 60,
        "core_absorption_ge_70": trades["absorption_score"] >= 70,
        "core_defensive_ge_60": trades["defensive_rs_score"] >= 60,
        "core_defensive_ge_70": trades["defensive_rs_score"] >= 70,
        "core_sector_ge_70": trades["sector_rs_score"] >= 70,
        "core_abs60_sector70": (trades["absorption_score"] >= 60) & (trades["sector_rs_score"] >= 70),
        "core_abs60_def60": (trades["absorption_score"] >= 60) & (trades["defensive_rs_score"] >= 60),
        "core_abs60_sector70_def60": (trades["absorption_score"] >= 60) & (trades["sector_rs_score"] >= 70) & (trades["defensive_rs_score"] >= 60),
        "core_atr_ge_3p5": trades["atr20_pct"] >= 0.035,
    }
    rows = [summarize_variant(trades[mask.fillna(False)], name) for name, mask in variants.items()]
    return pd.DataFrame(rows).sort_values(["hit_15pct_20d", "signals"], ascending=[False, False], na_position="last")


def by_year(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    x = trades.copy()
    x["year"] = pd.to_datetime(x["signal_date"]).dt.year
    return x.groupby("year").apply(lambda g: pd.Series(summarize_variant(g, str(g.name)))).reset_index(drop=True)


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(S: float, K: float, T: float, sigma: float, r: float = 0.04) -> float:
    if T <= 0:
        return max(S - K, 0.0)
    sigma = max(float(sigma), 0.05)
    if S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)


def bs_delta(S: float, K: float, T: float, sigma: float, r: float = 0.04) -> float:
    if T <= 0:
        return 1.0 if S > K else 0.0
    sigma = max(float(sigma), 0.05)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return norm_cdf(d1)


def strike_for_delta(S: float, T: float, sigma: float, target_delta: float = 0.60) -> float:
    lo, hi = S * 0.50, S * 1.50
    for _ in range(50):
        mid = (lo + hi) / 2
        if bs_delta(S, mid, T, sigma) > target_delta:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def option_proxy_backtest(trades: pd.DataFrame, close: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    if trades.empty:
        return pd.DataFrame(), pd.DataFrame()
    date_index = close.index
    for _, tr in trades.iterrows():
        ticker = tr["ticker"]
        if ticker not in close.columns:
            continue
        entry_date = pd.Timestamp(tr["entry_date"])
        if entry_date not in date_index:
            continue
        loc = date_index.get_loc(entry_date)
        if isinstance(loc, slice):
            continue
        S0 = float(tr["entry_price"])
        sigma = float(tr.get("rv20", np.nan))
        if not np.isfinite(sigma) or sigma <= 0:
            sigma = 0.45
        sigma = float(np.clip(sigma, 0.20, 1.50))
        path = close[ticker].iloc[loc : min(loc + 41, len(date_index))].dropna()
        if len(path) < 5:
            continue
        for dte in [45, 60, 90, 120]:
            T0 = dte / 252.0
            K_long = strike_for_delta(S0, T0, sigma, 0.60)
            for width_pct in [0.10, 0.15, 0.20]:
                K_short = max(K_long * 1.02, S0 * (1 + width_pct))
                prem0_mid = bs_call(S0, K_long, T0, sigma) - bs_call(S0, K_short, T0, sigma)
                if prem0_mid <= 0:
                    continue
                prem0 = prem0_mid * 1.05
                for tp in [0.50, 0.75, 1.00]:
                    for sl in [-0.30, -0.50]:
                        exit_ret = None
                        exit_day = None
                        exit_reason = None
                        for j, (_, Sj) in enumerate(path.iloc[1:21].items(), start=1):
                            Tj = max((dte - j) / 252.0, 0.0)
                            premj_mid = bs_call(float(Sj), K_long, Tj, sigma) - bs_call(float(Sj), K_short, Tj, sigma)
                            ret = premj_mid * 0.95 / prem0 - 1
                            if ret >= tp:
                                exit_ret, exit_day, exit_reason = ret, j, f"tp_{tp:.0%}"
                                break
                            if ret <= sl:
                                exit_ret, exit_day, exit_reason = ret, j, f"sl_{sl:.0%}"
                                break
                        if exit_ret is None:
                            Sj = float(path.iloc[min(20, len(path) - 1)])
                            Tj = max((dte - min(20, len(path) - 1)) / 252.0, 0.0)
                            premj_mid = bs_call(Sj, K_long, Tj, sigma) - bs_call(Sj, K_short, Tj, sigma)
                            exit_ret = premj_mid * 0.95 / prem0 - 1
                            exit_day = min(20, len(path) - 1)
                            exit_reason = "time_20d"
                        rows.append({"ticker": ticker, "signal_date": tr["signal_date"], "entry_date": tr["entry_date"], "dte": dte, "width_pct": width_pct, "tp": tp, "sl": sl, "entry_price": S0, "iv_proxy": sigma, "k_long": K_long, "k_short": K_short, "entry_debit_proxy": prem0, "return": float(exit_ret), "exit_day": exit_day, "exit_reason": exit_reason, "absorption_score": tr.get("absorption_score", np.nan), "sector_rs_score": tr.get("sector_rs_score", np.nan), "defensive_rs_score": tr.get("defensive_rs_score", np.nan)})
    opt = pd.DataFrame(rows)
    if opt.empty:
        return opt, pd.DataFrame()
    summary = opt.groupby(["dte", "width_pct", "tp", "sl"]).agg(trades=("return", "size"), win_rate=("return", lambda s: float((s > 0).mean())), avg_return=("return", "mean"), median_return=("return", "median"), worst_return=("return", "min"), best_return=("return", "max"), avg_exit_day=("exit_day", "mean")).reset_index().sort_values(["avg_return", "win_rate"], ascending=[False, False])
    return opt, summary


def write_report(cfg: BacktestConfig, holdings: pd.DataFrame, histories: dict[str, pd.DataFrame], trades: pd.DataFrame, variants: pd.DataFrame, option_summary: pd.DataFrame, outdir: Path) -> None:
    lines = []
    lines.append("# Momentum Scanner Backtest Diagnostics")
    lines.append("")
    lines.append("## Scope")
    lines.append("- Universe: current Russell1000 / IWB holdings.")
    lines.append(f"- Tickers loaded from holdings: {len(holdings)}")
    lines.append(f"- Price histories downloaded: {len(histories)}")
    lines.append(f"- Period argument: `{cfg.period}`")
    lines.append(f"- Per-ticker cooldown: {cfg.cooldown_days} trading days")
    lines.append("")
    lines.append("## Important limitations")
    lines.append("- This uses current IWB holdings, so it has survivorship bias.")
    lines.append("- Historical Russell1000 constituents are not used.")
    lines.append("- Market cap, if enabled, is a current proxy and not historical.")
    lines.append("- The vectorized scanner is an approximation of the latest daily scanner, not a perfect line-by-line replay.")
    lines.append("- Option strategy results are Black-Scholes proxy results using realized-volatility proxy IV, not historical option-chain prices.")
    lines.append("- Treat results as research / decision support only.")
    lines.append("")
    lines.append("## Equity summary")
    if trades.empty:
        lines.append("No trades generated.")
    else:
        lines.append(f"- Core signals after cooldown: {len(trades)}")
        lines.append(f"- Date range: {trades['signal_date'].min()} to {trades['signal_date'].max()}")
        lines.append("")
        lines.append("### Top variants by +15% hit rate")
        lines.append(variants.head(10).to_markdown(index=False))
    lines.append("")
    lines.append("## Option proxy summary")
    if option_summary.empty:
        lines.append("No option proxy trades generated.")
    else:
        lines.append(option_summary.head(15).to_markdown(index=False))
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "backtest_diagnostics.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", default="5y")
    parser.add_argument("--outdir", default="output/backtests")
    parser.add_argument("--max-tickers", type=int, default=None)
    parser.add_argument("--fetch-market-caps", action="store_true")
    parser.add_argument("--cooldown-days", type=int, default=20)
    parser.add_argument("--skip-option-proxy", action="store_true")
    args = parser.parse_args()
    cfg = BacktestConfig(period=args.period, max_tickers=args.max_tickers, fetch_market_caps=args.fetch_market_caps, cooldown_days=args.cooldown_days, outdir=Path(args.outdir))
    cfg.outdir.mkdir(parents=True, exist_ok=True)
    holdings = parse_iwb_holdings(Path("cache/russell1000_iwb_holdings.csv"))
    tickers = sorted(set(holdings["ticker"].map(clean_ticker).tolist()))
    if cfg.max_tickers:
        tickers = tickers[: cfg.max_tickers]
    tickers = sorted(set(tickers + [BENCHMARK]))
    sector_map = dict(zip(holdings["ticker"].map(clean_ticker), holdings["sector"].fillna("")))
    histories = download_ohlcv(tickers, cfg.period)
    if BENCHMARK not in histories:
        raise RuntimeError("QQQ benchmark history is missing")
    histories = {t: df for t, df in histories.items() if len(df.dropna(subset=["Close"])) >= 260}
    open_ = make_panel(histories, "Open")
    high = make_panel(histories, "High")
    low = make_panel(histories, "Low")
    close = make_panel(histories, "Close")
    volume = make_panel(histories, "Volume")
    market_caps = fetch_market_caps([t for t in close.columns if t != BENCHMARK], Path("cache/market_caps_current_proxy.csv")) if cfg.fetch_market_caps else {}
    scores = compute_scores(open_, high, low, close, volume, BENCHMARK, sector_map)
    trades = build_trades(scores, open_, high, low, close, market_caps, sector_map, cfg)
    variants = make_variants(trades) if not trades.empty else pd.DataFrame()
    yearly = by_year(trades)
    trades.to_csv(cfg.outdir / "equity_backtest_trades.csv", index=False)
    variants.to_csv(cfg.outdir / "equity_backtest_by_variant.csv", index=False)
    yearly.to_csv(cfg.outdir / "equity_backtest_by_year.csv", index=False)
    if not args.skip_option_proxy and not trades.empty:
        opt_trades, opt_summary = option_proxy_backtest(trades, close)
    else:
        opt_trades, opt_summary = pd.DataFrame(), pd.DataFrame()
    opt_trades.to_csv(cfg.outdir / "option_proxy_backtest_trades.csv", index=False)
    opt_summary.to_csv(cfg.outdir / "option_proxy_backtest_summary.csv", index=False)
    write_report(cfg, holdings, histories, trades, variants, opt_summary, cfg.outdir)
    print("Backtest complete.")
    print(f"Output directory: {cfg.outdir}")
    if not variants.empty:
        print(variants.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
