from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


TRANSITION_FILENAME = "scientific_transition_4ff_to_df2.json"
RUNTIME_FIELDS = {
    "requested_n_jobs",
    "resolved_n_jobs",
    "outer_workers",
    "inner_model_threads",
    "parallel_backend",
    "task_partition_version",
    "task_seed_strategy",
    "task_seed_hash",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_transition_contract(module_root: Path) -> dict[str, Any]:
    path = module_root / "config" / TRANSITION_FILENAME
    return json.loads(path.read_text(encoding="utf-8"))


def transition_id(module_root: Path) -> str:
    return str(load_transition_contract(module_root)["transition_id"])


def _without_runtime_fields(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if key not in RUNTIME_FIELDS}


def validate_scientific_transition(
    historical: dict[str, Any],
    current: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    historical_clean = _without_runtime_fields(deepcopy(historical))
    current_clean = _without_runtime_fields(deepcopy(current))

    allowed = contract["allowed_changes"]
    for path in ("m2.graph_edges.F_to_P", "m2.graph_edges.F_to_R"):
        _, _, edge = path.split(".")
        expected = allowed[path]
        actual_from = float(historical_clean["m2"]["graph_edges"][edge])
        actual_to = float(current_clean["m2"]["graph_edges"][edge])
        if actual_from != float(expected["from"]) or actual_to != float(expected["to"]):
            raise ValueError(f"UNDECLARED_SCIENTIFIC_DELTA:{path}")
        historical_clean["m2"]["graph_edges"][edge] = actual_to

    historical_actions = historical_clean["m3"]["actions"]
    current_actions = current_clean["m3"]["actions"]
    historical_ids = [str(item["id"]) for item in historical_actions]
    current_ids = [str(item["id"]) for item in current_actions]
    appended = [str(value) for value in allowed["m3.actions.append"]]
    if current_ids != historical_ids + appended:
        raise ValueError("UNDECLARED_SCIENTIFIC_DELTA:m3.actions")
    historical_clean["m3"]["actions"] = deepcopy(current_actions)

    historical_response = historical_clean["m3"]["response_parameters"]
    current_response = current_clean["m3"]["response_parameters"]
    additions = [str(value) for value in allowed["m3.response_parameters.add"]]
    if set(current_response) != set(historical_response) | set(additions):
        raise ValueError("UNDECLARED_SCIENTIFIC_DELTA:m3.response_parameters")
    for action_id in additions:
        if action_id in historical_response or action_id not in current_response:
            raise ValueError(
                f"UNDECLARED_SCIENTIFIC_DELTA:m3.response_parameters.{action_id}"
            )
        historical_response[action_id] = deepcopy(current_response[action_id])

    if historical_clean != current_clean:
        raise ValueError("UNDECLARED_SCIENTIFIC_DELTA:CONFIG_PAYLOAD")
    return {
        "status": "PASS",
        "transition_id": contract["transition_id"],
        "historical_config_hash": contract["historical_config_hash"],
        "current_config_hash": contract["current_config_hash"],
        "approved_delta_count": 6,
    }


def validate_fixture_hashes(
    baseline_root: Path,
    contract: dict[str, Any],
) -> dict[str, Any]:
    expected = dict(contract["historical_fixture_hashes"])
    missing = [relative for relative in expected if not (baseline_root / relative).is_file()]
    if missing:
        raise FileNotFoundError("BASELINE_FIXTURE_SET_MISSING:" + ",".join(sorted(missing)))
    mismatches = [
        relative
        for relative, digest in expected.items()
        if sha256_file(baseline_root / relative) != digest
    ]
    if mismatches:
        raise ValueError("BASELINE_FIXTURE_HASH_MISMATCH:" + ",".join(sorted(mismatches)))
    return {"status": "PASS", "fixture_count": len(expected)}
