"""Materialize the current-stage Development M1 V2 joint scenario envelope.

This module is intentionally narrower than the legacy V1 scenario artifact.
It consumes the refrozen, label-free PRE inputs and the frozen H32 checkpoint,
then emits class-aware rows.  Finite bins receive representative scalars;
zero outcomes receive an explicit ``ZERO`` class; values in the frozen
overflow class retain no fabricated scalar.  The artifact is Development-only
and is not a paper metric run.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import torch

from model.M1.loss import hazard_pmf, monotone_positive_quantiles, quantile_value
from model.M1.pipeline import M1Pipeline
from model.M1.scenario_envelope import (
    ABSTAIN_CLASS_ID,
    TAIL_CLASS_ID,
    ZERO_CLASS_ID,
    JointScenarioEnvelope,
    TargetScenarioEnvelope,
)
from model.M1.semantics import (
    M1_V2_HAZARD_COORDINATE_TARGET,
    derived_r_ib_minutes,
    t_ib_a00_from_remaining_minutes,
)
from model.common.errors import ContractError
from model.common.identity import content_id
from model.PRE.contracts.pre_state import PREState


DEFAULT_OUTPUT = Path("artifacts/experiment/m1_v2_current_stage_scenarios_v4")
INPUTS = Path(
    "artifacts/diagnostics/m1_v2_development_current_stage_refreeze_v3/"
    "M1_V2_CURRENT_STAGE_DEVELOPMENT_INFERENCE_INPUTS.json"
)
COHORT = Path("artifacts/experiment/exp2/DATA2_DEVELOPMENT_PILOT_COHORT_CURRENT_STAGE_V3.json")
CHECKPOINT = Path("artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt")
SUPPORT = Path(
    "artifacts/diagnostics/m1_v2_positive_tail_policy_freeze_v2/"
    "M1_V2_TARGET_SUPPORT_MANIFEST.json"
)
M1_BINDING = Path(
    "artifacts/diagnostics/exp1_formal_execution_preparation/"
    "EXP1_M1_V2_ARTIFACT_BINDING.json"
)
REFREEZE = Path(
    "artifacts/diagnostics/m1_v2_development_current_stage_refreeze_v3/"
    "M1_V2_CURRENT_STAGE_COHORT_REFREEZE_MANIFEST.json"
)
SCENARIO_COUNT = 250
SCENARIO_SEED = 20260813
TARGETS = ("T_IB_A00", "D_OB", "D_TX")

SAFETY = {
    "M1_TRAINING_RUNS_THIS_MATERIALIZATION": 0,
    "TUNING_RUNS_THIS_MATERIALIZATION": 0,
    "EXP1_RUNS_THIS_MATERIALIZATION": 0,
    "EXP2_RUNS_THIS_MATERIALIZATION": 0,
    "EXP3_RUNS_THIS_MATERIALIZATION": 0,
    "EXP4_RUNS_THIS_MATERIALIZATION": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "FULL": False,
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _uniform(seed: int, episode: str, scenario: int, target: str) -> tuple[float, str]:
    key = f"m1_v2_scenario|{seed}|{episode}|{scenario}|{target}"
    digest = sha256(key.encode("utf-8")).hexdigest()
    return (int(digest[:16], 16) + 0.5) / (2**64), f"sha256:{digest}"


def _rng_target(target: str) -> str:
    return M1_V2_HAZARD_COORDINATE_TARGET if target == "T_IB_A00" else target


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"M1_V2_SCENARIO_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(rendered, encoding="utf-8")
    tmp.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _target_support(pre: PREState) -> dict[str, str]:
    mapping = {"R_IB": "T_IB_A00", "DELTA_OB": "D_OB", "T_TX": "D_TX"}
    return {
        mapping.get(item.target_name, item.target_name): (
            item.support_state.value
            if hasattr(item.support_state, "value")
            else str(item.support_state)
        )
        for item in pre.target_support
        if mapping.get(item.target_name, item.target_name) in TARGETS
    }


def _supported_value(pre: PREState, section: str, key: str, cutoff: datetime) -> Any | None:
    item = getattr(pre, section).get(key)
    if item is None or item.support_state.value != "SUPPORTED" or item.value is None:
        return None
    availability = getattr(item, "availability_time", None)
    if availability is not None and availability > cutoff:
        return None
    return item.value


def _factual_observed(pre: PREState) -> dict[str, Any]:
    node = pre.decision_node
    cutoff = node.information_cutoff
    observed: dict[str, Any] = {}
    predecessor = _supported_value(pre, "current_state", "predecessor_operational_fact", cutoff)
    if isinstance(predecessor, dict):
        arrival = predecessor.get("actual_arrival_utc")
        availability = predecessor.get("declared_availability_by_field", {}).get("actual_arrival_utc")
        if arrival and availability and datetime.fromisoformat(str(availability).replace("Z", "+00:00")) <= cutoff:
            observed["T_IB_A00"] = str(arrival).replace("Z", "+00:00")
    if node.operational_stage.value == "POST_OB_PRE_TO":
        successor = _supported_value(pre, "successor_state", "successor_operational_fact", cutoff)
        schedule = _supported_value(pre, "successor_state", "schedule_reference", cutoff)
        if isinstance(successor, dict) and isinstance(schedule, dict):
            actual = successor.get("actual_departure_utc")
            planned = schedule.get("scheduled_departure_utc")
            availability = successor.get("declared_availability_by_field", {}).get("actual_departure_utc")
            if actual and planned and availability and datetime.fromisoformat(str(availability).replace("Z", "+00:00")) <= cutoff:
                actual_dt = datetime.fromisoformat(str(actual).replace("Z", "+00:00"))
                planned_dt = datetime.fromisoformat(str(planned).replace("Z", "+00:00"))
                observed["D_OB"] = max(0.0, (actual_dt - planned_dt).total_seconds() / 60.0)
    return observed


def _class_envelope(
    *, target: str, index: int | None, conditioning_index: int | None,
    contract: Any, source_role: str, decision_time: str,
    scalar: float | None, raw_observed_minutes: float | None = None,
    raw_observed_time_utc: str | None = None, raw_model_candidate_minutes: float | None = None,
    event_time_utc: str | None = None, lineage: tuple[str, ...],
) -> TargetScenarioEnvelope:
    if index is None:
        return TargetScenarioEnvelope(
            target_name=target, class_id=ABSTAIN_CLASS_ID, source_role="ABSTAIN",
            support_state="ABSTAIN", scalar_support_state="ABSTAIN_UNSUPPORTED",
            lineage=lineage,
        )
    overflow = contract.tail_state(index) == "OVERFLOW"
    if overflow:
        lower = float(contract.max_finite_minutes)
        public_index = index if target == "T_IB_A00" else index + 1
        return TargetScenarioEnvelope(
            target_name=target, class_index=public_index, conditioning_index=conditioning_index,
            class_id=TAIL_CLASS_ID, class_lower_minutes=lower, class_upper_minutes=None,
            scalar_minutes=None, event_time_utc=event_time_utc,
            raw_observed_minutes=raw_observed_minutes, raw_observed_time_utc=raw_observed_time_utc,
            raw_model_candidate_minutes=raw_model_candidate_minutes, source_role=source_role,
            support_state="SUPPORTED", scalar_support_state="ABSTAIN_TAIL_CLASS",
            overflow=True, lineage=lineage,
        )
    if target in ("D_OB", "D_TX") and index == 0 and abs(float(scalar or 0.0)) <= 1e-12:
        return TargetScenarioEnvelope(
            target_name=target, class_index=index, conditioning_index=conditioning_index,
            class_id=ZERO_CLASS_ID, class_lower_minutes=0.0, class_upper_minutes=0.0,
            scalar_minutes=0.0, raw_observed_minutes=raw_observed_minutes,
            source_role=source_role, support_state="SUPPORTED", scalar_support_state="SUPPORTED",
            lineage=lineage,
        )
    if target == "T_IB_A00":
        lower = float(contract.bin_start(index))
        upper = float(contract.bin_end(index))
    else:
        lower = float(index * contract.bin_width_minutes)
        upper = float((index + 1) * contract.bin_width_minutes)
    value = float(scalar if scalar is not None else (lower + upper) / 2.0)
    public_index = index if target == "T_IB_A00" else index + 1
    class_id = f"BIN_{index}" if target == "T_IB_A00" else f"POSITIVE_BIN_{index}"
    return TargetScenarioEnvelope(
        target_name=target, class_index=public_index, conditioning_index=conditioning_index,
        class_id=class_id, class_lower_minutes=lower, class_upper_minutes=upper,
        scalar_minutes=value, event_time_utc=event_time_utc,
        raw_observed_minutes=raw_observed_minutes, raw_observed_time_utc=raw_observed_time_utc,
        source_role=source_role, support_state="SUPPORTED", scalar_support_state="SUPPORTED",
        lineage=lineage,
    )


def _draw_target(
    pipeline: M1Pipeline, state: torch.Tensor, target: str, uniform: float,
    *, ib_index: int | None, d_ob_index: int | None, decision_time: str,
    lineage: tuple[str, ...], observed: Any | None,
) -> tuple[TargetScenarioEnvelope, int | None]:
    if target == "T_IB_A00":
        contract = pipeline.contracts[M1_V2_HAZARD_COORDINATE_TARGET]
        if observed is not None:
            remaining = derived_r_ib_minutes(observed, decision_time)
            index = contract.encode(remaining)
            return _class_envelope(
                target=target, index=index, conditioning_index=index, contract=contract,
                source_role="FACTUAL_OBSERVED", decision_time=decision_time,
                scalar=None if contract.tail_state(index) == "OVERFLOW" else remaining,
                raw_observed_minutes=remaining, raw_observed_time_utc=observed,
                event_time_utc=observed, lineage=lineage,
            ), index
        logits = pipeline.model.hazard_logits(state)[0].detach()
        pmf = hazard_pmf(logits / float(pipeline.temperatures.get(M1_V2_HAZARD_COORDINATE_TARGET, 1.0)), contract)
        index = int(torch.searchsorted(torch.cumsum(pmf, 0), torch.tensor(uniform)).clamp_max(contract.class_count - 1))
        tail = contract.tail_state(index) == "OVERFLOW"
        remaining = None if tail else float(contract.representative(index)[0])
        event = None if remaining is None else t_ib_a00_from_remaining_minutes(decision_time, remaining)
        return _class_envelope(
            target=target, index=index, conditioning_index=index, contract=contract,
            source_role="MODEL_DRAW", decision_time=decision_time, scalar=remaining,
            event_time_utc=event, lineage=lineage,
        ), index
    contract = pipeline.contracts[target]
    if target == "D_OB":
        if ib_index is None:
            return _class_envelope(target=target, index=None, conditioning_index=None, contract=contract,
                                   source_role="ABSTAIN", decision_time=decision_time, scalar=None, lineage=lineage), None
        zero_logit, q_logits = pipeline.model.d_ob_heads(state, ib_index)
    else:
        if ib_index is None or d_ob_index is None:
            return _class_envelope(target=target, index=None, conditioning_index=None, contract=contract,
                                   source_role="ABSTAIN", decision_time=decision_time, scalar=None, lineage=lineage), None
        zero_logit, q_logits = pipeline.model.d_tx_heads(state, ib_index, d_ob_index)
    if observed is not None:
        value = float(observed)
        index = contract.encode(value)
        return _class_envelope(target=target, index=index, conditioning_index=index,
                               contract=contract, source_role="FACTUAL_OBSERVED", decision_time=decision_time,
                               scalar=None if contract.tail_state(index) == "OVERFLOW" else value,
                               raw_observed_minutes=value, lineage=lineage), index
    zero_probability = float(torch.sigmoid(zero_logit[0]).detach())
    if uniform < zero_probability:
        index = 0
        return _class_envelope(target=target, index=index, conditioning_index=index,
                               contract=contract, source_role="MODEL_DRAW", decision_time=decision_time,
                               scalar=0.0, lineage=lineage), index
    positive_u = (uniform - zero_probability) / max(1.0 - zero_probability, 1e-12)
    quantiles = monotone_positive_quantiles(q_logits)[0].detach()
    if positive_u > contract.q_max:
        index = contract.overflow_index
        return _class_envelope(target=target, index=index, conditioning_index=index,
                               contract=contract, source_role="MODEL_DRAW", decision_time=decision_time,
                               scalar=None, lineage=lineage), index
    value = float(quantile_value(quantiles.unsqueeze(0), contract.quantile_levels, torch.tensor(positive_u),
                                 upper_tail_policy=contract.upper_tail_policy)[0])
    index = contract.encode(value)
    return _class_envelope(target=target, index=index, conditioning_index=index,
                           contract=contract, source_role="MODEL_DRAW", decision_time=decision_time,
                           scalar=value,
                           raw_model_candidate_minutes=(value if contract.tail_state(index) == "OVERFLOW" else None),
                           lineage=lineage), index


def materialize(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    inputs_path, cohort_path, checkpoint_path, support_path, binding_path, refreeze_path = (
        root / INPUTS, root / COHORT, root / CHECKPOINT, root / SUPPORT, root / M1_BINDING, root / REFREEZE
    )
    _require(all(p.is_file() for p in (inputs_path, cohort_path, checkpoint_path, support_path, binding_path, refreeze_path)),
             "M1_V2_SCENARIO_INPUT_ARTIFACT_MISSING")
    inputs, cohort, support, binding, refreeze = map(_load, (inputs_path, cohort_path, support_path, binding_path, refreeze_path))
    _require(inputs["status"] == "BOUND_CURRENT_STAGE_DEVELOPMENT_INFERENCE_INPUTS", "M1_V2_SCENARIO_INPUTS_NOT_BOUND")
    _require(cohort["split"] == "DEVELOPMENT" and cohort["cohort_hash"] == refreeze["new_cohort"]["cohort_hash"], "M1_V2_SCENARIO_COHORT_MISMATCH")
    _require(binding["model_id"] == "M1_V2_GRU_H32" and binding["checkpoint"]["sha256"] == _sha(checkpoint_path), "M1_V2_SCENARIO_CHECKPOINT_BINDING_INVALID")
    _require(support["representation"] == "FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS", "M1_V2_SCENARIO_TAIL_POLICY_INVALID")
    pipeline = M1Pipeline.load(checkpoint_path)
    pipeline.model.eval()
    rows: list[dict[str, Any]] = []
    counts = {target: {"ZERO": 0, "FINITE": 0, "OVERFLOW_TAIL": 0, "ABSTAIN": 0} for target in TARGETS}
    for episode_id, serialized_states in inputs["pre_states_by_episode"].items():
        for serialized in serialized_states:
            pre = PREState.model_validate(serialized)
            node = pre.decision_node
            decision_time = node.decision_time.isoformat()
            encoded = next(item for item in inputs["inference_inputs"] if item["decision_node_id"] == node.decision_node_id)
            values = torch.tensor(encoded["encoded_adaptive_prefix"], dtype=torch.float32)
            lengths = torch.tensor([values.shape[0]], dtype=torch.long)
            static = torch.tensor(encoded["encoded_static_context"], dtype=torch.float32).unsqueeze(0)
            with torch.no_grad():
                _, _, _, state = pipeline._information_state(values.unsqueeze(0), lengths, static_features=static)
            observed = _factual_observed(pre)
            base_lineage = (f"pre:cohort={cohort['cohort_hash']}", f"pre:node={node.decision_node_id}", f"m1:checkpoint={binding['checkpoint']['sha256']}")
            # A single model state is shared across all scenario draws; target uniforms preserve CRN identity.
            for scenario_id in range(SCENARIO_COUNT):
                ib, ib_index = _draw_target(pipeline, state, "T_IB_A00", _uniform(SCENARIO_SEED, episode_id, scenario_id, _rng_target("T_IB_A00"))[0],
                                            ib_index=None, d_ob_index=None, decision_time=decision_time, lineage=base_lineage,
                                            observed=observed.get("T_IB_A00"))
                d_ob, d_ob_index = _draw_target(pipeline, state, "D_OB", _uniform(SCENARIO_SEED, episode_id, scenario_id, "D_OB")[0],
                                                ib_index=ib_index, d_ob_index=None, decision_time=decision_time, lineage=base_lineage,
                                                observed=observed.get("D_OB"))
                d_tx, d_tx_index = _draw_target(pipeline, state, "D_TX", _uniform(SCENARIO_SEED, episode_id, scenario_id, "D_TX")[0],
                                                ib_index=ib_index, d_ob_index=d_ob_index, decision_time=decision_time, lineage=base_lineage,
                                                observed=observed.get("D_TX"))
                targets = (ib, d_ob, d_tx)
                for item in targets:
                    counts[item.target_name][item.class_id if item.class_id in ("ZERO", "OVERFLOW_TAIL", "ABSTAIN") else "FINITE"] += 1
                d_to = None if d_ob.scalar_support_state != "SUPPORTED" or d_tx.scalar_support_state != "SUPPORTED" else float(d_ob.scalar_minutes + d_tx.scalar_minutes)
                joint = JointScenarioEnvelope(
                    episode_id=episode_id, decision_node_id=node.decision_node_id, scenario_id=scenario_id,
                    scenario_weight=1.0 / SCENARIO_COUNT, operational_stage=node.operational_stage.value,
                    decision_time_utc=decision_time, information_cutoff_utc=node.information_cutoff.isoformat(),
                    targets=targets,
                    r_ib_minutes=ib.scalar_minutes, r_ib_support=("SUPPORTED" if ib.scalar_support_state == "SUPPORTED" else "ABSTAIN_TAIL_CLASS"),
                    d_to_minutes=d_to, d_to_support=("SUPPORTED" if d_to is not None else "ABSTAIN_TAIL_CLASS"),
                    scenario_seed_key="|".join(_uniform(SCENARIO_SEED, episode_id, scenario_id, _rng_target(target))[1] for target in TARGETS),
                    lineage=base_lineage + (f"m1:support={_sha(support_path)}",),
                )
                rows.append({
                    "episode_id": episode_id, "decision_node_id": node.decision_node_id,
                    "scenario_id": scenario_id, "scenario_weight": joint.scenario_weight,
                    "operational_stage": node.operational_stage.value,
                    "decision_time_utc": decision_time, "information_cutoff_utc": node.information_cutoff.isoformat(),
                    "T_IB_A00": ib.scalar_minutes, "D_OB": d_ob.scalar_minutes, "D_TX": d_tx.scalar_minutes,
                    "D_TO": d_to, "target_envelopes": [item.model_dump(mode="json") for item in targets],
                    "scenario_seed_key": joint.scenario_seed_key, "lineage": list(joint.lineage),
                })
    payload = {
        "schema_version": "M1_V2_CURRENT_STAGE_TYPED_JOINT_SCENARIO_ARTIFACT_V1",
        "status": "MATERIALIZED_TYPED_JOINT_SCENARIOS",
        "scope": "DATA2_DEVELOPMENT_CURRENT_STAGE_V3_NO_FINAL_TEST",
        "representation": "FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS",
        "scenario_count_per_node": SCENARIO_COUNT, "scenario_seed": SCENARIO_SEED,
        "cohort": {"path": str(COHORT).replace("\\", "/"), "cohort_hash": cohort["cohort_hash"], "node_count": len(cohort["node_ids"])},
        "checkpoint": {"path": str(CHECKPOINT).replace("\\", "/"), "sha256": _sha(checkpoint_path), "model_id": binding["model_id"]},
        "feature_schema_hash": binding["frozen_contracts"]["feature_schema_hash"],
        "support_hash": binding["frozen_contracts"]["support_hash"], "loss_version": binding["frozen_contracts"]["loss_version"],
        "target_support_manifest": {"path": str(SUPPORT).replace("\\", "/"), "sha256": _sha(support_path), "artifact_hash": support["artifact_hash"]},
        "rows": rows, "node_count": len({row["decision_node_id"] for row in rows}), "row_count": len(rows), "class_counts": counts,
        "raw_factual_values_preserved_separately": True, "tail_scalar_extrapolation": False,
        "safety": SAFETY,
    }
    payload["artifact_hash"] = content_id(payload)
    artifact_path = output_root / "M1_V2_CURRENT_STAGE_TYPED_JOINT_SCENARIOS.json"
    manifest = {"schema_version": "M1_V2_CURRENT_STAGE_TYPED_JOINT_SCENARIO_MANIFEST_V1", "status": "M1_CURRENT_STAGE_JOINT_SCENARIO_ARTIFACT_MATERIALIZED", "artifact": str(artifact_path.relative_to(root)).replace("\\", "/"), "artifact_hash": payload["artifact_hash"], "row_count": len(rows), "node_count": len({row["decision_node_id"] for row in rows}), "next_gate": "M2_SEVEN_COMPONENT_CU_ARTIFACT_REQUIRED", "safety": SAFETY}
    _write(artifact_path, payload)
    manifest_path = output_root / "M1_V2_CURRENT_STAGE_TYPED_JOINT_SCENARIO_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"artifact": artifact_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    materialize(root=root, output_root=args.output_root)
    print("M1_V2_CURRENT_STAGE_JOINT_SCENARIO_ARTIFACT_MATERIALIZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
