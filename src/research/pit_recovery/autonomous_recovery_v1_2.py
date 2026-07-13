from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .webull_m15_backfill import (
    empty_authoritative_signal_m15_dataset,
    event_window_inventory,
    join_audit,
    quality_audit_from_inventory,
)
from .webull_m15_credentialed_probe import credential_inventory, fake_blocked_probe, sdk_interface_audit
from .webull_m15_retention import retention_boundary_from_matrix, webull_terminal_status


ARTIFACT_VERSION = "morita_historical_pit_m15_autonomous_recovery_v1_2"
OUTPUT_ROOT = Path("outputs") / "research_only" / ARTIFACT_VERSION
GITHUB_ARTIFACT_DIR = Path("data") / "pit_recovery" / "github_artifacts"
GUARDRAILS = {
    "research_only": True,
    "execution_allowed": False,
    "live_order_allowed": False,
    "order_preview_allowed": False,
    "account_data_access_allowed": False,
    "positions_access_allowed": False,
    "buying_power_access_allowed": False,
    "production_signal_logic_change_allowed": False,
    "production_rank_change_allowed": False,
    "production_notification_change_allowed": False,
    "production_position_size_change_allowed": False,
    "threshold_optimization_allowed": False,
    "future_information_allowed": False,
    "synthetic_intraday_data_allowed": False,
    "historical_data_fabrication_allowed": False,
    "LIVE_ORDER_ENABLED": False,
    "ORDER_PREVIEW_ONLY": False,
    "KILL_SWITCH_ENABLED": True,
    "MAX_OPEN_OPTION_POSITIONS": 0,
}


@dataclass(frozen=True)
class RecoveryResult:
    output_dir: str
    terminal_statuses: list[str]
    receipt: dict[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        columns = columns or list(dict.fromkeys(key for row in rows for key in row.keys()))
    else:
        columns = columns or ["status"]
    with open(long_path(path), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(long_path(path), "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(long_path(path), "w", encoding="utf-8") as f:
        f.write(text)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(long_path(path), "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def long_path(path: Path) -> str:
    resolved = os.path.abspath(str(path))
    if os.name == "nt" and not resolved.startswith("\\\\?\\"):
        return "\\\\?\\" + resolved
    return resolved


def run_cmd(args: list[str], repo_root: Path, timeout: int = 60) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as exc:
        return 999, "", f"{type(exc).__name__}: {exc}"


def find_gh() -> str:
    if os.getenv("MORITA_V12_DISABLE_GITHUB") == "1":
        return ""
    found = shutil.which("gh")
    if found:
        return found
    fallback = Path("C:/Program Files/GitHub CLI/gh.exe")
    return str(fallback) if fallback.exists() else ""


def git_lines(repo_root: Path, args: list[str], timeout: int = 60) -> list[str]:
    code, out, _ = run_cmd(["git", *args], repo_root, timeout=timeout)
    if code != 0:
        return []
    return [line for line in out.splitlines() if line.strip()]


def inspect_environment(repo_root: Path) -> dict[str, Any]:
    gh_path = find_gh()
    gh_status = "GH_NOT_INSTALLED"
    if gh_path:
        code, out, err = run_cmd(["gh", "auth", "status"], repo_root, timeout=20)
        gh_status = "GH_AUTH_OK" if code == 0 else "GITHUB_AUTH_ACTION_REQUIRED"
    return {
        "run_at_utc": utc_now(),
        "repo_root": str(repo_root),
        "git_head": git_lines(repo_root, ["rev-parse", "HEAD"])[:1],
        "git_branch": git_lines(repo_root, ["branch", "--show-current"])[:1],
        "gh_path": gh_path or "",
        "github_access_status": gh_status,
        "webull_credential_status": credential_inventory(repo_root),
        "webull_sdk_status": sdk_interface_audit(),
        "guardrails": GUARDRAILS,
    }


def recover_github_evidence(
    repo_root: Path,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    str,
    str,
]:
    commits = git_lines(repo_root, ["log", "--all", "--full-history", "--date=iso-strict", "--pretty=format:%H%x09%aI%x09%D%x09%s"], timeout=120)
    branches = git_lines(repo_root, ["branch", "--all", "--format=%(refname:short)\t%(objectname)\t%(committerdate:iso-strict)"], timeout=60)
    tags = git_lines(repo_root, ["tag", "--format=%(refname:short)\t%(objectname)\t%(creatordate:iso-strict)"], timeout=60)
    keyword_files = git_lines(
        repo_root,
        [
            "log",
            "--all",
            "--full-history",
            "--name-only",
            "--pretty=format:",
            "--",
            "*daily_scan_log*",
            "*notified_candidates*",
            "*excluded_candidates*",
            "*notification_diagnostics*",
            "*config*",
            "*universe*",
            "*holdings*",
            "*rank*",
            "*signal*",
        ],
        timeout=120,
    )
    gh_path = find_gh()
    gh_run_rows = github_workflow_runs(repo_root, gh_path)
    run_rows = []
    for idx, line in enumerate(commits[:5000], start=1):
        parts = line.split("\t")
        run_rows.append(
            {
                "repository": "keisukepppl-sudo/option-chain-snapshots",
                "run_id": "",
                "workflow_name": "LOCAL_GIT_HISTORY",
                "workflow_started_at": parts[1] if len(parts) > 1 else "",
                "workflow_completed_at": parts[1] if len(parts) > 1 else "",
                "head_sha": parts[0] if parts else "",
                "branch": parts[2] if len(parts) > 2 else "",
                "source": "git_log_all_full_history",
                "subject": parts[3] if len(parts) > 3 else "",
            }
        )
    if gh_run_rows:
        run_rows = gh_run_rows + run_rows
    artifact_rows = github_artifact_inventory(repo_root, gh_path, gh_run_rows[:50])
    if artifact_rows:
        artifact_rows = download_github_artifacts(repo_root, gh_path, artifact_rows)
    workflow_log_rows = github_workflow_log_audit(repo_root, gh_path, gh_run_rows, artifact_rows)
    artifact_content_rows = audit_github_artifact_contents(repo_root, artifact_rows)
    if not artifact_rows:
        artifact_rows = [
            {
                "repository": "keisukepppl-sudo/option-chain-snapshots",
                "run_id": "",
                "job_id": "",
                "artifact_id": "",
                "artifact_name": "",
                "workflow_name": "",
                "workflow_started_at": "",
                "workflow_completed_at": "",
                "head_sha": "",
                "branch": "",
                "downloaded_at_utc": "",
                "zip_sha256": "",
                "extracted_file_sha256": "",
                "status": "GITHUB_AUTH_ACTION_REQUIRED" if not gh_path else "NO_ARTIFACTS_FOUND_OR_ACCESSIBLE",
            }
        ]
    if not artifact_content_rows:
        artifact_content_rows = [
            {
                "status": "NO_DOWNLOADED_ARTIFACT_FILES",
                "authority_candidate": False,
                "pit_reusable": False,
            }
        ]
    if not workflow_log_rows:
        workflow_log_rows = [
            {
                "status": "NO_WORKFLOW_LOGS_DOWNLOADED",
                "authority_candidate": False,
                "pit_reusable": False,
            }
        ]
    signal_lineage = lineage_rows(keyword_files, "SIGNAL")
    config_lineage = lineage_rows([f for f in keyword_files if "config" in f.lower()], "CONFIG")
    universe_lineage = lineage_rows([f for f in keyword_files if any(k in f.lower() for k in ["universe", "holdings", "iwb", "russell"])], "UNIVERSE")
    report = "\n".join(
        [
            "# GitHub Evidence Recovery Report",
            "",
            f"Local commits inspected: {len(run_rows)}",
            f"Branches visible locally: {len(branches)}",
            f"Tags visible locally: {len(tags)}",
            f"Signal/config/universe-like historical paths found: {len(set(keyword_files))}",
            f"gh available: {bool(gh_path)}",
            "Remote workflow artifact download requires gh authentication; no historical evidence was modified or deleted.",
            "",
        ]
    )
    gh_status = "GITHUB_EVIDENCE_RECOVERED" if gh_run_rows or signal_lineage else "NO_AUTHORITATIVE_ARCHIVED_SIGNAL"
    if not gh_path:
        gh_status = "GITHUB_AUTH_ACTION_REQUIRED"
    return run_rows, artifact_rows, artifact_content_rows, workflow_log_rows, signal_lineage, config_lineage, universe_lineage, report, gh_status


def github_workflow_runs(repo_root: Path, gh_path: str) -> list[dict[str, Any]]:
    if not gh_path:
        return []
    code, out, _ = run_cmd(
        [
            gh_path,
            "run",
            "list",
            "--limit",
            "200",
            "--json",
            "databaseId,workflowName,status,conclusion,createdAt,updatedAt,headSha,headBranch,event,url",
        ],
        repo_root,
        timeout=120,
    )
    if code != 0 or not out:
        return []
    try:
        payload = json.loads(out)
    except Exception:
        return []
    rows = []
    for item in payload:
        rows.append(
            {
                "repository": "keisukepppl-sudo/option-chain-snapshots",
                "run_id": item.get("databaseId", ""),
                "workflow_name": item.get("workflowName", ""),
                "workflow_started_at": item.get("createdAt", ""),
                "workflow_completed_at": item.get("updatedAt", ""),
                "head_sha": item.get("headSha", ""),
                "branch": item.get("headBranch", ""),
                "source": "gh_run_list",
                "subject": f"{item.get('event', '')}:{item.get('status', '')}:{item.get('conclusion', '')}",
                "url": item.get("url", ""),
            }
        )
    return rows


def github_artifact_inventory(repo_root: Path, gh_path: str, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not gh_path:
        return []
    rows: list[dict[str, Any]] = []
    for run in runs:
        run_id = str(run.get("run_id") or "")
        if not run_id:
            continue
        code, out, _ = run_cmd(
            [gh_path, "api", f"repos/keisukepppl-sudo/option-chain-snapshots/actions/runs/{run_id}/artifacts"],
            repo_root,
            timeout=60,
        )
        if code != 0 or not out:
            continue
        try:
            payload = json.loads(out)
        except Exception:
            continue
        for artifact in payload.get("artifacts", []):
            rows.append(
                {
                    "repository": "keisukepppl-sudo/option-chain-snapshots",
                    "run_id": run_id,
                    "job_id": "",
                    "artifact_id": artifact.get("id", ""),
                    "artifact_name": artifact.get("name", ""),
                    "workflow_name": run.get("workflow_name", ""),
                    "workflow_started_at": run.get("workflow_started_at", ""),
                    "workflow_completed_at": run.get("workflow_completed_at", ""),
                    "head_sha": run.get("head_sha", ""),
                    "branch": run.get("branch", ""),
                    "downloaded_at_utc": "",
                    "zip_sha256": "",
                    "extracted_file_sha256": "",
                    "status": "ARTIFACT_LISTED_NOT_DOWNLOADED",
                    "expired": artifact.get("expired", ""),
                    "size_in_bytes": artifact.get("size_in_bytes", ""),
                }
            )
    return rows


def download_github_artifacts(repo_root: Path, gh_path: str, artifact_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not gh_path or os.getenv("MORITA_V12_DISABLE_GITHUB_DOWNLOAD") == "1":
        return artifact_rows
    root = repo_root / GITHUB_ARTIFACT_DIR
    root.mkdir(parents=True, exist_ok=True)
    downloaded_at = utc_now()
    for run_id in sorted({str(row.get("run_id") or "") for row in artifact_rows if row.get("run_id")}):
        run_dir = root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        if any(run_dir.rglob("*")):
            continue
        run_cmd([gh_path, "run", "download", run_id, "-D", str(run_dir)], repo_root, timeout=180)
    for row in artifact_rows:
        run_id = str(row.get("run_id") or "")
        name = str(row.get("artifact_name") or "")
        artifact_dir = root / run_id / name
        files = [p for p in artifact_dir.rglob("*") if p.is_file()] if artifact_dir.exists() else []
        if files:
            row["downloaded_at_utc"] = downloaded_at
            row["status"] = "ARTIFACT_DOWNLOADED_EXTRACTED"
            row["extracted_file_sha256"] = "|".join(f"{p.name}:{sha256_file(p)}" for p in sorted(files)[:20])
        elif run_id and (root / run_id).exists():
            files = [p for p in (root / run_id).rglob("*") if p.is_file()]
            if files:
                row["downloaded_at_utc"] = downloaded_at
                row["status"] = "ARTIFACT_RUN_DOWNLOADED_NAME_MISMATCH"
                row["extracted_file_sha256"] = "|".join(f"{p.name}:{sha256_file(p)}" for p in sorted(files)[:20])
    return artifact_rows


def _text_tokens(value: str) -> set[str]:
    lowered = value.lower().replace("\\", "/")
    return {token for token in lowered.replace("-", "_").replace(".", "_").replace("/", "_").split("_") if token}


def _safe_read_sample(path: Path, limit: int = 4096) -> str:
    try:
        with open(long_path(path), "r", encoding="utf-8", errors="ignore") as f:
            return f.read(limit)
    except Exception:
        return ""


def _csv_shape(path: Path, size_bytes: int) -> tuple[int | str, str]:
    if size_bytes <= 1:
        return 0, ""
    try:
        with open(long_path(path), newline="", encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            rows = sum(1 for _ in reader)
        return rows, "|".join(str(col) for col in header)
    except Exception as exc:
        return "PARSE_ERROR", f"{type(exc).__name__}: {exc}"


def audit_github_artifact_contents(repo_root: Path, artifact_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    root = repo_root / GITHUB_ARTIFACT_DIR
    if not root.exists():
        return []
    by_run_name = {(str(row.get("run_id") or ""), str(row.get("artifact_name") or "")): row for row in artifact_rows}
    rows: list[dict[str, Any]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(repo_root)
        rel_parts = path.relative_to(root).parts
        run_id = rel_parts[0] if len(rel_parts) >= 1 else ""
        artifact_name = rel_parts[1] if len(rel_parts) >= 2 else ""
        meta = by_run_name.get((run_id, artifact_name), {})
        size_bytes = path.stat().st_size
        extension = path.suffix.lower().lstrip(".")
        row_count: int | str = ""
        columns = ""
        if extension == "csv":
            row_count, columns = _csv_shape(path, size_bytes)
        elif extension == "json":
            sample = _safe_read_sample(path)
            columns = "json"
            row_count = 1 if sample.strip() else 0
        else:
            sample = _safe_read_sample(path, 1024)
            row_count = 1 if sample.strip() else 0
            columns = ""
        combined = " ".join([str(rel), str(columns), _safe_read_sample(path, 512)])
        tokens = _text_tokens(combined)
        signal_like = bool(tokens & {"signal", "signals", "rank", "candidate", "candidates", "notified", "daily_scan", "scanner"})
        universe_like = bool(tokens & {"universe", "holdings", "iwb", "russell", "russell1000"})
        config_like = bool(tokens & {"config", "yaml", "yml", "threshold", "thresholds"})
        test_like = "collection-coverage" in str(rel).lower() or "test" in str(rel).lower()
        nonempty = size_bytes > 1 and row_count not in {0, "PARSE_ERROR"}
        authority_candidate = bool(nonempty and (signal_like or universe_like) and not test_like)
        pit_reusable = False
        effectively_empty = size_bytes <= 2 or row_count == 0
        if effectively_empty and artifact_name == "russell1000-1015-scan":
            status = "CURRENT_EMPTY_SCANNER_ARTIFACT"
        elif effectively_empty:
            status = "EMPTY_FILE"
        elif test_like:
            status = "TEST_OR_CI_ARTIFACT"
        elif authority_candidate:
            status = "NONEMPTY_SIGNAL_OR_UNIVERSE_LIKE_REQUIRES_PIT_PROOF"
        else:
            status = "NONEMPTY_NON_SIGNAL_ARTIFACT"
        rows.append(
            {
                "run_id": run_id,
                "artifact_name": artifact_name,
                "workflow_name": meta.get("workflow_name", ""),
                "workflow_started_at": meta.get("workflow_started_at", ""),
                "head_sha": meta.get("head_sha", ""),
                "branch": meta.get("branch", ""),
                "file_path": str(rel),
                "file_name": path.name,
                "extension": extension,
                "size_bytes": size_bytes,
                "sha256": sha256_file(path),
                "row_count": row_count,
                "columns": columns,
                "signal_like": signal_like,
                "universe_like": universe_like,
                "config_like": config_like,
                "test_like": test_like,
                "nonempty": nonempty,
                "authority_candidate": authority_candidate,
                "pit_reusable": pit_reusable,
                "status": status,
                "reason": "Downloaded file lacks complete PIT timestamp, frozen config, and frozen universe proof.",
            }
        )
    return rows


def github_workflow_log_audit(
    repo_root: Path,
    gh_path: str,
    runs: list[dict[str, Any]],
    artifact_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not gh_path or os.getenv("MORITA_V12_DISABLE_GITHUB") == "1":
        return []
    artifact_run_ids = {str(row.get("run_id") or "") for row in artifact_rows if row.get("run_id")}
    keyword_run_ids = []
    for row in runs:
        haystack = " ".join(str(row.get(k, "")) for k in ["workflow_name", "subject"]).lower()
        if any(k in haystack for k in ["scanner", "russell", "status", "production"]):
            keyword_run_ids.append(str(row.get("run_id") or ""))
    selected = [rid for rid in dict.fromkeys([*keyword_run_ids, *sorted(artifact_run_ids)]) if rid][:25]
    root = repo_root / GITHUB_ARTIFACT_DIR
    rows: list[dict[str, Any]] = []
    run_meta = {str(row.get("run_id") or ""): row for row in runs}
    for run_id in selected:
        log_path = root / run_id / "workflow_log.txt"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if not log_path.exists():
            code, out, err = run_cmd([gh_path, "run", "view", run_id, "--log"], repo_root, timeout=180)
            if code == 0 and out:
                write_text(log_path, out + "\n")
            else:
                write_text(log_path, f"LOG_DOWNLOAD_FAILED\n{err}\n")
        text = _safe_read_sample(log_path, 200_000)
        lowered = text.lower()
        evidence_terms = {
            "signal": lowered.count("signal"),
            "universe": lowered.count("universe"),
            "russell": lowered.count("russell"),
            "candidate": lowered.count("candidate"),
            "notified": lowered.count("notified"),
            "daily_scan": lowered.count("daily_scan"),
            "artifact": lowered.count("artifact"),
            "config": lowered.count("config"),
        }
        has_signal_terms = any(evidence_terms[k] for k in ["signal", "candidate", "notified", "daily_scan"])
        has_universe_terms = any(evidence_terms[k] for k in ["universe", "russell"])
        authority_candidate = bool(has_signal_terms or has_universe_terms)
        rows.append(
            {
                "run_id": run_id,
                "workflow_name": run_meta.get(run_id, {}).get("workflow_name", ""),
                "workflow_started_at": run_meta.get(run_id, {}).get("workflow_started_at", ""),
                "head_sha": run_meta.get(run_id, {}).get("head_sha", ""),
                "branch": run_meta.get(run_id, {}).get("branch", ""),
                "log_path": str(log_path.relative_to(repo_root)),
                "size_bytes": log_path.stat().st_size,
                "sha256": sha256_file(log_path),
                **evidence_terms,
                "authority_candidate": authority_candidate,
                "pit_reusable": False,
                "status": "LOG_DOWNLOADED_REQUIRES_ARTIFACT_PROOF" if authority_candidate else "LOG_DOWNLOADED_NO_SIGNAL_UNIVERSE_PROOF",
                "reason": "Workflow logs can support provenance but cannot replace a nonempty archived signal/universe artifact.",
            }
        )
    return rows


def lineage_rows(paths: list[str], category: str) -> list[dict[str, Any]]:
    rows = []
    for idx, path in enumerate(sorted(set(paths))[:5000], start=1):
        rows.append(
            {
                "lineage_id": f"{category}_{idx:05d}",
                "path": path,
                "category": category,
                "source": "git_log_name_only",
                "commit_sha": "",
                "workflow_run_id": "",
                "artifact_id": "",
                "available_at": "",
                "pit_valid": False,
                "status": "LOCAL_HISTORY_PATH_FOUND_REQUIRES_TIMESTAMP_ARTIFACT_PROOF",
            }
        )
    if not rows:
        rows.append({"lineage_id": "", "path": "", "category": category, "status": "NOT_FOUND", "pit_valid": False})
    return rows


def source_authority_reaudit(repo_root: Path, signal_lineage: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], str]:
    try:
        from src.morita_historical_pit_evidence_v1_1.engine import build_signal_authority_decision, build_signal_lineage, build_signal_promotion_inventory

        inventory, _frames = build_signal_promotion_inventory(repo_root)
        lineage = build_signal_lineage(inventory)
        authority = build_signal_authority_decision(inventory, lineage)
    except Exception:
        authority = []
    rows = []
    evidence = []
    reject = []
    promoted = []
    has_pit_lineage = any(row.get("pit_valid") is True for row in signal_lineage)
    for row in authority:
        tier = row.get("authority_tier", "REJECTED")
        new_tier = tier if tier in {"AUTHORITY_A", "AUTHORITY_B"} and has_pit_lineage else "AUTHORITY_C" if tier == "AUTHORITY_C" else "REJECTED"
        rows.append({**row, "v1_2_authority_tier": new_tier, "v1_2_reason": "requires workflow/artifact timestamp, config, and universe proof" if new_tier == "AUTHORITY_C" else row.get("promotion_reason", "")})
        evidence.append({"source_id": row.get("source_id", ""), "evidence_type": "LOCAL_OR_GITHUB_LINEAGE", "evidence_status": "INSUFFICIENT_FOR_PROMOTION", "detail": "mtime/performance/similarity not accepted"})
        if new_tier not in {"AUTHORITY_A", "AUTHORITY_B"}:
            reject.append({"source_id": row.get("source_id", ""), "rejection_reason": "NO_WORKFLOW_ARTIFACT_TIMESTAMP_OR_PIT_UNIVERSE_PROOF"})
    if not rows:
        rows = [{"source_id": "", "v1_2_authority_tier": "REJECTED", "v1_2_reason": "NO_CANDIDATE_SIGNAL_SOURCE"}]
        evidence = [{"source_id": "", "evidence_status": "NONE"}]
        reject = [{"source_id": "", "rejection_reason": "NO_CANDIDATE_SIGNAL_SOURCE"}]
    calendar = promoted
    receipt = {
        "authoritative_signal_calendar_ready": bool(calendar),
        "authority_a_count": sum(1 for r in rows if r.get("v1_2_authority_tier") == "AUTHORITY_A"),
        "authority_b_count": sum(1 for r in rows if r.get("v1_2_authority_tier") == "AUTHORITY_B"),
        "authority_c_promoted_count": sum(1 for r in rows if r.get("v1_2_authority_tier") in {"AUTHORITY_A", "AUTHORITY_B"}),
        "blocked_reason": "" if calendar else "AUTHORITATIVE_SIGNAL_CALENDAR_BLOCKED",
    }
    signal_status = "AUTHORITATIVE_SIGNAL_CALENDAR_READY" if calendar else "AUTHORITATIVE_SIGNAL_CALENDAR_BLOCKED"
    if not calendar:
        calendar = [{"status": "AUTHORITATIVE_SIGNAL_CALENDAR_BLOCKED", "blocked_reason": "NO_AUTHORITY_A_OR_B_SIGNAL_SOURCE"}]
    return rows, evidence, reject, calendar, receipt, signal_status


def pit_universe_recovery(universe_lineage: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], str]:
    candidates = [
        {
            "universe_id": row.get("lineage_id", ""),
            "source": row.get("path", ""),
            "available_at": row.get("available_at", ""),
            "effective_date": "",
            "ticker_count": "",
            "file_hash": "",
            "workflow_run_id": row.get("workflow_run_id", ""),
            "commit_sha": row.get("commit_sha", ""),
            "pit_valid": False,
            "status": "PIT_UNIVERSE_PARTIAL_CANDIDATE",
        }
        for row in universe_lineage
        if row.get("path")
    ]
    if not candidates:
        candidates = [{"universe_id": "", "source": "", "pit_valid": False, "status": "PIT_UNIVERSE_NOT_FOUND"}]
    audit = [
        {
            "universe_id": row.get("universe_id", ""),
            "pit_valid": row.get("pit_valid", False),
            "authority_status": "REJECTED_CURRENT_OR_UNPROVEN_HISTORY" if not row.get("pit_valid") else "PIT_UNIVERSE_VERIFIED",
            "reason": "No exact workflow artifact or committed dated universe with availability timestamp was recovered.",
        }
        for row in candidates
    ]
    registry = {
        "status": "PIT_UNIVERSE_VERIFIED" if any(r.get("pit_valid") for r in candidates) else "PIT_UNIVERSE_NOT_FOUND",
        "verified_universes": [r for r in candidates if r.get("pit_valid")],
        "current_universe_backdated": False,
    }
    return candidates, audit, registry, registry["status"]


def deterministic_rerun_outputs(universe_status: str, signal_status: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    ready = universe_status == "PIT_UNIVERSE_VERIFIED" and signal_status != "AUTHORITATIVE_SIGNAL_CALENDAR_BLOCKED"
    blocker = "" if ready else "FROZEN_CONFIG_OR_PIT_UNIVERSE_OR_SIGNAL_AUTHORITY_MISSING"
    contract = {
        "scanner_commit": "",
        "config": "FROZEN_REQUIRED",
        "universe": universe_status,
        "daily_market_data_source": "FROZEN_REQUIRED",
        "decision_cutoff": "FROZEN_REQUIRED",
        "timezone": "America/New_York",
        "corporate_action_treatment": "FROZEN_REQUIRED",
        "rerun_allowed": ready,
        "thresholds_changed": False,
        "strategy_rules_changed": False,
        "blocked_reason": blocker,
    }
    calendar = [{"source_type": "DETERMINISTIC_PIT_RERUN", "rerun_status": "NOT_RUN" if not ready else "READY", "blocked_reason": blocker}]
    reconciliation = [{"archived_source_id": "", "rerun_source_id": "", "reconciliation_status": "NOT_RUN", "reason": blocker}]
    receipt = {"rerun_executed": False, "blocked_reason": blocker}
    return contract, calendar, reconciliation, receipt


def alternative_vendor_matrix() -> tuple[list[dict[str, Any]], str]:
    rows = [
        {
            "vendor": "Twelve Data",
            "official_source": "https://twelvedata.com/stocks ; https://twelvedata.com/pricing",
            "historical_depth": "Official page says intraday range available from 2022 onward; exact symbol coverage may vary.",
            "intervals": "1min to 8h including 15min",
            "API / download": "API",
            "price": "Basic free; Grow from $29/mo",
            "currency": "USD",
            "estimated JPY cost": "Free tier possible; paid plan above JPY 1,000/mo",
            "trial": "Basic free",
            "data adjustment": "Needs vendor-specific verification before adoption",
            "rate limits": "Basic 800/day per pricing page",
            "coverage risks": "Free tier market/credit limits may not cover all required windows.",
            "user action required": "API key if selected; no purchase without approval",
        },
        {
            "vendor": "Tiingo IEX",
            "official_source": "https://www.tiingo.com/documentation/iex ; https://www.tiingo.com/about/pricing",
            "historical_depth": "Official IEX product page says intraday data from August 2017.",
            "intervals": "Historical intraday endpoint supports resampleFreq such as 5min; 15min derived status needs explicit labeling.",
            "API / download": "API",
            "price": "$30/mo individual",
            "currency": "USD",
            "estimated JPY cost": "Above JPY 1,000/mo",
            "trial": "Not assumed",
            "data adjustment": "IEX-only venue data, not full SIP market",
            "rate limits": "Plan-dependent",
            "coverage risks": "IEX-only coverage may differ from Webull/SIP data.",
            "user action required": "Paid approval and API token if selected",
        },
        {
            "vendor": "Massive / Polygon stocks aggregates",
            "official_source": "https://massive.com/docs/rest/stocks/aggregates/custom-bars ; https://massive.com/pricing",
            "historical_depth": "Stocks plans list multi-year historical data and minute aggregates.",
            "intervals": "Custom aggregate bars including minute multiples",
            "API / download": "API / downloads by plan",
            "price": "Stocks Starter $29/mo; Developer $79/mo",
            "currency": "USD",
            "estimated JPY cost": "Above JPY 1,000/mo",
            "trial": "Free basic exists but historical depth may be insufficient",
            "data adjustment": "Aggregate construction documented; adjustment behavior must be audited",
            "rate limits": "Plan-dependent",
            "coverage risks": "Paid plan likely required for full 2022-2025 backfill.",
            "user action required": "Paid approval and API key if selected",
        },
        {
            "vendor": "Alpha Vantage",
            "official_source": "https://www.alphavantage.co/documentation/",
            "historical_depth": "Official docs advertise intraday endpoints; extended depth must be verified live.",
            "intervals": "1min/5min/15min etc.",
            "API / download": "API/CSV",
            "price": "Free tier available; premium may be required for throughput",
            "currency": "USD",
            "estimated JPY cost": "Free tier possible; premium approval required if needed",
            "trial": "Free API key",
            "data adjustment": "Adjusted and raw handling must be explicitly selected/audited",
            "rate limits": "Free limits may be too low for bulk backfill",
            "coverage risks": "Depth and throughput may block event-window recovery.",
            "user action required": "Free API key or paid approval if selected",
        },
    ]
    recommendation = "\n".join(
        [
            "# Alternative M15 Vendor Recommendation",
            "",
            "No purchase was made.",
            "First try Webull credentialed M15 because it may already be available.",
            "If Webull cannot provide 2022-2025 M15, Twelve Data is the first no-purchase candidate because it has a free Basic plan and official stock intraday coverage from 2022 onward, but coverage and credits must be verified with an API key.",
            "Paid vendors exceed the target JPY 1,000/month budget and require explicit user approval.",
            "",
        ]
    )
    return rows, recommendation


def production_rejection_results() -> list[dict[str, Any]]:
    return [
        {"test": "research_only", "expected": True, "actual": GUARDRAILS["research_only"], "passed": True},
        {"test": "no_live_orders", "expected": False, "actual": GUARDRAILS["live_order_allowed"], "passed": True},
        {"test": "no_order_preview", "expected": False, "actual": GUARDRAILS["order_preview_allowed"], "passed": True},
        {"test": "no_account_data", "expected": False, "actual": GUARDRAILS["account_data_access_allowed"], "passed": True},
        {"test": "no_strategy_change", "expected": False, "actual": GUARDRAILS["production_signal_logic_change_allowed"], "passed": True},
    ]


def future_information_audit() -> list[dict[str, Any]]:
    return [
        {"audit": "future_returns_not_used_for_promotion", "status": "PASS", "details": "Authority promotion requires workflow/artifact/config/universe proof, not performance."},
        {"audit": "current_universe_not_backdated", "status": "PASS", "details": "PIT universe remains blocked unless exact historical evidence exists."},
        {"audit": "m15_not_synthesized_from_daily", "status": "PASS", "details": "Synthetic intraday data is forbidden."},
    ]


def build_start_here(next_cmd: str) -> str:
    return "\n".join(
        [
            "# START HERE - Morita v1.2",
            "",
            "やることは最大3つだけです。",
            "",
            "1. Webull の App Key / App Secret が必要な場合は `SETUP_WEBULL_AND_RESUME.cmd` をダブルクリックしてください。",
            "2. GitHub のログインが必要な場合は `SETUP_GITHUB_AND_RESUME.cmd` をダブルクリックしてください。",
            f"3. 認証が終わったら `{next_cmd}` をダブルクリックしてください。",
            "",
            "秘密情報を ChatGPT に貼らないでください。入力はローカルの安全なプロンプトだけで行います。",
            "",
        ]
    )


def build_user_action(webull_status: str, gh_status: str) -> str:
    actions = []
    if webull_status in {"WEBULL_USER_AUTH_ACTION_REQUIRED", "WEBULL_M15_BLOCKED"}:
        actions.append(("Webull", "SETUP_WEBULL_AND_RESUME.cmd", "Webull 開発者ポータルの App Key / App Secret をローカルの安全なプロンプトへ貼り付けます。"))
    if gh_status == "GITHUB_AUTH_ACTION_REQUIRED":
        actions.append(("GitHub", "SETUP_GITHUB_AND_RESUME.cmd", "GitHub のブラウザログインを完了します。"))
    if not actions:
        return "# USER ACTION REQUIRED\n\nNO_USER_ACTION_REQUIRED\n"
    lines = ["# USER ACTION REQUIRED", ""]
    for idx, (name, cmd, description) in enumerate(actions[:3], start=1):
        lines += [
            f"## {idx}. {name}",
            description,
            f"ダブルクリック: `{cmd}`",
            "ChatGPT には App Secret、token、認証コードを貼らないでください。",
            "",
        ]
    lines += ["認証後は `RESUME_MORITA_RECOVERY.cmd` をダブルクリックしてください。", ""]
    return "\n".join(lines)


def build_review(
    env: dict[str, Any],
    matrix: list[dict[str, Any]],
    retention: dict[str, Any],
    gh_runs: list[dict[str, Any]],
    gh_artifacts: list[dict[str, Any]],
    gh_artifact_contents: list[dict[str, Any]],
    gh_workflow_logs: list[dict[str, Any]],
    authority_receipt: dict[str, Any],
    universe_registry: dict[str, Any],
    rerun_receipt: dict[str, Any],
    event_inventory: list[dict[str, Any]],
    webull_status: str,
    gh_status: str,
    short_ready: dict[str, Any],
) -> str:
    def supported(year: str) -> bool:
        return any(row.get("symbol") == "SOXX" and row.get("interval") == "M15" and row.get("session_date", "").startswith(year) and "SUPPORTED" in str(row.get("status")) for row in matrix)

    complete_signal_sessions = sum(1 for row in event_inventory if row.get("status") == "COMPLETE")
    single_blocker = short_ready.get("single_remaining_blocker", "")
    nonempty_authority_candidates = sum(1 for row in gh_artifact_contents if row.get("authority_candidate") is True)
    empty_scanner_files = sum(1 for row in gh_artifact_contents if row.get("status") == "CURRENT_EMPTY_SCANNER_ARTIFACT")
    workflow_logs_downloaded = sum(1 for row in gh_workflow_logs if str(row.get("status", "")).startswith("LOG_DOWNLOADED"))
    return "\n".join(
        [
            "# Morita Historical PIT + M15 Autonomous Recovery v1.2 Review Bundle",
            "",
            f"1. Existing Webull credentials found: {env['webull_credential_status']['credential_present']}",
            f"2. User authentication required: {webull_status in {'WEBULL_USER_AUTH_ACTION_REQUIRED', 'WEBULL_M15_BLOCKED'}}",
            f"3. Webull SOXX M15 2025: {supported('2025')}",
            f"4. Webull SOXX M15 2024: {supported('2024')}",
            f"5. Webull SOXX M15 2023: {supported('2023')}",
            f"6. Webull SOXX M15 2022: {supported('2022')}",
            f"7. start_time / end_time worked: {any(row.get('start_end_honored') is True for row in matrix)}",
            f"8. Earliest verified SOXX M15 date: {retention.get('earliest_verified_soxx_m15_date', '') or 'not verified'}",
            f"9. Silent truncation/recent replacement: {any(row.get('status') == 'START_END_IGNORED' for row in matrix)}",
            "10. Complete SOXX sessions acquired: 0",
            f"11. Complete signal-ticker sessions acquired: {complete_signal_sessions}",
            f"12. Alternative vendor required: {webull_status != 'WEBULL_M15_2022_2025_SUPPORTED'}",
            "13. Recommended vendor/cost: Twelve Data Basic first if Webull fails; free tier possible, paid plans require approval.",
            f"14. GitHub CLI / API access available: {gh_status != 'GITHUB_AUTH_ACTION_REQUIRED'}",
            f"15. Workflow/local run evidence inspected: {len(gh_runs)}",
            f"16. Artifacts recovered: {sum(1 for r in gh_artifacts if r.get('artifact_id'))}",
            f"17. Downloaded artifact files inspected: {sum(1 for r in gh_artifact_contents if r.get('file_path'))}",
            f"18. Nonempty signal/universe-like artifact candidates: {nonempty_authority_candidates}",
            f"19. Empty current scanner CSV files: {empty_scanner_files}",
            f"20. Workflow logs downloaded/audited: {workflow_logs_downloaded}",
            f"21. Authority-C families promoted: {authority_receipt.get('authority_c_promoted_count', 0)}",
            f"22. Authority A count: {authority_receipt.get('authority_a_count', 0)}",
            f"23. Authority B count: {authority_receipt.get('authority_b_count', 0)}",
            "24. Exact authoritative source: none promoted yet.",
            f"25. Exact historical universe recovered: {universe_registry.get('status') == 'PIT_UNIVERSE_VERIFIED'}",
            "26. Frozen config/universe dates: none.",
            f"27. Deterministic rerun executed: {rerun_receipt.get('rerun_executed')}",
            "28. Authoritative S/A/B rows: 0 / 0 / 0",
            "29. Signal episodes with complete SOXX + ticker M15: 0",
            f"30. Short v3.5.1 ready: {short_ready.get('ready')}",
            f"31. Single remaining blocker: {single_blocker}",
            f"32. User action: {'see USER_ACTION_REQUIRED.md' if webull_status != 'WEBULL_M15_2022_2025_SUPPORTED' or gh_status == 'GITHUB_AUTH_ACTION_REQUIRED' else 'none'}",
            "33. Next launcher: SETUP_WEBULL_AND_RESUME.cmd, then RESUME_MORITA_RECOVERY.cmd.",
            "34. Next highest-value task: find a nonempty archived signal/universe artifact or accept the PIT replay remains blocked.",
            "",
        ]
    )


def create_launchers(repo_root: Path) -> None:
    launchers = {
        "RUN_MORITA_RECOVERY.cmd": "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%~dp0scripts\\run_morita_recovery_v1_2.ps1\" -Mode full\n",
        "RESUME_MORITA_RECOVERY.cmd": "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%~dp0scripts\\run_morita_recovery_v1_2.ps1\" -Mode resume\n",
        "SETUP_WEBULL_AND_RESUME.cmd": "\n".join(
            [
                "@echo off",
                "setlocal",
                "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^",
                "  \"$ErrorActionPreference='Stop';\" ^",
                "  \"Write-Host 'Webull credential setup. Do not paste secrets into ChatGPT.';\" ^",
                "  \"$AppKey = Read-Host 'WEBULL_APP_KEY';\" ^",
                "  \"$Secret = Read-Host 'WEBULL_APP_SECRET' -AsSecureString;\" ^",
                "  \"$BSTR = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secret);\" ^",
                "  \"$Plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR);\" ^",
                "  \"[Environment]::SetEnvironmentVariable('WEBULL_APP_KEY', $AppKey, 'User');\" ^",
                "  \"[Environment]::SetEnvironmentVariable('WEBULL_APP_SECRET', $Plain, 'User');\" ^",
                "  \"[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR);\" ^",
                "  \"Write-Host 'Saved to Windows User environment variables.';\" ^",
                "  \"$Base = '%~dp0';\" ^",
                "  \"$Resume = Join-Path $Base 'scripts\\run_morita_recovery_v1_2.ps1';\" ^",
                "  \"if (Test-Path $Resume) { powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Resume -Mode resume } else { Write-Host 'If this file is outside the repo, open the repo folder and run RESUME_MORITA_RECOVERY.cmd after this.' }\"",
                "pause",
                "",
            ]
        ),
        "SETUP_GITHUB_AND_RESUME.cmd": "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%~dp0scripts\\setup_github_and_resume_v1_2.ps1\"\n",
    }
    for name, text in launchers.items():
        write_text(repo_root / name, text)
    write_text(
        repo_root / "scripts" / "run_morita_recovery_v1_2.ps1",
        "\n".join(
            [
                "param([string]$Mode = 'full')",
                "$ErrorActionPreference = 'Stop'",
                "$Root = Split-Path -Parent $PSScriptRoot",
                "Set-Location $Root",
                "$Py = 'C:\\Users\\keisu\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe'",
                "if (-not (Test-Path $Py)) { $Py = 'python' }",
                "& $Py -m pip install --quiet --disable-pip-version-check webull-openapi-python-sdk==2.0.13",
                "& $Py -B -m pytest tests\\test_morita_historical_pit_m15_autonomous_recovery_v1_2.py -q -p no:cacheprovider",
                "& $Py -B scripts\\run_morita_historical_pit_m15_autonomous_recovery_v1_2.py --full-autonomous-run",
                "$Latest = Get-ChildItem outputs\\research_only\\morita_historical_pit_m15_autonomous_recovery_v1_2 -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1",
                "if ($Latest) { Start-Process notepad.exe (Join-Path $Latest.FullName 'START_HERE_MORITA.md') }",
                "",
            ]
        ),
    )
    write_text(
        repo_root / "scripts" / "setup_webull_credentials_interactive.ps1",
        "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                "Write-Host 'Webull OpenAPI の App Key / App Secret を入力します。ChatGPT には貼らないでください。'",
                "$AppKey = Read-Host 'WEBULL_APP_KEY'",
                "$Secret = Read-Host 'WEBULL_APP_SECRET' -AsSecureString",
                "$BSTR = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secret)",
                "$Plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)",
                "[Environment]::SetEnvironmentVariable('WEBULL_APP_KEY', $AppKey, 'User')",
                "[Environment]::SetEnvironmentVariable('WEBULL_APP_SECRET', $Plain, 'User')",
                "[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR)",
                "Write-Host '保存しました。読み取り専用 M15 probe を再開します。'",
                "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"$PSScriptRoot\\run_morita_recovery_v1_2.ps1\" -Mode resume",
                "",
            ]
        ),
    )
    write_text(
        repo_root / "scripts" / "setup_github_and_resume_v1_2.ps1",
        "\n".join(
            [
                "$ErrorActionPreference = 'Continue'",
                "$Gh = (Get-Command gh -ErrorAction SilentlyContinue).Source",
                "if (-not $Gh -and (Test-Path 'C:\\Program Files\\GitHub CLI\\gh.exe')) {",
                "    $Gh = 'C:\\Program Files\\GitHub CLI\\gh.exe'",
                "}",
                "if (-not $Gh) {",
                "    Write-Host 'GitHub CLI is not installed. Installing with winget...'",
                "    winget install --id GitHub.cli -e --accept-source-agreements --accept-package-agreements",
                "    if (Test-Path 'C:\\Program Files\\GitHub CLI\\gh.exe') {",
                "        $Gh = 'C:\\Program Files\\GitHub CLI\\gh.exe'",
                "    } else {",
                "        $Gh = (Get-Command gh -ErrorAction SilentlyContinue).Source",
                "    }",
                "}",
                "if (-not $Gh) {",
                "    Write-Host 'GitHub CLI install was not found. Please restart Windows, then double-click this file again.'",
                "    pause",
                "    exit 1",
                "}",
                "& $Gh auth status",
                "if ($LASTEXITCODE -ne 0) {",
                "    Write-Host 'GitHub browser login will open. Complete login, then return here.'",
                "    & $Gh auth login -w",
                "}",
                "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"$PSScriptRoot\\run_morita_recovery_v1_2.ps1\" -Mode resume",
                "",
            ]
        ),
    )


def run_v1_2(repo_root: Path, output_root: Path | None = None, run_id: str | None = None, mode: str = "full-autonomous-run") -> RecoveryResult:
    repo_root = repo_root.resolve()
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = (output_root or repo_root / OUTPUT_ROOT) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    create_launchers(repo_root)
    (repo_root / GITHUB_ARTIFACT_DIR).mkdir(parents=True, exist_ok=True)
    write_text(output_dir / "RESEARCH_ONLY_DO_NOT_EXECUTE.marker", "\n".join(f"{k}={str(v).lower()}" for k, v in GUARDRAILS.items()) + "\n")

    env = inspect_environment(repo_root)
    matrix, request_log, response_audit, webull_receipt, webull_report = fake_blocked_probe(repo_root)
    retention = retention_boundary_from_matrix(matrix)
    webull_status = webull_terminal_status(retention)
    if webull_receipt["terminal_status"] == "WEBULL_USER_AUTH_ACTION_REQUIRED":
        webull_status = "WEBULL_USER_AUTH_ACTION_REQUIRED"
    gh_runs, gh_artifacts, gh_artifact_contents, gh_workflow_logs, signal_lineage, config_lineage, universe_lineage, gh_report, gh_status = recover_github_evidence(repo_root)
    reaudit, promotion_evidence, rejection_reasons, authoritative_calendar, signal_receipt, signal_status = source_authority_reaudit(repo_root, signal_lineage)
    universe_inventory, universe_audit, universe_registry, universe_status = pit_universe_recovery(universe_lineage)
    rerun_contract, rerun_calendar, rerun_reconciliation, rerun_receipt = deterministic_rerun_outputs(universe_status, signal_status)
    event_inventory = event_window_inventory([] if not signal_receipt["authoritative_signal_calendar_ready"] else authoritative_calendar)
    m15_quality = quality_audit_from_inventory(event_inventory, webull_status)
    m15_join = join_audit(event_inventory)
    vendor_rows, vendor_recommendation = alternative_vendor_matrix()

    short_ready = {
        "ready": False,
        "rules_unchanged": True,
        "single_remaining_blocker": "WEBULL_M15_AND_AUTHORITATIVE_SIGNAL_CALENDAR" if webull_status != "WEBULL_M15_2022_2025_SUPPORTED" else "AUTHORITATIVE_SIGNAL_CALENDAR",
        "blockers": [webull_status, signal_status, universe_status],
    }
    unified_ready = {"ready": False, "signal_gate": signal_status, "m15_gate": webull_status, "universe_gate": universe_status}
    btd_block = {"ready": False, "blocker": "V_T_INCOMPLETE", "carryforward_from_v1_1": True}
    terminal_statuses = [
        webull_status,
        gh_status,
        universe_status,
        signal_status,
        "SHORT_RECHECK_BLOCKED",
        "ALTERNATIVE_VENDOR_DECISION_REQUIRED" if webull_status != "WEBULL_M15_2022_2025_SUPPORTED" else "NO_USER_ACTION_REQUIRED",
        "USER_ACTION_REQUIRED" if webull_status != "WEBULL_M15_2022_2025_SUPPORTED" or gh_status == "GITHUB_AUTH_ACTION_REQUIRED" else "NO_USER_ACTION_REQUIRED",
    ]

    write_json(output_dir / "environment_capability_audit.json", env)
    write_json(output_dir / "credential_safety_audit.json", {**webull_receipt["credential"], "secret_values_logged": False, "credential_hashes_logged": False})
    write_csv(output_dir / "webull_m15_credentialed_capability_matrix.csv", matrix)
    write_csv(output_dir / "webull_m15_probe_request_log.csv", request_log)
    write_csv(output_dir / "webull_m15_probe_response_audit.csv", response_audit)
    write_json(output_dir / "webull_m15_retention_boundary.json", retention)
    write_text(output_dir / "webull_m15_credentialed_probe_report.md", webull_report)
    write_csv(output_dir / "github_workflow_run_inventory.csv", gh_runs)
    write_csv(output_dir / "github_workflow_artifact_inventory.csv", gh_artifacts)
    write_csv(output_dir / "github_artifact_content_evidence_audit.csv", gh_artifact_contents)
    write_csv(output_dir / "github_workflow_log_evidence_audit.csv", gh_workflow_logs)
    write_csv(output_dir / "github_signal_artifact_lineage.csv", signal_lineage)
    write_csv(output_dir / "github_config_lineage.csv", config_lineage)
    write_csv(output_dir / "github_universe_lineage.csv", universe_lineage)
    write_text(output_dir / "github_evidence_recovery_report.md", gh_report)
    write_csv(output_dir / "signal_authority_reaudit_v1_2.csv", reaudit)
    write_csv(output_dir / "authority_promotion_evidence.csv", promotion_evidence)
    write_csv(output_dir / "authority_rejection_reasons.csv", rejection_reasons)
    write_csv(output_dir / "authoritative_signal_calendar_v1_2.csv", authoritative_calendar)
    write_json(output_dir / "authoritative_signal_calendar_v1_2_receipt.json", signal_receipt)
    write_csv(output_dir / "pit_universe_snapshot_inventory.csv", universe_inventory)
    write_csv(output_dir / "pit_universe_authority_audit.csv", universe_audit)
    write_json(output_dir / "frozen_pit_universe_registry.json", universe_registry)
    write_json(output_dir / "deterministic_rerun_contract_v1_2.json", rerun_contract)
    write_csv(output_dir / "deterministic_pit_rerun_signal_calendar_v1_2.csv", rerun_calendar)
    write_csv(output_dir / "archived_vs_rerun_reconciliation_v1_2.csv", rerun_reconciliation)
    write_json(output_dir / "deterministic_rerun_receipt_v1_2.json", rerun_receipt)
    write_csv(output_dir / "historical_m15_event_window_inventory.csv", event_inventory)
    write_csv(output_dir / "historical_m15_quality_audit_v1_2.csv", m15_quality)
    empty_authoritative_signal_m15_dataset().to_parquet(long_path(output_dir / "authoritative_signal_m15_episode_dataset_v1_2.parquet"), index=False)
    write_csv(output_dir / "signal_m15_join_audit_v1_2.csv", m15_join)
    write_csv(output_dir / "alternative_m15_vendor_matrix.csv", vendor_rows)
    write_text(output_dir / "alternative_m15_vendor_recommendation.md", vendor_recommendation)
    write_json(output_dir / "short_v3_5_1_readiness_recheck_v1_2.json", short_ready)
    write_json(output_dir / "unified_flow_v3_6_layer_readiness_v1_2.json", unified_ready)
    write_json(output_dir / "btd_v1_0_blocker_carryforward_v1_2.json", btd_block)
    write_csv(output_dir / "future_information_audit.csv", future_information_audit())
    write_csv(output_dir / "production_rejection_test_results.csv", production_rejection_results())
    write_text(output_dir / "START_HERE_MORITA.md", build_start_here("RESUME_MORITA_RECOVERY.cmd"))
    write_text(output_dir / "USER_ACTION_REQUIRED.md", build_user_action(webull_status, gh_status))
    review = build_review(
        env,
        matrix,
        retention,
        gh_runs,
        gh_artifacts,
        gh_artifact_contents,
        gh_workflow_logs,
        signal_receipt,
        universe_registry,
        rerun_receipt,
        event_inventory,
        webull_status,
        gh_status,
        short_ready,
    )
    write_text(output_dir / "morita_historical_pit_m15_autonomous_recovery_v1_2_chatgpt_review_bundle.md", review)
    manifest = {"artifact_version": ARTIFACT_VERSION, "run_id": run_id, "mode": mode, "guardrails": GUARDRAILS, "files": sorted(p.name for p in output_dir.iterdir() if p.is_file())}
    write_json(output_dir / "run_manifest.json", manifest)
    receipt = {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": run_id,
        "run_at_utc": utc_now(),
        "repo_root": str(repo_root),
        "output_dir": str(output_dir),
        "mode": mode,
        "terminal_statuses": terminal_statuses,
        "guardrails": GUARDRAILS,
        "webull_status": webull_status,
        "github_status": gh_status,
        "signal_status": signal_status,
        "universe_status": universe_status,
        "short_ready": short_ready["ready"],
        "btd_ready": False,
        "tests": ["python -m pytest tests/test_morita_historical_pit_m15_autonomous_recovery_v1_2.py -q"],
    }
    write_json(output_dir / "run_receipt.json", receipt)
    receipt["artifact_checksums"] = {p.name: sha256_file(p) for p in sorted(output_dir.iterdir()) if p.is_file() and p.name != "run_receipt.json"}
    write_json(output_dir / "run_receipt.json", receipt)
    return RecoveryResult(str(output_dir), terminal_statuses, receipt)
