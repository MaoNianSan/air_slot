from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import AUTHORITATIVE_CODE, load_config
from src.m1_metrics import approximate_crps, pinball_loss
from src.m4 import evaluate_m4, fit_m4, screen_physical_actions
from src.m4_pnb_audit import manual_pnb_reconstruction
from src.pipeline import run_experiment
from src.report import generate_report, publish_report, validate_publication
from src.utils import stable_seed


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "output_logs" / "POST_REFACTOR_BASELINE_FILES_20260727_113547"


def _subprocess_import(module: str, names: list[str]) -> None:
    code = f"from src.{module} import {', '.join(names)}; print('PASS')"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT / module.split(".")[0] if "." in module else ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_refactor_public_api_compatibility() -> None:
    assert callable(run_experiment)
    assert all(callable(value) for value in (
        fit_m4, screen_physical_actions, evaluate_m4,
        generate_report, publish_report, validate_publication,
    ))
    commands = {
        "pre": "from src.pipeline import build_all, load_config, validate_existing",
        "overall_adv": "from src.pipeline import report, run, validate",
        "part_adv": "from src.pipeline import MODELS, _RunTelemetry, report, run, validate",
    }
    for directory, statement in commands.items():
        result = subprocess.run(
            [sys.executable, "-c", statement], cwd=ROOT / directory,
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr


def test_refactor_config_merge_equivalence() -> None:
    current = load_config(ROOT / "overall_run", "fast")
    frozen = json.loads(
        (BASELINE / "overall_run" / "fast" / "merged_config.json").read_text(encoding="utf-8")
    )
    runtime_fields = {
        "requested_n_jobs", "resolved_n_jobs", "outer_workers", "inner_model_threads",
        "parallel_backend", "task_partition_version", "task_seed_strategy", "task_seed_hash",
    }
    assert current.merged == {key: value for key, value in frozen.items() if key not in runtime_fields}
    assert current.config_hash == "4ff9a8382e317df0f796cb3f4581f3ec529fe0767a48e7a73373d191aa188531"


def test_refactor_seed_namespace_equivalence() -> None:
    parts = (20260718, "M3_RESPONSE", "A11", "success")
    payload = "\x1f".join(str(value) for value in parts).encode("utf-8")
    expected = int(hashlib.sha256(payload).hexdigest()[:16], 16) % (2**32 - 1)
    assert stable_seed(*parts) == expected
    assert stable_seed(20260718, "M1", "f1") != stable_seed(20260718, "M3", "f1")


def test_refactor_action_order_equivalence() -> None:
    actions = pd.read_parquet(
        BASELINE / "overall_run" / "fast" / "action_metadata.parquet"
    )
    expected = actions.sort_values(["priority", "id"], kind="mergesort")["id"].tolist()
    assert expected[0] == "A00"
    assert len(expected) == len(set(expected)) == 11


def test_refactor_channel_order_equivalence() -> None:
    pre = {"F": np.array([4.0, 2.0]), "P": np.array([3.0, 1.0]), "R": np.array([2.0, 1.0])}
    recovery = {key: value * 0.2 for key, value in pre.items()}
    implementation = {key: np.array([0.1, 0.2]) for key in pre}
    first = manual_pnb_reconstruction(pre, recovery, implementation)
    reverse = lambda value: dict(reversed(list(value.items())))
    second = manual_pnb_reconstruction(reverse(pre), reverse(recovery), reverse(implementation))
    np.testing.assert_array_equal(first["net_benefit"], second["net_benefit"])


def test_refactor_metric_formula_equivalence() -> None:
    y = np.array([0.0, 2.0, 6.0])
    quantiles = np.array([0.1, 0.5, 0.9])
    qmat = np.array([[-1.0, 0.0, 2.0], [0.0, 2.0, 4.0], [2.0, 5.0, 7.0]])
    losses = np.column_stack([
        pinball_loss(y, qmat[:, index], tau)
        for index, tau in enumerate(quantiles)
    ])
    integrate = np.trapezoid if hasattr(np, "trapezoid") else np.trapz
    expected = 2.0 * integrate(losses, quantiles, axis=1)
    np.testing.assert_array_equal(approximate_crps(y, qmat, quantiles), expected)


def test_refactor_artifact_schema_equivalence() -> None:
    current = ROOT / "overall_run" / "output" / "fast"
    baseline = BASELINE / "overall_run" / "fast"
    paths = [
        "metrics/m1_predictions_evaluation.parquet",
        "metrics/m2_summary.parquet",
        "m3_response_samples.parquet",
        "m4_candidate_screen.parquet",
        "m4_rankings.parquet",
    ]
    for relative in paths:
        left = pd.read_parquet(baseline / relative)
        right = pd.read_parquet(current / relative)
        assert list(left.columns) == list(right.columns)
        assert left.dtypes.astype(str).tolist() == right.dtypes.astype(str).tolist()


def test_refactor_audit_isolation() -> None:
    pipeline_source = (ROOT / "overall_run" / "src" / "pipeline.py").read_text(encoding="utf-8")
    assert "m1_lineage" not in pipeline_source
    assert "m4_pnb_audit" not in pipeline_source


def test_refactor_no_duplicate_authoritative_path() -> None:
    assert len(AUTHORITATIVE_CODE) == len({path for path, _ in AUTHORITATIVE_CODE})
    tree = ast.parse((ROOT / "overall_run" / "src" / "pipeline.py").read_text(encoding="utf-8"))
    runs = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_experiment"]
    assert len(runs) == 1
    assert evaluate_m4.__module__ == "src.m4_evaluation"
    assert screen_physical_actions.__module__ == "src.m4_screening"
