#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto option-chain snapshotter for QQQ / MU / DRAM.

Install:
  pip install yfinance pandas numpy scipy

Manual run:
  python C:\\Users\\keisu\\Downloads\\option_snapshot_auto.py --tickers QQQ SPY SOXX SMH MU DRAM

Windows Task Scheduler:
  Program: python
  Arguments: C:\\Users\\keisu\\Downloads\\option_snapshot_auto.py --tickers QQQ SPY SOXX SMH MU DRAM
  Start in: C:\\Users\\keisu\\.vscode-shared
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm


def today_str() -> str:
    return pd.Timestamp.today().strftime("%Y-%m-%d")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def latest_price(ticker: str) -> float:
    hist = yf.Ticker(ticker).history(period="10d", auto_adjust=False)
    if hist.empty:
        raise RuntimeError(f"Could not fetch price for {ticker}")
    return float(hist["Close"].dropna().iloc[-1])


def previous_price(ticker: str):
    hist = yf.Ticker(ticker).history(period="10d", auto_adjust=False)
    close = hist["Close"].dropna()
    if len(close) < 2:
        return None
    return float(close.iloc[-2])


def underlying_return(ticker: str) -> float:
    px = latest_price(ticker)
    p0 = previous_price(ticker)
    if p0 is None or p0 == 0:
        return 0.0
    return px / p0 - 1.0


def t_to_expiry(expiry: str) -> float:
    exp = pd.Timestamp(expiry).tz_localize(None)
    today = pd.Timestamp.today().normalize()
    return max((exp - today).days, 1) / 365.0


def bs_gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return norm.pdf(d1) / (S * sigma * math.sqrt(T))


def bs_delta(S: float, K: float, T: float, r: float, sigma: float, typ: str) -> float:
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return norm.cdf(d1) if typ == "call" else norm.cdf(d1) - 1.0


def fetch_options(ticker: str, max_expiries: int):
    ticker = ticker.upper()
    tk = yf.Ticker(ticker)
    spot = latest_price(ticker)
    ret = underlying_return(ticker)
    expiries = list(tk.options or [])[:max_expiries]
    if not expiries:
        raise RuntimeError(f"No options expiries for {ticker}")

    rows = []
    for exp in expiries:
        try:
            ch = tk.option_chain(exp)
        except Exception as exc:
            print(f"[WARN] {ticker} {exp} failed: {exc}")
            continue
        T = t_to_expiry(exp)
        for typ, df in [("call", ch.calls), ("put", ch.puts)]:
            if df is None or df.empty:
                continue
            tmp = df.copy()
            tmp["ticker"] = ticker
            tmp["type"] = typ
            tmp["expiration"] = exp
            tmp["T"] = T
            rows.append(tmp)

    if not rows:
        raise RuntimeError(f"No option data for {ticker}")

    data = pd.concat(rows, ignore_index=True)
    data = data.rename(columns={"impliedVolatility": "iv", "openInterest": "oi", "lastPrice": "last_price"})

    for col in ["strike", "iv", "oi", "volume", "last_price", "bid", "ask"]:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")
        else:
            data[col] = np.nan

    data["oi"] = data["oi"].fillna(0.0)
    data["volume"] = data["volume"].fillna(0.0)
    data = data[(data["iv"] > 0.001) & (data["iv"] < 5.0)].copy()

    data["mid"] = np.where(
        (data["bid"].notna()) & (data["ask"].notna()) & (data["ask"] > 0),
        (data["bid"] + data["ask"]) / 2.0,
        data["last_price"],
    )

    gammas, deltas, public_gex = [], [], []
    for _, r in data.iterrows():
        gamma = bs_gamma(spot, float(r["strike"]), float(r["T"]), 0.04, float(r["iv"]))
        delta = bs_delta(spot, float(r["strike"]), float(r["T"]), 0.04, float(r["iv"]), r["type"])
        sign = 1.0 if r["type"] == "call" else -1.0
        gex = sign * gamma * float(r["oi"]) * 100.0 * spot * spot * 0.01
        gammas.append(gamma)
        deltas.append(delta)
        public_gex.append(gex)

    data["gamma"] = gammas
    data["delta"] = deltas
    data["public_gex"] = public_gex
    data["spot"] = spot
    data["underlying_return"] = ret
    data["snapshot_date"] = today_str()
    return spot, data


def save_snapshot(data_dir: Path, ticker: str, data: pd.DataFrame) -> Path:
    folder = data_dir / ticker.upper()
    ensure_dir(folder)
    out = folder / f"{ticker.upper()}_{today_str()}.csv"
    data.to_csv(out, index=False)
    return out


def write_log(log_path: Path, msg: str) -> None:
    ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", default=["QQQ", "SPY", "SOXX", "SMH", "MU", "DRAM"])
    parser.add_argument("--max-expiries", type=int, default=10)
    parser.add_argument("--data-dir", default="option_chain_snapshots")
    parser.add_argument("--log", default="option_snapshot_log.txt")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    ensure_dir(data_dir)
    log_path = Path(args.log)
    write_log(log_path, "=== snapshot started ===")

    for ticker in args.tickers:
        ticker = ticker.upper()
        try:
            print(f"[{ticker}] fetching...")
            spot, data = fetch_options(ticker, args.max_expiries)
            out = save_snapshot(data_dir, ticker, data)
            msg = f"{ticker}: saved {len(data)} rows, spot={spot:.2f}, file={out}"
            print(msg)
            write_log(log_path, msg)
        except Exception as exc:
            msg = f"{ticker}: ERROR {exc}"
            print(msg)
            write_log(log_path, msg)

    write_log(log_path, "=== snapshot finished ===")


if __name__ == "__main__":
    main()
