"""Regression tests for paired marginal increments and Section 5.4 robustness."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from formal.v2_phase7 import constants as C
from formal.v2_phase7.executor import stages as S
from formal.v2_phase7.executor.bootstrap import _paired_marginal_increment
from formal.v2_phase7.gate_b0 import _scientific_guard_results
from formal.v2_phase7.executor.paper_views import build_paper_views
from formal.v2_phase7.executor.runner import run_development_safe_dag

NODE_LIMIT = 16


@pytest.fixture(scope="module")
def completeness_dag(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("scientific_output_completeness")
    run = run_development_safe_dag(
        output_root=root,
        node_limit=NODE_LIMIT,
        resume=False,
    )
    return {"root": root, "run": run}


def _section_payload(
    dag: dict[str, Any], mode: str
) -> dict[str, Any]:
    payload = dag["run"].payload(S.BOOTSTRAP)[
        "marginal_uncertainty_increment"
    ]
    return payload["attention" if mode == "ATTENTION" else "recovery"]


def _paired_values(section: dict[str, Any]) -> tuple[list[int], list[float]]:
    point_field = (
        "L_att_point" if section["mode"] == "ATTENTION" else "L_rec_point"
    )
    marginal_field = (
        "L_att_marginal"
        if section["mode"] == "ATTENTION"
        else "L_rec_marginal"
    )
    delta_field = (
        "delta_L_att_marginal"
        if section["mode"] == "ATTENTION"
        else "delta_L_rec_marginal"
    )
    ids: list[int] = []
    deltas: list[float] = []
    for row in section["replicates"]:
        if (
            row[point_field] is not None
            and row[marginal_field] is not None
            and row[delta_field] is not None
        ):
            ids.append(int(row["replicate_id"]))
            deltas.append(float(row[delta_field]))
    return ids, deltas


@pytest.mark.parametrize("mode", ["ATTENTION", "RECOVERY"])
def test_point_marginal_use_identical_bootstrap_replicates(
    completeness_dag: dict[str, Any], mode: str
) -> None:
    section = _section_payload(completeness_dag, mode)
    assert section["paired_assertions"][
        "POINT_MARGINAL_REPLICATE_IDS_IDENTICAL"
    ] is True
    assert [
        int(row["replicate_id"]) for row in section["replicates"]
    ] == list(range(C.BOOTSTRAP_REPLICATES))


@pytest.mark.parametrize("mode", ["ATTENTION", "RECOVERY"])
def test_point_marginal_use_identical_episode_resamples(
    completeness_dag: dict[str, Any], mode: str
) -> None:
    section = _section_payload(completeness_dag, mode)
    assert section["paired_assertions"][
        "POINT_MARGINAL_RESAMPLED_EPISODES_IDENTICAL"
    ] is True
    assert section["paired_assertions"][
        "POINT_MARGINAL_CANONICAL_IDENTITIES_IDENTICAL"
    ] is True
    assert section["paired_assertions"][
        "POINT_MARGINAL_REFERENCE_EVALUATOR_IDENTICAL"
    ] is True


@pytest.mark.parametrize("mode", ["ATTENTION", "RECOVERY"])
def test_marginal_increment_equals_point_minus_marginal_per_replicate(
    completeness_dag: dict[str, Any], mode: str
) -> None:
    section = _section_payload(completeness_dag, mode)
    point_field = (
        "L_att_point" if mode == "ATTENTION" else "L_rec_point"
    )
    marginal_field = (
        "L_att_marginal" if mode == "ATTENTION" else "L_rec_marginal"
    )
    delta_field = (
        "delta_L_att_marginal" if mode == "ATTENTION" else "delta_L_rec_marginal"
    )
    for row in section["replicates"]:
        if row[delta_field] is None:
            continue
        assert row[delta_field] == pytest.approx(
            float(row[point_field]) - float(row[marginal_field])
        )


@pytest.mark.parametrize("mode", ["ATTENTION", "RECOVERY"])
def test_marginal_increment_ci_uses_paired_difference_distribution(
    completeness_dag: dict[str, Any], mode: str
) -> None:
    section = _section_payload(completeness_dag, mode)
    _ids, deltas = _paired_values(section)
    assert deltas
    expected_low, expected_high = np.quantile(deltas, [0.025, 0.975])
    assert section["ci_low"] == pytest.approx(float(expected_low))
    assert section["ci_high"] == pytest.approx(float(expected_high))
    assert section["numeric_replicate_count"] == len(deltas)
    assert section["undefined_replicate_count"] == (
        len(section["replicates"]) - len(deltas)
    )


def test_marginal_increment_ci_is_not_ci_subtraction(
    completeness_dag: dict[str, Any],
) -> None:
    bootstrap = completeness_dag["run"].payload(S.BOOTSTRAP)
    point = bootstrap["comparators"]["HISTORY_POINT"]["attention"]
    marginal = bootstrap["comparators"]["HISTORY_MARGINAL"]["attention"]
    paired = bootstrap["marginal_uncertainty_increment"]["attention"]
    ci_subtraction_low = float(point["ci_low"]) - float(marginal["ci_low"])
    ci_subtraction_high = float(point["ci_high"]) - float(marginal["ci_high"])
    assert (paired["ci_low"], paired["ci_high"]) != pytest.approx(
        (ci_subtraction_low, ci_subtraction_high)
    )
    _ids, deltas = _paired_values(paired)
    expected_low, expected_high = np.quantile(deltas, [0.025, 0.975])
    assert paired["ci_low"] == pytest.approx(float(expected_low))
    assert paired["ci_high"] == pytest.approx(float(expected_high))


def test_marginal_increment_typed_undefined_preserved() -> None:
    common = {
        "resampled_episodes_hash": "sha256:same",
        "canonical_identity_hash": "sha256:same",
        "reference_evaluator_id": "sha256:same",
    }
    point = {
        **common,
        "point_estimate": 0.2,
        "replicates": [
            {"replicate_id": 0, "value": 0.2, "status": "DEFINED"},
            {"replicate_id": 1, "value": 0.3, "status": "DEFINED"},
        ],
    }
    marginal = {
        **common,
        "point_estimate": 0.1,
        "replicates": [
            {"replicate_id": 0, "value": 0.1, "status": "DEFINED"},
            {
                "replicate_id": 1,
                "value": None,
                "status": "UNDEFINED_ZERO_RECOVERABLE_VALUE",
            },
        ],
    }
    result = _paired_marginal_increment(
        point_record=point,
        marginal_record=marginal,
        mode="RECOVERY",
    )
    assert result["numeric_replicate_count"] == 1
    assert result["undefined_replicate_count"] == 1
    assert result["replicates"][1]["delta_L_rec_marginal"] is None
    assert result["replicates"][1]["increment_status"] == "TYPED_UNDEFINED"
    assert result["undefined_reason_counts"]


def test_cross_state_dependence_and_marginal_increment_have_distinct_labels(
    completeness_dag: dict[str, Any],
) -> None:
    run = completeness_dag["run"]
    views = build_paper_views(
        run.payload(S.ATTENTION_DECISIONS),
        run.payload(S.M4_COMPARISONS),
        run.payload(S.BOOTSTRAP),
        run.payload(S.ROBUSTNESS),
    )
    aliases = views["information_value"]
    assert "cross_state_dependence" in aliases
    assert "marginal_uncertainty_increment" in aliases
    assert aliases["no_ambiguous_marginal_labels"] is True

    def keys(value: Any) -> list[str]:
        if isinstance(value, dict):
            return [
                str(key)
                for key, item in value.items()
                for key in [key, *keys(item)]
            ]
        if isinstance(value, (list, tuple)):
            return [key for item in value for key in keys(item)]
        return []

    all_keys = keys(views)
    assert "MARGINAL_L_ATT" not in all_keys
    assert "MARGINAL_L_REC" not in all_keys
    assert "CROSS_STATE_DEPENDENCE_L_ATT" in all_keys
    assert "MARGINAL_UNCERTAINTY_INCREMENT_L_ATT" in all_keys


def test_robustness_uses_fixed_Rstar(
    completeness_dag: dict[str, Any],
) -> None:
    robustness = completeness_dag["run"].payload(S.ROBUSTNESS)
    reference = completeness_dag["run"].payload(S.REFERENCE_RECOVERY_COHORT)
    assert robustness["fixed_r_star"] is True
    assert robustness["fixed_r_star_node_ids"] == reference[
        "stage2_actionable_node_ids_flattened"
    ]


def test_robustness_does_not_rerun_stage1(
    completeness_dag: dict[str, Any],
) -> None:
    robustness = completeness_dag["run"].payload(S.ROBUSTNESS)
    assert robustness["stage1_rerun"] is False


def test_lambda_ofat_changes_only_lambda(
    completeness_dag: dict[str, Any],
) -> None:
    robustness = completeness_dag["run"].payload(S.ROBUSTNESS)
    rows = [row for row in robustness["rows"] if row["axis"] == "lambda"]
    assert rows
    assert all(
        row["turnaround_lower_bound"] == C.NOMINAL_TURNAROUND_Q20
        and row["u_max"] == C.NOMINAL_U_MAX
        for row in rows
    )


def test_turnaround_ofat_changes_only_turnaround(
    completeness_dag: dict[str, Any],
) -> None:
    robustness = completeness_dag["run"].payload(S.ROBUSTNESS)
    rows = [
        row
        for row in robustness["rows"]
        if row["axis"] == "turnaround_lower_bound"
    ]
    assert rows
    assert all(
        row["lambda"] == C.NOMINAL_LAMBDA
        and row["u_max"] == C.NOMINAL_U_MAX
        for row in rows
    )


def test_umax_ofat_changes_only_umax(
    completeness_dag: dict[str, Any],
) -> None:
    robustness = completeness_dag["run"].payload(S.ROBUSTNESS)
    rows = [row for row in robustness["rows"] if row["axis"] == "u_max"]
    assert rows
    assert all(
        row["lambda"] == C.NOMINAL_LAMBDA
        and row["turnaround_lower_bound"] == C.NOMINAL_TURNAROUND_Q20
        for row in rows
    )


def test_nominal_reference_identity(
    completeness_dag: dict[str, Any],
) -> None:
    robustness = completeness_dag["run"].payload(S.ROBUSTNESS)
    nominal_rows = [row for row in robustness["rows"] if row["nominal_flag"]]
    assert nominal_rows
    assert len({row["nominal_reference_id"] for row in nominal_rows}) == 1
    assert nominal_rows[0]["nominal_reference_id"] == robustness[
        "nominal_reference_id"
    ]


def test_section4_h_capacity_not_called(
    completeness_dag: dict[str, Any],
) -> None:
    robustness = completeness_dag["run"].payload(S.ROBUSTNESS)
    assert robustness["section4_h_capacity_called"] is False


def test_robustness_uses_exact_enumeration(
    completeness_dag: dict[str, Any],
) -> None:
    robustness = completeness_dag["run"].payload(S.ROBUSTNESS)
    assert robustness["exact_enumeration"] is True
    assert robustness["solver"]["stage2_primary_solver"] == (
        C.STAGE2_PRIMARY_SOLVER
    )


def test_robustness_has_no_taxi_comp_actions(
    completeness_dag: dict[str, Any],
) -> None:
    robustness = completeness_dag["run"].payload(S.ROBUSTNESS)
    assert robustness["taxi_comp_actions"] == []
    assert all(row["stage"] in {"PRE", "TURN"} for row in robustness["rows"])


def test_new_epoch_root_is_distinct_from_failed_epochs() -> None:
    assert C.STAGE_MATCHED_FINAL_TEST_ROOT != (
        C.CONSUMED_CANONICAL_V1_FINAL_TEST_ROOT
    )
    assert C.STAGE_MATCHED_FINAL_TEST_ROOT != (
        C.CONSUMED_STAGE_MATCHED_FINAL_TEST_ROOT
    )
    assert not C.STAGE_MATCHED_FINAL_TEST_ROOT.exists()


def test_formal_dag_exposes_machine_readable_scientific_guards(
    completeness_dag: dict[str, Any],
) -> None:
    guards = _scientific_guard_results(completeness_dag["run"])
    assert guards["status"] == "PASS"
    assert guards["CANONICALIZATION_BEFORE_SUPPORT"] == "PASS"
    assert guards["DUPLICATE_EPISODE_STAGE_GROUPS_AFTER_CANONICALIZATION"] == 0
    assert guards["PRE_STAGE1_UNIQUENESS"] == "PASS"
    assert guards["TURN_STAGE1_UNIQUENESS"] == "PASS"
    assert guards["NO_POOLED_STAGE1_RANKING"] == "PASS"
    assert guards["TAXI_COMP_STAGE1_PARTICIPATION"] == "NONE"
    assert guards["R_STAR_SUPPORT_QUALIFIED_PRE_TURN_UNION"] == "PASS"
    assert guards["STAGE2_SOBT_COORDINATE"] == "NODE_RELATIVE_SOBT"
    assert guards["STAGE1_OVERALL_AGGREGATION"] == "OBJECTIVES_THEN_NORMALIZE"
