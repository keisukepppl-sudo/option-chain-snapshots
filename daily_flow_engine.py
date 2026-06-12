#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

DEFAULT_TICKERS = ["SPY", "QQQ", "SOXX", "SMH", "MU", "DRAM"]
LEVERAGED_ETFS = {
    "TQQQ": {"underlying": "QQQ", "leverage": 3.0, "issuer": "ProShares"},
    "QLD": {"underlying": "QQQ", "leverage": 2.0, "issuer": "ProShares"},
    "SQQQ": {"underlying": "QQQ", "leverage": -3.0, "issuer": "ProShares"},
    "SOXL": {"underlying": "SOXX", "leverage": 3.0, "issuer": "Direxion"},
    "SOXS": {"underlying": "SOXX", "leverage": -3.0, "issuer": "Direxion"},
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
    return float(r.tail(window).std() * math.sqrt(252)) if len(r) >= window else np.nan

def get_aum_yfinance(ticker: str):
    try:
        info = yf.Ticker(ticker).info or {}
        for key in ["totalAssets", "netAssets"]:
            val = info.get(key)
            if val and float(val) > 0:
                return float(val), f"yfinance:{key}"
    except Exception:
        pass
    return np.nan, "missing"

def load_manual_aum(path: Path):
    if not path.exists():
        return pd.DataFrame(columns=["date", "ticker", "aum_manual"])
    df = pd.read_csv(path, comment="#")
    if df.empty:
        return pd.DataFrame(columns=["date", "ticker", "aum_manual"])
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["ticker"] = df["ticker"].astype(str).str.upper()
    df["aum_manual"] = pd.to_numeric(df["aum"], errors="coerce")
    return df[["date", "ticker", "aum_manual"]]

def cta_signal(ticker):
    close = hist(ticker, "1y")["Close"].dropna()
    spot = float(close.iloc[-1])
    ret1d = float(close.iloc[-1] / close.iloc[-2] - 1.0)
    out = {"date": today_str(), "ticker": ticker, "spot": spot, "ret1d": ret1d}
    score, flow, notes = 0, 0.0, []
    for w in [20, 50, 100, 200]:
        ma = float(close.rolling(w).mean().iloc[-1]) if len(close) >= w else np.nan
        out[f"ma{w}"] = ma
        if pd.isna(ma):
            out[f"dist_ma{w}"] = np.nan
            continue
        dist = spot / ma - 1.0
        out[f"dist_ma{w}"] = dist
        score += 1 if dist > 0 else -1
        if abs(dist) < 0.01:
            notes.append(f"near MA{w}")
            flow += (0.01 - abs(dist)) * 100
        flow += min(max(dist, -0.05), 0.05) * (10 if dist > 0 else 20)
    out["cta_score"] = score
    out["cta_regime"] = "CTA_LONG" if score >= 3 else ("CTA_SELL_RISK" if score <= -3 else "CTA_MIXED")
    out["cta_flow_proxy"] = flow
    out["cta_notes"] = "; ".join(notes)
    out["rv20"] = rv(close, 20)
    out["rv60"] = rv(close, 60)
    return out

def leveraged_etf_aum_flows(out_root: Path, manual_aum_path: Path):
    today = today_str()
    manual = load_manual_aum(manual_aum_path)
    hist_file = out_root / "leveraged_etf_aum_history.csv"
    old = pd.read_csv(hist_file) if hist_file.exists() else pd.DataFrame()
    rows = []
    for etf, meta in LEVERAGED_ETFS.items():
        try:
            e = hist(etf, "10d")
            u = hist(meta["underlying"], "10d")
            ep, up = e["Close"].dropna(), u["Close"].dropna()
            etf_px = float(ep.iloc[-1])
            etf_ret = float(ep.iloc[-1] / ep.iloc[-2] - 1.0)
            und_ret = float(up.iloc[-1] / up.iloc[-2] - 1.0)
            volume = float(e["Volume"].dropna().iloc[-1])
            dollar_volume = volume * etf_px
            aum_auto, source = get_aum_yfinance(etf)
            man = manual[(manual["date"] == today) & (manual["ticker"] == etf)]
            if not man.empty and not pd.isna(man["aum_manual"].iloc[-1]):
                aum = float(man["aum_manual"].iloc[-1])
                source = "manual_csv"
            else:
                aum = aum_auto
            prev_aum = np.nan
            if not old.empty and "ticker" in old.columns:
                vals = pd.to_numeric(old[old["ticker"] == etf].sort_values("date")["aum"], errors="coerce").dropna()
                if len(vals):
                    prev_aum = float(vals.iloc[-1])
            L = meta["leverage"]
            if pd.isna(aum):
                creation = dollar_volume * 0.03 * np.sign(etf_ret - L * und_ret)
                rebalance = dollar_volume * 0.10 * L * (L - 1.0) * und_ret
                method = "fallback_volume_proxy"
            else:
                creation = aum - prev_aum * (1.0 + etf_ret) if not pd.isna(prev_aum) else np.nan
                rebalance = aum * L * (L - 1.0) * und_ret
                method = "aum_based"
            total = (0 if pd.isna(creation) else creation) + (0 if pd.isna(rebalance) else rebalance)
            rows.append({
                "date": today, "ticker": etf, "issuer": meta["issuer"], "underlying": meta["underlying"],
                "leverage": L, "etf_price": etf_px, "etf_ret1d": etf_ret, "underlying_ret1d": und_ret,
                "volume": volume, "dollar_volume": dollar_volume, "aum": aum, "prev_aum": prev_aum,
                "aum_source": source, "creation_redemption_flow": creation, "rebalance_flow": rebalance,
                "total_estimated_flow": total, "method": method,
            })
        except Exception as exc:
            rows.append({"date": today, "ticker": etf, "error": str(exc)})
    df = pd.DataFrame(rows)
    combined = pd.concat([old, df], ignore_index=True).drop_duplicates(["date", "ticker"], keep="last") if not old.empty else df.copy()
    ensure_dir(out_root)
    combined.to_csv(hist_file, index=False)
    return df, combined

def vol_control_proxy(tickers):
    rows = []
    for t in tickers:
        try:
            close = hist(t, "1y")["Close"].dropna()
            rv20, prev_rv20 = rv(close, 20), rv(close.iloc[:-1], 20)
            target = 0.10
            exp = min(1.5, target / rv20) if rv20 and rv20 > 0 else np.nan
            prev_exp = min(1.5, target / prev_rv20) if prev_rv20 and prev_rv20 > 0 else np.nan
            change = exp - prev_exp if not pd.isna(exp) and not pd.isna(prev_exp) else np.nan
            rows.append({
                "date": today_str(), "ticker": t, "spot": float(close.iloc[-1]),
                "ret1d": float(close.iloc[-1]/close.iloc[-2]-1.0), "rv20": rv20, "rv60": rv(close, 60),
                "vol_control_exposure_proxy": exp, "vol_control_exposure_change": change,
                "vol_control_flow_proxy": change * 100 if not pd.isna(change) else np.nan,
                "regime": "VOL_CONTROL_BUY" if change and change > 0 else ("VOL_CONTROL_SELL" if change and change < 0 else "NEUTRAL"),
            })
        except Exception as exc:
            rows.append({"date": today_str(), "ticker": t, "error": str(exc)})
    return pd.DataFrame(rows)

def market_down_rs(tickers, benchmark="QQQ"):
    bench = hist(benchmark, "6mo")["Close"].dropna().pct_change()
    down = bench[bench < -0.005].index
    rows = []
    for t in tickers:
        try:
            ret = hist(t, "6mo")["Close"].dropna().pct_change()
            dd = pd.DataFrame({"stock": ret, "bench": bench}).dropna()
            dd = dd.loc[dd.index.intersection(down)]
            if dd.empty:
                hit = excess = score = np.nan
            else:
                ex = dd["stock"] - dd["bench"]
                hit, excess = float((ex > 0).mean()), float(ex.mean())
                score = hit * 70 + max(min(excess * 100, 10), -10) * 3
            rows.append({"date": today_str(), "ticker": t, "benchmark": benchmark, "down_day_count": len(dd),
                         "down_day_rs_hit_rate": hit, "down_day_avg_excess_return": excess, "down_day_rs_score": score})
        except Exception as exc:
            rows.append({"date": today_str(), "ticker": t, "error": str(exc)})
    return pd.DataFrame(rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    ap.add_argument("--outdir", default="daily_flow_outputs")
    ap.add_argument("--manual-aum", default="manual_etf_aum.csv")
    args = ap.parse_args()
    root = Path(args.outdir)
    outdir = root / today_str()
    ensure_dir(outdir)
    cta = pd.DataFrame([cta_signal(t) for t in args.tickers])
    etf_today, etf_hist = leveraged_etf_aum_flows(root, Path(args.manual_aum))
    vc = vol_control_proxy(["SPY", "QQQ"])
    rs = market_down_rs(args.tickers, "QQQ")
    cta.to_csv(outdir / "cta_signals.csv", index=False)
    etf_today.to_csv(outdir / "leveraged_etf_aum_flows.csv", index=False)
    etf_hist.to_csv(root / "leveraged_etf_aum_history.csv", index=False)
    vc.to_csv(outdir / "vol_control_proxy.csv", index=False)
    rs.to_csv(outdir / "market_down_rs.csv", index=False)
    report = "# Daily Flow Engine v2 AUM Report\\n\\n" + f"Date: {today_str()}\\n\\n"
    for title, df in [("CTA", cta), ("Leveraged ETF AUM Flow", etf_today), ("Vol Control Proxy", vc), ("Market-Down RS", rs)]:
        report += f"## {title}\\n\\n" + df.to_markdown(index=False) + "\\n\\n"
    (outdir / "daily_flow_report.md").write_text(report, encoding="utf-8")
    print(f"Saved to {outdir}")

if __name__ == "__main__":
    main()
