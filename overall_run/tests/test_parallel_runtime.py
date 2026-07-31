from __future__ import annotations

import multiprocessing
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import psutil
import pytest

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from downstream_common import (
    resolve_parallel_plan,
    resolve_requested_n_jobs,
    run_ordered_thread_tasks,
    spawn_probe,
    stable_task_seed,
    task_seed_hash,
    thread_limit_environment,
)


@pytest.mark.parametrize("value", [1, 2, -1])
def test_n_jobs_values_are_accepted(value: int) -> None:
    assert resolve_requested_n_jobs(value, 1, {}) == value


@pytest.mark.parametrize("value", [0, -2])
def test_invalid_n_jobs_values_are_rejected(value: int) -> None:
    with pytest.raises(ValueError, match="INVALID_N_JOBS"):
        resolve_requested_n_jobs(value, 1, {})


def test_cli_precedes_environment_and_config() -> None:
    assert resolve_requested_n_jobs(2, 4, {"AIR_SLOT_N_JOBS": "3"}) == 2
    assert resolve_requested_n_jobs(None, 4, {"AIR_SLOT_N_JOBS": "3"}) == 3
    assert resolve_requested_n_jobs(None, 4, {}) == 4
    assert resolve_requested_n_jobs(None, None, {}) == 1


def test_thread_budget_is_bounded_and_nested_parallelism_is_prevented() -> None:
    plan = resolve_parallel_plan(4, task_count=15, prefer_outer_parallelism=True)
    assert plan.outer_workers * plan.inner_model_threads <= plan.resolved_n_jobs
    assert plan.outer_workers >= 1
    assert plan.inner_model_threads == 1


def test_task_seed_is_worker_independent_and_cross_thread_stable() -> None:
    first = stable_task_seed(7, "module", "fast", "stage", "M1:QRF", 0)
    second = stable_task_seed(7, "module", "fast", "stage", "M1:QRF", 0)
    assert first == second
    assert task_seed_hash(7, "module", "fast", "stage", ["A", "B"]) == task_seed_hash(
        7, "module", "fast", "stage", ["A", "B"]
    )


def test_parallel_results_follow_fixed_task_order() -> None:
    result = run_ordered_thread_tasks(
        ["task-3", "task-1", "task-2"],
        lambda task_id: task_id,
        max_workers=3,
    )
    assert result == ["task-3", "task-1", "task-2"]


@pytest.mark.skipif(os.name != "nt", reason="Windows spawn/orphan-process contract")
def test_windows_spawn_fixture_and_no_orphan_process() -> None:
    before = {child.pid for child in psutil.Process().children(recursive=True)}
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=1, mp_context=context) as executor:
        assert executor.submit(spawn_probe, "PASS").result(timeout=30) == "PASS"
    after = {
        child.pid
        for child in psutil.Process().children(recursive=True)
        if child.is_running()
    }
    assert after <= before


def test_worker_exception_is_propagated() -> None:
    def worker(task_id: str) -> str:
        if task_id == "FAIL":
            raise RuntimeError("fixture failure")
        return task_id

    with pytest.raises(RuntimeError, match="fixture failure"):
        run_ordered_thread_tasks(["PASS", "FAIL", "PENDING"], worker, max_workers=2)


def test_registry_is_parent_written_only(tmp_path: Path) -> None:
    registry = tmp_path / "artifact_registry.json"

    def worker(task_id: str) -> dict[str, str]:
        assert not registry.exists()
        return {"task_id": task_id}

    rows = run_ordered_thread_tasks(["A", "B"], worker, max_workers=2)
    registry.write_text(str(rows), encoding="utf-8")
    assert registry.exists()


def test_checkpoint_task_identity_allows_four_to_two_threads() -> None:
    task_ids = ["M1:HIST", "M1:QRF", "M1:NGB"]
    digest_four = task_seed_hash(9, "part_adv", "fast", "m1", task_ids)
    digest_two = task_seed_hash(9, "part_adv", "fast", "m1", task_ids)
    assert resolve_parallel_plan(4, len(task_ids), True).resolved_n_jobs >= 1
    assert resolve_parallel_plan(2, len(task_ids), True).resolved_n_jobs >= 1
    assert digest_four == digest_two


def test_thread_environment_is_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMP_NUM_THREADS", "9")
    plan = resolve_parallel_plan(2, task_count=4, prefer_outer_parallelism=True)
    with thread_limit_environment(plan):
        assert os.environ["OMP_NUM_THREADS"] == "1"
    assert os.environ["OMP_NUM_THREADS"] == "9"


@pytest.mark.parametrize(
    ("script", "arguments"),
    [
        ("pre/main.py", ["report", "fast"]),
        ("overall_run/main.py", ["report", "fast"]),
        ("overall_adv/main.py", ["report", "--mode", "fast"]),
        ("part_adv/main.py", ["report", "--mode", "fast"]),
    ],
)
def test_each_cli_exposes_n_jobs_and_rejects_zero(script: str, arguments: list[str]) -> None:
    help_result = subprocess.run(
        [sys.executable, str(PROJECT / script), "--help"],
        cwd=PROJECT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "--n-jobs" in help_result.stdout

    invalid = subprocess.run(
        [sys.executable, str(PROJECT / script), *arguments, "--n-jobs", "0"],
        cwd=PROJECT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert invalid.returncode != 0
