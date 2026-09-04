"""Validate current runtime behavior against the frozen V1R1 goldens."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from model.M1 import M1V2Scenario
from model.PRE import PREState
from model.common.identity import content_id
from model.common.paths import PROJECT_ROOT
from validation.materialize_m1_positive_tail_e2e_smoke import _m1
from validation.materialize_model_refactor_goldens_v1 import (
    DEFAULT_OUTPUT,
    SANITY_RECORDS,
    SANITY_SUMMARY,
    SCENARIO_PATH,
    _action_chain,
)


STANDARD_KEYS = {
    "schema_version",
    "scientific_parent_fingerprint",
    "artifact_scope",
    "guards",
    "artifact_hash",
}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_hash(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _body(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in STANDARD_KEYS}


def _artifact_hash_valid(payload: dict[str, Any]) -> bool:
    return payload["artifact_hash"] == content_id(
        {key: value for key, value in payload.items() if key != "artifact_hash"}
    )


def validate(golden_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    goldens = {
        name: _read(golden_dir / name)
        for name in (
            "PRE_GOLDEN.json",
            "M1_GOLDEN.json",
            "M2_GOLDEN.json",
            "M3_GOLDEN.json",
            "M4_GOLDEN.json",
            "NON_A00_GOLDEN.json",
        )
    }
    integrity = {
        name: _artifact_hash_valid(payload) for name, payload in goldens.items()
    }
    if not all(integrity.values()):
        raise RuntimeError(f"MODEL_REFACTOR_GOLDEN_INTEGRITY_FAILED:{integrity}")

    pre = goldens["PRE_GOLDEN.json"]
    pre_roundtrip = [
        PREState.model_validate(row).model_dump(mode="json") for row in pre["pre_states"]
    ]
    pre_pass = pre_roundtrip == pre["pre_states"]

    m1 = goldens["M1_GOLDEN.json"]
    m1_contract_rows = [
        _m1(row).model_dump(mode="json", exclude_computed_fields=True)
        for row in m1["scenarios"]
    ]
    m1_pass = len(m1_contract_rows) == 64 and all(
        M1V2Scenario.model_validate(row).model_dump(
            mode="json", exclude_computed_fields=True
        )
        == row
        for row in m1_contract_rows
    )
    source_payload = _read(SCENARIO_PATH)
    source_pass = (
        _file_hash(SCENARIO_PATH) == m1["source_artifact_hash"]
        and source_payload["artifact_hash"] == m1["source_declared_artifact_hash"]
    )

    fixed_node = m1["decision_node_id"]
    live_m2, live_m3, live_m4 = _action_chain(source_payload, fixed_node)
    layer_parity = {
        "PRE": pre_pass,
        "M1": m1_pass and source_pass,
        "M2": live_m2 == _body(goldens["M2_GOLDEN.json"]),
        "M3": live_m3 == _body(goldens["M3_GOLDEN.json"]),
        "M4": live_m4 == _body(goldens["M4_GOLDEN.json"]),
    }

    non_a00 = goldens["NON_A00_GOLDEN.json"]
    current_summary = _read(SANITY_SUMMARY)
    distribution = current_summary["best_action_distribution"]
    non_a00_pass = (
        _file_hash(SANITY_RECORDS) == non_a00["records_source_hash"]
        and _file_hash(SANITY_SUMMARY) == non_a00["summary_source_hash"]
        and distribution["A00_best_count"] == 26
        and distribution["non_A00_best_count"] == 38
        and distribution["winner_distribution"]
        == {"A00": 26, "A22": 4, "A23": 15, "A32": 4, "A61": 15}
        and non_a00["non_A00_chi_num_defined"] == 640
        and non_a00["non_A00_M4_evaluated"] == 640
    )
    layer_parity["NON_A00"] = non_a00_pass
    if not all(layer_parity.values()):
        raise RuntimeError(f"MODEL_REFACTOR_GOLDEN_PARITY_FAILED:{layer_parity}")
    return {
        "schema_version": "MODEL_REFACTOR_GOLDEN_PARITY_V1",
        "golden_integrity": integrity,
        "layer_parity": layer_parity,
        "fixed_node_id": fixed_node,
        "A00_best": 26,
        "non_A00_best": 38,
        "non_A00_chi_num_defined": 640,
        "non_A00_M4_evaluated": 640,
        "final_test_access_count": 0,
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(validate(args.golden_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
