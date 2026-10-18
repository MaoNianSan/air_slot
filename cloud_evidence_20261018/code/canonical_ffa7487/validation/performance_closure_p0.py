from __future__ import annotations

import json
import platform
import statistics
import tempfile
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import psutil
import torch

from model.common.config import load_config_layers
from model.common.identity import content_id
from model.M1.cache import M1DevelopmentBaseCache, _stable_store_hash, cache_key
from model.M1.coverage import active_node_prefixes
from model.M1.data import FEATURE_NAMES, encode_pre_sequence, fit_train_normalization
from model.M1.history import adaptive_history
from model.M1.lifecycle import M1Lifecycle, M1TrainingExample
from model.M1.pipeline import M1Pipeline
from model.M1.preparation import normalization_rows
from model.PRE.profiling import (
    EPISODE_LIMIT,
    PROFILE_MONTH,
    PROJECTED_ONTIME_COLUMNS,
    ROW_LIMIT,
    build_profile_pre_bundle,
)
from model.PRE.streaming.data2 import registry_hash

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "diagnostics" / "performance"
FLOAT_TOLERANCE = {"rtol": 1e-6, "atol": 1e-7}
TARGETS = ("R_IB", "R_OB", "T_TX")


@dataclass(frozen=True)
class ProfileResult:
    profile: dict
    examples: tuple[M1TrainingExample, ...]
    normalization: object
    equivalence: dict
    cache_smoke: dict | None


class StageProfiler:
    def __init__(self):
        self.process = psutil.Process()
        self.stages: dict[str, dict] = {}
        self.started = time.perf_counter()
        self.cpu_started = time.process_time()
        self.peak_rss_mb = self._rss_mb()

    def _rss_mb(self) -> float:
        rss = self.process.memory_info().rss / 1024**2
        self.peak_rss_mb = max(getattr(self, "peak_rss_mb", 0.0), rss)
        return rss

    def capture(self, name, function, *, input_rows=0, bytes_read=0, note=None):
        wall_started = time.perf_counter()
        cpu_started = time.process_time()
        result = function()
        rss = self._rss_mb()
        output_rows = len(result) if hasattr(result, "__len__") else 0
        self.stages[name] = {
            "wall_seconds": time.perf_counter() - wall_started,
            "cpu_seconds": time.process_time() - cpu_started,
            "peak_rss_mb": rss,
            "input_rows": int(input_rows),
            "output_rows": int(output_rows),
            "bytes_read": int(bytes_read),
        }
        if note:
            self.stages[name]["note"] = note
        return result

    def summary(self):
        return {
            "wall_seconds": time.perf_counter() - self.started,
            "cpu_seconds": time.process_time() - self.cpu_started,
            "peak_rss_mb": self.peak_rss_mb,
            "stages": self.stages,
        }


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _contract_hashes(scientific) -> dict[str, str]:
    episode_hash = content_id(
        {
            "builder": _file_hash(ROOT / "model" / "PRE" / "episode" / "builder.py"),
            "node_builder": _file_hash(
                ROOT / "model" / "PRE" / "episode" / "node_builder.py"
            ),
        }
    )
    return {
        "PRE_contract_hash": content_id(
            {
                "pipeline": _file_hash(ROOT / "model" / "PRE" / "pipeline.py"),
                "mapping": _file_hash(ROOT / "model" / "PRE" / "mapping.py"),
                "registry": registry_hash(ROOT),
            }
        ),
        "episode_contract_hash": episode_hash,
        "episode_construction_hash": episode_hash,
        "feature_contract_hash": content_id(
            {
                "data": _file_hash(ROOT / "model" / "M1" / "data.py"),
                "coverage": _file_hash(ROOT / "model" / "M1" / "coverage.py"),
                "feature_names": FEATURE_NAMES,
            }
        ),
        "split_contract_hash": _file_hash(ROOT / "model" / "M1" / "splits.py"),
        "roll_contract_hash": content_id(
            {
                "roll_minutes": scientific.parameters["roll_minutes"].value,
                "node_builder": _file_hash(
                    ROOT / "model" / "PRE" / "episode" / "node_builder.py"
                ),
            }
        ),
        "normalization_contract_hash": content_id(
            {
                "fit_code": _file_hash(ROOT / "model" / "M1" / "data.py"),
                "fitted_split": "train",
            }
        ),
    }


def _sequences(bundle):
    rows = []
    for episode_id, item in bundle.items.items():
        for _, prefix, labels in active_node_prefixes(
            episode=item[0],
            nodes=bundle.nodes_by_episode[episode_id],
            states=bundle.states_by_episode[episode_id],
            successor_schedule=item[1],
            predecessor_outcome=item[2],
            successor_outcome=item[3],
        ):
            rows.append((item[0], adaptive_history(prefix), labels))
    return tuple(rows)


def _label_audit(rows):
    for _, prefix, labels in rows:
        if {label.target_name for label in labels} != set(TARGETS):
            raise RuntimeError("PROFILE_LABEL_TARGET_SET_MISMATCH")
        if len({label.decision_node_id for label in labels}) != 1:
            raise RuntimeError("PROFILE_LABEL_NODE_ID_MISMATCH")
        if {label.episode_id for label in labels} != {
            prefix[-1].decision_node.episode_id
        }:
            raise RuntimeError("PROFILE_LABEL_EPISODE_ID_MISMATCH")
    return rows


def _encode_examples(rows, scientific):
    normalization = fit_train_normalization(
        normalization_rows([prefix for _, prefix, _ in rows]), split="train"
    )
    template = M1Pipeline.from_scientific_config(
        scientific,
        input_size=len(FEATURE_NAMES),
        normalization=normalization,
        hidden_size=16,
    )
    examples = tuple(
        M1TrainingExample.from_target_labels(
            values=encode_pre_sequence(prefix, normalization),
            labels=labels,
            bins=template.bins,
        )
        for _, prefix, labels in rows
    )
    return normalization, examples


def _equivalence_payload(bundle, rows, examples):
    support_states = []
    evidence_states = []
    for episode in bundle.selected:
        for state in bundle.states_by_episode[episode.episode_id]:
            support_states.append(
                (
                    state.decision_node.decision_node_id,
                    tuple(
                        (item.target_name, item.active, item.support_state.value)
                        for item in state.target_support
                    ),
                    tuple(
                        sorted(
                            (family, name, value.support_state.value)
                            for family in (
                                "predecessor_state",
                                "current_state",
                                "successor_state",
                            )
                            for name, value in getattr(state, family).items()
                        )
                    ),
                )
            )
            evidence_states.append(
                (
                    state.decision_node.decision_node_id,
                    tuple(
                        (
                            item.scientific_object,
                            item.evidence_class.value,
                            item.episode_support.value,
                            item.abstention_reason,
                        )
                        for item in state.evidence_ledger
                    ),
                )
            )
    return {
        "episode_ids": tuple(item.episode_id for item in bundle.selected),
        "decision_node_ids": tuple(
            node.decision_node_id
            for episode in bundle.selected
            for node in bundle.nodes_by_episode[episode.episode_id]
        ),
        "pre_decision_node_ids": tuple(
            state.decision_node.decision_node_id
            for episode in bundle.selected
            for state in bundle.states_by_episode[episode.episode_id]
        ),
        "split": tuple("train" for _ in examples),
        "labels": tuple(
            tuple((name, example.labels[name]) for name in TARGETS)
            for example in examples
        ),
        "active_masks": tuple(
            tuple((name, example.active[name]) for name in TARGETS)
            for example in examples
        ),
        "support_states": tuple(support_states),
        "evidence_states": tuple(evidence_states),
        "sequence_lengths": tuple(len(example.values) for example in examples),
        "decision_label_ids": tuple(example.decision_node_id for example in examples),
        "features": tuple(example.values for example in examples),
        "label_count": sum(len(labels) for _, _, labels in rows),
    }


def _serialize_baseline(examples, normalization, path):
    torch.save(
        {"normalization": normalization.model_dump(mode="json"), "examples": examples},
        path,
    )
    return path.stat().st_size


def _serialize_cache(examples, normalization, audit, scientific, input_hash, directory):
    contracts = _contract_hashes(scientific)
    key = cache_key(
        source_manifest_hash=input_hash,
        contract_hashes=contracts,
        cohort_counts={"train": len(examples), "calibration": 0, "development": 0},
        cohort_seed=20260817,
    )
    cache = M1DevelopmentBaseCache.from_partitions(
        partitions={"train": examples, "calibration": (), "development": ()},
        normalization=normalization,
        audit=audit,
        cache_key=key,
        source_manifest_hash=input_hash,
        contract_hashes=contracts,
    )
    data_path = directory / "M1_BASE_CACHE_SMOKE.npz"
    manifest_path = directory / "M1_BASE_CACHE_SMOKE_MANIFEST.json"
    manifest = cache.save(data_path, manifest_path)
    return cache, manifest, data_path, manifest_path


def _run_profile(*, optimized: bool) -> ProfileResult:
    scientific = load_config_layers(ROOT / "configs").scientific
    profiler = StageProfiler()
    bundle = build_profile_pre_bundle(
        scientific, root=ROOT, profiler=profiler, optimized=optimized
    )
    rows = profiler.capture(
        "episode_sequence_construction",
        lambda: _sequences(bundle),
        input_rows=bundle.decision_node_count,
    )
    rows = profiler.capture(
        "label_construction", lambda: _label_audit(rows), input_rows=len(rows)
    )
    normalization, examples = profiler.capture(
        "tensor_conversion",
        lambda: _encode_examples(rows, scientific),
        input_rows=len(rows),
    )
    equivalence = _equivalence_payload(bundle, rows, examples)
    cache_smoke = None
    with tempfile.TemporaryDirectory(prefix="air_slot_p0_") as temporary:
        directory = Path(temporary)
        if optimized:
            audit = {
                "profile_scope": f"{PROFILE_MONTH}:first_{ROW_LIMIT}_rows",
                "profile_input_hash": bundle.profile_input_hash,
                "profile_airport": bundle.airport,
                "final_test_access_count": 0,
            }
            cache, manifest, data_path, manifest_path = profiler.capture(
                "serialization",
                lambda: _serialize_cache(
                    examples,
                    normalization,
                    audit,
                    scientific,
                    bundle.profile_input_hash,
                    directory,
                ),
                input_rows=len(examples),
            )
            logical_hash = profiler.capture(
                "hashing",
                lambda: _stable_store_hash(cache.store),
                input_rows=len(examples),
            )
            loaded = M1DevelopmentBaseCache.load(
                data_path, manifest_path, expected_cache_key=manifest["cache_key"]
            )
            roundtrip = all(
                torch.equal(left.values, right.values)
                and left.labels == right.labels
                and left.active == right.active
                and left.decision_node_id == right.decision_node_id
                for left, right in zip(
                    cache.partition("train"), loaded.partition("train")
                )
            )
            cache_smoke = {
                "schema_version": "AIR_SLOT_M1_BASE_CACHE_SMOKE_V1",
                "status": "PASS" if roundtrip else "FAIL",
                "cache_key": manifest["cache_key"],
                "cache_hash": logical_hash,
                "roundtrip_equal": roundtrip,
                "final_test_access_count": 0,
            }
        else:
            data_path = directory / "legacy_prepared.pt"
            profiler.capture(
                "serialization",
                lambda: _serialize_baseline(examples, normalization, data_path),
                input_rows=len(examples),
            )
    summary = profiler.summary()
    ranked = sorted(
        summary["stages"].items(),
        key=lambda item: item[1]["wall_seconds"],
        reverse=True,
    )
    profile = {
        "schema_version": "AIR_SLOT_DATA_PREP_PROFILE_V3",
        "profile_kind": (
            "OPTIMIZED_P0_FIXED_REAL_SUBSET"
            if optimized
            else "BEFORE_P0_FIXED_REAL_SUBSET"
        ),
        "paper_result": False,
        "profile_scope": f"{PROFILE_MONTH}:first_{ROW_LIMIT}_projected_rows:{bundle.airport}:{EPISODE_LIMIT}_episodes",
        "profile_input_hash": bundle.profile_input_hash,
        "profile_rows": bundle.input_rows,
        "profile_dates": [PROFILE_MONTH],
        "profile_airports": [bundle.airport],
        "profile_episodes": len(bundle.selected),
        "profile_decision_nodes": bundle.decision_node_count,
        "profile_examples": len(examples),
        "source_format": "CSV",
        "required_columns": list(PROJECTED_ONTIME_COLUMNS),
        "weather_station": bundle.station,
        "weather_rows": bundle.weather_rows,
        "bytes_read": bundle.bytes_read,
        "final_test_access_count": 0,
        "TOP_1_BOTTLENECK": ranked[0][0],
        "TOP_2_BOTTLENECK": ranked[1][0],
        "TOP_3_BOTTLENECK": ranked[2][0],
        **summary,
    }
    return ProfileResult(profile, examples, normalization, equivalence, cache_smoke)


def _compare_equivalence(before: dict, after: dict) -> dict:
    exact_fields = (
        "episode_ids",
        "decision_node_ids",
        "pre_decision_node_ids",
        "split",
        "labels",
        "active_masks",
        "support_states",
        "evidence_states",
        "sequence_lengths",
        "decision_label_ids",
    )
    exact = {name: before[name] == after[name] for name in exact_fields}
    differences = [
        float((left - right).abs().max())
        for left, right in zip(before["features"], after["features"])
    ]
    features_close = len(before["features"]) == len(after["features"]) and all(
        torch.allclose(left, right, **FLOAT_TOLERANCE)
        for left, right in zip(before["features"], after["features"])
    )
    passed = all(exact.values()) and features_close
    return {
        "status": "PASS" if passed else "FAIL",
        "exact_checks": exact,
        "floating_features_close": features_close,
        "floating_feature_max_abs_difference": max(differences, default=0.0),
        "floating_tolerance": FLOAT_TOLERANCE,
    }


def _training_smoke(examples, scientific, normalization) -> dict:
    selected = tuple(examples[: min(len(examples), 32)])
    if not selected:
        raise RuntimeError("P0_TRAINING_SMOKE_EMPTY")
    template = M1Pipeline.from_scientific_config(
        scientific,
        input_size=selected[0].values.shape[1],
        normalization=normalization,
        hidden_size=16,
    )
    initial = {
        name: value.detach().clone()
        for name, value in template.model.state_dict().items()
    }
    full = M1Pipeline.from_scientific_config(
        scientific,
        input_size=selected[0].values.shape[1],
        normalization=normalization,
        hidden_size=16,
    )
    micro = M1Pipeline.from_scientific_config(
        scientific,
        input_size=selected[0].values.shape[1],
        normalization=normalization,
        hidden_size=16,
    )
    full.model.load_state_dict(initial)
    micro.model.load_state_dict(initial)
    full_lifecycle, micro_lifecycle = M1Lifecycle(full), M1Lifecycle(micro)
    full_history = full_lifecycle.train(
        selected, epochs=1, learning_rate=0.01, batch_size=None, seed=20260817
    )
    micro_history = micro_lifecycle.train(
        selected, epochs=1, learning_rate=0.01, batch_size=8, seed=20260817
    )
    parameter_max_abs = max(
        float((left - right).abs().max())
        for left, right in zip(
            full.model.state_dict().values(), micro.model.state_dict().values()
        )
    )
    passed = (
        abs(full_history[0]["loss"] - micro_history[0]["loss"]) <= 1e-5
        and parameter_max_abs <= 1e-5
    )
    return {
        "schema_version": "AIR_SLOT_M1_MICROBATCH_SMOKE_V1",
        "status": "PASS" if passed else "FAIL",
        "sample_count": len(selected),
        "fullbatch_loss": full_history[0]["loss"],
        "microbatch_loss": micro_history[0]["loss"],
        "parameter_max_abs_difference_after_one_epoch": parameter_max_abs,
        "final_test_access_count": 0,
    }


def _device_status() -> dict:
    return {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "logical_cores": psutil.cpu_count(logical=True),
        "physical_cores": psutil.cpu_count(logical=False),
        "ram_mb": round(psutil.virtual_memory().total / 1024**2, 3),
        "cuda_available": torch.cuda.is_available(),
    }


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> None:
    torch.set_num_threads(min(8, torch.get_num_threads()))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    baseline = _run_profile(optimized=False)
    optimized = _run_profile(optimized=True)
    equivalence = _compare_equivalence(baseline.equivalence, optimized.equivalence)
    optimized.profile["data_equivalence"] = equivalence
    optimized.profile["speedup"] = baseline.profile["wall_seconds"] / max(
        optimized.profile["wall_seconds"], 1e-12
    )
    _write_json(OUTPUT / "data_prep_baseline.json", baseline.profile)
    _write_json(OUTPUT / "data_prep_after.json", optimized.profile)
    _write_json(OUTPUT / "cache_smoke.json", optimized.cache_smoke)
    scientific = load_config_layers(ROOT / "configs").scientific
    training = _training_smoke(optimized.examples, scientific, optimized.normalization)
    training["device_benchmark"] = _device_status()
    _write_json(OUTPUT / "training_microbatch_smoke.json", training)
    print(
        json.dumps(
            {
                "DATA_EQUIVALENCE_STATUS": equivalence["status"],
                "CACHE_SMOKE_STATUS": optimized.cache_smoke["status"],
                "MICROBATCH_STATUS": training["status"],
                "FINAL_TEST_ACCESS_COUNT": 0,
            },
            sort_keys=True,
        )
    )
    if equivalence["status"] != "PASS":
        raise SystemExit("DATA_EQUIVALENCE_FAILED")


if __name__ == "__main__":
    main()
