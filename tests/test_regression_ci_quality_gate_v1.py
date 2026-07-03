from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import test_quality_v1 as q


def test_registry_parses_and_has_unique_shards() -> None:
    registry = q.load_registry()
    shard_ids = [shard["shard_id"] for shard in registry["shards"]]
    assert len(shard_ids) == len(set(shard_ids))
    assert registry["canonical_collection_command"] == ["python", "-m", "pytest", "--collect-only", "-q"]
    assert registry["path_regression"]["shard_id"] == "windows_path_regression"


def test_collection_comparison_detects_duplicate_missing_and_unexpected() -> None:
    result = q.compare_collections(
        ["tests/a.py::test_a", "tests/b.py::test_b"],
        {
            "s1": ["tests/a.py::test_a", "tests/c.py::test_c"],
            "s2": ["tests/a.py::test_a"],
        },
    )
    assert result["coverage_equal"] is False
    assert result["duplicate_ids"] == ["tests/a.py::test_a"]
    assert result["missing_ids"] == ["tests/b.py::test_b"]
    assert result["unexpected_ids"] == ["tests/c.py::test_c"]


def test_collection_comparison_output_order_is_deterministic() -> None:
    left = q.compare_collections(["tests/b.py::test_b", "tests/a.py::test_a"], {"z": ["tests/b.py::test_b"], "a": ["tests/a.py::test_a"]})
    right = q.compare_collections(["tests/a.py::test_a", "tests/b.py::test_b"], {"a": ["tests/a.py::test_a"], "z": ["tests/b.py::test_b"]})
    assert json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)
    assert list(left["shard_counts"]) == ["a", "z"]


def test_parse_node_ids_ignores_summary_lines() -> None:
    output = """
tests/test_a.py::test_one
tests/test_a.py::test_two[param]
2 tests collected in 0.01s
================ no tests ran ================
"""
    assert q.parse_node_ids(output) == ["tests/test_a.py::test_one", "tests/test_a.py::test_two[param]"]


def test_no_forbidden_options_in_registry_or_commands() -> None:
    registry = q.load_registry()
    for shard in registry["shards"]:
        command = q.build_pytest_command(sys.executable, shard["pytest_targets"], Path("C:/t/example"), durations=1)
        assert "--ignore" not in command
        assert "--deselect" not in command
        assert "-k" not in command
    with pytest.raises(ValueError, match="forbidden_pytest_option"):
        q.assert_no_forbidden_pytest_options(["--deselect=tests/test_a.py::test_one"])


def test_short_unique_temp_root_creation_and_cleanup() -> None:
    first = q.create_short_temp_root("p15e")
    second = q.create_short_temp_root("p15e")
    try:
        assert first != second
        assert first.exists()
        assert second.exists()
        assert len(str(first)) < 80
    finally:
        q.cleanup_temp_root(first)
        q.cleanup_temp_root(second)
    assert not first.exists()
    assert not second.exists()


def test_every_test_file_is_assigned_once_in_coverage_shards() -> None:
    registry = q.load_registry()
    expected = sorted(path.relative_to(REPO_ROOT).as_posix() for path in (REPO_ROOT / "tests").glob("test_*.py"))
    assigned = sorted(target for shard in registry["shards"] for target in shard["pytest_targets"])
    assert assigned == expected


def test_windows_path_regression_targets_original_qqq_nodes() -> None:
    targets = q.load_registry()["path_regression"]["pytest_targets"]
    assert len(targets) == 11
    assert all(target.startswith("tests/test_market_bomb_flow_pressure_research_v0.py::test_qqq_phase1_") for target in targets)
    assert any("readiness_valid_path_outputs_report" in target for target in targets)


def test_local_runner_fails_on_failed_shard(tmp_path: Path) -> None:
    failing = tmp_path / "test_intentional_failure.py"
    failing.write_text("def test_intentional_failure():\n    assert False\n", encoding="utf-8")
    registry = {
        "registry_version": "test",
        "purpose": "unit test",
        "canonical_collection_command": ["python", "-m", "pytest", "--collect-only", "-q"],
        "shards": [
            {
                "shard_id": "failing",
                "description": "intentional failure",
                "pytest_targets": [str(failing)],
                "platform_scope": "unit",
                "expected_runtime_class": "short",
            }
        ],
        "path_regression": {"shard_id": "none", "pytest_targets": []},
    }
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "scripts/run_full_regression.py", "--registry", str(registry_path), "--shard", "failing", "--artifacts-dir", str(tmp_path / "artifacts")],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    assert completed.returncode != 0


def test_workflow_regression_jobs_do_not_mask_failures() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "continue-on-error" not in workflow
    assert "allow-failure" not in workflow
    assert "--ignore" not in workflow
    assert "--deselect" not in workflow


def test_workflow_artifacts_exclude_raw_and_historical_roots() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    forbidden = ["market_bomb_history", "raw/", "raw\\", "canonical"]
    for token in forbidden:
        assert token not in workflow

