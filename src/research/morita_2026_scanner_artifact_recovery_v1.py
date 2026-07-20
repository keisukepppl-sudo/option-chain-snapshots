from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ARTIFACT_VERSION = "morita_2026_scanner_artifact_recovery_v1"
OUTPUT_ROOT = Path("outputs") / "research_only" / ARTIFACT_VERSION
PIT_STATUS = "PIT_ARTIFACT_CAPTURED_CURRENT_UNIVERSE_PARTIAL"

INVENTORY_COLUMNS = [
    "source_artifact_id",
    "source_path",
    "source_kind",
    "source_sha256",
    "source_bytes",
    "rows",
    "columns",
    "status",
    "research_only",
    "execution_allowed",
]

CALENDAR_COLUMNS = [
    "ticker",
    "rank",
    "signal_decision_date",
    "decision_timestamp_et",
    "production_adjusted_score",
    "total_score",
    "alert_type",
    "breakout_today",
    "failed_breakout",
    "latest_price",
    "prior_20d_high",
    "volume_multiple",
    "standard_rs_score",
    "gap_pct",
    "exclusion_reason",
    "notified_in_source_artifact",
    "excluded_in_source_artifact",
    "source_artifact_id",
    "source_path",
    "source_kind",
    "source_sha256",
    "pit_status",
    "complete_frozen_2026_source",
    "research_only",
    "execution_allowed",
    "headline_eligible",
]


@dataclass(frozen=True)
class RecoveryResult:
    output_dir: str
    receipt: dict[str, Any]


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def artifact_id_from_path(path: Path, artifact_root: Path) -> str:
    try:
        return path.relative_to(artifact_root).parts[0]
    except (ValueError, IndexError):
        return ""


def nonempty_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def first_value(row: pd.Series, columns: list[str]) -> Any:
    for column in columns:
        if column in row and nonempty_text(row.get(column)):
            return row.get(column)
    return ""


def ticker_set(path: Path) -> set[str]:
    frame = read_csv(path)
    if frame.empty or "ticker" not in frame:
        return set()
    return set(frame["ticker"].dropna().astype(str).str.upper().str.strip())


def companion_tickers(directory: Path, prefix: str) -> set[str]:
    tickers: set[str] = set()
    for path in directory.glob(f"{prefix}*.csv"):
        tickers.update(ticker_set(path))
    return tickers


def snapshot_source_files(artifact_root: Path) -> list[tuple[Path, str]]:
    sources: list[tuple[Path, str]] = []
    for directory in sorted(path for path in artifact_root.glob("*/scanner/*") if path.is_dir()):
        logs = sorted(directory.glob("daily_scan_log_*.csv"))
        if logs:
            sources.extend((path, "daily_scan_log") for path in logs)
            continue
        fallback = directory / "russell1000_momentum_candidates.csv"
        if fallback.exists():
            sources.append((fallback, "momentum_candidates_fallback"))
    return sources


def normalize_decision_timestamp(value: Any, fallback_date: str) -> tuple[str, str, bool]:
    raw = nonempty_text(value)
    parsed = pd.to_datetime(raw, errors="coerce")
    if not pd.isna(parsed):
        return raw, parsed.date().isoformat(), False
    return fallback_date, fallback_date, True


def source_inventory(artifact_root: Path, repo_root: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path, source_kind in snapshot_source_files(artifact_root):
        frame = read_csv(path)
        rows.append(
            {
                "source_artifact_id": artifact_id_from_path(path, artifact_root),
                "source_path": str(path.relative_to(repo_root)) if path.is_relative_to(repo_root) else str(path),
                "source_kind": source_kind,
                "source_sha256": sha256_file(path),
                "source_bytes": path.stat().st_size,
                "rows": int(len(frame)),
                "columns": int(len(frame.columns)),
                "status": "RECOVERED_NONEMPTY" if not frame.empty else "RECOVERED_EMPTY",
                "research_only": True,
                "execution_allowed": False,
            }
        )
    return pd.DataFrame(rows, columns=INVENTORY_COLUMNS)


def recover_observations(artifact_root: Path, repo_root: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path, source_kind in snapshot_source_files(artifact_root):
        frame = read_csv(path)
        if frame.empty or "ticker" not in frame:
            continue
        artifact_id = artifact_id_from_path(path, artifact_root)
        source_hash = sha256_file(path)
        capture_date = path.parent.name if len(path.parent.name) == 10 else ""
        notified = companion_tickers(path.parent, "notified_candidates_")
        excluded = companion_tickers(path.parent, "excluded_candidates_")
        source_path = str(path.relative_to(repo_root)) if path.is_relative_to(repo_root) else str(path)
        for _, row in frame.iterrows():
            ticker = nonempty_text(row.get("ticker")).upper()
            if not ticker:
                continue
            decision_timestamp, decision_date, used_fallback = normalize_decision_timestamp(
                first_value(row, ["latest_price_time", "timestamp_et", "decision_timestamp_et"]),
                capture_date,
            )
            rank = nonempty_text(first_value(row, ["production_rank", "alert_rank", "rank"])).upper()
            rows.append(
                {
                    "ticker": ticker,
                    "rank": rank,
                    "signal_decision_date": decision_date,
                    "decision_timestamp_et": decision_timestamp,
                    "production_adjusted_score": first_value(row, ["production_adjusted_score", "adjusted_score"]),
                    "total_score": row.get("total_score", ""),
                    "alert_type": row.get("alert_type", ""),
                    "breakout_today": row.get("breakout_today", ""),
                    "failed_breakout": row.get("failed_breakout", ""),
                    "latest_price": first_value(row, ["latest_price", "close"]),
                    "prior_20d_high": row.get("prior_20d_high", ""),
                    "volume_multiple": row.get("volume_multiple", ""),
                    "standard_rs_score": row.get("standard_rs_score", ""),
                    "gap_pct": first_value(row, ["gap_pct", "gap_up_pct"]),
                    "exclusion_reason": first_value(row, ["exclusion_reason", "skip_reason"]),
                    "notified_in_source_artifact": ticker in notified,
                    "excluded_in_source_artifact": ticker in excluded,
                    "timestamp_fallback_used": used_fallback,
                    "source_artifact_id": artifact_id,
                    "source_path": source_path,
                    "source_kind": source_kind,
                    "source_sha256": source_hash,
                    "pit_status": PIT_STATUS,
                    "complete_frozen_2026_source": False,
                    "research_only": True,
                    "execution_allowed": False,
                    "headline_eligible": False,
                }
            )
    columns = CALENDAR_COLUMNS + ["timestamp_fallback_used"]
    return pd.DataFrame(rows, columns=columns)


def build_calendar(observations: pd.DataFrame) -> pd.DataFrame:
    if observations.empty:
        return pd.DataFrame(columns=CALENDAR_COLUMNS)
    work = observations.copy()
    work["_artifact_order"] = pd.to_numeric(work["source_artifact_id"], errors="coerce").fillna(-1)
    work = work.sort_values(
        ["signal_decision_date", "ticker", "decision_timestamp_et", "_artifact_order", "source_path"],
        kind="stable",
    )
    work = work.drop_duplicates(
        subset=["ticker", "rank", "signal_decision_date", "decision_timestamp_et"],
        keep="last",
    )
    return work.loc[:, CALENDAR_COLUMNS].reset_index(drop=True)


def review_bundle(receipt: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Morita 2026 Scanner Artifact Recovery v1",
            "",
            "## Decision",
            "",
            "`PARTIAL_RECOVERY_ONLY / NOT_A_FROZEN_BASELINE_REPRODUCTION`",
            "",
            f"- Source files inventoried: {receipt['source_files']}",
            f"- Raw recovered observations: {receipt['raw_observations']}",
            f"- Deduplicated signal rows: {receipt['calendar_rows']}",
            f"- Decision dates: {receipt['decision_dates']}",
            f"- Unique tickers: {receipt['unique_tickers']}",
            f"- Rank counts: {json.dumps(receipt['rank_counts'], sort_keys=True)}",
            "- The source artifacts preserve production scanner rows and timestamps.",
            "- They do not prove full 2026 coverage, historical-universe completeness, or exact frozen baseline identity.",
            "- This output is research-only and cannot enable live execution or headline claims.",
            "",
        ]
    )


def run_recovery(
    repo_root: Path,
    artifact_root: Path | None = None,
    output_root: Path | None = None,
    run_id: str | None = None,
) -> RecoveryResult:
    repo_root = repo_root.resolve()
    artifact_root = (artifact_root or repo_root / "data" / "pit_recovery" / "github_artifacts").resolve()
    output_root = (output_root or repo_root / OUTPUT_ROOT).resolve()
    out = output_root / (run_id or utc_stamp())
    out.mkdir(parents=True, exist_ok=True)

    inventory = source_inventory(artifact_root, repo_root)
    observations = recover_observations(artifact_root, repo_root)
    calendar = build_calendar(observations)
    rank_counts = {str(k): int(v) for k, v in calendar["rank"].value_counts().to_dict().items()}
    receipt: dict[str, Any] = {
        "artifact_version": ARTIFACT_VERSION,
        "status": "PARTIAL_RECOVERY_ONLY",
        "source_root": str(artifact_root.relative_to(repo_root)) if artifact_root.is_relative_to(repo_root) else str(artifact_root),
        "source_files": int(len(inventory)),
        "nonempty_source_files": int(inventory["rows"].gt(0).sum()) if not inventory.empty else 0,
        "raw_observations": int(len(observations)),
        "calendar_rows": int(len(calendar)),
        "decision_dates": int(calendar["signal_decision_date"].nunique()) if not calendar.empty else 0,
        "unique_tickers": int(calendar["ticker"].nunique()) if not calendar.empty else 0,
        "rank_counts": rank_counts,
        "complete_frozen_2026_source": False,
        "research_only": True,
        "execution_allowed": False,
        "headline_eligible": False,
        "blocker": "ORIGINAL_FROZEN_2026_SIGNAL_CALENDAR_AND_COMPLETE_ARTIFACT_COVERAGE_MISSING",
    }

    inventory.to_csv(out / "source_inventory.csv", index=False)
    observations.to_csv(out / "recovered_signal_observations.csv", index=False)
    calendar.to_csv(out / "rank_weighted_signal_calendar_recovered.csv", index=False)
    (out / "run_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "RESEARCH_ONLY_DO_NOT_EXECUTE.marker").write_text(
        "research_only=true\nexecution_allowed=false\ncomplete_frozen_2026_source=false\n",
        encoding="utf-8",
    )
    (out / f"{ARTIFACT_VERSION}_chatgpt_review_bundle.md").write_text(review_bundle(receipt), encoding="utf-8")
    return RecoveryResult(output_dir=str(out), receipt=receipt)


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover a research-only 2026 signal ledger from scanner artifacts.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    result = run_recovery(args.repo_root, args.artifact_root, args.output_root, args.run_id)
    print(json.dumps({"output_dir": result.output_dir, **result.receipt}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
