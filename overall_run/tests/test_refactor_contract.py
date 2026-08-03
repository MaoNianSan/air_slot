from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.config import AUTHORITATIVE_CODE, load_config
from src.artifacts import (
    CORE_REGISTRY_CONTRACT_ID,
    CORE_REQUIRED_ARTIFACT_IDS,
    PUBLICATION_REGISTRY_CONTRACT_ID,
    ArtifactContractError,
    validate_registry,
    write_artifact_registry,
)
from src.m1_metrics import approximate_crps, pinball_loss
from src.m4 import evaluate_m4, fit_m4, screen_physical_actions
from src.m4_pnb_audit import manual_pnb_reconstruction
from src.pipeline import run_experiment
from src.pipeline_modes import _is_engineering_dev_summary
from src.report import generate_report, publish_report, validate_publication
from src.scientific_transition import (
    load_transition_contract,
    sha256_file,
    validate_fixture_hashes,
    validate_scientific_transition,
)
from src.utils import stable_seed


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "output_logs" / "POST_REFACTOR_BASELINE_FILES_20260727_113547"
BASELINE_FAST = BASELINE / "overall_run" / "fast"
SCHEMA_FIXTURES = {
    "metrics/m1_predictions_evaluation.parquet": ["episode_id", "snapshot_id"],
    "metrics/m2_summary.parquet": ["episode_id", "snapshot_id"],
    "m3_response_samples.parquet": ["action_id", "sample_id"],
    "m4_candidate_screen.parquet": ["episode_id", "snapshot_id", "action_id"],
    "m4_rankings.parquet": ["episode_id", "snapshot_id", "action_id"],
}


def test_engineering_dev_validation_boundary_is_explicit() -> None:
    summary = {
        "run_purpose": "three_change_engineering_validation",
        "publication_allowed": False,
        "formal_baseline_replaced": False,
    }
    assert _is_engineering_dev_summary(summary)
    assert not _is_engineering_dev_summary({**summary, "publication_allowed": True})
    assert not _is_engineering_dev_summary({**summary, "formal_baseline_replaced": True})
    assert not _is_engineering_dev_summary({**summary, "run_purpose": "formal_fast"})


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
    contract = load_transition_contract(ROOT / "overall_run")
    validate_fixture_hashes(BASELINE_FAST, contract)
    frozen = json.loads((BASELINE_FAST / "merged_config.json").read_text(encoding="utf-8"))
    formal_current = json.loads(
        (ROOT / "overall_run" / "output" / "fast" / "merged_config.json").read_text(
            encoding="utf-8"
        )
    )
    result = validate_scientific_transition(frozen, formal_current, contract)
    assert result["status"] == "PASS"
    current = load_config(ROOT / "overall_run", "fast")
    assert current.config_hash != contract["current_config_hash"]
    assert current.scientific["m3"]["publication_allowed"] is False
    assert current.scientific["m3"]["action_library_version"] == "M3_RESPONSE_V3_EXPANDED_PROVISIONAL"
    registry = json.loads((BASELINE_FAST / "artifact_registry.json").read_text(encoding="utf-8"))
    assert registry["config_hash"] == contract["historical_config_hash"]
    assert sha256_file(BASELINE_FAST / "artifact_registry.json") == contract["historical_registry_sha256"]


def test_refactor_config_mismatch_is_explicit() -> None:
    current = load_config(ROOT / "overall_run", "fast")
    contract = load_transition_contract(ROOT / "overall_run")
    changed = json.loads(json.dumps(current.merged))
    changed["m2"]["graph_edges"]["P_to_R"] = 0.999
    frozen = json.loads((BASELINE_FAST / "merged_config.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="UNDECLARED_SCIENTIFIC_DELTA"):
        validate_scientific_transition(frozen, changed, contract)


def test_core_and_publication_registry_contracts_are_distinct(tmp_path: Path) -> None:
    for name in CORE_REQUIRED_ARTIFACT_IDS:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode("ascii"))
    core = write_artifact_registry(
        tmp_path, mode="fast", run_id="test", config_hash="c", implementation_hash="i",
        contract_version="v", upstream_artifact_hashes={}, scientific_status="PASS",
        artifact_names=list(CORE_REQUIRED_ARTIFACT_IDS), registry_kind="core",
        required_artifact_ids=CORE_REQUIRED_ARTIFACT_IDS,
    )
    assert core["registry_contract_id"] == CORE_REGISTRY_CONTRACT_ID
    validate_registry(
        tmp_path, expected_config_hash="c", expected_implementation_hash="i",
        expected_contract_version="v", allowed_scientific_statuses={"PASS"},
        expected_registry_kind="core", required_artifact_ids=CORE_REQUIRED_ARTIFACT_IDS,
    )
    extra = tmp_path / "publication_manifest.json"
    extra.write_text("{}", encoding="utf-8")
    publication = write_artifact_registry(
        tmp_path, mode="fast", run_id="test", config_hash="c", implementation_hash="i",
        contract_version="v", upstream_artifact_hashes={}, scientific_status="PASS",
        artifact_names=[*CORE_REQUIRED_ARTIFACT_IDS, "publication_manifest.json"],
        registry_kind="publication",
        required_artifact_ids=[*CORE_REQUIRED_ARTIFACT_IDS, "publication_manifest.json"],
    )
    assert publication["registry_contract_id"] == PUBLICATION_REGISTRY_CONTRACT_ID
    with pytest.raises(ArtifactContractError, match="REGISTRY_KIND_MISMATCH"):
        validate_registry(
            tmp_path, expected_config_hash="c", expected_implementation_hash="i",
            expected_contract_version="v", allowed_scientific_statuses={"PASS"},
            expected_registry_kind="core", required_artifact_ids=CORE_REQUIRED_ARTIFACT_IDS,
        )


def test_refactor_seed_namespace_equivalence() -> None:
    parts = (20260718, "M3_RESPONSE", "A11", "success")
    payload = "\x1f".join(str(value) for value in parts).encode("utf-8")
    expected = int(hashlib.sha256(payload).hexdigest()[:16], 16) % (2**32 - 1)
    assert stable_seed(*parts) == expected
    assert stable_seed(20260718, "M1", "f1") != stable_seed(20260718, "M3", "f1")


def test_refactor_action_order_equivalence() -> None:
    contract = load_transition_contract(ROOT / "overall_run")
    historical = pd.read_parquet(BASELINE_FAST / "action_metadata.parquet").sort_values(
        ["priority", "id"], kind="mergesort"
    ).reset_index(drop=True)
    current = pd.read_parquet(ROOT / "overall_run" / "output" / "fast" / "action_metadata.parquet").sort_values(
        ["priority", "id"], kind="mergesort"
    ).reset_index(drop=True)
    historical_ids = historical["id"].astype(str).tolist()
    additions = contract["allowed_changes"]["m3.actions.append"]
    assert historical_ids[0] == "A00"
    assert len(historical_ids) == len(set(historical_ids)) == 11
    assert current["id"].astype(str).tolist() == historical_ids + additions
    pd.testing.assert_frame_equal(
        historical,
        current[current["id"].isin(historical_ids)].reset_index(drop=True),
        check_exact=True,
    )


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
    contract = load_transition_contract(ROOT / "overall_run")
    validate_fixture_hashes(BASELINE_FAST, contract)
    registry = json.loads((BASELINE_FAST / "artifact_registry.json").read_text(encoding="utf-8"))
    registered = {str(entry["artifact_name"]): str(entry["sha256"]) for entry in registry["artifacts"]}
    for relative, required_keys in SCHEMA_FIXTURES.items():
        assert registered[relative] == contract["historical_fixture_hashes"][relative]
        left = pd.read_parquet(BASELINE_FAST / relative)
        right = pd.read_parquet(current / relative)
        assert list(left.columns) == list(right.columns)
        assert left.dtypes.astype(str).tolist() == right.dtypes.astype(str).tolist()
        assert set(required_keys).issubset(left.columns)


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
