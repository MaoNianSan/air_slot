"""Synthetic exact-23 action-state audit and M4 A00 fallback guard."""

from pathlib import Path

from model.M3.contracts import InstantiationState
from model.M3.instantiate import instantiate_action_records
from model.M3.registry import ActionRegistry
from model.M3.response_registry import ResponseScenarioRegistry


ROOT = Path(__file__).resolve().parents[2]


def test_exact_23_action_state_matrix_has_independent_rows():
    registry = ActionRegistry.load(ROOT / "registries" / "action_templates.yaml")
    response_registry = ResponseScenarioRegistry.load(
        ROOT / "registries" / "m3_response_scenarios.yaml",
        structural_registry=registry,
    )
    records = instantiate_action_records(
        {
            "episode_id": "episode-matrix",
            "decision_node_id": "node-matrix",
            "facts": {
                "successor_schedule": True,
                "cancellation_authority": True,
                "network_authority": True,
            },
        },
        registry,
        response_registry=response_registry,
    )
    matrix = []
    for record in records:
        candidate = record.candidate
        matrix.append({
            "action_id": record.template_id,
            "chi_inst": record.instantiation_state.value,
            "chi_fact": candidate.precondition_state if candidate else "UNKNOWN",
            "chi_num": "UNDEFINED",
            "chi_resp": (
                candidate.response_support.support_state.value
                if candidate and candidate.response_support is not None
                else (candidate.response_provenance.value if candidate else "UNSUPPORTED")
            ),
            "chi_opp": "NOT_REQUIRED" if record.template_id == "A00" else "UNKNOWN",
            "reason": record.reason if candidate is None else candidate.precondition_reason,
        })
    expected = tuple(template.template_id for template in registry.templates)
    assert len(matrix) == 23
    assert tuple(row["action_id"] for row in matrix) == expected
    assert len({row["action_id"] for row in matrix}) == 23
    assert all(row["chi_inst"] == InstantiationState.FORMED.value for row in matrix)
    by_id = {row["action_id"]: row for row in matrix}
    assert by_id["A00"]["chi_fact"] == "TRUE"
    assert by_id["A00"]["chi_opp"] == "NOT_REQUIRED"
    assert by_id["A21"]["chi_fact"] == "UNKNOWN"
    assert by_id["A71"]["chi_fact"] == "UNKNOWN"
    assert by_id["A72"]["chi_fact"] == "UNKNOWN"
    assert by_id["A21"]["reason"] == "CONTRACT_UNDERSPECIFIED"
    assert by_id["A71"]["reason"] == "CONTRACT_UNDERSPECIFIED"
    assert by_id["A72"]["reason"] == "CONTRACT_UNDERSPECIFIED"
    for action_id in ("A71", "A72"):
        candidate = next(item.candidate for item in records if item.template_id == action_id)
        assert candidate is not None
        assert "capability_label_not_contemporaneous_authority" in candidate.factual_provenance
    assert len({row["chi_fact"] for row in matrix}) > 1


def test_m4_has_no_a00_fallback_selector_special_case():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "model" / "M4").glob("*.py")
    )
    forbidden = (
        "if no_supported_non_a00",
        "recommended_action = \"A00\"",
        "recommended_action_id",
        "best_action = min(actions)",
        "return best_action",
        "return A00\n",
        "return \"A00\"",
    )
    assert all(pattern not in source for pattern in forbidden)
