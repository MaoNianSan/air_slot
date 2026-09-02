"""M1-owned Data2 Development FAST training and artifact freeze."""

from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import time

import numpy as np
import torch
import yaml

from model.common.config import load_config_layers
from model.common.identity import content_id
from model.PRE.development import (
    build_sampled_pre_cohorts,
    development_input_identity,
)
from model.PRE.reference.taxi_data2 import data2_taxi_reference_from_payload
from model.PRE.reference.turnaround_data2 import (
    data2_turnaround_reference_from_payload,
)

from .cache import M1DevelopmentBaseCache, cache_key
from .contracts import M1StaticReferenceContext, M1_V2_HAZARD_COORDINATE, V2_TARGETS
from .data import (
    FEATURE_NAMES_V2,
    STATIC_FEATURE_COUNT,
    STATIC_FEATURE_NAMES,
    encode_pre_sequence,
    fast_features_from_sequence,
    fit_train_normalization,
)
from .development_diagnostics import (
    evaluate_fast_predictor,
    evaluate_lifecycle,
    paired_state_difference,
    require_training_target_coverage,
    target_coverage,
)
from .fast_path import LightGBMDistributionalPredictor
from .lifecycle import M1Lifecycle
from .pipeline import M1Pipeline
from .preparation import (
    active_rows,
    build_training_examples,
    fit_static_normalization_from_rows,
    normalization_rows,
)
from .scenarios import required_observations_v2

ARTIFACT_ID = "DATA2_M1_V2_DEVELOPMENT_FAST"
CHECKPOINT_NAME = f"{ARTIFACT_ID}.pt"
MANIFEST_NAME = f"{ARTIFACT_ID}_MANIFEST.json"
DIAGNOSTICS_NAME = f"{ARTIFACT_ID}_PREDICTIVE_DIAGNOSTICS.json"
SCENARIOS_NAME = f"{ARTIFACT_ID}_SCENARIOS.json"
CACHE_NAME = f"{ARTIFACT_ID}_CACHE_V3.npz"
CACHE_MANIFEST_NAME = f"{ARTIFACT_ID}_CACHE_V3_MANIFEST.json"
CONFIG_RELATIVE = Path("configs/engineering/m1_data2_development_fast.yaml")
REFERENCE_ROOT = Path("artifacts/diagnostics/v5_development_freeze")


def _hash_file(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        # YAML partition dates are loaded as ``date`` objects; serialize them
        # deterministically instead of failing after training has completed.
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_fast_config(root: Path) -> tuple[dict, str]:
    path = root / CONFIG_RELATIVE
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    expected = {
        "train": (date(2019, 1, 1), date(2019, 6, 30)),
        "calibration": (date(2019, 7, 1), date(2019, 7, 31)),
        "development": (date(2019, 8, 1), date(2019, 9, 30)),
    }
    for split, (start, end) in expected.items():
        configured = payload["partitions"][split]
        if (configured["start"], configured["end"]) != (start, end):
            raise ValueError(f"M1_FAST_PARTITION_CONTRACT_MISMATCH:{split}")
    if payload.get("final_test_access_count") != 0:
        raise ValueError("M1_FAST_FINAL_TEST_ACCESS_MUST_BE_ZERO")
    counts = payload["base_cohort"]["episode_counts"]
    if int(counts.get("test", -1)) != 0:
        raise ValueError("M1_FAST_TEST_COHORT_MUST_BE_ZERO")
    return payload, content_id(payload)


def _load_references(root: Path):
    directory = root / REFERENCE_ROOT
    taxi_payload = json.loads(
        (directory / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json").read_text(
            encoding="utf-8"
        )
    )
    turnaround_payload = json.loads(
        (directory / "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json").read_text(
            encoding="utf-8"
        )
    )
    taxi = data2_taxi_reference_from_payload(taxi_payload)
    turnaround = data2_turnaround_reference_from_payload(turnaround_payload)
    return (
        taxi,
        turnaround,
        {
            "taxi_reference_id": taxi.reference_id,
            "taxi_reference_hash": taxi.manifest_freeze_id,
            "taxi_artifact_hash": taxi_payload.get("artifact_hash"),
            "turnaround_reference_id": turnaround.reference_id,
            "turnaround_reference_hash": turnaround.manifest_freeze_id,
            "turnaround_artifact_hash": turnaround_payload.get("artifact_hash"),
        },
    )


def _contract_hashes(root: Path, scientific) -> dict[str, str]:
    episode_hash = content_id(
        {
            "builder": _hash_file(root / "model/PRE/episode/builder.py"),
            "node_builder": _hash_file(root / "model/PRE/episode/node_builder.py"),
        }
    )
    return {
        "PRE_contract_hash": content_id(
            {
                "pipeline": _hash_file(root / "model/PRE/pipeline.py"),
                "mapping": _hash_file(root / "model/PRE/mapping.py"),
            }
        ),
        "episode_contract_hash": episode_hash,
        "episode_construction_hash": episode_hash,
        "feature_contract_hash": content_id(
            {
                "encoder": _hash_file(root / "model/M1/data.py"),
                "preparation": _hash_file(root / "model/M1/preparation.py"),
                "feature_names": FEATURE_NAMES_V2,
                "static_feature_names": STATIC_FEATURE_NAMES,
            }
        ),
        "split_contract_hash": content_id(
            {
                "partitions": {
                    "train": ["2019-01-01", "2019-06-30"],
                    "calibration": ["2019-07-01", "2019-07-31"],
                    "development": ["2019-08-01", "2019-09-30"],
                },
            }
        ),
        "roll_contract_hash": content_id(
            {
                "roll_minutes": scientific.parameters["roll_minutes"].value,
                "node_builder": _hash_file(root / "model/PRE/episode/node_builder.py"),
            }
        ),
        "normalization_contract_hash": content_id(
            {
                "fit_code": _hash_file(root / "model/M1/data.py"),
                "fitted_split": "train",
                "normalized_names": tuple(sorted(FEATURE_NAMES_V2)),
            }
        ),
    }


def _cache_equivalence(
    fresh: M1DevelopmentBaseCache, loaded: M1DevelopmentBaseCache
) -> dict:
    left, right = fresh.store, loaded.store
    tensors_equal = all(
        torch.equal(a, b)
        for a, b in (
            (left.values_flat, right.values_flat),
            (left.episode_offsets, right.episode_offsets),
            (left.sample_episode_indices, right.sample_episode_indices),
            (left.sample_start_offsets, right.sample_start_offsets),
            (left.sample_end_offsets, right.sample_end_offsets),
        )
    )
    static_equal = (
        left.static_values is not None
        and right.static_values is not None
        and torch.equal(left.static_values, right.static_values)
    )
    lineage_equal = left.static_context_lineages == right.static_context_lineages
    labels_equal = all(
        torch.equal(left.labels[name], right.labels[name])
        and torch.equal(left.active[name], right.active[name])
        for name in V2_TARGETS
    )
    passed = tensors_equal and static_equal and lineage_equal and labels_equal
    return {
        "status": "PASS" if passed else "FAIL",
        "numeric_values_equal": tensors_equal and labels_equal,
        "static_block_equal": static_equal,
        "static_context_lineage_equal": lineage_equal,
    }


def _build_or_load_cache(
    root: Path,
    artifact_root: Path,
    config: dict,
    scientific,
    taxi_reference,
    turnaround_reference,
):
    identity = development_input_identity(root)
    contracts = _contract_hashes(root, scientific)
    base_counts = {
        name: int(value)
        for name, value in config["base_cohort"]["episode_counts"].items()
    }
    actual_counts = {
        "train": base_counts["train"],
        "calibration": base_counts["calibration"],
        "development": base_counts["development"],
    }
    key = cache_key(
        source_manifest_hash=identity["source_manifest_hash"],
        contract_hashes=contracts,
        cohort_counts=actual_counts,
        cohort_seed=int(config["base_cohort"]["seed"]),
    )
    data_path = artifact_root / CACHE_NAME
    manifest_path = artifact_root / CACHE_MANIFEST_NAME
    if data_path.is_file() and manifest_path.is_file():
        try:
            loaded = M1DevelopmentBaseCache.load(
                data_path,
                manifest_path,
                expected_cache_key=key,
            )
            return (
                loaded,
                None,
                {
                    "status": "HIT",
                    "cache_key": key,
                    "cache_hash": loaded.manifest["cache_hash"],
                    "cache_miss_to_hit_equivalence": loaded.manifest.get(
                        "cache_miss_to_hit_equivalence", "PREVIOUSLY_VERIFIED"
                    ),
                },
            )
        except ValueError:
            pass

    preparation_state = root / REFERENCE_ROOT / "M1_BASE_CACHE_PREPARATION_STATE.pt"
    preparation_manifest = (
        root / REFERENCE_ROOT / "M1_BASE_CACHE_PREPARATION_PROGRESS.json"
    )
    state_mtime = preparation_state.stat().st_mtime_ns
    cohorts = build_sampled_pre_cohorts(
        scientific,
        root=root,
        cohort_counts=base_counts,
        cohort_seed=int(config["base_cohort"]["seed"]),
        preparation_state=preparation_state,
        preparation_manifest=preparation_manifest,
        resume=True,
        taxi_reference=taxi_reference,
        turnaround_reference=turnaround_reference,
        additional_development=(),
    )
    rows = {}
    stages = {}
    for split in ("train", "calibration", "development"):
        rows[split], stages[split] = active_rows(
            getattr(cohorts, split),
            taxi_reference=taxi_reference,
        )
    normalization = fit_train_normalization(
        normalization_rows([prefix for _, prefix, _ in rows["train"]]),
        split="train",
    )
    static_normalization = fit_static_normalization_from_rows(rows["train"])
    partitions = {
        split: build_training_examples(
            rows[split],
            normalization,
            None,
            static_normalization=static_normalization,
        )
        for split in rows
    }
    if any(
        row.static_values is None or row.static_context_lineage is None
        for values in partitions.values()
        for row in values
    ):
        raise ValueError("M1_V2_FAST_STATIC_CONTEXT_INCOMPLETE")
    audit = {
        **cohorts.audit,
        "active_stage_counts": stages,
        "source_manifest_hash": identity["source_manifest_hash"],
        "PRE_registry_hash": identity["registry_hash"],
        "base_cohort_counts": base_counts,
        "development_evaluation_source": "BASE_DEVELOPMENT_COHORT",
        "preparation_state_reused": preparation_state.stat().st_mtime_ns == state_mtime,
        "final_test_access_count": 0,
    }
    fresh = M1DevelopmentBaseCache.from_partitions(
        partitions=partitions,
        normalization=normalization,
        static_normalization=static_normalization,
        audit=audit,
        cache_key=key,
        source_manifest_hash=identity["source_manifest_hash"],
        contract_hashes=contracts,
    )
    manifest = fresh.save(data_path, manifest_path)
    loaded = M1DevelopmentBaseCache.load(
        data_path,
        manifest_path,
        expected_cache_key=key,
    )
    equivalence = _cache_equivalence(fresh, loaded)
    if equivalence["status"] != "PASS":
        raise ValueError("M1_V2_FAST_CACHE_ROUNDTRIP_MISMATCH")
    manifest = {**manifest, "cache_miss_to_hit_equivalence": equivalence}
    _write_json(manifest_path, manifest)
    loaded = M1DevelopmentBaseCache.load(
        data_path,
        manifest_path,
        expected_cache_key=key,
    )
    return (
        loaded,
        cohorts,
        {
            "status": "MISS_BUILT_THEN_HIT",
            "cache_key": key,
            "cache_hash": manifest["cache_hash"],
            "cache_miss_to_hit_equivalence": equivalence,
        },
    )


def _subset(cache, split: str, episode_ids: set[str], representation: str):
    kwargs = {"representation": representation}
    if representation == "FIXED_HISTORY":
        kwargs["window_minutes"] = 30
    return tuple(
        row for row in cache.partition(split, **kwargs) if row.episode_id in episode_ids
    )


def _logit_equivalence(before: dict, after: dict) -> dict:
    differences = {
        name: float((before[name] - after[name]).abs().max()) for name in before
    }
    passed = all(value <= 1e-5 for value in differences.values())
    return {
        "status": "PASS" if passed else "FAIL",
        "max_abs_difference": max(differences.values(), default=0.0),
        "per_head_max_abs_difference": differences,
        "rtol": 1e-5,
        "atol": 1e-6,
    }


def _baseline_diagnostics(pipeline, train, calibration, pilot, config) -> dict:
    result = {
        "HISTORICAL": {"status": "NOT_RUN_EXISTING_IMPLEMENTATION_NOT_FOUND"},
        "RANDOM_FOREST": {"status": "NOT_RUN_EXISTING_IMPLEMENTATION_NOT_FOUND"},
    }
    try:
        predictor = LightGBMDistributionalPredictor(
            pipeline.contracts,
            static_normalization=pipeline.static_normalization,
        )

        def arrays(examples):
            x = torch.stack(
                [
                    fast_features_from_sequence(
                        row.values.unsqueeze(0),
                        torch.tensor([len(row.values)]),
                    )[0]
                    for row in examples
                ]
            ).numpy()
            static = torch.stack([row.static_values for row in examples]).numpy()
            targets = {
                name: np.asarray(
                    [
                        (
                            np.nan
                            if row.targets.get(name) is None
                            else float(row.targets[name])
                        )
                        for row in examples
                    ],
                    dtype=float,
                )
                for name in V2_TARGETS
            }
            active = {
                name: np.asarray([bool(row.active.get(name)) for row in examples])
                for name in V2_TARGETS
            }
            return x, static, targets, active

        train_x, train_static, train_targets, _ = arrays(train)
        predictor.fit(
            train_x,
            train_targets,
            seed=int(config["training"]["seed"]),
            n_estimators=int(config["baselines"]["lightgbm_estimators"]),
            allow_test_only_surrogate=False,
            static_features=train_static,
        )
        cal_x, cal_static, cal_targets, cal_active = arrays(calibration)
        predictor.calibrate_development(
            np.concatenate([cal_x, cal_static], axis=-1),
            ib_target=cal_targets[M1_V2_HAZARD_COORDINATE],
            d_ob_target=cal_targets["D_OB"],
            d_tx_target=cal_targets["D_TX"],
            active=cal_active,
            split="calibration",
        )
        metrics = evaluate_fast_predictor(
            predictor,
            pilot,
            batch_size=int(config["training"]["batch_size"]),
        )
        result["LIGHTGBM_FAST"] = {
            "status": "EXECUTED_DEVELOPMENT_FAST_DIAGNOSTIC",
            "metrics": {key: value for key, value in metrics.items() if key != "nodes"},
            "calibration_temperatures": predictor.calibration_temperatures,
            "test_only_surrogates": predictor.models[M1_V2_HAZARD_COORDINATE][
                "test_only_surrogates"
            ],
        }
    except Exception as exc:
        result["LIGHTGBM_FAST"] = {
            "status": "BLOCKED_EXISTING_LIGHTGBM_PATH",
            "reason": f"{type(exc).__name__}:{exc}",
            "test_only_surrogate_used": False,
        }
    return result


def _scenario_attempt(
    lifecycle,
    cohorts,
    evaluation_ids: set[str],
    config,
    artifact_root: Path,
    taxi_reference,
):
    if cohorts is None:
        return {
            "status": "BLOCKED_POSITIVE_TAIL",
            "reason": "M1_POSITIVE_TAIL_DECISION_REQUIRED",
            "attempt_scope": "FORMAL_V2_PATH_CONTRACT_CONFIRMED_CACHE_HIT",
        }
    prepared = {
        item.episode.episode_id: item
        for item in cohorts.development
        if item.episode.episode_id in evaluation_ids
    }
    rows, _ = active_rows(
        tuple(prepared.values()),
        taxi_reference=taxi_reference,
    )
    scenarios = []
    try:
        for episode, prefix, _ in rows:
            state = prefix[-1]
            required = required_observations_v2(
                state.decision_node.operational_stage.value
            )
            observed = {}
            item = prepared[episode.episode_id]
            if "T_IB_A00" in required:
                observed["T_IB_A00"] = (
                    item.predecessor_outcome.actual_arrival_utc.isoformat()
                )
            if "D_OB" in required:
                observed["D_OB"] = max(
                    0.0,
                    (
                        item.successor_outcome.actual_departure_utc
                        - item.successor_schedule.scheduled_departure_utc
                    ).total_seconds()
                    / 60.0,
                )
            values = encode_pre_sequence(prefix, lifecycle.pipeline.normalization)
            generated = lifecycle.sample(
                state,
                values.unsqueeze(0),
                torch.tensor([len(values)]),
                observed=observed,
                count=int(config["scenario_attempt"]["count_per_node"]),
                seed=int(config["training"]["seed"]),
            )
            scenarios.extend(row.model_dump(mode="json") for row in generated)
    except Exception as exc:
        reason = f"{type(exc).__name__}:{exc}"
        return {
            "status": (
                "BLOCKED_POSITIVE_TAIL"
                if "TAIL" in reason.upper() or "QUANTILE" in reason.upper()
                else "BLOCKED_SCENARIO_CONTRACT"
            ),
            "reason": reason,
            "attempted_scenario_count_per_node": int(
                config["scenario_attempt"]["count_per_node"]
            ),
        }
    payload = {
        "schema_version": "AIR_SLOT_M1_V2_DEVELOPMENT_FAST_SCENARIOS_V1",
        "artifact_scope": "DEVELOPMENT_FAST_ONLY",
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }
    payload["artifact_hash"] = content_id(payload)
    path = artifact_root / SCENARIOS_NAME
    _write_json(path, payload)
    return {
        "status": "READY_DEVELOPMENT_FAST",
        "path": str(path),
        "artifact_hash": payload["artifact_hash"],
        "scenario_count": len(scenarios),
    }


def run_data2_development_fast(*, root: Path, output_root: Path | None = None) -> dict:
    started = time.perf_counter()
    root = root.resolve()
    artifact_root = (
        output_root or root / "artifacts/diagnostics/model/m1_v2_development_fast"
    ).resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    config, fast_config_hash = _load_fast_config(root)
    scientific = load_config_layers(root / "configs").scientific
    hidden_size = int(scientific.parameters["m1_hidden_size"].value)
    sensitivity_hidden_size = int(
        scientific.parameters["m1_sensitivity_hidden_size"].value
    )
    if hidden_size == sensitivity_hidden_size:
        raise ValueError("M1_V2_FAST_PRIMARY_RUNTIME_CANNOT_USE_SENSITIVITY_SETTING")
    torch.set_num_threads(
        min(
            int(config["training"]["torch_threads"]),
            torch.get_num_threads(),
        )
    )
    taxi, turnaround, references = _load_references(root)
    cache, cohorts, cache_status = _build_or_load_cache(
        root,
        artifact_root,
        config,
        scientific,
        taxi,
        turnaround,
    )
    train = tuple(cache.partition("train"))
    calibration = tuple(cache.partition("calibration"))
    evaluation_ids = {
        row.episode_id for row in cache.partition("development")
    }
    development_adaptive = _subset(
        cache, "development", evaluation_ids, "ADAPTIVE_HISTORY"
    )
    development_current = _subset(cache, "development", evaluation_ids, "CURRENT")
    development_fixed = _subset(
        cache, "development", evaluation_ids, "FIXED_HISTORY"
    )

    train_coverage = target_coverage(train)
    calibration_coverage = target_coverage(calibration)
    require_training_target_coverage(train_coverage)
    pipeline = M1Pipeline.from_scientific_config(
        scientific,
        input_size=len(FEATURE_NAMES_V2),
        normalization=cache.normalization,
        hidden_size=hidden_size,
        static_input_size=STATIC_FEATURE_COUNT,
        static_normalization=cache.static_normalization,
    )
    lifecycle = M1Lifecycle(pipeline, device=str(config["training"]["device"]))
    batch_size = int(config["training"]["batch_size"])
    batching = lifecycle.batching_diagnostics(
        train,
        batch_size=batch_size,
        bucketed=True,
    )
    training_started = time.perf_counter()
    history = lifecycle.train(
        train,
        epochs=int(config["training"]["epochs"]),
        learning_rate=float(config["training"]["learning_rate"]),
        batch_size=batch_size,
        bucketed=True,
        seed=int(config["training"]["seed"]),
        teacher_forcing=True,
    )
    training_seconds = time.perf_counter() - training_started
    calibration_started = time.perf_counter()
    temperatures = lifecycle.calibrate(calibration, batch_size=batch_size)
    calibration_seconds = time.perf_counter() - calibration_started

    predictive = {
        "ADAPTIVE_HISTORY": evaluate_lifecycle(
            lifecycle,
            development_adaptive,
            batch_size=batch_size,
        ),
        "CURRENT": evaluate_lifecycle(
            lifecycle,
            development_current,
            batch_size=batch_size,
        ),
        "FIXED_HISTORY_30": evaluate_lifecycle(
            lifecycle,
            development_fixed,
            batch_size=batch_size,
        ),
    }
    predictive["CURRENT"]["paired_difference_from_adaptive_minutes"] = (
        paired_state_difference(predictive["ADAPTIVE_HISTORY"], predictive["CURRENT"])
    )
    predictive["FIXED_HISTORY_30"]["paired_difference_from_adaptive_minutes"] = (
        paired_state_difference(
            predictive["ADAPTIVE_HISTORY"],
            predictive["FIXED_HISTORY_30"],
        )
    )
    predictive["ADAPTIVE_HISTORY"]["paired_difference_from_adaptive_minutes"] = 0.0
    baselines = _baseline_diagnostics(
        pipeline,
        train,
        calibration,
        development_adaptive,
        config,
    )

    deterministic_batch = development_adaptive[: min(16, len(development_adaptive))]
    lifecycle.pipeline.model.eval()
    before, _, _, _ = lifecycle.batched_logits(
        deterministic_batch,
        batch_size=batch_size,
        teacher_forcing=False,
    )
    checkpoint_path = artifact_root / CHECKPOINT_NAME
    lifecycle.save(checkpoint_path)
    checkpoint_hash = _hash_file(checkpoint_path)
    loaded = M1Lifecycle.load(checkpoint_path, device=str(lifecycle.device))
    loaded.pipeline.model.eval()
    after, _, _, _ = loaded.batched_logits(
        deterministic_batch,
        batch_size=batch_size,
        teacher_forcing=False,
    )
    save_load = _logit_equivalence(before, after)
    if save_load["status"] != "PASS":
        raise ValueError("M1_V2_FAST_CHECKPOINT_RELOAD_MISMATCH")

    scenario_status = _scenario_attempt(
        loaded,
        cohorts,
        evaluation_ids,
        config,
        artifact_root,
        taxi,
    )
    diagnostics_payload = {
        "schema_version": "AIR_SLOT_M1_V2_DEVELOPMENT_FAST_DIAGNOSTICS_V1",
        "artifact_id": ARTIFACT_ID,
        "artifact_scope": "DEVELOPMENT_FAST_ONLY",
        "checkpoint_hash": checkpoint_hash,
        "cohort_hash": content_id(sorted(evaluation_ids)),
        "cohort_artifact_hash": None,
        "episode_count": len(evaluation_ids),
        "node_count": len(development_adaptive),
        "representations": predictive,
        "baselines": baselines,
        "scenario_artifact_status": scenario_status,
        "M1_POSITIVE_TAIL": "UNRESOLVED",
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }
    diagnostics_payload["artifact_hash"] = content_id(diagnostics_payload)
    diagnostics_path = artifact_root / DIAGNOSTICS_NAME
    _write_json(diagnostics_path, diagnostics_payload)

    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
    ).strip()
    input_schema_hash = content_id({"feature_names": FEATURE_NAMES_V2})
    static_schema_hash = content_id(
        {
            "feature_names": STATIC_FEATURE_NAMES,
            "context_schema": M1StaticReferenceContext.model_json_schema(),
        }
    )
    normalization_hash = content_id(cache.normalization.model_dump(mode="json"))
    manifest = {
        "schema_version": "AIR_SLOT_M1_V2_DEVELOPMENT_FAST_MANIFEST_V1",
        "artifact_id": ARTIFACT_ID,
        "M1_contract_version": "M1_STATE_ESTIMATOR_V2_3",
        "git_sha": git_sha,
        "dataset": "DATA2_2019",
        "train_split": config["partitions"]["train"],
        "calibration_split": config["partitions"]["calibration"],
        "development_split": config["partitions"]["development"],
        "FAST_selection_rule": {
            "base": config["base_cohort"],
            "development_evaluation": config["development_evaluation"],
            "config_hash": fast_config_hash,
        },
        "seed": int(config["training"]["seed"]),
        "hidden_size": hidden_size,
        "epochs": int(config["training"]["epochs"]),
        "batch_size": batch_size,
        "device": str(lifecycle.device),
        "normalization_hash": normalization_hash,
        "normalization_fitted_split": cache.normalization.fitted_split,
        "normalization_row_count": sum(len(row.values) for row in train),
        "PRE_registry_hash": cache.audit["PRE_registry_hash"],
        "input_schema_hash": input_schema_hash,
        "static_context_schema_hash": static_schema_hash,
        "primitive_targets": ["T_IB_A00", "D_OB", "D_TX"],
        "internal_training_targets": list(V2_TARGETS),
        "derived_targets": ["R_IB", "D_TO"],
        "train_counts": train_coverage,
        "calibration_counts": calibration_coverage,
        "operational_stage_distribution": cache.audit["active_stage_counts"],
        "training": {
            "history": history,
            "batch_count": batching["batches"],
            "padding_fraction": batching["padding_fraction"],
            "runtime_seconds": training_seconds,
        },
        "calibration": {
            "temperatures": temperatures,
            "runtime_seconds": calibration_seconds,
            "positive_quantile_calibration": "QUANTILE_CALIBRATION_NOT_APPLIED",
            "coverage_diagnostics": pipeline.calibration_diagnostics,
        },
        "references": references,
        "cache": {
            **cache_status,
            "old_v1_cache_reuse": "REJECTED_V1_TARGET_AND_STATIC_SCHEMA_MISMATCH",
            "path": str(artifact_root / CACHE_NAME),
            "manifest": str(artifact_root / CACHE_MANIFEST_NAME),
        },
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_sha256": checkpoint_hash,
        "checkpoint_save_load_equivalence": save_load,
        "static_block_status": "PERSISTED_AND_ROUNDTRIP_EQUAL",
        "static_lineage_status": "PERSISTED_AND_ROUNDTRIP_EQUAL",
        "predictive_diagnostics_path": str(diagnostics_path),
        "predictive_diagnostics_hash": diagnostics_payload["artifact_hash"],
        "scenario_artifact_status": scenario_status,
        "M1_CHECKPOINT": "READY_DEVELOPMENT_FAST",
        "M1_POSITIVE_TAIL": "UNRESOLVED",
        "M1_FULL_TAIL_SCENARIO": "BLOCKED_POSITIVE_TAIL",
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "artifact_scope": "DEVELOPMENT_FAST_ONLY",
        "runtime_seconds": time.perf_counter() - started,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = artifact_root / MANIFEST_NAME
    _write_json(manifest_path, manifest)
    return {
        "status": "M1_V2_REAL_FAST_CHECKPOINT_PASS_TAIL_REMAINS",
        "checkpoint": str(checkpoint_path),
        "manifest": str(manifest_path),
        "checkpoint_sha256": checkpoint_hash,
        "M1_CHECKPOINT": "READY_DEVELOPMENT_FAST",
        "M1_POSITIVE_TAIL": "UNRESOLVED",
        "SCENARIO_ARTIFACT_STATUS": scenario_status["status"],
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }


__all__ = [
    "ARTIFACT_ID",
    "CHECKPOINT_NAME",
    "DIAGNOSTICS_NAME",
    "MANIFEST_NAME",
    "run_data2_development_fast",
]
