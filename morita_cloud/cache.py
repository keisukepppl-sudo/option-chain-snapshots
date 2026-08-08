from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

import scanner_notify as sn
from morita_cloud.state_store import GcsStore
from scanner.pipeline import scan_universe


@dataclass(frozen=True)
class PrecomputeBundle:
    results: pd.DataFrame
    histories: dict[str, pd.DataFrame]
    metadata: dict[str, dict[str, str]]
    manifest: dict[str, Any]


def _frame_to_parquet_bytes(frame: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.to_parquet(buffer, index=False)
    return buffer.getvalue()


def _frame_from_parquet_bytes(payload: bytes) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(payload))


def _clip_before_trading_date(history: pd.DataFrame, trading_date_et: str) -> pd.DataFrame:
    if history.empty:
        return history.copy()
    cutoff = pd.Timestamp(trading_date_et).date()
    frame = history.copy()
    dates = pd.to_datetime(frame.index).date
    return frame[dates < cutoff].copy()


def _histories_to_frame(histories: dict[str, pd.DataFrame], max_rows: int = 120) -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    for ticker, history in sorted(histories.items()):
        frame = history.tail(max_rows).copy()
        if frame.empty:
            continue
        frame = frame.reset_index()
        date_col = frame.columns[0]
        frame = frame.rename(columns={date_col: "bar_date"})
        frame.insert(0, "ticker", ticker)
        pieces.append(frame)
    if not pieces:
        return pd.DataFrame(columns=["ticker", "bar_date", "Open", "High", "Low", "Close", "Volume"])
    out = pd.concat(pieces, ignore_index=True)
    out["bar_date"] = pd.to_datetime(out["bar_date"]).dt.tz_localize(None)
    return out


def _frame_to_histories(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    histories: dict[str, pd.DataFrame] = {}
    if frame.empty:
        return histories
    for ticker, group in frame.groupby("ticker", sort=False):
        history = group.drop(columns=["ticker"]).copy()
        history["bar_date"] = pd.to_datetime(history["bar_date"])
        history = history.set_index("bar_date").sort_index()
        histories[str(ticker)] = history
    return histories


def cache_prefix(trading_date_et: str) -> str:
    return f"cache/{trading_date_et}"


def manifest_name(trading_date_et: str) -> str:
    return f"{cache_prefix(trading_date_et)}/manifest.json"


def build_precompute(
    store: GcsStore,
    trading_date_et: str,
    config_path: str = "config.yaml",
    period: str = "18mo",
) -> dict[str, Any]:
    config = sn.load_config(Path(config_path))
    holdings = sn.parse_blackrock_holdings(sn.BLACKROCK_IWB_PORTFOLIO_ID)
    if holdings.empty:
        raise RuntimeError("Russell 1000 holdings download returned no rows")

    tickers = sorted(set(holdings["ticker"].astype(str).tolist() + [sn.BENCHMARK]))
    downloaded = sn.fetch_histories(tickers, period=period)
    histories = {
        ticker: _clip_before_trading_date(history, trading_date_et)
        for ticker, history in downloaded.items()
    }
    histories = {
        ticker: history
        for ticker, history in histories.items()
        if len(history.dropna(subset=["Close"])) >= 60
    }

    benchmark = histories.pop(sn.BENCHMARK, None)
    if benchmark is None or benchmark.empty:
        raise RuntimeError(f"benchmark history missing after cutoff: {sn.BENCHMARK}")

    market_caps = sn.fetch_market_caps(list(histories))
    thresholds = sn.thresholds_from_config(config)
    results = scan_universe(histories, benchmark, market_caps=market_caps, thresholds=thresholds)
    for key, value in sn.benchmark_regime_fields(benchmark).items():
        results[key] = value
    prod = sn.production_config(config)
    rs_min = float(prod.get("rs_min", 98))
    rs_scores = pd.to_numeric(results.get("standard_rs_score"), errors="coerce")
    base = results[rs_scores >= rs_min].copy()
    if "ticker" not in base.columns:
        raise RuntimeError("precompute results missing ticker column")

    candidate_tickers = sorted(set(base["ticker"].astype(str)))
    candidate_histories = {
        ticker: histories[ticker]
        for ticker in candidate_tickers
        if ticker in histories
    }
    metadata_frame = holdings[holdings["ticker"].astype(str).isin(candidate_tickers)].copy()
    history_frame = _histories_to_frame(candidate_histories)

    prefix = cache_prefix(trading_date_et)
    store.upload_bytes(f"{prefix}/base_results.parquet", _frame_to_parquet_bytes(base))
    store.upload_bytes(f"{prefix}/histories.parquet", _frame_to_parquet_bytes(history_frame))
    store.upload_bytes(f"{prefix}/metadata.parquet", _frame_to_parquet_bytes(metadata_frame))

    latest_daily_bar = None
    if candidate_histories:
        latest_daily_bar = max(
            pd.Timestamp(history.index.max()).date().isoformat()
            for history in candidate_histories.values()
            if not history.empty
        )

    manifest = {
        "trading_date_et": trading_date_et,
        "created_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "period": period,
        "universe_count": int(len(holdings)),
        "history_count": int(len(histories)),
        "candidate_count": int(len(candidate_tickers)),
        "candidate_tickers": candidate_tickers,
        "rs_min": rs_min,
        "latest_daily_bar": latest_daily_bar,
        "objects": {
            "base_results": f"{prefix}/base_results.parquet",
            "histories": f"{prefix}/histories.parquet",
            "metadata": f"{prefix}/metadata.parquet",
        },
    }
    existing, generation = store.read_json(manifest_name(trading_date_et), {})
    store.write_json(
        manifest_name(trading_date_et),
        manifest,
        generation=generation if existing else None,
    )
    return manifest


def load_precompute(store: GcsStore, trading_date_et: str) -> PrecomputeBundle:
    manifest, _ = store.read_json(manifest_name(trading_date_et), {})
    if not manifest:
        raise FileNotFoundError(f"precompute manifest missing for {trading_date_et}")

    objects = manifest.get("objects", {})
    results = _frame_from_parquet_bytes(store.download_bytes(str(objects["base_results"])))
    history_frame = _frame_from_parquet_bytes(store.download_bytes(str(objects["histories"])))
    metadata_frame = _frame_from_parquet_bytes(store.download_bytes(str(objects["metadata"])))
    histories = _frame_to_histories(history_frame)

    metadata: dict[str, dict[str, str]] = {}
    if not metadata_frame.empty:
        for _, row in metadata_frame.iterrows():
            ticker = str(row.get("ticker", ""))
            if ticker:
                metadata[ticker] = {
                    "name": str(row.get("name", "")),
                    "sector": str(row.get("sector", "")),
                }

    return PrecomputeBundle(
        results=results,
        histories=histories,
        metadata=metadata,
        manifest=manifest,
    )
