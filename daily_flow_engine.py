#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

DEFAULT_TICKERS = ["SPY", "QQQ", "SOXX", "SMH", "MU", "DRAM"]

LEVERAGED_ETFS = {
    "TQQQ": {"underlying": "QQQ", "leverage": 3.0},
    "QLD": {"underlying": "QQQ", "leverage": 2.0},
    "SQQQ": {"underlying": "QQQ", "leverage": -3.0},
    "SOXL": {"underlying": "SOXX", "leverage": 3.0},
    "SOXS": {"underlying": "SOXX", "leverage": -3.0},
}

def today_str():
    return pd.Timestamp.today().strftime("%Y-%m-%d")

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def hist(ticker, period="1y"):
    df = yf.Ticker(ticker).history(period=period, auto_adjust=False)
    if df.empty:
        raise RuntimeError(f"No data: {ticker}")
    return df

def rv(close, window):
    r = np.log(close / close.shift(1)).dropna()
    if len(r) < window:
        return np.nan
    return float(r.tail(window).std() * math.sqrt(252))

def cta_signal(ticker):
    close = hist(ticker, "1y")["Close"].dropna()
    spot = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) > 1 else np.nan
    ret1d = spot / prev - 1.0 if prev and prev > 0 else np.nan

    out = {"date": today_str(), "ticker": ticker, "spot": spot, "ret1d": ret1d}
    score = 0
    flow_proxy = 0.0
    notes = []
    for w in [20, 50, 100, 200]:
        ma = float(close.rolling(w).mean().iloc[-1]) if len(close) >= w else np.nan
        out[f"ma{w}"] = ma
        if not pd.isna(ma):
            dist = spot / ma - 1.0
            out[f"dist_ma{w}"] = dist
            score += 1 if dist > 0 else -1
            if abs(dist) < 0.01:
                notes.append(f"near MA{w}")
                flow_proxy += (0.01 - abs(dist)) * 100
            flow_proxy += min(max(dist, -0.05), 0.05) * (10 if dist > 0 else 20)
        else:
            out[f"dist_ma{w}"] = np.nan

    out["cta_score"] = score
    out["cta_regime"] = "CTA_LONG" if score >= 3 else ("CTA_SELL_RISK" if score <= -3 else "CTA_MIXED")
    out["cta_flow_proxy"] = flow_proxy
    out["cta_notes"] = "; ".join(notes)
    out["rv20"] = rv(close, 20)
    out["rv60"] = rv(close, 60)
    return out

def leveraged_etf_flows():
    rows = []
    for etf, meta in LEVERAGED_ETFS.items():
        try:
            e = hist(etf, "10d")
            u = hist(meta["underlying"], "10d")
            ep = e["Close"].dropna()
            up = u["Close"].dropna()
            etf_px = float(ep.iloc[-1])
            etf_ret = float(ep.iloc[-1] / ep.iloc[-2] - 1.0)
            und_ret = float(up.iloc[-1] / up.iloc[-2] - 1.0)
            volume = float(e["Volume"].dropna().iloc[-1])
            dollar_volume = volume * etf_px
            L = meta["leverage"]
            rebalance_proxy = dollar_volume * 0.10 * L * (L - 1.0) * und_ret
            creation_proxy = dollar_volume * 0.03 * np.sign(etf_ret - L * und_ret)
            rows.append({
                "date": today_str(), "etf": etf, "underlying": meta["underlying"], "leverage": L,
                "etf_price": etf_px, "etf_ret1d": etf_ret, "underlying_ret1d": und_ret,
                "volume": volume, "dollar_volume": dollar_volume,
                "rebalance_flow_proxy": rebalance_proxy,
                "creation_flow_proxy": creation_proxy,
                "total_flow_proxy": rebalance_proxy + creation_proxy,
            })
        except Exception as exc:
            rows.append({"date": today_str(), "etf": etf, "error": str(exc)})
    return pd.DataFrame(rows)

def vol_control_proxy(tickers):
    rows = []
    for t in tickers:
        try:
            close = hist(t, "1y")["Close"].dropna()
            rv20 = rv(close, 20)
            prev_rv20 = rv(close.iloc[:-1], 20)
            target = 0.10
            exp = min(1.5, target / rv20) if rv20 and rv20 > 0 else np.nan
            prev_exp = min(1.5, target / prev_rv20) if prev_rv20 and prev_rv20 > 0 else np.nan
            change = exp - prev_exp if not pd.isna(exp) and not pd.isna(prev_exp) else np.nan
            rows.append({
                "date": today_str(), "ticker": t, "spot": float(close.iloc[-1]),
                "ret1d": float(close.iloc[-1]/close.iloc[-2]-1.0),
                "rv20": rv20, "rv60": rv(close, 60),
                "vol_control_exposure_proxy": exp,
                "vol_control_exposure_change": change,
                "vol_control_flow_proxy": change * 100 if not pd.isna(change) else np.nan,
                "regime": "VOL_CONTROL_BUY" if change and change > 0 else ("VOL_CONTROL_SELL" if change and change < 0 else "NEUTRAL"),
            })
        except Exception as exc:
            rows.append({"date": today_str(), "ticker": t, "error": str(exc)})
    return pd.DataFrame(rows)

def market_down_rs(tickers, benchmark="QQQ"):
    bench_close = hist(benchmark, "6mo")["Close"].dropna()
    bench_ret = bench_close.pct_change()
    down_idx = bench_ret[bench_ret < -0.005].index
    rows = []
    for t in tickers:
        try:
            close = hist(t, "6mo")["Close"].dropna()
            ret = close.pct_change()
            aligned = pd.DataFrame({"stock": ret, "bench": bench_ret}).dropna()
            dd = aligned.loc[aligned.index.intersection(down_idx)]
            if dd.empty:
                hit = excess = score = np.nan
            else:
                ex = dd["stock"] - dd["bench"]
                hit = float((ex > 0).mean())
                excess = float(ex.mean())
                score = hit * 70 + max(min(excess * 100, 10), -10) * 3
            rows.append({
                "date": today_str(), "ticker": t, "benchmark": benchmark,
                "down_day_count": len(dd), "down_day_rs_hit_rate": hit,
                "down_day_avg_excess_return": excess, "down_day_rs_score": score,
            })
        except Exception as exc:
            rows.append({"date": today_str(), "ticker": t, "error": str(exc)})
    return pd.DataFrame(rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    ap.add_argument("--outdir", default="daily_flow_outputs")
    args = ap.parse_args()

    outdir = Path(args.outdir) / today_str()
    ensure_dir(outdir)

    cta = pd.DataFrame([cta_signal(t) for t in args.tickers])
    etf = leveraged_etf_flows()
    vc = vol_control_proxy(["SPY", "QQQ"])
    rs = market_down_rs(args.tickers, "QQQ")

    cta.to_csv(outdir / "cta_signals.csv", index=False)
    etf.to_csv(outdir / "leveraged_etf_flows.csv", index=False)
    vc.to_csv(outdir / "vol_control_proxy.csv", index=False)
    rs.to_csv(outdir / "market_down_rs.csv", index=False)

    report = "# Daily Flow Engine Report\n\n"
    report += f"Date: {today_str()}\n\n"
    for title, df in [("CTA", cta), ("Leveraged ETF Flow Proxy", etf), ("Vol Control Proxy", vc), ("Market-Down RS", rs)]:
        report += f"## {title}\n\n"
        report += df.to_markdown(index=False)
        report += "\n\n"
    (outdir / "daily_flow_report.md").write_text(report, encoding="utf-8")
    print(f"Saved to {outdir}")

if __name__ == "__main__":
    main()
