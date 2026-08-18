"""Focused tests for the Exp3.7 LLM audit V2 (state-conditioned explanation).

DECISION_ID = AIR_SLOT_LLM_AUDIT_V2_STATE_CONDITIONED_EXPLANATION.
Scope: V2 case serialization, frozen hashes, schema validation,
experiment-side error detectors, pilot gates, diagnostic table and
principal allocation. No API calls are made.
"""
import json

import pytest

from exp.exp234.llm_audit_v2 import (
    CASE_STRATA_ORDER,
    V2_VERDICTS,
    contract_hash,
    detect_prerequisite_handling_errors,
    detect_unsupported_fact_assertions,
    evaluate_v2_pilot_gates,
    pilot_diagnostic_table,
    prompt_hash,
    schema_hash,
    select_principal_cases,
    serialize_case_v2,
    v2_request_payload,
    validate_audit_response_v2,
)

POST_HOC_FIELD_MARKERS = (
    "realized",
    "outcome",
    "final_test",
    "post_hoc",
    "success_label",
    "actual_",
)


def _sample_case_v1(**overrides):
    case = {
        "case_id": "dev-0000",
        "episode_id": "ep-1",
        "decision_node_id": "node-1",
        "stratum": "scenario_conditional_close_call",
        "decision_time": "2019-08-29T18:43:00+00:00",
        "operational_stage": "POST_IB_PRE_OB",
        "admissible_operational_state": {
            "observed_r_ib_minutes": 0.0,
            "observed_delta_ob_minutes": None,
            "observed_t_tx_minutes": None,
            "schedule_support_state": "SUPPORTED",
            "taxi_reference_support_state": "SUPPORTED",
            "connection_airport_id": "DSM",
            "successor_destination_airport_id": "PHX",
        },
        "major_uncertainty": {"scenario_count": 250, "m1_scenario_spread_cu": 2.0},
        "m2_consequence_profile": {
            "formal_cu_mean": 6.6, "top1_action": "A23", "top1_cu": 6.2,
            "top3_actions": ["A23", "A22", "A00"],
        },
        "recommended_action": "A23",
        "action_family": "capacity_coordination",
        "preconditions": "UNKNOWN",
        "preparation_time_minutes": 10,
        "authority_requirements": ["ATFM"],
        "m3_response_provenance": "PURE_SCENARIO",
        "m3_scenario_parameters": {"registry": "M3_RESPONSE_SCENARIO_V1", "sensitivity": "BASE"},
        "m4_lane": "NOT_RUN",
        "m4_blocker": "M4_MATERIAL_COVERAGE_UNFROZEN",
        "m4_score_rank": None,
        "closest_alternatives": ["A22", "A00", "A61"],
        "exp3_row": {"formal_action_count": 23, "numerically_evaluable": True,
                     "relaxed_top1": "A53"},
        "exp4_sensitivity_base_top1": "A23",
    }
    case.update(overrides)
    return case


def _valid_response(**overrides):
    response = {
        "plausible_operational_outcomes": ["delay propagation contained"],
        "primary_mitigation": ["recover downstream connection"],
        "execution_burdens": ["coordination with ATFM"],
        "resource_dependencies": ["ATFM slot"],
        "downstream_effects": ["successor flight protected"],
        "timing_feasibility": {"assessment": "CONDITIONAL", "reason": "depends on ATFM slot"},
        "missing_critical_information": ["ATFM slot availability"],
        "state_grounded_explanation": "Action is plausible if the ATFM slot is available.",
        "final_judgement": "ACCEPT_WITH_RESERVATIONS",
        "confidence": "MEDIUM",
    }
    response.update(overrides)
    return response


class TestSerializer:
    def test_whitelisted_keys_and_metadata_isolated(self):
        v2 = serialize_case_v2(_sample_case_v1())
        allowed = {
            "case_id", "episode_id", "decision_node_id", "stratum", "decision_time",
            "operational_stage", "admissible_operational_state", "major_uncertainty",
            "m2_consequence_profile", "recommended_action", "action_family",
            "preconditions", "preparation_time_minutes", "authority_requirements",
            "model_metadata", "unknown_facts",
        }
        assert set(v2) == allowed
        assert set(v2["model_metadata"]) == {
            "m3_response_provenance", "m3_scenario_parameters", "m4_lane", "m4_blocker",
            "m4_score_rank", "exp3_row", "exp4_sensitivity_base_top1", "closest_alternatives",
        }

    def test_no_post_hoc_markers_in_serialized_json(self):
        text = json.dumps(serialize_case_v2(_sample_case_v1()))
        lowered = text.lower()
        for marker in POST_HOC_FIELD_MARKERS:
            assert marker not in lowered

    def test_unknowns_preserved(self):
        v2 = serialize_case_v2(_sample_case_v1())
        state = v2["admissible_operational_state"]
        assert state["observed_delta_ob_minutes"] == "UNKNOWN"
        assert state["observed_t_tx_minutes"] == "UNKNOWN"
        assert state["observed_r_ib_minutes"] == 0.0
        unknown_fields = {e["field"] for e in v2["unknown_facts"]}
        assert unknown_fields == {"observed_delta_ob_minutes", "observed_t_tx_minutes",
                                  "preconditions"}
        critical = {e["field"] for e in v2["unknown_facts"] if e["critical"]}
        assert critical == {"preconditions"}

    def test_metadata_enrichment_backfill(self):
        v2 = serialize_case_v2(_sample_case_v1(
            action_family=None, preparation_time_minutes=None, authority_requirements=[],
            recommended_action="A51"))
        assert v2["action_family"] == "aircraft_recovery"
        assert v2["preparation_time_minutes"] == 30
        assert v2["authority_requirements"] == ["AIRCRAFT"]

    def test_a00_family_label_preserved(self):
        v2 = serialize_case_v2(_sample_case_v1(recommended_action="A00", action_family="null",
                                               preconditions="TRUE"))
        assert v2["action_family"] == "null"
        assert v2["preconditions"] == "TRUE"

    def test_deterministic(self):
        assert serialize_case_v2(_sample_case_v1()) == serialize_case_v2(_sample_case_v1())
class TestHashes:
    def test_hashes_stable_and_distinct(self):
        assert prompt_hash() == prompt_hash()
        assert schema_hash() == schema_hash()
        assert contract_hash() == contract_hash()
        assert len({prompt_hash(), schema_hash(), contract_hash()}) == 3
        for digest in (prompt_hash(), schema_hash(), contract_hash()):
            assert digest.startswith("sha256:") and len(digest) == 71


class TestSchemaValidation:
    def test_valid_response_passes(self):
        assert validate_audit_response_v2(_valid_response())["final_judgement"]

    @pytest.mark.parametrize("bad", [
        {"final_judgement": "MAYBE"},
        {"confidence": "VERY_HIGH"},
        {"timing_feasibility": {"assessment": "POSSIBLE", "reason": "x"}},
        {"state_grounded_explanation": ""},
        {"missing_critical_information": "not-a-list"},
        {"timing_feasibility": {"assessment": "FEASIBLE", "reason": ""}},
    ])
    def test_invalid_response_fails(self, bad):
        with pytest.raises(ValueError):
            validate_audit_response_v2(_valid_response(**bad))

    def test_missing_field_fails(self):
        response = _valid_response()
        del response["execution_burdens"]
        with pytest.raises(ValueError):
            validate_audit_response_v2(response)


class TestDetectors:
    def test_unsupported_assertion_flagged(self):
        case = serialize_case_v2(_sample_case_v1())
        response = _valid_response(
            state_grounded_explanation="The observed delay is confirmed at 40 minutes.",
            final_judgement="ACCEPT",
        )
        evidence = detect_unsupported_fact_assertions(response, case)
        assert evidence, "UNKNOWN fact asserted available must be flagged"

    def test_hedged_uncertainty_not_flagged(self):
        case = serialize_case_v2(_sample_case_v1())
        response = _valid_response(
            state_grounded_explanation=(
                "Gate availability is unresolved and therefore remains a feasibility risk."
            ),
            final_judgement="ACCEPT_WITH_RESERVATIONS",
        )
        assert detect_unsupported_fact_assertions(response, case) == []

    def test_conditional_statement_not_flagged(self):
        case = serialize_case_v2(_sample_case_v1())
        response = _valid_response(
            state_grounded_explanation="Action is plausible if the required slot is available.",
        )
        assert detect_unsupported_fact_assertions(response, case) == []

    def test_known_false_prerequisite_ignored(self):
        case = serialize_case_v2(_sample_case_v1(preconditions="FALSE"))
        response = _valid_response(final_judgement="ACCEPT")
        evidence = detect_prerequisite_handling_errors(response, case)
        assert any(e.startswith("known_false_prerequisite_ignored") for e in evidence)

    def test_unknown_prerequisite_asserted_true(self):
        case = serialize_case_v2(_sample_case_v1(preconditions="UNKNOWN"))
        response = _valid_response(
            state_grounded_explanation="All prerequisites are met.",
            final_judgement="ACCEPT",
        )
        evidence = detect_prerequisite_handling_errors(response, case)
        assert any(e.startswith("unknown_prerequisite_asserted_true") for e in evidence)

    def test_unconditional_accept_without_uncertainty_mention(self):
        case = serialize_case_v2(_sample_case_v1(preconditions="UNKNOWN"))
        response = _valid_response(
            state_grounded_explanation="The action is clearly the right choice.",
            final_judgement="ACCEPT",
            timing_feasibility={"assessment": "FEASIBLE",
                                "reason": "The action is straightforward."},
        )
        evidence = detect_prerequisite_handling_errors(response, case)
        assert any(e.startswith("unknown_prerequisite_asserted_true") for e in evidence)

    def test_reserved_accept_with_uncertainty_mention_ok(self):
        case = serialize_case_v2(_sample_case_v1(preconditions="UNKNOWN"))
        response = _valid_response(
            state_grounded_explanation=(
                "Plausible if preconditions can be satisfied; current information does not "
                "confirm them."
            ),
            final_judgement="ACCEPT_WITH_RESERVATIONS",
        )
        assert detect_prerequisite_handling_errors(response, case) == []
class TestPilotGates:
    def _row(self, schema_valid=True, parse=False, unsupported=False, known_false=False,
             unknown_true=False):
        return {
            "schema_valid": schema_valid,
            "unrecoverable_parse_failure": parse,
            "unsupported_fact_assertions": ["x"] if unsupported else [],
            "known_false_prerequisite_ignored": ["x"] if known_false else [],
            "unknown_prerequisite_asserted_true": ["x"] if unknown_true else [],
        }

    def test_all_clean_passes(self):
        gates = evaluate_v2_pilot_gates([self._row() for _ in range(50)])
        assert gates["gates_passed"] is True
        assert gates["schema_pass_rate"] == 1.0

    def test_one_hallucination_fails(self):
        rows = [self._row() for _ in range(50)]
        rows[0] = self._row(unsupported=True)
        assert evaluate_v2_pilot_gates(rows)["gates_passed"] is False

    def test_one_unknown_prereq_true_fails(self):
        rows = [self._row() for _ in range(50)]
        rows[0] = self._row(unknown_true=True)
        assert evaluate_v2_pilot_gates(rows)["gates_passed"] is False

    def test_two_known_false_prereq_ok_three_fail(self):
        rows = [self._row() for _ in range(50)]
        rows[0] = self._row(known_false=True)
        rows[1] = self._row(known_false=True)
        assert evaluate_v2_pilot_gates(rows)["gates_passed"] is True
        rows[2] = self._row(known_false=True)
        assert evaluate_v2_pilot_gates(rows)["gates_passed"] is False

    def test_parse_failure_limits(self):
        rows = [self._row() for _ in range(50)]
        rows[0] = self._row(parse=True)
        assert evaluate_v2_pilot_gates(rows)["gates_passed"] is True
        rows[1] = self._row(parse=True)
        rows[2] = self._row(parse=True)
        assert evaluate_v2_pilot_gates(rows)["gates_passed"] is False

    def test_missing_information_is_not_failure(self):
        rows = [self._row() for _ in range(50)]
        for row in rows:
            row["response"] = {"missing_critical_information": ["many missing facts"]}
        assert evaluate_v2_pilot_gates(rows)["gates_passed"] is True


class TestDiagnosticTable:
    def test_columns(self):
        row = {
            "case_id": "dev-0000", "recommended_action": "A23",
            "known_blocking_fact": "NONE", "unknown_critical_fact_count": 1,
            "response": {"final_judgement": "ACCEPT_WITH_RESERVATIONS",
                         "missing_critical_information": ["a", "b"]},
            "unsupported_fact_assertions": [], "known_false_prerequisite_ignored": [],
            "unknown_prerequisite_asserted_true": [], "schema_valid": True,
        }
        table = pilot_diagnostic_table([row])
        assert table[0]["case_id"] == "dev-0000"
        assert table[0]["missing_information_count"] == 2
        assert table[0]["schema_pass"] is True
        assert set(table[0]) == {
            "case_id", "recommended_action", "known_blocking_fact",
            "unknown_critical_fact_count", "final_judgement",
            "missing_information_count", "unsupported_fact_assertion",
            "prerequisite_handling_error", "schema_pass",
        }


class TestPrincipalSelection:
    def _case(self, i, stratum, episode):
        return {"case_id": f"dev-{i:04d}", "episode_id": f"ep-{episode}",
                "stratum": stratum, "recommended_action": "A23"}

    def test_allocation_and_redistribution(self):
        cases = []
        n = 0
        for episode in range(1073):
            cases.append(self._case(n, "scenario_conditional_close_call", f"s{episode}"))
            n += 1
        for episode in range(750):
            cases.append(self._case(n, "formal_a00_top1", f"a{episode}"))
            n += 1
        cases.append(self._case(n, "formal_non_null_top1", "f0"))
        selected, report = select_principal_cases(cases, target_episodes=400, global_seed=0)
        assert report["ACTUAL_EPISODES"] == 400
        assert len({c["episode_id"] for c in selected}) == 400
        alloc = report["ALLOCATION"]
        assert alloc["formal_non_null_top1"]["ACTUAL_N"] == 1
        assert alloc["formal_non_null_top1"]["REDISTRIBUTED_N"] == 99
        assert alloc["relaxed_only_invalidated_top1"]["ACTUAL_N"] == 0
        assert alloc["relaxed_only_invalidated_top1"]["REDISTRIBUTED_N"] == 100
        assert alloc["formal_a00_top1"]["ACTUAL_N"] == 200
        assert alloc["scenario_conditional_close_call"]["ACTUAL_N"] == 199
        for stratum in CASE_STRATA_ORDER:
            assert alloc[stratum]["TARGET_N"] == 100

    def test_deterministic(self):
        cases = [self._case(i, "formal_a00_top1", i % 200) for i in range(400)]
        first, _ = select_principal_cases(cases, target_episodes=400, global_seed=0)
        second, _ = select_principal_cases(cases, target_episodes=400, global_seed=0)
        assert [c["case_id"] for c in first] == [c["case_id"] for c in second]


class TestPayload:
    def test_judgement_index_and_model_in_hash(self):
        case = serialize_case_v2(_sample_case_v1())
        p0 = v2_request_payload(case, model="deepseek-v4-flash", judgement_index=0)
        p1 = v2_request_payload(case, model="deepseek-v4-flash", judgement_index=1)
        p2 = v2_request_payload(case, model="deepseek-v4-pro", judgement_index=0)
        from exp.exp3.llm_audit import request_hash
        digests = {request_hash(p) for p in (p0, p1, p2)}
        assert len(digests) == 3
        assert p0["judgement_index"] == 0 and p1["judgement_index"] == 1

