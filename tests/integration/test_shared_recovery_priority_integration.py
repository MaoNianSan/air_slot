from __future__ import annotations

import json
from pathlib import Path

from exp.shared.recovery_priority import materialize_priority_score_record
from model.M1.contracts import M1V2Scenario
from model.M2.contracts import ScenarioConsequence

ROOT = Path(__file__).resolve().parents[2]
M1_FIXTURE = (
    ROOT
    / "artifacts"
    / "diagnostics"
    / "numerical_best_action_sanity_v1"
    / "M1_DEVELOPMENT_64_NODE_SCENARIOS.json"
)
M2_FIXTURE = (
    ROOT
    / "artifacts"
    / "diagnostics"
    / "model_refactor_v1"
    / "M2_GOLDEN.json"
)
HEAD = "b6ed055d3ce92892b76eca99624d865f9d83444c"


def _without_computed_fields(item: dict) -> dict:
    payload = dict(item)
    payload.pop("consequence_artifact_id", None)
    component_vector = dict(payload["component_vector"])
    rows = []
    for row in component_vector["rows"]:
        clean = dict(row)
        clean.pop("cu_artifact_id", None)
        clean.pop("reference_lineage_hash", None)
        rows.append(clean)
    component_vector["rows"] = rows
    payload["component_vector"] = component_vector
    return payload


def _load_fixed_development_node():
    m1_payload = json.loads(M1_FIXTURE.read_text(encoding="utf-8"))
    m2_payload = json.loads(M2_FIXTURE.read_text(encoding="utf-8"))
    consequences = tuple(
        ScenarioConsequence.model_validate(_without_computed_fields(item))
        for item in m2_payload["scenario_consequences"]
    )
    node_id = m2_payload["decision_node_id"]
    m1_rows = tuple(
        item for item in m1_payload["scenarios"] if item["decision_node_id"] == node_id
    )
    scenarios = tuple(
        M1V2Scenario.model_validate(
            {key: value for key, value in item.items() if key in M1V2Scenario.model_fields}
        )
        for item in m1_rows
    )
    lineage = (
        m1_payload["artifact_id"],
        m1_payload["artifact_hash"],
        m1_payload["checkpoint_hash"],
    )
    return scenarios, consequences, lineage


def test_fixed_development_fixture_materializes_deterministically():
    scenarios, consequences, lineage = _load_fixed_development_node()
    assert len(scenarios) == len(consequences) == 64
    first = materialize_priority_score_record(
        scenarios,
        consequences,
        repository_head=HEAD,
        m1_lineage=lineage,
    )
    second = materialize_priority_score_record(
        tuple(reversed(scenarios)),
        tuple(reversed(consequences)),
        repository_head=HEAD,
        m1_lineage=lineage,
    )
    assert first.artifact_id == second.artifact_id
    assert first.m2_registry_id == "M2_DATA2_FORMAL_CU_V4"
    assert first.m2_scope_hash == consequences[0].consequence_scope.scope_hash
    assert first.delay_score is not None and first.delay_score >= 0
    assert first.score_C is not None and first.score_C >= 0
    assert first.reason_codes == ()
