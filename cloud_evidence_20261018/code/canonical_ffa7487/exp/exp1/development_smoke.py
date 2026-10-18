"""Fail-closed Development-only Exp1 plumbing smoke preflight.

The formal H16 cache contains encoded model inputs, but not the PREState
objects required by the formal M1 scenario producer. This runner validates the
frozen artifact gate and records a typed BLOCKED result instead of rebuilding
PREState from raw Data2 or synthesizing it from cached tensors.
"""

from __future__ import annotations

import json
from datetime import date
from hashlib import sha256
from pathlib import Path

import torch

from model.M1.cache import M1DevelopmentBaseCache
from model.common.paths import PROJECT_ROOT


MODEL_ROOT = PROJECT_ROOT / "artifacts" / "models" / "m1"
COHORT_PATH = MODEL_ROOT / "M1_FORMAL_TRAINING_COHORT_V1.json"
HISTORY_ROOT = MODEL_ROOT / "M1_H16_HISTORY_PRIMARY"
CURRENT_ROOT = MODEL_ROOT / "M1_H16_CURRENT_COMPARATOR"
HISTORY_MANIFEST_PATH = HISTORY_ROOT / "M1_H16_HISTORY_PRIMARY_MANIFEST.json"
CURRENT_MANIFEST_PATH = CURRENT_ROOT / "M1_H16_CURRENT_COMPARATOR_MANIFEST.json"
MATCHED_AUDIT_PATH = MODEL_ROOT / "M1_H16_HISTORY_CURRENT_MATCHED_AUDIT.json"
SOURCE_ROOT = MODEL_ROOT / "M1_FROZEN_H16"
CACHE_PATH = SOURCE_ROOT / "DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3.npz"
CACHE_MANIFEST_PATH = SOURCE_ROOT / "DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3_MANIFEST.json"
PREPARATION_STATE_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "v5_development_freeze"
    / "M1_BASE_CACHE_PREPARATION_STATE.pt"
)
PRE_GOLDEN_PATH = (
    PROJECT_ROOT / "artifacts" / "diagnostics" / "model_refactor_v1" / "PRE_GOLDEN.json"
)
OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "diagnostics" / "exp1_development_smoke"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def require_development_date(value: date) -> None:
    if value >= date(2019, 10, 1):
        raise ValueError("EXP1_DEVELOPMENT_SMOKE_FINAL_TEST_DATE_REJECTED")


def validate_gate_a() -> dict:
    required = (
        COHORT_PATH,
        HISTORY_MANIFEST_PATH,
        CURRENT_MANIFEST_PATH,
        MATCHED_AUDIT_PATH,
        HISTORY_ROOT / "M1_H16_HISTORY_PRIMARY.pt",
        CURRENT_ROOT / "M1_H16_CURRENT_COMPARATOR.pt",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"EXP1_SMOKE_FORMAL_ARTIFACT_MISSING:{missing}")

    cohort = _read_json(COHORT_PATH)
    history = _read_json(HISTORY_MANIFEST_PATH)
    current = _read_json(CURRENT_MANIFEST_PATH)
    matched = _read_json(MATCHED_AUDIT_PATH)
    same_fields = (
        "training_cohort_hash",
        "calibration_cohort_hash",
        "target_contract_hash",
        "support_contract_hash",
        "feature_contract_hash",
        "scenario_count",
    )
    checks = {
        "formal_cohort_development_count": cohort["development_episode_count"] == 128,
        "formal_cohort_final_test_episode_count": cohort["final_test_episode_count"] == 0,
        "formal_cohort_final_test_access_count": cohort["final_test_access_count"] == 0,
        "matched_status": matched["status"] == "PASS",
        "matched_final_test_access_count": matched["final_test_access_count"] == 0,
        "matched_final_test_access_check": matched["final_test_access_check"] is True,
        "history_hidden_size": history["hidden_size"] == 16,
        "current_hidden_size": current["hidden_size"] == 16,
        "history_seed": history["training_seed"] == 20260813,
        "current_seed": current["training_seed"] == 20260813,
        "history_mode": history["history_mode"] == "FULL_ADAPTIVE_CAUSAL_PREFIX",
        "current_mode": current["history_mode"] == "NO_HISTORY_CURRENT_OBSERVATION",
        "matched_fields": all(history[key] == current[key] for key in same_fields),
        "history_final_test_access_count": history["final_test_access_count"] == 0,
        "current_final_test_access_count": current["final_test_access_count"] == 0,
    }
    if not all(checks.values()):
        raise RuntimeError(f"EXP1_DEVELOPMENT_SMOKE_GATE_A_FAILED:{checks}")
    return {
        "status": "PASS",
        "checks": checks,
        "development_cohort_hash": cohort["development_episode_hash"],
        "matched_contract_status": matched["status"],
    }


def audit_frozen_prestate_availability() -> dict:
    cohort = _read_json(COHORT_PATH)
    cache_manifest = _read_json(CACHE_MANIFEST_PATH)
    cache = M1DevelopmentBaseCache.load(
        CACHE_PATH,
        CACHE_MANIFEST_PATH,
        expected_cache_key=cache_manifest["cache_key"],
    )
    cache_keys = {
        (row.episode_id, row.decision_node_id)
        for row in cache.partition("development", representation="ADAPTIVE_HISTORY")
    }

    preparation = torch.load(
        PREPARATION_STATE_PATH, map_location="cpu", weights_only=False
    )
    reservoirs = preparation.get("reservoirs", {})
    reservoir_ids = {
        split: tuple(sorted(item.episode_id for item in reservoirs.get(split, ())))
        for split in ("train", "calibration", "development")
    }
    exact_reservoir_match = all(
        reservoir_ids[split] == tuple(sorted(cohort[f"{split}_episode_ids"]))
        for split in reservoir_ids
    )

    golden = _read_json(PRE_GOLDEN_PATH)
    golden_keys = {
        (
            state["decision_node"]["episode_id"],
            state["decision_node"]["decision_node_id"],
        )
        for state in golden.get("pre_states", ())
    }
    matched_golden_keys = tuple(sorted(golden_keys & cache_keys))
    return {
        "formal_reservoir_ids_exact": exact_reservoir_match,
        "preparation_test_reservoir_count": len(reservoirs.get("test", ())),
        "cache_development_node_count": len(cache_keys),
        "cache_contains_encoded_inputs": True,
        "cache_contains_pre_state": False,
        "pre_golden_state_count": len(golden_keys),
        "pre_golden_formal_development_match_count": len(matched_golden_keys),
        "pre_golden_formal_development_matches": list(matched_golden_keys),
        "formal_pre_state_available": bool(matched_golden_keys),
        "blocker": "FORMAL_DEVELOPMENT_PRESTATE_ARTIFACT_UNAVAILABLE",
    }


def run(output_root: Path = OUTPUT_ROOT) -> dict:
    gate_a = validate_gate_a()
    prestate = audit_frozen_prestate_availability()
    if prestate["formal_pre_state_available"]:
        raise RuntimeError("EXP1_SMOKE_PRESTATE_SOURCE_REQUIRES_EXPLICIT_IMPLEMENTATION")

    gates = {
        "A_artifacts": "PASS",
        "B_m1_history_current": "BLOCKED",
        "C_joint": "NOT_RUN",
        "D_point": "NOT_RUN",
        "E_marginal": "NOT_RUN",
        "F_m1_to_m2": "NOT_RUN",
        "G_invariants": "NOT_RUN",
        "H_support_lineage": "NOT_RUN",
    }
    audit = {
        "schema_version": "EXP1_DEVELOPMENT_PLUMBING_SMOKE_V1",
        "scope": "DEVELOPMENT_ONLY_DIAGNOSTIC",
        "paper_result": False,
        "formal_exp1_execution": False,
        "final_test_access_count": 0,
        "status": "BLOCKED",
        "blocker": prestate["blocker"],
        "gate_a": gate_a,
        "prestate_availability": prestate,
        "gates": gates,
        "smoke_hc_node_count": 0,
        "smoke_3d_node_count": 0,
    }
    manifest = {
        "schema_version": "EXP1_DEVELOPMENT_SMOKE_MANIFEST_V1",
        "scope": audit["scope"],
        "paper_result": False,
        "formal_exp1_execution": False,
        "final_test_access_count": 0,
        "status": "BLOCKED",
        "inputs": {
            "formal_cohort": {"path": str(COHORT_PATH), "sha256": _sha256(COHORT_PATH)},
            "history_manifest": {"path": str(HISTORY_MANIFEST_PATH), "sha256": _sha256(HISTORY_MANIFEST_PATH)},
            "current_manifest": {"path": str(CURRENT_MANIFEST_PATH), "sha256": _sha256(CURRENT_MANIFEST_PATH)},
            "matched_audit": {"path": str(MATCHED_AUDIT_PATH), "sha256": _sha256(MATCHED_AUDIT_PATH)},
            "frozen_cache": {"path": str(CACHE_PATH), "sha256": _sha256(CACHE_PATH)},
            "preparation_state": {"path": str(PREPARATION_STATE_PATH), "sha256": _sha256(PREPARATION_STATE_PATH)},
            "pre_golden": {"path": str(PRE_GOLDEN_PATH), "sha256": _sha256(PRE_GOLDEN_PATH)},
        },
        "outputs": {
            "audit": "EXP1_DEVELOPMENT_SMOKE_AUDIT.json",
            "nodes": "EXP1_DEVELOPMENT_SMOKE_NODES.json",
        },
    }
    nodes = {
        "schema_version": "EXP1_DEVELOPMENT_SMOKE_NODES_V1",
        "scope": audit["scope"],
        "status": "BLOCKED",
        "nodes": [],
        "final_test_access_count": 0,
    }
    _write_json(output_root / "EXP1_DEVELOPMENT_SMOKE_MANIFEST.json", manifest)
    _write_json(output_root / "EXP1_DEVELOPMENT_SMOKE_AUDIT.json", audit)
    _write_json(output_root / "EXP1_DEVELOPMENT_SMOKE_NODES.json", nodes)
    return audit


def main() -> int:
    print(json.dumps(run(), indent=2, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
