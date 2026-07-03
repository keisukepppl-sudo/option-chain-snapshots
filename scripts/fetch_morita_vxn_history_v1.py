from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTHORIZED_SYMBOL = "^VXN"
AUTHORIZED_START_DATE = "2023-06-01"
AUTHORIZED_END_DATE = "2026-07-02"
AUTHORIZED_INTERVAL = "1d"
RAW_FILE = "vxn_yahoo_chart_raw.json"
NORMALIZED_FILE = "vxn_history_normalized.csv"
RECEIPT_FILE = "vxn_intake_receipt.json"
MANIFEST_FILE = "vxn_input_manifest.json"


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True)


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json_dumps(obj) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def validate_authorized_request(start_date: str, end_date: str, symbol: str = AUTHORIZED_SYMBOL) -> None:
    if symbol != AUTHORIZED_SYMBOL:
        raise SystemExit("unauthorized_symbol:only_^VXN_allowed")
    if start_date != AUTHORIZED_START_DATE or end_date != AUTHORIZED_END_DATE:
        raise SystemExit("unauthorized_date_range:expected_2023-06-01_to_2026-07-02")


def yahoo_chart_url(symbol: str, start_date: str, end_date: str) -> str:
    start = parse_date(start_date)
    end = parse_date(end_date)
    period1 = int(datetime.combine(start, time.min, tzinfo=timezone.utc).timestamp())
    period2 = int(datetime.combine(end, time.min, tzinfo=timezone.utc).timestamp()) + 24 * 60 * 60
    encoded_symbol = urllib.parse.quote(symbol, safe="")
    params = urllib.parse.urlencode(
        {
            "period1": period1,
            "period2": period2,
            "interval": AUTHORIZED_INTERVAL,
            "includePrePost": "false",
            "events": "history",
        }
    )
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?{params}"


def fetch_yahoo_chart(symbol: str, start_date: str, end_date: str, timeout: int = 60) -> dict[str, Any]:
    validate_authorized_request(start_date, end_date, symbol=symbol)
    url = yahoo_chart_url(symbol, start_date, end_date)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "morita-vxn-history-v1/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def normalize_chart(payload: dict[str, Any]) -> pd.DataFrame:
    chart = payload.get("chart", {})
    if chart.get("error"):
        raise SystemExit(f"vxn_yahoo_error:{chart['error']}")
    result = chart.get("result") or []
    if len(result) != 1:
        raise SystemExit("vxn_yahoo_payload_invalid:expected_one_result")
    data = result[0]
    timestamps = data.get("timestamp") or []
    quote = ((data.get("indicators") or {}).get("quote") or [{}])[0]
    rows: list[dict[str, Any]] = []
    for idx, ts in enumerate(timestamps):
        row = {"date": datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat(), "symbol": AUTHORIZED_SYMBOL}
        for col in ["open", "high", "low", "close", "volume"]:
            values = quote.get(col) or []
            row[col] = values[idx] if idx < len(values) else None
        rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("vxn_yahoo_payload_empty")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["date", "close"]).drop_duplicates("date").sort_values("date")
    return df


def build_manifest(output_dir: Path) -> dict[str, Any]:
    files = []
    for child in sorted(output_dir.rglob("*")):
        if child.is_file() and child.name != MANIFEST_FILE:
            files.append({"relative_path": child.relative_to(output_dir).as_posix(), "sha256": file_sha256(child), "bytes": child.stat().st_size})
    manifest = {
        "artifact_version": "morita_vxn_history_input_v1",
        "created_at_utc": iso_now(),
        "authorized_symbol": AUTHORIZED_SYMBOL,
        "authorized_start_date": AUTHORIZED_START_DATE,
        "authorized_end_date": AUTHORIZED_END_DATE,
        "files": files,
        "content_set_hash": text_hash(json_dumps(files)),
    }
    write_json(output_dir / MANIFEST_FILE, manifest)
    return manifest


def run_fetch(start_date: str, end_date: str, output_dir: Path) -> dict[str, Any]:
    validate_authorized_request(start_date, end_date)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "vxn_history_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    payload = fetch_yahoo_chart(AUTHORIZED_SYMBOL, start_date, end_date)
    raw_path = raw_dir / RAW_FILE
    write_json(raw_path, payload)
    normalized = normalize_chart(payload)
    normalized_path = output_dir / NORMALIZED_FILE
    normalized.to_csv(normalized_path, index=False)
    receipt = {
        "artifact_version": "morita_vxn_history_input_v1",
        "status": "vxn_history_intake_completed",
        "created_at_utc": iso_now(),
        "symbol": AUTHORIZED_SYMBOL,
        "provider": "Yahoo Finance chart",
        "start_date": start_date,
        "end_date": end_date,
        "interval": AUTHORIZED_INTERVAL,
        "auto_adjust": False,
        "actions": False,
        "row_count": int(len(normalized)),
        "min_date": str(normalized["date"].min()),
        "max_date": str(normalized["date"].max()),
        "raw_path": repo_relative(raw_path),
        "normalized_path": repo_relative(normalized_path),
        "raw_sha256": file_sha256(raw_path),
        "normalized_sha256": file_sha256(normalized_path),
        "only_authorized_external_data_fetched": True,
    }
    write_json(output_dir / RECEIPT_FILE, receipt)
    manifest = build_manifest(output_dir)
    return {
        "status": receipt["status"],
        "output_dir": repo_relative(output_dir),
        "row_count": receipt["row_count"],
        "min_date": receipt["min_date"],
        "max_date": receipt["max_date"],
        "manifest_hash": file_sha256(output_dir / MANIFEST_FILE),
        "file_count": len(manifest["files"]),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    print(json_dumps(run_fetch(args.start_date, args.end_date, output_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
