"""Retired pre-P0/P1 bounded real-chain probe.

The former probe encoded the obsolete global four-context gate. It is retained
only as historical source text and must not execute before D1-D5 freeze.
"""
from __future__ import annotations

import json
import time
import tracemalloc
from pathlib import Path

import torch

from model.common.config import load_config_layers
from model.common.errors import ContractError
from model.M1.data import FEATURE_NAMES, encode_pre_sequence
from model.M1.lifecycle import M1Lifecycle
from model.M2.drivers import native_quantities
from model.PRE.feature_registry.loader import load_registry_bundle
from validation.data2_m1_bounded_smoke_v2 import ROOT, _cohort, _source_stats, _states
from model.common.enums import OperationalStage


OUT = ROOT / "outputs" / "real_smoke" / "data2_m1_m4_bounded_chain"


def main() -> None:
    raise ContractError(
        "DATA2_M1_M4_BOUNDED_CHAIN_BLOCKED_PENDING_D1_D5_FREEZE"
    )
    # Historical implementation below is intentionally unreachable until a
    # separately authorized typed real-chain validator replaces it.
    started = time.perf_counter()
    tracemalloc.start()
    checkpoint = ROOT / "outputs" / "real_smoke" / "data2_m1_bounded_smoke_v2" / "m1.pt"
    august_zip = ROOT / "data2" / "_download" / "bts" / "ontime" / "2019" / \
        "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2019_8.zip"
    timezone_ref = ROOT / "data2" / "refs" / "us_airport_timezones.csv"
    raw_before = _source_stats((august_zip, timezone_ref))

    statuses = {
        "PREFLIGHT": "PASS", "M1_REPLAY": "BLOCKED", "M2_INPUT_CONTRACT": "BLOCKED",
        "M2_SCENARIO_PRESERVATION": "BLOCKED", "M2_SUPPORT_HANDLING": "PARTIAL",
        "M3_CANDIDATE_INSTANTIATION": "BLOCKED", "M3_RESPONSE_PROVENANCE": "BLOCKED",
        "A00_IDENTITY": "BLOCKED", "M4_TYPED_BOUNDARY": "BLOCKED",
        "M4_LANE_ASSIGNMENT": "BLOCKED", "M4_OPPORTUNITY": "BLOCKED",
        "M4_RESIDUAL_RISK": "BLOCKED", "M4_FORMAL_RANKING": "BLOCKED",
        "BERNOULLI_BETA_EXECUTION": "NOT_APPLICABLE", "END_TO_END_LINEAGE": "BLOCKED",
        "POSTHOC_ISOLATION": "PASS", "RAW_READ_ONLY": "BLOCKED",
        "NUMERICAL_VALIDITY": "BLOCKED",
    }
    scientific = load_config_layers(ROOT / "configs").scientific
    supports = {name: scientific.parameters[name].value for name in (
        "m1_r_ib_max_finite_minutes", "m1_r_ob_max_finite_minutes",
        "m1_t_tx_max_finite_minutes")}
    if tuple(supports.values()) != (360, 180, 60):
        raise RuntimeError("FROZEN_M1_SUPPORT_REGRESSION")
    registry = load_registry_bundle(ROOT / "registries")
    lifecycle = M1Lifecycle.load(checkpoint)
    pipeline = lifecycle.pipeline
    if pipeline.normalization is None or pipeline.normalization.fitted_split != "train":
        raise RuntimeError("M1_CHECKPOINT_NORMALIZATION_MISMATCH")
    if len(FEATURE_NAMES) != pipeline.model.input_size:
        raise RuntimeError("M1_CHECKPOINT_FEATURE_SCHEMA_MISMATCH")
    if {name: bins.max_finite_minutes for name, bins in pipeline.bins.items()} != {
            "R_IB": 360, "R_OB": 180, "T_TX": 60}:
        raise RuntimeError("M1_CHECKPOINT_SUPPORT_MISMATCH")

    scenario_path = OUT / "m1_scenarios.json"
    episode_summaries = []
    numerical = True
    if scenario_path.is_file():
        all_scenarios = json.loads(scenario_path.read_text(encoding="utf-8"))
        groups = {}
        for row in all_scenarios:
            groups.setdefault((row["episode_id"], row["decision_node_id"]), []).append(row)
        for (episode_id, decision_node_id), rows in groups.items():
            if tuple(row["scenario_id"] for row in rows) != tuple(range(64)):
                raise RuntimeError("M1_SCENARIO_IDENTITY_REGRESSION")
            episode_summaries.append({"episode_id": episode_id,
                "decision_node_id": decision_node_id, "stage": rows[0]["operational_stage"],
                "history_length": None, "scenario_count": len(rows),
                "target_support": {"R_IB": rows[0]["ib_support"],
                                   "R_OB": rows[0]["ob_support"],
                                   "T_TX": rows[0]["tx_support"]},
                "pre_lineage_ids": None})
            for row in rows:
                values = (row["r_ib_minutes"], row["r_ob_minutes"], row["t_tx_minutes"])
                numerical &= all(value is None or torch.isfinite(torch.tensor(value)).item()
                                 for value in values)
    else:
        items = _cohort(8, 8)
        prepared = [(item, *_states(item)) for item in items]
        requested_stages = (OperationalStage.PRE_IB, OperationalStage.POST_IB_PRE_OB,
                            OperationalStage.POST_OB_PRE_TO, OperationalStage.COMPLETED,
                            OperationalStage.PRE_IB)
        selected = []
        used = set()
        for stage in requested_stages:
            match = None
            for item, nodes, states in prepared:
                if item[0].episode_id in used:
                    continue
                candidates = [index for index, node in enumerate(nodes)
                              if node.operational_stage is stage]
                if not candidates:
                    continue
                index = candidates[-1] if stage is OperationalStage.PRE_IB else candidates[0]
                match = (item, nodes[index], states[:index + 1])
                break
            if match is None:
                raise RuntimeError(f"BOUNDED_STAGE_NOT_AVAILABLE:{stage.value}")
            selected.append(match)
            used.add(match[0][0].episode_id)
        all_scenarios = []
        for item, node, states in selected:
            episode, schedule, predecessor_outcome, successor_outcome = item
            values = encode_pre_sequence(states, pipeline.normalization).unsqueeze(0)
            lengths = torch.tensor([len(states)])
            distributions = lifecycle.infer(values, lengths)
            numerical &= all(torch.isfinite(value).all().item()
                             and abs(float(value.sum()) - 1.0) < 1e-5
                             for value in distributions.values())
            observed = {}
            if node.operational_stage in {OperationalStage.POST_IB_PRE_OB,
                                          OperationalStage.POST_OB_PRE_TO,
                                          OperationalStage.COMPLETED}:
                observed["R_IB"] = 0.0
            if node.operational_stage in {OperationalStage.POST_OB_PRE_TO,
                                          OperationalStage.COMPLETED}:
                observed["R_OB"] = max(0.0, (successor_outcome.actual_departure_utc -
                    schedule.scheduled_departure_utc).total_seconds() / 60)
            if node.operational_stage is OperationalStage.COMPLETED:
                observed["T_TX"] = float(successor_outcome.taxi_out_minutes)
            scenarios = lifecycle.sample(states[-1], values, lengths, observed=observed,
                                         count=64, seed=20260813)
            repeated = lifecycle.sample(states[-1], values, lengths, observed=observed,
                                        count=64, seed=20260813)
            if scenarios != repeated or tuple(row.scenario_id for row in scenarios) != tuple(range(64)):
                raise RuntimeError("M1_SCENARIO_IDENTITY_REGRESSION")
            all_scenarios.extend(row.model_dump(mode="json") for row in scenarios)
            episode_summaries.append({"episode_id": episode.episode_id,
                "decision_node_id": node.decision_node_id, "stage": node.operational_stage.value,
                "history_length": len(states), "scenario_count": len(scenarios),
                "target_support": {support.target_name: support.support_state.value
                                   for support in states[-1].target_support},
                "pre_lineage_ids": [entry.source_record_id for entry in states[-1].variable_lineage]})
    statuses["M1_REPLAY"] = "PASS"
    statuses["NUMERICAL_VALIDITY"] = "PASS" if numerical else "FAIL"

    # Do not invent the four formal context values.  The real chain currently
    # has no frozen source for them, so the typed M2 driver must reject input.
    first = all_scenarios[0]
    m2_error = None
    try:
        native_quantities(first, {})
    except ContractError as exc:
        m2_error = str(exc)
    if not m2_error or not m2_error.startswith("M2_CONTEXT_PARAMETER_MISSING:"):
        raise RuntimeError("EXPECTED_M2_FORMAL_GATE_NOT_OBSERVED")

    OUT.mkdir(parents=True, exist_ok=True)
    if not scenario_path.is_file():
        scenario_path.write_text(json.dumps(all_scenarios, indent=2), encoding="utf-8")
    raw_after = _source_stats((august_zip, timezone_ref))
    statuses["RAW_READ_ONLY"] = "PASS" if raw_before == raw_after else "FAIL"
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    metrics = {
        "classification": "FORMAL_CONTRACT_MISMATCH",
        "recommendation": "C",
        "statuses": statuses,
        "preflight": {
            "checkpoint": str(checkpoint.relative_to(ROOT)),
            "checkpoint_bytes": checkpoint.stat().st_size,
            "feature_count": len(FEATURE_NAMES),
            "normalization_split": pipeline.normalization.fitted_split,
            "scientific_supports": supports,
            "registry_manifest_hash": registry.manifest.combined_sha256,
            "synthetic_fixture_fallback_used": False,
        },
        "m1_replay": {
            "episode_count": len(episode_summaries),
            "scenario_count_per_episode": 64,
            "total_scenarios": len(all_scenarios),
            "episodes": episode_summaries,
            "scenario_artifact": str(scenario_path.relative_to(ROOT)),
        },
        "blocking_finding": {
            "stage": "M2_INPUT_CONTRACT",
            "error": m2_error,
            "missing_frozen_parameters": ["turnaround_buffer_minutes", "downstream_exposure",
                "service_threshold_minutes", "taxi_reference_minutes"],
            "formal_valuation_registry": "ABSENT",
            "development_only_factory": "ValuationRegistry.smoke/DEV-1",
            "scientific_semantics_patched": False,
        },
        "downstream_static_findings_not_executed": {
            "action_template_count": 23,
            "action_registry_validated_by_tests": True,
            "non_a00_response_parameters_frozen": False,
            "candidate_deadline_parameters_available_from_current_pre": False,
            "m4_accepts_null_formal_m2_total": False,
        },
        "engineering": {
            "wall_seconds": time.perf_counter() - started,
            "python_peak_tracemalloc_bytes": peak,
            "m1_scenario_artifact_bytes": scenario_path.stat().st_size,
            "m2_artifact_bytes": 0, "m3_artifact_bytes": 0, "m4_artifact_bytes": 0,
        },
        "raw_read_only": raw_before == raw_after,
        "paper_result": False, "experiment": False,
    }
    metrics_path = OUT / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(metrics, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
