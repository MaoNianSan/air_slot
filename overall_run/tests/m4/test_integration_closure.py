from __future__ import annotations

import copy
import hashlib
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

import src.config as config_module
from src.config import AUTHORITATIVE_CODE, LEGACY_AUDIT_CODE, ConfigError, load_config
from src.failures import M3ParameterNotFrozen
from src.m2.contracts import ParameterStatus
from src.m4 import adapt_m4_inputs, evaluate_publication_gate, run_m4_formal_stage
from src.m4.contracts import (
    DecisionLane,
    M4ResultStatus,
    M4UpstreamBlocked,
)
from src.m4.pipeline import run_m4_synthetic_integration
from src.m4.ranking import assign_lane_ranks, build_authoritative_ranking
from src.m4.status import determine_result_status
from src.pipeline import run_experiment
from src.ranking_contract import (
    RANKING_CONTRACT_VERSION,
    build_ranking_prefixes_from_authoritative_order,
)


OVERALL_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = OVERALL_ROOT.parent


def _override(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "override.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _future_inputs(m4_input_factory, m3_artifact):
    m2_bundle, losses = m4_input_factory()
    valuation = replace(
        m2_bundle.valuation_context,
        test_only=False,
        source="FROZEN_FIXTURE",
    )
    m2_bundle = replace(m2_bundle, valuation_context=valuation)
    metadata = dict(m3_artifact.version_metadata)
    metadata["publication_allowed"] = True
    frozen_m3 = replace(
        m3_artifact,
        version_metadata=metadata,
        parameter_freeze_status="DONE",
        formal_library_status="READY",
        test_only=False,
    )
    return m2_bundle, losses, frozen_m3


def _future_cfg(cfg, *, evaluation_enabled: bool = False, output_dir: str = "evaluation/m4"):
    merged = copy.deepcopy(cfg.merged)
    merged["m3"]["status"].update({
        "parameter_freeze": "DONE",
        "formal_library": "READY",
        "scientific_approved": True,
        "publication_allowed": True,
    })
    merged["evaluation"]["m4"].update({
        "enabled": evaluation_enabled,
        "fail_on_error": False,
        "output_dir": output_dir,
    })
    return replace(cfg, merged=merged)


def _synthetic_artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides):
    bundle, losses = m4_input_factory()
    return run_m4_synthetic_integration(
        bundle,
        losses,
        m3_artifact,
        cfg.scientific,
        stage_mapping={"TURNAROUND": "t1"},
        opportunity_overrides=opportunity_overrides,
    )


def _status_fixture(artifact, selected: dict[str, tuple[DecisionLane, tuple[str, ...]]]):
    rows = []
    for item in artifact.action_evaluations:
        if item.action_id == "A00":
            lane, reasons = DecisionLane.FORMAL, ("FORMAL_SUPPORTED",)
        elif item.action_id in selected:
            lane, reasons = selected[item.action_id]
        else:
            lane, reasons = DecisionLane.EXCLUDED, ("ACTION_DISABLED",)
        rows.append(
            replace(
                item,
                decision_lane=lane,
                reason_codes=reasons,
                lane_rank=None,
                test_only=False,
            )
        )
    return assign_lane_ranks(tuple(rows))


def _future_bundle_and_valid_evaluations(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
):
    m2_bundle, losses, frozen_m3 = _future_inputs(m4_input_factory, m3_artifact)
    bundle = adapt_m4_inputs(
        m2_bundle,
        losses,
        frozen_m3,
        stage_mapping={"TURNAROUND": "t1"},
        stage_mapping_version="FROZEN_FIXTURE_V1",
    )
    bundle = replace(bundle, formal_mode=True, test_only=False)
    artifact = _synthetic_artifact(
        cfg, m4_input_factory, m3_artifact, opportunity_overrides
    )
    evaluations = _status_fixture(
        artifact,
        {"A12": (DecisionLane.FORMAL, ("FORMAL_SUPPORTED",))},
    )
    return bundle, evaluations


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_m4_v2_config_loads(cfg) -> None:
    assert cfg.scientific["m4"]["identity"] == "M4_CONTEXTUAL_RESIDUAL_RISK_V2"


def test_legacy_decision_value_config_rejected(tmp_path) -> None:
    override = _override(tmp_path, "m4:\n  decision_value: {}\n")
    with pytest.raises(ConfigError, match="retired keys"):
        load_config(OVERALL_ROOT, "fast", override=override)


def test_draw_pairing_snapshot_id_must_be_false(tmp_path) -> None:
    override = _override(tmp_path, "m4:\n  draw_pairing:\n    include_snapshot_id: true\n")
    with pytest.raises(ConfigError, match="draw_pairing"):
        load_config(OVERALL_ROOT, "fast", override=override)


def test_draw_pairing_action_id_must_be_false(tmp_path) -> None:
    override = _override(tmp_path, "m4:\n  draw_pairing:\n    include_action_id: true\n")
    with pytest.raises(ConfigError, match="draw_pairing"):
        load_config(OVERALL_ROOT, "fast", override=override)


def test_risk_weights_sum_to_one(tmp_path) -> None:
    override = _override(
        tmp_path,
        "m4:\n  risk:\n    expected_weight: 0.8\n    cvar_weight: 0.3\n",
    )
    with pytest.raises(ConfigError, match="sum to one"):
        load_config(OVERALL_ROOT, "fast", override=override)


def test_ranking_depths_exactly_1_2_3_5(tmp_path) -> None:
    override = _override(tmp_path, "m4:\n  ranking:\n    depths: [1, 3, 5]\n")
    with pytest.raises(ConfigError, match="depths"):
        load_config(OVERALL_ROOT, "fast", override=override)


def test_evaluation_output_not_inside_formal_output(tmp_path) -> None:
    override = _override(
        tmp_path,
        "evaluation:\n  m4:\n    output_dir: output/m4/evaluation\n",
    )
    with pytest.raises(ConfigError, match="outside output/m4"):
        load_config(OVERALL_ROOT, "fast", override=override)


def test_authoritative_code_contains_all_m4_v2_formal_files() -> None:
    authoritative = {path for path, _ in AUTHORITATIVE_CODE}
    actual = {
        path.relative_to(OVERALL_ROOT).as_posix()
        for path in (OVERALL_ROOT / "src" / "m4").glob("*.py")
    }
    assert actual.issubset(authoritative)


def test_authoritative_code_excludes_legacy_m4_v1() -> None:
    authoritative = {path for path, _ in AUTHORITATIVE_CODE}
    assert authoritative.isdisjoint(LEGACY_AUDIT_CODE)
    assert {"src/m4.py", "src/m4_screening.py", "src/m4_evaluation.py"}.isdisjoint(
        authoritative
    )


def test_m4_v2_code_change_changes_implementation_hash(tmp_path, monkeypatch) -> None:
    source = tmp_path / "src" / "m4" / "contracts.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n", encoding="ascii")
    monkeypatch.setattr(
        config_module,
        "AUTHORITATIVE_CODE",
        (("src/m4/contracts.py", "m4_v2_contracts"),),
    )
    first = config_module._canonical_hash(
        config_module._implementation_manifest(tmp_path, [])
    )
    source.write_text("VALUE = 2\n", encoding="ascii")
    second = config_module._canonical_hash(
        config_module._implementation_manifest(tmp_path, [])
    )
    assert first != second


def test_pipeline_still_blocks_at_m3_parameter_not_frozen(cfg) -> None:
    with pytest.raises(M3ParameterNotFrozen, match="M3_PARAMETER_NOT_FROZEN"):
        run_experiment(cfg, "fast")


def test_pipeline_calls_m4_after_m3_gates_pass_in_fixture(
    tmp_path, cfg, m4_input_factory, m3_artifact
) -> None:
    future_cfg = _future_cfg(cfg)
    m4_inputs = _future_inputs(m4_input_factory, m3_artifact)
    artifact = run_experiment(
        future_cfg,
        "fast",
        m4_inputs=m4_inputs,
        m4_stage_mapping={"TURNAROUND": "t1"},
        m4_stage_mapping_version="FROZEN_FIXTURE_V1",
        m4_output_dir=tmp_path / "formal",
    )
    assert artifact.formal_status == "PASS"
    assert artifact.evaluation_status == "NOT_RUN"
    assert (tmp_path / "formal" / "m4_manifest.json").is_file()


def test_pipeline_no_longer_has_unconditional_m4_contract_mismatch() -> None:
    source = (OVERALL_ROOT / "src" / "pipeline.py").read_text(encoding="utf-8")
    finalizer = (OVERALL_ROOT / "src" / "pipeline_finalize.py").read_text(
        encoding="utf-8"
    )
    assert "M4_CONTRACT_MISMATCH" not in source
    assert "M4_CONTRACT_MISMATCH" not in finalizer


def test_test_only_m4_does_not_bypass_formal_pipeline(
    tmp_path, cfg, m4_input_factory, m3_artifact
) -> None:
    future_cfg = _future_cfg(cfg)
    bundle, losses = m4_input_factory()
    with pytest.raises(M4UpstreamBlocked, match="TEST_ONLY_ARTIFACT"):
        run_experiment(
            future_cfg,
            "fast",
            m4_inputs=(bundle, losses, m3_artifact),
            m4_stage_mapping={"TURNAROUND": "t1"},
            m4_stage_mapping_version="FROZEN_FIXTURE_V1",
            m4_output_dir=tmp_path / "formal",
        )


def test_only_one_authoritative_sort() -> None:
    source = (OVERALL_ROOT / "src" / "m4" / "ranking.py").read_text(
        encoding="utf-8"
    )
    assert "full_ranking_from_scores" not in source
    assert "build_ranking_prefixes_from_authoritative_order" in source


def test_prefix_builder_does_not_resort() -> None:
    universe = pd.DataFrame([{"episode_id": "e", "snapshot_id": "s"}])
    ranking = pd.DataFrame([
        {
            "episode_id": "e",
            "snapshot_id": "s",
            "action_id": "A22",
            "action_family": "F2",
            "score": 2.0,
            "expected_residual": 2.0,
            "cvar_residual": 2.0,
            "rank": 1,
        },
        {
            "episode_id": "e",
            "snapshot_id": "s",
            "action_id": "A12",
            "action_family": "F1",
            "score": 1.0,
            "expected_residual": 1.0,
            "cvar_residual": 1.0,
            "rank": 2,
        },
    ])
    _, views = build_ranking_prefixes_from_authoritative_order(universe, ranking)
    assert views[2]["action_id"].tolist() == ["A22", "A12"]


def test_cost_tie_break_preserved(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    artifact = _synthetic_artifact(
        cfg, m4_input_factory, m3_artifact, opportunity_overrides
    )
    selected = []
    for item in artifact.action_evaluations:
        if item.action_id not in {"A12", "A22"}:
            continue
        selected.append(
            replace(
                item,
                decision_lane=DecisionLane.FORMAL,
                reason_codes=("FORMAL_SUPPORTED",),
                risk_score=1.0,
                expected_total_post_loss_rmb=2.0,
                cvar90_post_loss_rmb=3.0,
                expected_implementation_cost_rmb=1.0 if item.action_id == "A22" else 2.0,
            )
        )
    ranked = assign_lane_ranks(tuple(reversed(selected)))
    full, _, _ = build_authoritative_ranking(ranked)
    assert full["action_id"].tolist() == ["A22", "A12"]


def test_manifest_tie_break_matches_actual_sort(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    artifact = _synthetic_artifact(
        cfg, m4_input_factory, m3_artifact, opportunity_overrides
    )
    assert artifact.manifest["tie_break"] == [
        "risk_score",
        "expected_total_post_loss_rmb",
        "cvar90_post_loss_rmb",
        "expected_implementation_cost_rmb",
        "action_id",
    ]


def test_ranking_contract_version_is_v2(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    artifact = _synthetic_artifact(
        cfg, m4_input_factory, m3_artifact, opportunity_overrides
    )
    assert RANKING_CONTRACT_VERSION == "M4_RANKING_1235_V2"
    assert artifact.manifest["ranking_contract_version"] == RANKING_CONTRACT_VERSION


def test_A00_plus_conditional_actions_is_conditional_only(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    artifact = _synthetic_artifact(
        cfg, m4_input_factory, m3_artifact, opportunity_overrides
    )
    rows = _status_fixture(
        artifact,
        {"A12": (DecisionLane.CONDITIONAL, ("OPPORTUNITY_CONTRACT_NOT_CONFIGURED",))},
    )
    assert determine_result_status(rows, test_only=False) is M4ResultStatus.CONDITIONAL_ONLY


def test_A00_plus_scenario_actions_is_scenario_only(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    artifact = _synthetic_artifact(
        cfg, m4_input_factory, m3_artifact, opportunity_overrides
    )
    rows = _status_fixture(
        artifact,
        {"A71": (DecisionLane.SCENARIO, ("M3_SCENARIO_ONLY",))},
    )
    assert determine_result_status(rows, test_only=False) is M4ResultStatus.SCENARIO_ONLY


def test_true_A00_only_requires_no_other_evaluable_actions(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    artifact = _synthetic_artifact(
        cfg, m4_input_factory, m3_artifact, opportunity_overrides
    )
    rows = _status_fixture(artifact, {})
    assert determine_result_status(rows, test_only=False) is M4ResultStatus.A00_ONLY


def test_upstream_blocker_not_reported_as_A00_only(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    artifact = _synthetic_artifact(
        cfg, m4_input_factory, m3_artifact, opportunity_overrides
    )
    rows = _status_fixture(
        artifact,
        {"A12": (DecisionLane.CONDITIONAL, ("M3_PARAMETER_NOT_FROZEN",))},
    )
    assert determine_result_status(rows, test_only=False) is M4ResultStatus.BLOCKED_BY_UPSTREAM


def test_formal_mode_alone_not_publication_allowed(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, evaluations = _future_bundle_and_valid_evaluations(
        cfg, m4_input_factory, m3_artifact, opportunity_overrides
    )
    bundle = replace(
        bundle,
        m3_artifact=replace(bundle.m3_artifact, parameter_freeze_status="NOT_YET_DONE"),
    )
    result = evaluate_publication_gate(bundle, evaluations, M4ResultStatus.VALID)
    assert not result.allowed


def test_unfrozen_m2_blocks_publication(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, evaluations = _future_bundle_and_valid_evaluations(
        cfg, m4_input_factory, m3_artifact, opportunity_overrides
    )
    valuation = replace(
        bundle.m2_input_bundle.valuation_context,
        parameter_status=ParameterStatus.REQUIRES_DEVELOPMENT_FREEZE,
    )
    bundle = replace(
        bundle,
        m2_input_bundle=replace(bundle.m2_input_bundle, valuation_context=valuation),
    )
    result = evaluate_publication_gate(bundle, evaluations, M4ResultStatus.VALID)
    assert "M2_VALUATION_NOT_FROZEN" in result.reason_codes


def test_unfrozen_m3_blocks_publication(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, evaluations = _future_bundle_and_valid_evaluations(
        cfg, m4_input_factory, m3_artifact, opportunity_overrides
    )
    bundle = replace(
        bundle,
        m3_artifact=replace(bundle.m3_artifact, formal_library_status="NOT_YET_RUN"),
    )
    result = evaluate_publication_gate(bundle, evaluations, M4ResultStatus.VALID)
    assert "M3_FORMAL_LIBRARY_NOT_READY" in result.reason_codes


def test_test_only_blocks_publication(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, evaluations = _future_bundle_and_valid_evaluations(
        cfg, m4_input_factory, m3_artifact, opportunity_overrides
    )
    result = evaluate_publication_gate(
        replace(bundle, test_only=True), evaluations, M4ResultStatus.VALID
    )
    assert "TEST_ONLY_ARTIFACT" in result.reason_codes


def test_contract_error_blocks_publication(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, evaluations = _future_bundle_and_valid_evaluations(
        cfg, m4_input_factory, m3_artifact, opportunity_overrides
    )
    result = evaluate_publication_gate(
        bundle,
        evaluations,
        M4ResultStatus.CONTRACT_ERROR,
        contract_pass=False,
    )
    assert not result.allowed
    assert "M4_CONTRACT_NOT_PASS" in result.reason_codes


def test_valid_frozen_fixture_allows_publication(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, evaluations = _future_bundle_and_valid_evaluations(
        cfg, m4_input_factory, m3_artifact, opportunity_overrides
    )
    result = evaluate_publication_gate(bundle, evaluations, M4ResultStatus.VALID)
    assert result.allowed
    assert result.reason_codes == ()


def test_evaluation_config_path(
    tmp_path, cfg, m4_input_factory, m3_artifact
) -> None:
    m2_bundle, losses, frozen_m3 = _future_inputs(m4_input_factory, m3_artifact)
    config = copy.deepcopy(cfg.scientific)
    config["evaluation"]["m4"].update({
        "enabled": True,
        "output_dir": "evaluation/m4",
    })
    artifact = run_m4_formal_stage(
        m2_bundle,
        losses,
        frozen_m3,
        config,
        stage_mapping={"TURNAROUND": "t1"},
        stage_mapping_version="FROZEN_FIXTURE_V1",
        output_dir=tmp_path / "formal",
        project_root=tmp_path,
    )
    assert artifact.evaluation_enabled
    assert artifact.evaluation_status == "PASS"
    assert (tmp_path / "evaluation" / "m4" / "m4_v2_evaluation.json").is_file()


def test_formal_hash_identical_evaluation_on_off(
    tmp_path, cfg, m4_input_factory, m3_artifact
) -> None:
    m2_bundle, losses, frozen_m3 = _future_inputs(m4_input_factory, m3_artifact)
    hashes = []
    for enabled, name in ((False, "off"), (True, "on")):
        config = copy.deepcopy(cfg.scientific)
        config["evaluation"]["m4"].update({
            "enabled": enabled,
            "output_dir": f"evaluation/{name}",
        })
        output = tmp_path / f"formal_{name}"
        run_m4_formal_stage(
            m2_bundle,
            losses,
            frozen_m3,
            config,
            stage_mapping={"TURNAROUND": "t1"},
            stage_mapping_version="FROZEN_FIXTURE_V1",
            output_dir=output,
            project_root=tmp_path,
        )
        hashes.append(tuple(_sha256(output / name) for name in (
            "m4_episode_decision.parquet",
            "m4_action_evaluation.parquet",
            "m4_manifest.json",
        )))
    assert hashes[0] == hashes[1]


def test_evaluation_failure_does_not_change_formal_status(
    tmp_path, cfg, m4_input_factory, m3_artifact
) -> None:
    m2_bundle, losses, frozen_m3 = _future_inputs(m4_input_factory, m3_artifact)
    config = copy.deepcopy(cfg.scientific)
    config["evaluation"]["m4"].update({
        "enabled": True,
        "fail_on_error": False,
        "output_dir": "formal/evaluation",
    })
    artifact = run_m4_formal_stage(
        m2_bundle,
        losses,
        frozen_m3,
        config,
        stage_mapping={"TURNAROUND": "t1"},
        stage_mapping_version="FROZEN_FIXTURE_V1",
        output_dir=tmp_path / "formal",
        project_root=tmp_path,
    )
    assert artifact.formal_status == "PASS"
    assert artifact.evaluation_status == "FAIL"
    assert (tmp_path / "formal" / "m4_manifest.json").is_file()


def test_no_active_legacy_m4_module() -> None:
    for name in ("m4.py", "m4_screening.py", "m4_evaluation.py"):
        assert not (OVERALL_ROOT / "src" / name).exists()


def test_src_m4_resolves_to_package() -> None:
    import src.m4 as m4

    assert Path(m4.__file__).name == "__init__.py"
    assert Path(m4.__file__).parent.name == "m4"


def test_formal_pipeline_imports_new_m4() -> None:
    source = (OVERALL_ROOT / "src" / "pipeline.py").read_text(encoding="utf-8")
    assert "from .m4 import M4FormalArtifact, run_m4_formal_stage" in source
    assert "legacy.m4" not in source
