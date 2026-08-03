from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from src.artifacts import CORE_REQUIRED_ARTIFACT_IDS, write_artifact_registry
from src.pipeline_checkpoint import requires_fast_acceptance
from src.report import (
    CORE_FIGURE_STEMS,
    M4_AUDIT_FILES,
    build_m4_diagnostics,
    validate_publication,
)


def _candidate(snapshot: str, *, physical: bool, decision: bool, candidate: bool) -> dict:
    return {
        "episode_id": f"e{snapshot}",
        "snapshot_id": snapshot,
        "flight_id": f"f{snapshot}",
        "airport": "EHAM",
        "snapshot_stage": "t1",
        "action_id": "A11",
        "trigger": True,
        "gate_capacity": physical,
        "gate_window": True,
        "gate_resource": True,
        "gate_authority": True,
        "gate_lead": True,
        "physical_feasible": physical,
        "gate_burden_ratio": decision,
        "gate_positive_net_benefit": decision,
        "decision_value_pass": decision,
        "candidate_flag": candidate,
        "recovery_ratio": 0.25 if decision else 0.10,
        "burden_ratio": 0.80 if decision else 1.20,
        "positive_net_benefit_probability": 0.70 if decision else 0.50,
    }


def test_middle_interface_smoke_does_not_require_long_run_recommendation() -> None:
    formal = {"smoke_subset": False}
    smoke = {"smoke_subset": True}
    assert requires_fast_acceptance("middle", formal, override_fast_gate=False)
    assert requires_fast_acceptance("full", formal, override_fast_gate=False)
    assert not requires_fast_acceptance("middle", smoke, override_fast_gate=False)
    assert not requires_fast_acceptance("middle", formal, override_fast_gate=True)


def test_m4_concentration_decomposition_is_exhaustive() -> None:
    candidates = pd.DataFrame([
        _candidate("sA", physical=False, decision=False, candidate=False),
        _candidate("sB", physical=True, decision=False, candidate=False),
        _candidate("sC", physical=True, decision=True, candidate=True),
        _candidate("sD", physical=True, decision=True, candidate=True),
    ])
    rankings = pd.DataFrame([
        {"episode_id": "esA", "snapshot_id": "sA", "flight_id": "fsA", "airport": "EHAM", "snapshot_stage": "t1", "action_id": "A00", "score": 1.0, "recommended": True},
        {"episode_id": "esB", "snapshot_id": "sB", "flight_id": "fsB", "airport": "EHAM", "snapshot_stage": "t1", "action_id": "A00", "score": 1.0, "recommended": True},
        {"episode_id": "esC", "snapshot_id": "sC", "flight_id": "fsC", "airport": "EHAM", "snapshot_stage": "t1", "action_id": "A00", "score": 1.0, "recommended": True},
        {"episode_id": "esC", "snapshot_id": "sC", "flight_id": "fsC", "airport": "EHAM", "snapshot_stage": "t1", "action_id": "A11", "score": 2.0, "recommended": False},
        {"episode_id": "esD", "snapshot_id": "sD", "flight_id": "fsD", "airport": "EHAM", "snapshot_stage": "t1", "action_id": "A00", "score": 1.0, "recommended": False},
        {"episode_id": "esD", "snapshot_id": "sD", "flight_id": "fsD", "airport": "EHAM", "snapshot_stage": "t1", "action_id": "A11", "score": 0.5, "recommended": True},
    ])

    result = build_m4_diagnostics(
        candidates,
        rankings,
        burden_ratio_max=1.00,
        positive_net_benefit_probability_min=0.60,
    )

    concentration = result["concentration"].set_index("category")
    assert concentration["snapshot_count"].to_dict() == {
        "A_NO_NON_NULL_PHYSICALLY_FEASIBLE": 1,
        "B_PHYSICAL_EXISTS_NONE_PASS_DECISION_VALUE": 1,
        "C_NON_NULL_CANDIDATE_EXISTS_A00_LOWER_SCORE": 1,
        "D_NON_NULL_ACTION_RECOMMENDED": 1,
    }
    assert len(result["score_gaps"]) == 2
    assert sorted(result["score_gaps"]["best_non_null_minus_a00"]) == [-0.5, 1.0]
    assert set(result["margin_summary"]["action_id"]) == {"A11"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_publication_validation_requires_registered_figure_triplets(tmp_path: Path) -> None:
    for directory in (
        "metrics", "tables/core", "tables/optional", "figures/core",
        "figures/audit", "figures/optional", "audits", "logs",
    ):
        (tmp_path / directory).mkdir(parents=True)
    required = [
        "tables/core/table01_m1_distributional_validity.parquet",
        "tables/core/table03_m2_channel_cost_summary.parquet",
        "tables/core/table04_m3_response_library.parquet",
        "tables/core/table05_m4_screening_and_recommendation.parquet",
        "tables/core/figure_metadata.parquet",
        "figures/figure_metadata.json",
        "logs/publication.log",
        *[f"audits/{name}" for name in M4_AUDIT_FILES],
        *[
            f"figures/core/{stem}.{suffix}"
            for stem in CORE_FIGURE_STEMS
            for suffix in ("png", "pdf", "svg")
        ],
    ]
    for relative in required:
        (tmp_path / relative).write_bytes(b"published")
    publication = {
        "run_id": "run-1",
        "config_hash": "config-1",
        "scientific_status": "STOP_AND_REVIEW",
        "publication_implementation_hash": "publication-1",
        "scientific_values_modified": False,
        "source_hashes": {},
        "output_hashes": {},
    }
    publication_path = tmp_path / "publication_manifest.json"
    publication_path.write_text(json.dumps(publication), encoding="utf-8")
    registered = sorted(set(["publication_manifest.json", *required, *CORE_REQUIRED_ARTIFACT_IDS]))
    for relative in CORE_REQUIRED_ARTIFACT_IDS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(b"core")
    write_artifact_registry(
        tmp_path,
        mode="fast",
        run_id="run-1",
        config_hash="config-1",
        implementation_hash="scientific-1",
        contract_version="contract-1",
        upstream_artifact_hashes={},
        scientific_status="STOP_AND_REVIEW",
        artifact_names=registered,
        registry_kind="publication",
        required_artifact_ids=registered,
    )

    result = validate_publication(
        tmp_path,
        expected_run_id="run-1",
        expected_config_hash="config-1",
        expected_scientific_status="STOP_AND_REVIEW",
        expected_publication_implementation_hash="publication-1",
    )
    assert result["status"] == "PASS"
    assert result["core_figure_triplets"] == 5

    corrupted = tmp_path / "figures/core/fig01_execution_risk_validity.png"
    corrupted.write_bytes(b"changed")
    with pytest.raises(ValueError, match="PUBLICATION_ARTIFACT_HASH_MISMATCH"):
        validate_publication(
            tmp_path,
            expected_run_id="run-1",
            expected_config_hash="config-1",
            expected_scientific_status="STOP_AND_REVIEW",
            expected_publication_implementation_hash="publication-1",
        )
