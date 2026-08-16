from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = REPO_ROOT / "config" / "test_quality_v1" / "full_regression_shards.json"
FORBIDDEN_PYTEST_OPTIONS = ("--ignore", "--ignore-glob", "--deselect", "--continue-on-collection-errors", "-k")
NODE_ID_RE = re.compile(r"^(?P<node>(?:\.?[\\/])?tests[\\/].+::.+)$")


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def normalize_node_id(value: str) -> str:
    return value.strip().replace("\\", "/").lstrip("./")


def parse_node_ids(output: str) -> list[str]:
    ids: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or "::" not in line:
            continue
        match = NODE_ID_RE.match(line)
        if match:
            ids.append(normalize_node_id(match.group("node")))
    return sorted(ids)


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    registry = json.loads(path.read_text(encoding="utf-8"))
    seen: set[str] = set()
    for shard in registry.get("shards", []):
        shard_id = str(shard.get("shard_id", ""))
        if not shard_id:
            raise ValueError("shard_id_missing")
        if shard_id in seen:
            raise ValueError(f"duplicate_shard_id:{shard_id}")
        seen.add(shard_id)
        targets = shard.get("pytest_targets", [])
        if not isinstance(targets, list) or not targets:
            raise ValueError(f"pytest_targets_missing:{shard_id}")
        assert_no_forbidden_pytest_options([str(target) for target in targets])
    path_regression = registry.get("path_regression", {})
    if path_regression:
        assert_no_forbidden_pytest_options([str(target) for target in path_regression.get("pytest_targets", [])])
    return registry


def assert_no_forbidden_pytest_options(args: list[str]) -> None:
    for arg in args:
        for forbidden in FORBIDDEN_PYTEST_OPTIONS:
            if arg == forbidden or arg.startswith(f"{forbidden}="):
                raise ValueError(f"forbidden_pytest_option:{arg}")


def build_pytest_command(python_executable: str, targets: list[str], basetemp: Path | None = None, durations: int = 30, collect_only: bool = False) -> list[str]:
    command = [python_executable, "-m", "pytest", *targets]
    if collect_only:
        command.extend(["--collect-only", "-q"])
    else:
        command.extend(["-q", f"--durations={durations}"])
    if basetemp is not None:
        command.extend(["--basetemp", str(basetemp), "-o", f"cache_dir={basetemp / '.pytest_cache'}"])
    assert_no_forbidden_pytest_options(command)
    return command


def run_command(command: list[str], cwd: Path = REPO_ROOT, timeout: int | None = None) -> CommandResult:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    return CommandResult(command=command, returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


def collect_nodes_for_targets(python_executable: str, targets: list[str]) -> tuple[list[str], CommandResult]:
    result = run_command(build_pytest_command(python_executable, targets, collect_only=True), timeout=300)
    if result.returncode != 0:
        return [], result
    return parse_node_ids(result.stdout), result


def compare_collections(canonical_ids: list[str], shard_nodes: dict[str, list[str]]) -> dict[str, Any]:
    canonical = set(canonical_ids)
    owner: dict[str, list[str]] = {}
    for shard_id in sorted(shard_nodes):
        for node_id in shard_nodes[shard_id]:
            owner.setdefault(node_id, []).append(shard_id)
    union = set(owner)
    duplicate_ids = sorted(node_id for node_id, shard_ids in owner.items() if len(shard_ids) > 1)
    missing_ids = sorted(canonical - union)
    unexpected_ids = sorted(union - canonical)
    return {
        "canonical_count": len(canonical_ids),
        "union_count": len(union),
        "duplicate_count": len(duplicate_ids),
        "missing_count": len(missing_ids),
        "unexpected_count": len(unexpected_ids),
        "coverage_equal": not duplicate_ids and not missing_ids and not unexpected_ids and len(canonical_ids) == len(canonical),
        "duplicate_ids": duplicate_ids,
        "missing_ids": missing_ids,
        "unexpected_ids": unexpected_ids,
        "shard_counts": {shard_id: len(shard_nodes[shard_id]) for shard_id in sorted(shard_nodes)},
    }


def collect_coverage(registry: dict[str, Any], python_executable: str = sys.executable) -> dict[str, Any]:
    canonical_nodes, canonical_result = collect_nodes_for_targets(python_executable, [])
    shard_nodes: dict[str, list[str]] = {}
    command_results: dict[str, dict[str, Any]] = {
        "canonical": {
            "command": canonical_result.command,
            "returncode": canonical_result.returncode,
            "stderr": canonical_result.stderr,
        }
    }
    if canonical_result.returncode != 0:
        return {"coverage_equal": False, "collection_failed": "canonical", "command_results": command_results}
    for shard in registry["shards"]:
        shard_id = str(shard["shard_id"])
        nodes, result = collect_nodes_for_targets(python_executable, [str(target) for target in shard["pytest_targets"]])
        command_results[shard_id] = {"command": result.command, "returncode": result.returncode, "stderr": result.stderr}
        if result.returncode != 0:
            return {"coverage_equal": False, "collection_failed": shard_id, "command_results": command_results}
        shard_nodes[shard_id] = nodes
    comparison = compare_collections(canonical_nodes, shard_nodes)
    comparison["command_results"] = command_results
    comparison["registry_version"] = registry.get("registry_version")
    return comparison


def short_temp_parent() -> Path:
    requested = os.environ.get("PYTEST_SHORT_TEMP_PARENT")
    candidates: list[Path] = []
    if requested:
        candidates.append(Path(requested))
    if os.name == "nt":
        candidates.append(Path("C:/t"))
    candidates.append(Path(tempfile.gettempdir()))
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / f"probe_{uuid.uuid4().hex}"
            probe.mkdir()
            probe.rmdir()
            return candidate
        except OSError:
            continue
    raise RuntimeError("no_writable_short_temp_parent")


def create_short_temp_root(prefix: str = "p15e") -> Path:
    parent = short_temp_parent()
    root = parent / f"{prefix}_{uuid.uuid4().hex[:12]}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def cleanup_temp_root(path: Path) -> None:
    resolved = path.resolve()
    parent = resolved.parent
    if resolved == parent or not resolved.name.startswith("p15e"):
        raise ValueError(f"unsafe_temp_cleanup:{resolved}")
    shutil.rmtree(resolved, ignore_errors=True)

