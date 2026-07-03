from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pickle
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
DEFAULT_HISTORY = Path(
    r"C:\Users\keisu\Documents\Codex\2026-06-14\files-mentioned-by-the-user-codex\work\option-chain-snapshots\backtest_outputs_universe_reproducibility\russell1000_histories.pkl"
)
DEFAULT_INPUT_ROOT = REPO_ROOT / "market_bomb_history" / "morita_bot_historical_baseline_v1" / "input" / "morita_baseline_2023_2026_v1"
SOURCE_DIR = "sources"
TAIL_RAW_DIR = "yahoo_tail_raw"
OVERLAP_START = "2026-06-01"
EXISTING_CUTOFF = "2026-06-12"
TAIL_END = "2026-07-02"
TAIL_DOWNLOAD_END_EXCLUSIVE = "2026-07-03"
BENCHMARK = "QQQ"


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(payload) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def load_existing_histories(path: Path) -> dict[str, pd.DataFrame]:
    with path.open("rb") as f:
        obj = pickle.load(f)
    if not isinstance(obj, dict):
        raise SystemExit("morita_tail_existing_history_not_dict")
    histories: dict[str, pd.DataFrame] = {}
    for ticker, df in obj.items():
        symbol = str(ticker).strip().upper()
        if not symbol or not isinstance(df, pd.DataFrame) or df.empty:
            continue
        required = ["Open", "High", "Low", "Close", "Volume"]
        if not set(required).issubset(df.columns):
            continue
        out = df[required].copy()
        out.index = pd.to_datetime(out.index).tz_localize(None)
        histories[symbol] = out.sort_index()
    return histories


def ticker_set_from_history(path: Path) -> list[str]:
    tickers = sorted(load_existing_histories(path))
    if BENCHMARK not in tickers:
        tickers.append(BENCHMARK)
    return sorted(set(tickers))


def normalize_existing_rows(histories: dict[str, pd.DataFrame], cutoff: str) -> pd.DataFrame:
    rows = []
    cutoff_ts = pd.Timestamp(cutoff)
    for ticker in sorted(histories):
        df = histories[ticker].copy()
        df = df[pd.to_datetime(df.index) <= cutoff_ts]
        if df.empty:
            continue
        tmp = df.reset_index()
        first_col = tmp.columns[0]
        tmp = tmp.rename(columns={first_col: "date"})
        tmp["date"] = pd.to_datetime(tmp["date"]).dt.strftime("%Y-%m-%d")
        tmp["ticker"] = ticker
        tmp["raw_or_adjusted"] = "local_cached_existing_history_basis_unspecified"
        tmp = tmp.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        rows.append(tmp[["date", "ticker", "open", "high", "low", "close", "volume", "raw_or_adjusted"]])
    if not rows:
        return pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume", "raw_or_adjusted"])
    out = pd.concat(rows, ignore_index=True)
    return out.drop_duplicates(["date", "ticker"], keep="last").sort_values(["date", "ticker"]).reset_index(drop=True)


def batch_symbols(symbols: list[str], size: int) -> list[list[str]]:
    return [symbols[i : i + size] for i in range(0, len(symbols), size)]


def _extract_symbol_frame(raw: pd.DataFrame, symbol: str, batch_size: int) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        if symbol in raw.columns.get_level_values(0):
            return raw[symbol].copy()
        if symbol in raw.columns.get_level_values(-1):
            return raw.xs(symbol, axis=1, level=-1).copy()
        return pd.DataFrame()
    if batch_size == 1:
        return raw.copy()
    return pd.DataFrame()


def normalize_provider_frame(raw: pd.DataFrame, requested_symbols: list[str]) -> pd.DataFrame:
    rows = []
    for symbol in requested_symbols:
        df = _extract_symbol_frame(raw, symbol, len(requested_symbols))
        if df.empty:
            continue
        cols = {str(c).strip().lower(): c for c in df.columns}
        required = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
        selected = {}
        for lower, canonical in required.items():
            src = cols.get(lower)
            if src is None:
                selected = {}
                break
            selected[src] = canonical
        if not selected:
            continue
        out = df.rename(columns=selected)[list(required.values())].copy()
        out = out.dropna(subset=["Open", "High", "Low", "Close"])
        if out.empty:
            continue
        out = out.reset_index().rename(columns={"index": "date", "Date": "date"})
        out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None).dt.strftime("%Y-%m-%d")
        out["ticker"] = symbol
        out["raw_or_adjusted"] = "raw_unadjusted_provider_tail"
        out = out.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        rows.append(out[["date", "ticker", "open", "high", "low", "close", "volume", "raw_or_adjusted"]])
    if not rows:
        return pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume", "raw_or_adjusted"])
    merged = pd.concat(rows, ignore_index=True)
    for col in ["open", "high", "low", "close", "volume"]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
    merged = merged.dropna(subset=["open", "high", "low", "close"])
    return merged.drop_duplicates(["date", "ticker"], keep="last").sort_values(["date", "ticker"]).reset_index(drop=True)


def fetch_tail(tickers: list[str], raw_dir: Path, batch_size: int, retries: int, sleep_seconds: float) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    import yfinance as yf

    raw_dir.mkdir(parents=True, exist_ok=True)
    all_rows = []
    reports = []
    for batch_id, symbols in enumerate(batch_symbols(sorted(tickers), batch_size), start=1):
        request = {
            "batch_id": batch_id,
            "symbols": symbols,
            "provider": "Yahoo Finance via yfinance.download",
            "interval": "1d",
            "auto_adjust": False,
            "actions": False,
            "start": OVERLAP_START,
            "end_exclusive": TAIL_DOWNLOAD_END_EXCLUSIVE,
            "request_timestamp_utc": iso_now(),
        }
        write_json(raw_dir / f"batch_{batch_id:04d}_request.json", request)
        last_error = ""
        raw = pd.DataFrame()
        for attempt in range(retries + 1):
            try:
                raw = yf.download(
                    symbols,
                    start=OVERLAP_START,
                    end=TAIL_DOWNLOAD_END_EXCLUSIVE,
                    interval="1d",
                    auto_adjust=False,
                    actions=False,
                    group_by="ticker",
                    progress=False,
                    threads=True,
                    timeout=45,
                )
                break
            except Exception as exc:
                last_error = str(exc)
                if attempt < retries:
                    time.sleep(sleep_seconds * (2**attempt))
        if raw is None or raw.empty:
            reports.append({"batch_id": batch_id, "requested": len(symbols), "returned_rows": 0, "status": "failed", "failure_reason": last_error or "empty_provider_response"})
            continue
        raw.to_csv(raw_dir / f"batch_{batch_id:04d}_raw.csv")
        normalized = normalize_provider_frame(raw, symbols)
        normalized.to_csv(raw_dir / f"batch_{batch_id:04d}_normalized.csv", index=False)
        all_rows.append(normalized)
        returned_symbols = set(normalized["ticker"].astype(str)) if not normalized.empty else set()
        failed_symbols = sorted(set(symbols) - returned_symbols)
        reports.append({"batch_id": batch_id, "requested": len(symbols), "returned_rows": len(normalized), "status": "ok", "failure_reason": "", "failed_symbols": failed_symbols})
        if sleep_seconds:
            time.sleep(sleep_seconds)
    tail = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume", "raw_or_adjusted"])
    tail = tail.drop_duplicates(["date", "ticker"], keep="last").sort_values(["date", "ticker"]).reset_index(drop=True)
    return tail, reports


def compare_overlap(existing: pd.DataFrame, provider: pd.DataFrame) -> dict[str, Any]:
    old = existing[(existing["date"] >= OVERLAP_START) & (existing["date"] <= EXISTING_CUTOFF)].copy()
    new = provider[(provider["date"] >= OVERLAP_START) & (provider["date"] <= EXISTING_CUTOFF)].copy()
    merged = old.merge(new, on=["date", "ticker"], suffixes=("_old", "_new"), how="inner")
    price_fields = ["open", "high", "low", "close"]
    price_total = 0
    price_match = 0
    price_mismatch_rows = set()
    for field in price_fields:
        a = pd.to_numeric(merged[f"{field}_old"], errors="coerce")
        b = pd.to_numeric(merged[f"{field}_new"], errors="coerce")
        valid = a.notna() & b.notna()
        price_total += int(valid.sum())
        matched = (a[valid] - b[valid]).abs() <= 1e-8
        price_match += int(matched.sum())
        price_mismatch_rows.update(merged.loc[valid & ~((a - b).abs() <= 1e-8), "ticker"].astype(str).tolist())
    va = pd.to_numeric(merged.get("volume_old"), errors="coerce")
    vb = pd.to_numeric(merged.get("volume_new"), errors="coerce")
    vvalid = va.notna() & vb.notna()
    vmatched = (va[vvalid] - vb[vvalid]).abs() <= 1e-8
    volume_mismatch_symbols = set(merged.loc[vvalid & ~((va - vb).abs() <= 1e-8), "ticker"].astype(str).tolist())
    price_rate = price_match / price_total if price_total else 0.0
    volume_rate = int(vmatched.sum()) / int(vvalid.sum()) if int(vvalid.sum()) else 0.0
    return {
        "overlap_row_count": int(len(merged)),
        "price_field_match_rate": float(price_rate),
        "volume_match_rate": float(volume_rate),
        "price_mismatch_count": int(price_total - price_match),
        "volume_mismatch_count": int(vvalid.sum() - vmatched.sum()),
        "symbols_with_any_mismatch_count": int(len(price_mismatch_rows | volume_mismatch_symbols)),
        "overlap_status": "passed" if price_rate >= 0.98 else "morita_tail_overlap_price_basis_blocked",
    }


def tail_coverage(provider: pd.DataFrame, tickers: list[str]) -> dict[str, Any]:
    tail = provider[(provider["date"] > EXISTING_CUTOFF) & (provider["date"] <= TAIL_END)].copy()
    qqq_dates = sorted(tail.loc[tail["ticker"] == BENCHMARK, "date"].astype(str).unique().tolist())
    expected = set(qqq_dates)
    by_symbol = tail.groupby("ticker")["date"].agg(lambda s: set(s.astype(str))).to_dict() if not tail.empty else {}
    any_tail = {t for t, dates in by_symbol.items() if dates}
    complete = {t for t, dates in by_symbol.items() if expected and expected.issubset(dates)}
    requested = set(tickers)
    ratio = len(complete & requested) / len(requested) if requested else 0.0
    if ratio >= 0.90:
        status = "tail_coverage_passed"
    elif ratio >= 0.75:
        status = "materially_incomplete_proxy_run"
    else:
        status = "morita_bot_baseline_tail_coverage_blocked"
    daily = []
    for date in qqq_dates:
        count = int(tail[tail["date"] == date]["ticker"].nunique())
        daily.append({"date": date, "active_symbol_count": count, "requested_symbols": len(requested), "coverage_ratio": count / len(requested) if requested else 0.0})
    return {
        "requested_symbols": len(requested),
        "symbols_with_any_tail_bar": len(any_tail & requested),
        "symbols_with_complete_tail_to_2026_07_02": len(complete & requested),
        "symbol_tail_coverage_ratio": float(ratio),
        "QQQ_tail_complete": bool(BENCHMARK in complete and TAIL_END in expected),
        "tail_coverage_status": status,
        "expected_tail_sessions": qqq_dates,
        "failed_symbols": sorted(requested - any_tail),
        "incomplete_symbols": sorted(requested - complete),
        "daily_active_symbol_coverage": daily,
    }


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def build_manifest(root: Path) -> dict[str, Any]:
    files = []
    manifest_name = "source_manifest.json"
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != manifest_name:
            files.append({"relative_path": path.relative_to(root).as_posix(), "sha256": file_sha256(path), "bytes": path.stat().st_size})
    manifest = {"manifest_version": "morita_bot_historical_baseline_input_v1", "created_at_utc": iso_now(), "files": files, "content_hash": text_hash(json_dumps(files))}
    write_json(root / manifest_name, manifest)
    return manifest


def build_input(history_path: Path, output_root: Path, batch_size: int, retries: int, sleep_seconds: float, use_existing_raw: bool = False) -> dict[str, Any]:
    sources = output_root / SOURCE_DIR
    raw_dir = sources / TAIL_RAW_DIR
    output_root.mkdir(parents=True, exist_ok=True)
    histories = load_existing_histories(history_path)
    tickers = sorted(set(histories) | {BENCHMARK})
    existing = normalize_existing_rows(histories, EXISTING_CUTOFF)
    if use_existing_raw:
        parts = list(raw_dir.glob("batch_*_normalized.csv"))
        if not parts:
            raise SystemExit("morita_tail_raw_cache_missing")
        provider = pd.concat([pd.read_csv(p) for p in parts], ignore_index=True)
        reports = [{"batch_id": "cached", "requested": len(tickers), "returned_rows": len(provider), "status": "cached", "failure_reason": ""}]
    else:
        provider, reports = fetch_tail(tickers, raw_dir, batch_size=batch_size, retries=retries, sleep_seconds=sleep_seconds)
    provider = provider.drop_duplicates(["date", "ticker"], keep="last").sort_values(["date", "ticker"]).reset_index(drop=True)
    overlap = compare_overlap(existing, provider)
    coverage = tail_coverage(provider, tickers)
    tail_only = provider[(provider["date"] > EXISTING_CUTOFF) & (provider["date"] <= TAIL_END)].copy()
    merged = pd.concat([existing, tail_only], ignore_index=True).drop_duplicates(["date", "ticker"], keep="last").sort_values(["date", "ticker"])
    merged.to_csv(sources / "daily_ohlcv_merged.csv", index=False)
    universe_rows = [{"ticker": t, "effective_date": "2023-07-03", "end_date": "", "universe_pit_status": "static_historical_proxy"} for t in tickers]
    write_csv(sources / "universe_membership.csv", universe_rows, ["ticker", "effective_date", "end_date", "universe_pit_status"])
    qqq_dates = sorted(merged.loc[(merged["ticker"] == BENCHMARK) & (merged["date"] >= "2023-07-03") & (merged["date"] <= TAIL_END), "date"].astype(str).unique().tolist())
    schedule = []
    for idx, date in enumerate(qqq_dates):
        next_session = qqq_dates[idx + 1] if idx + 1 < len(qqq_dates) else ""
        schedule.append({"observation_date": date, "next_eligible_session": next_session, "decision_timestamp_convention": "after_regular_close_america_new_york"})
    write_csv(sources / "decision_schedule.csv", schedule, ["observation_date", "next_eligible_session", "decision_timestamp_convention"])
    write_json(
        sources / "existing_history_reference.json",
        {
            "path_alias": "known_local_russell1000_histories_pickle",
            "absolute_path": str(history_path),
            "sha256": file_sha256(history_path),
            "ticker_count": len(histories),
            "date_min": str(min(pd.to_datetime(df.index).min() for df in histories.values() if not df.empty).date()),
            "date_max": str(max(pd.to_datetime(df.index).max() for df in histories.values() if not df.empty).date()),
        },
    )
    validation_rows = [
        {"check": "overlap_price_basis", "status": overlap["overlap_status"], "value": overlap["price_field_match_rate"]},
        {"check": "tail_coverage", "status": coverage["tail_coverage_status"], "value": coverage["symbol_tail_coverage_ratio"]},
        {"check": "qqq_tail_complete", "status": "passed" if coverage["QQQ_tail_complete"] else "failed", "value": coverage["QQQ_tail_complete"]},
    ]
    write_csv(sources / "tail_intake_validation_report.csv", validation_rows, ["check", "status", "value"])
    write_csv(output_root / "tail_intake_validation_report.csv", validation_rows, ["check", "status", "value"])
    write_json(
        output_root / "tail_intake_receipt.json",
        {
            "status": "morita_tail_intake_completed" if overlap["overlap_status"] == "passed" and coverage["QQQ_tail_complete"] and coverage["tail_coverage_status"] != "morita_bot_baseline_tail_coverage_blocked" else "morita_tail_intake_blocked",
            "created_at_utc": iso_now(),
            "authorized_provider": "Yahoo Finance daily OHLCV via yfinance",
            "request_window": {"start": OVERLAP_START, "end": TAIL_END, "interval": "1d", "auto_adjust": False, "actions": False},
            "overlap_reconciliation": overlap,
            "tail_coverage": {k: v for k, v in coverage.items() if k not in {"failed_symbols", "incomplete_symbols", "daily_active_symbol_coverage"}},
            "failed_symbols_count": len(coverage["failed_symbols"]),
            "incomplete_symbols_count": len(coverage["incomplete_symbols"]),
            "batch_reports": reports,
            "research_only": True,
            "actionization_allowed": False,
        },
    )
    write_json(raw_dir / "provider_batch_report.json", {"batches": reports})
    build_manifest(output_root)
    if overlap["overlap_status"] != "passed":
        raise SystemExit(overlap["overlap_status"])
    if not coverage["QQQ_tail_complete"]:
        raise SystemExit("morita_bot_baseline_qqq_tail_blocked")
    if coverage["tail_coverage_status"] == "morita_bot_baseline_tail_coverage_blocked":
        raise SystemExit("morita_bot_baseline_tail_coverage_blocked")
    return {"status": "morita_tail_intake_completed", "output_root": repo_relative(output_root), "overlap": overlap, "coverage": coverage}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history-pkl", default=str(DEFAULT_HISTORY))
    parser.add_argument("--output-root", default=str(DEFAULT_INPUT_ROOT))
    parser.add_argument("--batch-size", type=int, default=80)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--use-existing-raw", action="store_true")
    parser.add_argument("--print-ticker-count", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    history = Path(args.history_pkl)
    if args.print_ticker_count:
        print(json_dumps({"ticker_count": len(ticker_set_from_history(history)), "benchmark": BENCHMARK}))
        return 0
    result = build_input(history, Path(args.output_root), args.batch_size, args.retries, args.sleep_seconds, use_existing_raw=args.use_existing_raw)
    print(json_dumps({k: v for k, v in result.items() if k != "coverage"} | {"coverage": {kk: vv for kk, vv in result["coverage"].items() if kk not in {"failed_symbols", "incomplete_symbols", "daily_active_symbol_coverage"}}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
