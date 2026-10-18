"""Independent E3 exact-weighted-marginal pilot.

This path consumes an existing serialized M1 state variant and audits the new
lazy product coupling. It does not call the sealed formal executor or rewrite
historical results. Large Cartesian products remain lazy; materialization is
performed only below an explicit caller-provided limit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from model.M1.marginal_distribution import ExactWeightedMarginalDistribution
from model.common.decision_contracts import (
    StateRepresentationSpec,
    StateScenario,
    StateScenarioSet,
)
from model.common.enums import SupportState


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def state_set_from_payload(payload: dict[str, Any]) -> StateScenarioSet:
    return StateScenarioSet(
        episode_id=payload["episode_id"],
        chain_id=payload["chain_id"],
        node_id=payload["node_id"],
        stage=payload["stage"],
        representation=StateRepresentationSpec.model_validate(payload["representation"]),
        scenarios=tuple(StateScenario.model_validate(item) for item in payload["scenarios"]),
    )


def _mass_table(adapter: ExactWeightedMarginalDistribution, coordinate: str) -> list[dict[str, float]]:
    return [
        {"value": float(atom.value), "mass": float(atom.mass)}
        for atom in adapter.weighted_atoms(coordinate)
    ]


def audit_state_set(
    source: StateScenarioSet, *, max_materialize: int
) -> dict[str, Any]:
    adapter = ExactWeightedMarginalDistribution.from_source(source)
    weighted_marginal_match = True
    source_tables: dict[str, dict[float, float]] = {}
    for coordinate in ("t_ib_minutes", "d_ob_minutes", "d_tx_minutes"):
        masses: dict[float, float] = {}
        for item in source.scenarios:
            value = float(getattr(item, coordinate))
            masses[value] = masses.get(value, 0.0) + float(item.scenario_weight)
        source_tables[coordinate] = masses
        adapter_table = {atom.value: atom.mass for atom in adapter.weighted_atoms(coordinate)}
        if set(source_tables[coordinate]) != set(adapter_table):
            weighted_marginal_match = False
        for value, mass in masses.items():
            if abs(mass - adapter_table.get(value, float("nan"))) > 1e-9:
                weighted_marginal_match = False
    probability_mass_ok = all(
        abs(sum(atom.mass for atom in marginal) - 1.0) <= 1e-9
        for marginal in adapter.atoms
    )
    materialized = adapter.scenario_count <= max_materialize
    d_to_identity_ok = True
    materialized_weight_sum = None
    if materialized:
        scenarios = tuple(adapter.iter_scenarios())
        materialized_weight_sum = sum(item.scenario_weight for item in scenarios)
        d_to_identity_ok = all(
            abs(item.d_to_minutes - item.d_ob_minutes - item.d_tx_minutes) <= 1e-9
            for item in scenarios
        )
    common_support_status = (
        "PASS_COMMON_SUPPORT"
        if adapter.support is not SupportState.ABSTAIN
        else "BLOCKED_COMMON_SUPPORT"
    )
    status = (
        "PASS_EXACT_WEIGHTED_MARGINAL"
        if weighted_marginal_match
        and probability_mass_ok
        and d_to_identity_ok
        and common_support_status == "PASS_COMMON_SUPPORT"
        else "BLOCKED_MARGINAL_PILOT"
    )
    return {
        "episode_id": source.episode_id,
        "chain_id": source.chain_id,
        "node_id": source.node_id,
        "stage": source.stage.value,
        "representation_id": source.representation.representation_id,
        "source_scenario_count": len(source.scenarios),
        "product_scenario_count": adapter.scenario_count,
        "materialized": materialized,
        "max_materialize": max_materialize,
        "support": adapter.support.value,
        "common_support_status": common_support_status,
        "weighted_marginal_match": weighted_marginal_match,
        "probability_mass_ok": probability_mass_ok,
        "materialized_weight_sum": materialized_weight_sum,
        "d_to_identity_ok": d_to_identity_ok,
        "marginal_mass_tables": {
            coordinate: _mass_table(adapter, coordinate)
            for coordinate in ("t_ib_minutes", "d_ob_minutes", "d_tx_minutes")
        },
        "identity_note": adapter.identity_note,
        "status": status,
    }


def run_pilot(
    state_variants_path: Path,
    *,
    variant: str = "HISTORY_JOINT",
    max_materialize: int = 100_000,
) -> dict[str, Any]:
    payload = json.loads(state_variants_path.read_text(encoding="utf-8"))["payload"]
    selected = next(item for item in payload["variants"] if item["variant"] == variant)
    rows = [
        audit_state_set(state_set_from_payload(node["state_set"]), max_materialize=max_materialize)
        for node in selected["nodes"]
    ]
    return {
        "schema_version": "JATM_S34_E3_EXACT_MARGINAL_PILOT_V1",
        "source_git_head": "WORKTREE",
        "source_artifact": str(state_variants_path),
        "source_artifact_hash": _sha256(state_variants_path),
        "variant": variant,
        "max_materialize": max_materialize,
        "scientific_recomputation": False,
        "sealed_executor_called": False,
        "rows": rows,
        "summary": {
            "node_count": len(rows),
            "pass_count": sum(item["status"] == "PASS_EXACT_WEIGHTED_MARGINAL" for item in rows),
            "blocked_count": sum(item["status"] != "PASS_EXACT_WEIGHTED_MARGINAL" for item in rows),
            "lazy_count": sum(not item["materialized"] for item in rows),
            "max_product_scenario_count": max(item["product_scenario_count"] for item in rows),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state-variants", type=Path, required=True)
    parser.add_argument("--variant", default="HISTORY_JOINT")
    parser.add_argument("--max-materialize", type=int, default=100_000)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run_pilot(
        args.state_variants,
        variant=args.variant,
        max_materialize=args.max_materialize,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
