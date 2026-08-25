"""Development-pilot materialization coordinator with explicit M1/M2/M4 gates."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import yaml

from model.common.identity import content_id

from ..artifacts.m3_scenario_bundle import materialize_m3_scenario_bundle
from ..artifacts.m4_policy_binding import materialize_m4_policy
from .data2_development_cohort import materialize_development_pilot_cohort


AUDIT_FILENAME = "EXP2_PRE_M4_REAL_DATA_PILOT_AUDIT.json"
_ARTIFACT_SUFFIXES = {".json", ".yaml", ".yml", ".pt", ".pth", ".ckpt"}
_M1_ARTIFACT_SEARCH_ROOTS = (
    "artifacts/experiment/exp2",
    "artifacts",
    "outputs",
)


def _write_json(path: Path, payload: dict) -> None:
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) == payload:
            return
        raise RuntimeError("EXP2_DEVELOPMENT_MATERIALIZATION_AUDIT_EXISTS_WITH_DIFFERENT_CONTENT")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def inspect_m1_v2_artifact_gate(root: Path) -> dict:
    scientific = yaml.safe_load(
        (root / "configs" / "scientific" / "foundation.yaml").read_text(encoding="utf-8")
    )
    v2_contract = scientific["parameters"]["m1_state_estimator_v2"]
    legacy_v1_paths: list[str] = []
    unverified_v2_candidates: list[str] = []
    for relative_root in _M1_ARTIFACT_SEARCH_ROOTS:
        search_root = root / relative_root
        if not search_root.exists():
            continue
        for path in search_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _ARTIFACT_SUFFIXES:
                continue
            upper_name = path.name.upper()
            if "M1" not in upper_name:
                continue
            relative_path = path.relative_to(root).as_posix()
            if "V1" in upper_name or "SIGNED" in upper_name or "WARNING" in upper_name:
                legacy_v1_paths.append(relative_path)
            elif "V2" in upper_name:
                unverified_v2_candidates.append(relative_path)
    return {
        "status": "BLOCKED_M1_V2_ARTIFACT_NOT_FROZEN",
        "contract": v2_contract["value"],
        "required_primitive_targets": tuple(v2_contract["provenance"]["primitive_targets"]),
        "required_scenario_count": int(v2_contract["provenance"]["scenario_count"]),
        "searched_artifact_roots": _M1_ARTIFACT_SEARCH_ROOTS,
        "legacy_v1_paths_excluded": tuple(sorted(legacy_v1_paths)),
        "unverified_v2_candidates": tuple(sorted(unverified_v2_candidates)),
        "freeze_requirement": "TRAIN_FROZEN_EXECUTABLE_M1_V2_CHECKPOINT_AND_SCENARIO_ARTIFACT",
    }


def materialize_development_pre_m4(root: Path) -> dict:
    artifact_root = root / "artifacts" / "experiment" / "exp2"
    cohort = materialize_development_pilot_cohort(root=root)
    m3_bundle = materialize_m3_scenario_bundle(root=root)
    m4_policy = materialize_m4_policy(root=root)
    m1_gate = inspect_m1_v2_artifact_gate(root)
    payload = {
        "schema_version": "AIR_SLOT_EXP2_PRE_M4_REAL_DATA_PILOT_AUDIT_V1",
        "status": "M1_M2_REAL_ARTIFACT_BLOCKED",
        "execution_tier": "DEVELOPMENT_PILOT_ONLY",
        "cohort": {
            "path": str((artifact_root / "DATA2_DEVELOPMENT_PILOT_COHORT.json").relative_to(root)),
            "cohort_hash": cohort["cohort_hash"],
            "episode_count": len(cohort["episode_ids"]),
            "node_count": len(cohort["node_ids"]),
        },
        "M1": m1_gate,
        "M2": {
            "status": "NOT_RUN_DEPENDS_ON_M1_V2_ARTIFACT",
            "required_component_order": (
                "F_continuity", "F_execution", "F_propagation", "P_time",
                "P_itinerary", "P_service", "R_operating",
            ),
            "zero_fill_forbidden": True,
            "scenario_lineage_parity": "NOT_RUN_DEPENDS_ON_M1_V2_ARTIFACT",
        },
        "EXP2A": {
            "JOINT": "BLOCKED_M1_V2_ARTIFACT_NOT_FROZEN",
            "MARGINAL": "BLOCKED_M1_V2_ARTIFACT_NOT_FROZEN",
            "COLLAPSED": "BLOCKED_M1_V2_ARTIFACT_NOT_FROZEN",
        },
        "EXP2B": {
            "COMPONENT": "BLOCKED_M2_V2_ARTIFACT_NOT_MATERIALIZED",
            "CHANNEL": "BLOCKED_M2_V2_ARTIFACT_NOT_MATERIALIZED",
            "SCALAR": "BLOCKED_M2_V2_ARTIFACT_NOT_MATERIALIZED",
        },
        "M3": {
            "status": "MATERIALIZED_CONDITIONAL_SCENARIO_ASSUMPTION",
            "path": str((artifact_root / "DATA2_DEV_PILOT_M3_SCENARIO_BUNDLE.json").relative_to(root)),
            "bundle_hash": m3_bundle.bundle_hash,
            "action_count": len(m3_bundle.rules),
            "formal_support_upgrade": False,
        },
        "action_set": {
            "status": "BLOCKED_M2_V2_CONSEQUENCE_ARTIFACT_NOT_MATERIALIZED",
            "rule": "A00_PLUS_ALL_PREDECLARED_COMPLETE_LEGALLY_INSTANTIABLE_COMMON_ACTIONS",
            "score_or_disagreement_selection": "FORBIDDEN",
        },
        "M4": {
            "status": "POLICY_FROZEN_EXECUTION_BLOCKED",
            "path": str((artifact_root / "DATA2_DEV_PILOT_M4_RISK_POLICY.json").relative_to(root)),
            "policy_hash": m4_policy["policy"]["policy_hash"],
            "tail_support": "M1_POSITIVE_TAIL_DECISION_REQUIRED",
            "monetary_mapping": "FROZEN_ASSUMPTION_GROUNDED",
        },
        "MANUSCRIPT_EXPERIMENT_INTERPRETATION_NOTE": (
            "The current manuscript's monetary language cannot be claimed by this Exp2 "
            "Development lane until a complete seven-component monetary mapping is frozen; "
            "no internal-loss ranking was executed."
        ),
        "real_development_pilot": False,
        "pilot_metric_support": "NOT_RUN_NO_M1_V2_ARTIFACT",
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }
    payload["artifact_hash"] = content_id(payload)
    _write_json(artifact_root / AUDIT_FILENAME, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    payload = materialize_development_pre_m4(root)
    print(json.dumps({
        "status": payload["status"],
        "cohort_hash": payload["cohort"]["cohort_hash"],
        "m1_status": payload["M1"]["status"],
        "final_test_access_count": payload["FINAL_TEST_ACCESS_COUNT"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
