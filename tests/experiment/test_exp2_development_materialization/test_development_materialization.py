from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from exp.exp2.artifacts.m3_scenario_bundle import (
    M3ScenarioBundle,
    materialize_m3_scenario_bundle,
)
from exp.exp2.artifacts.m4_policy_binding import materialize_m4_policy
from exp.exp2.execution import data2_development_cohort as cohort
from exp.exp2.execution.development_materialization import inspect_m1_v2_artifact_gate
from model.PRE import development as pre_development
from model.M4.residual_risk import ResidualRiskPolicy


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_development_source_paths_are_exact_and_reject_test_named_paths(tmp_path: Path):
    for month in (8, 9):
        source = (
            tmp_path
            / "data2"
            / "raw"
            / "bts"
            / "ontime"
            / "2019"
            / f"month={month:02d}"
            / "ontime.csv"
        )
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("FlightDate\n", encoding="utf-8")

    paths = cohort.development_ontime_paths(tmp_path)

    assert tuple(path.parent.name for path in paths) == ("month=08", "month=09")
    with pytest.raises(RuntimeError, match="FINAL_TEST_SOURCE_PATH_SELECTED"):
        cohort._assert_development_paths(
            (
                tmp_path / "month=08" / "ontime.csv",
                tmp_path / "month=10" / "ontime.csv",
            )
        )


def test_deterministic_cohort_selection_is_stable_and_pre_outcome():
    candidates = tuple(
        (
            SimpleNamespace(episode_id=episode_id),
            {"outcome": {"arbitrary": "never inspected by selector"}},
        )
        for episode_id in ("episode-c", "episode-a", "episode-b")
    )

    selected = cohort.select_deterministic_pilot(candidates, episode_count=2)

    assert tuple(item.episode_id for item in selected) == ("episode-a", "episode-b")


def test_eligible_episode_requires_successor_development_split_and_full_containment(monkeypatch):
    development = SimpleNamespace(
        predecessor_flight_id="pre-dev",
        successor_flight_id="suc-dev",
        episode_id="episode-development",
    )
    final_test = SimpleNamespace(
        predecessor_flight_id="pre-test",
        successor_flight_id="suc-test",
        episode_id="episode-final-test",
    )
    rows = [
        {"flight_id": "pre-dev", "service_date": "2019-08-01"},
        {"flight_id": "suc-dev", "service_date": "2019-08-01"},
        {"flight_id": "pre-test", "service_date": "2019-09-30"},
        {"flight_id": "suc-test", "service_date": "2019-10-01"},
    ]
    allowed = SimpleNamespace(allowed=True, split="development")

    monkeypatch.setattr(
        pre_development,
        "build_data2_episode_records",
        lambda _: (development, final_test),
    )
    monkeypatch.setattr(
        pre_development, "episode_containment_from_rows", lambda *_: allowed,
    )

    eligible = tuple(pre_development.eligible_development_episodes_from_rows(rows))

    assert tuple(item[0].episode_id for item in eligible) == ("episode-development",)


def test_m3_bundle_is_typed_conditional_and_never_upgrades_support(tmp_path: Path):
    output_path = tmp_path / "m3.json"

    bundle = materialize_m3_scenario_bundle(root=REPOSITORY_ROOT, output_path=output_path)
    persisted = M3ScenarioBundle.model_validate(json.loads(output_path.read_text(encoding="utf-8")))

    assert bundle == persisted
    assert bundle.rules[0].action_id == "A00"
    assert len(bundle.rules) == 23
    assert all(not rule.formal_support_upgrade for rule in bundle.rules)
    assert all(
        rule.support_state == "SCENARIO_ASSUMPTION"
        for rule in bundle.rules
        if rule.action_id != "A00"
    )


def test_m4_policy_uses_declared_parameters_and_preserves_both_execution_gates(tmp_path: Path):
    artifact = materialize_m4_policy(root=REPOSITORY_ROOT, output_path=tmp_path / "m4.json")
    policy = ResidualRiskPolicy.model_validate(artifact["policy"])

    assert artifact["policy_id"] == "EXP2_DATA2_DEVELOPMENT_RESIDUAL_RISK_POLICY_V1"
    assert policy.alpha == 0.90
    assert policy.expected_loss_coefficient == 0.75
    assert policy.cvar_coefficient == 0.25
    assert artifact["m4_execution_status"] == "M1_POSITIVE_TAIL_DECISION_REQUIRED"
    assert artifact["monetary_mapping_status"] == "MONETARY_MAPPING_BLOCKED"


def test_m1_gate_rejects_legacy_and_unverified_v2_artifacts(tmp_path: Path):
    foundation = tmp_path / "configs" / "scientific" / "foundation.yaml"
    foundation.parent.mkdir(parents=True)
    foundation.write_text(
        """
parameters:
  m1_state_estimator_v2:
    value: M1_STATE_ESTIMATOR_V2
    provenance:
      primitive_targets: [T_IB_A00, D_OB, D_TX]
      scenario_count: 1000
""".lstrip(),
        encoding="utf-8",
    )
    legacy = tmp_path / "artifacts" / "diagnostics" / "M1_SIGNED_WARNING_MODEL_V1.pt"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"legacy")
    unverified = tmp_path / "outputs" / "M1_STATE_ESTIMATOR_V2.pt"
    unverified.parent.mkdir(parents=True)
    unverified.write_bytes(b"unfrozen")

    gate = inspect_m1_v2_artifact_gate(tmp_path)

    assert gate["status"] == "BLOCKED_M1_V2_ARTIFACT_NOT_FROZEN"
    assert gate["legacy_v1_paths_excluded"] == (
        "artifacts/diagnostics/M1_SIGNED_WARNING_MODEL_V1.pt",
    )
    assert gate["unverified_v2_candidates"] == ("outputs/M1_STATE_ESTIMATOR_V2.pt",)
    assert gate["freeze_requirement"] == "TRAIN_FROZEN_EXECUTABLE_M1_V2_CHECKPOINT_AND_SCENARIO_ARTIFACT"
