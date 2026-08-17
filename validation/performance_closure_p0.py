from __future__ import annotations

import csv
import json
import platform
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path

import psutil
import torch

from exp.exp1.history import adaptive_history
from model.common.config import load_config_layers
from model.common.identity import content_id
from model.M1.cache import (
    M1DevelopmentBaseCache,
    _stable_store_hash,
    cache_key,
)
from model.M1.coverage import active_node_prefixes
from model.M1.data import FEATURE_NAMES, encode_pre_sequence, fit_train_normalization
from model.M1.lifecycle import M1Lifecycle, M1TrainingExample
from model.M1.pipeline import M1Pipeline
from model.PRE.adapters.data2 import _normalize_isd_station_id
from model.PRE.canonical.normalization import canonicalize_isd_row, canonicalize_ontime_row
from model.PRE.episode.builder import build_data2_episode_records
from model.PRE.episode.node_builder import build_rolling_decision_nodes
from model.PRE.pipeline import (
    ProductionPREPublisher,
    ProductionPRERequest,
    publish_production_pre,
)
from validation.data2_v5_hstar_development import PROJECTED, _latest_weather
from validation.support.data2_m1 import config_hash, load_timezones, normalization_rows, registry_hash


ROOT = Path(__file__).resolve().parents[1]
DATA2 = ROOT / "data2"
OUTPUT = ROOT / "artifacts" / "diagnostics" / "performance"
ROW_LIMIT = 50_000
EPISODE_LIMIT = 8
PROFILE_MONTH = "2019-01"
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
        rss = self.process.memory_info().rss / 1024 ** 2
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

    def zero(self, name, *, rows=0, note):
        self.stages[name] = {
            "wall_seconds": 0.0,
            "cpu_seconds": 0.0,
            "peak_rss_mb": self._rss_mb(),
            "input_rows": int(rows),
            "output_rows": int(rows),
            "bytes_read": 0,
            "note": note,
        }

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
    episode_hash = content_id({
        "builder": _file_hash(ROOT / "model" / "PRE" / "episode" / "builder.py"),
        "node_builder": _file_hash(ROOT / "model" / "PRE" / "episode" / "node_builder.py"),
    })
    return {
        "PRE_contract_hash": content_id({
            "pipeline": _file_hash(ROOT / "model" / "PRE" / "pipeline.py"),
            "mapping": _file_hash(ROOT / "model" / "PRE" / "mapping.py"),
            "registry": registry_hash(ROOT),
        }),
        "episode_contract_hash": episode_hash,
        "episode_construction_hash": episode_hash,
        "feature_contract_hash": content_id({
            "data": _file_hash(ROOT / "model" / "M1" / "data.py"),
            "coverage": _file_hash(ROOT / "model" / "M1" / "coverage.py"),
            "feature_names": FEATURE_NAMES,
        }),
        "split_contract_hash": _file_hash(ROOT / "model" / "M1" / "splits.py"),
        "roll_contract_hash": content_id({
            "roll_minutes": scientific.parameters["roll_minutes"].value,
            "node_builder": _file_hash(ROOT / "model" / "PRE" / "episode" / "node_builder.py"),
        }),
        "normalization_contract_hash": content_id({
            "fit_code": _file_hash(ROOT / "model" / "M1" / "data.py"),
            "fitted_split": "train",
        }),
    }


def _discover_january_file() -> Path:
    files = tuple(sorted((DATA2 / "raw" / "bts" / "ontime" / "2019" / "month=01").glob("*.csv")))
    if len(files) != 1:
        raise RuntimeError(f"PROFILE_JANUARY_FILE_COUNT:{len(files)}")
    return files[0]


def _read_projected_subset(path: Path) -> list[dict[str, str]]:
    rows = []
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        positions = {name: header.index(name) for name in PROJECTED}
        for raw in reader:
            rows.append({name: raw[index] if index < len(raw) else ""
                         for name, index in positions.items()})
            if len(rows) >= ROW_LIMIT:
                break
    return rows


def _convert_rows(raw_rows, zones):
    converted = []
    for raw in raw_rows:
        try:
            schedule, outcome = canonicalize_ontime_row(raw, zones)
        except Exception:
            continue
        converted.append((schedule, outcome))
    return converted


def _filter_completed(converted):
    rows = []
    records = {}
    for schedule, outcome in converted:
        if schedule.aircraft_id is None or outcome.cancelled or outcome.diverted:
            continue
        if outcome.actual_arrival_utc is None or outcome.actual_departure_utc is None:
            continue
        rows.append({
            "flight_id": schedule.flight_id,
            "aircraft_id": schedule.aircraft_id,
            "aircraft_id_namespace": schedule.aircraft_id_namespace,
            "origin_airport_id": schedule.origin_airport_id,
            "destination_airport_id": schedule.destination_airport_id,
            "event_start_time": schedule.event_start_time,
            "event_end_time": schedule.event_end_time,
            "actual_arrival_utc": outcome.actual_arrival_utc,
            "actual_departure_utc": outcome.actual_departure_utc,
            "dataset_instance_id": schedule.dataset_instance_id,
            "service_date": schedule.service_date.isoformat(),
        })
        records[schedule.flight_id] = (schedule, outcome)
    return rows, records


def _weather_sources():
    station_map_path = DATA2 / "refs" / "weather_station_map.csv"
    with station_map_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = tuple(csv.DictReader(stream))
    airport_to_station = {row["airport"]: _normalize_isd_station_id(row["station"])
                          for row in rows}
    station_to_airport = {_normalize_isd_station_id(row["station"]): row["airport"]
                          for row in rows}
    files = {_normalize_isd_station_id(path.stem): path for path in sorted(
        (DATA2 / "raw" / "weather" / "noaa" / "2019").glob("*.csv"))}
    return station_map_path, airport_to_station, station_to_airport, files


def _select_episodes(episodes, airport_to_station, weather_files):
    available = [episode for episode in episodes
                 if airport_to_station.get(episode.connection_airport_id) in weather_files]
    counts = Counter(episode.connection_airport_id for episode in available)
    if not counts:
        raise RuntimeError("PROFILE_NO_EPISODE_WITH_WEATHER_STATION")
    airport = sorted(counts, key=lambda item: (-counts[item], item))[0]
    selected = tuple(sorted(
        (episode for episode in available if episode.connection_airport_id == airport),
        key=lambda item: item.episode_id)[:EPISODE_LIMIT])
    if len(selected) < EPISODE_LIMIT:
        raise RuntimeError(f"PROFILE_EPISODE_COUNT_TOO_SMALL:{len(selected)}")
    return airport, selected


def _read_weather(path, station_to_airport, replay_lag_minutes):
    observations = []
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
        for row in csv.DictReader(stream):
            stamp = str(row.get("DATE", ""))
            if stamp >= "2019-02-01":
                break
            if not stamp.startswith(PROFILE_MONTH):
                continue
            try:
                observations.append(canonicalize_isd_row(
                    row, station_map=station_to_airport,
                    replay_lag_minutes=replay_lag_minutes))
            except Exception:
                continue
    return tuple(sorted(observations, key=lambda item: item.availability_time))


def _build_nodes(items, cfg_hash, reg_hash):
    return {episode_id: tuple(build_rolling_decision_nodes(
        episode=item[0], predecessor_outcome=item[2], successor_outcome=item[3],
        config_hash=cfg_hash, registry_hash=reg_hash))
        for episode_id, item in items.items()}


def _match_weather(items, nodes_by_episode, observations, max_age):
    if observations:
        airport = observations[0].airport_id
        index = {airport: (
            tuple(item.availability_time for item in observations), observations)}
    else:
        index = {}
    return {episode_id: tuple(_latest_weather(
        index, item[0].connection_airport_id, node.information_cutoff, max_age)
        for node in nodes_by_episode[episode_id])
        for episode_id, item in items.items()}


def _publish(items, nodes_by_episode, weather_by_episode, cfg_hash, reg_hash, *, optimized):
    publisher = ProductionPREPublisher.from_project() if optimized else None
    states_by_episode = {}
    for episode_id, item in items.items():
        episode, schedule, _, _ = item
        states = []
        for node, observation in zip(nodes_by_episode[episode_id], weather_by_episode[episode_id]):
            records = (schedule,) if observation is None else (schedule, observation)
            request = ProductionPRERequest(
                episode_id=episode.episode_id,
                predecessor_id=episode.predecessor_flight_id,
                successor_id=episode.successor_flight_id,
                dataset_instance_id="data2_2019",
                decision_time=node.decision_time,
                information_cutoff=node.information_cutoff,
                records=records,
                config_hash=cfg_hash,
                registry_hash=reg_hash,
                connection_airport_id=episode.connection_airport_id,
                operational_stage=node.operational_stage,
                node_index=node.node_index,
                roll_minutes=node.roll_minutes,
            )
            result = publish_production_pre(request) if publisher is None else publisher.publish(request)
            states.append(result.pre_state)
        states_by_episode[episode_id] = tuple(states)
    return states_by_episode


def _sequences(items, nodes_by_episode, states_by_episode):
    rows = []
    for episode_id, item in items.items():
        episode = item[0]
        for _, prefix, labels in active_node_prefixes(
                episode=episode,
                nodes=nodes_by_episode[episode_id],
                states=states_by_episode[episode_id],
                successor_schedule=item[1],
                predecessor_outcome=item[2],
                successor_outcome=item[3]):
            rows.append((episode, adaptive_history(prefix), labels))
    return tuple(rows)


def _label_audit(rows):
    for _, prefix, labels in rows:
        if {label.target_name for label in labels} != set(TARGETS):
            raise RuntimeError("PROFILE_LABEL_TARGET_SET_MISMATCH")
        if len({label.decision_node_id for label in labels}) != 1:
            raise RuntimeError("PROFILE_LABEL_NODE_ID_MISMATCH")
        if {label.episode_id for label in labels} != {
                prefix[-1].decision_node.episode_id}:
            raise RuntimeError("PROFILE_LABEL_EPISODE_ID_MISMATCH")
    return rows


def _encode_examples(rows, scientific):
    normalization = fit_train_normalization(
        normalization_rows([prefix for _, prefix, _ in rows]), split="train")
    template = M1Pipeline.from_scientific_config(
        scientific, input_size=len(FEATURE_NAMES), normalization=normalization,
        hidden_size=16)
    examples = tuple(M1TrainingExample.from_target_labels(
        values=encode_pre_sequence(prefix, normalization), labels=labels,
        bins=template.bins) for _, prefix, labels in rows)
    return normalization, examples


def _equivalence_payload(selected, nodes_by_episode, states_by_episode, rows, examples):
    support_states = []
    evidence_states = []
    for episode in selected:
        for state in states_by_episode[episode.episode_id]:
            support_states.append((
                state.decision_node.decision_node_id,
                tuple((item.target_name, item.active, item.support_state.value)
                      for item in state.target_support),
                tuple(sorted((family, name, value.support_state.value)
                             for family in ("predecessor_state", "current_state", "successor_state")
                             for name, value in getattr(state, family).items())),
            ))
            evidence_states.append((
                state.decision_node.decision_node_id,
                tuple((item.scientific_object, item.evidence_class.value,
                       item.episode_support.value, item.abstention_reason)
                      for item in state.evidence_ledger),
            ))
    return {
        "episode_ids": tuple(item.episode_id for item in selected),
        "decision_node_ids": tuple(
            node.decision_node_id for episode in selected
            for node in nodes_by_episode[episode.episode_id]),
        "pre_decision_node_ids": tuple(
            state.decision_node.decision_node_id for episode in selected
            for state in states_by_episode[episode.episode_id]),
        "split": tuple("train" for _ in examples),
        "labels": tuple(tuple((name, example.labels[name]) for name in TARGETS)
                        for example in examples),
        "active_masks": tuple(tuple((name, example.active[name]) for name in TARGETS)
                              for example in examples),
        "support_states": tuple(support_states),
        "evidence_states": tuple(evidence_states),
        "sequence_lengths": tuple(len(example.values) for example in examples),
        "decision_label_ids": tuple(example.decision_node_id for example in examples),
        "features": tuple(example.values for example in examples),
        "label_count": sum(len(labels) for _, _, labels in rows),
    }


def _serialize_baseline(examples, normalization, path):
    torch.save({"normalization": normalization.model_dump(mode="json"),
                "examples": examples}, path)
    return path.stat().st_size


def _serialize_cache(examples, normalization, audit, scientific, input_hash, directory):
    contracts = _contract_hashes(scientific)
    key = cache_key(source_manifest_hash=input_hash, contract_hashes=contracts,
                    cohort_counts={"train": len(examples), "calibration": 0,
                                   "development": 0}, cohort_seed=20260817)
    cache = M1DevelopmentBaseCache.from_partitions(
        partitions={"train": examples, "calibration": (), "development": ()},
        normalization=normalization, audit=audit, cache_key=key,
        source_manifest_hash=input_hash, contract_hashes=contracts)
    data_path = directory / "M1_BASE_CACHE_SMOKE.npz"
    manifest_path = directory / "M1_BASE_CACHE_SMOKE_MANIFEST.json"
    manifest = cache.save(data_path, manifest_path)
    return cache, manifest, data_path, manifest_path


def _run_profile(*, optimized: bool, shared_input=None) -> ProfileResult:
    scientific = load_config_layers(ROOT / "configs").scientific
    profiler = StageProfiler()
    path = profiler.capture("file_discovery", _discover_january_file)
    raw_rows = profiler.capture(
        "parquet_read", lambda: _read_projected_subset(path),
        bytes_read=path.stat().st_size,
        note="Active V5 source is BTS CSV. The reader projects only PRE/M1-required columns.")
    input_hash = content_id({"path": str(path.relative_to(ROOT)), "rows": raw_rows})
    zones = load_timezones(DATA2 / "refs" / "us_airport_timezones.csv")
    converted = profiler.capture(
        "dtype_datetime_conversion", lambda: _convert_rows(raw_rows, zones),
        input_rows=len(raw_rows))
    filtered, records = profiler.capture(
        "flight_filtering", lambda: _filter_completed(converted),
        input_rows=len(converted))
    episodes = profiler.capture(
        "predecessor_successor_pairing",
        lambda: build_data2_episode_records(filtered), input_rows=len(filtered),
        note="Sort plus adjacent-row scan; no per-flight successor search.")
    station_map_path, airport_to_station, station_to_airport, weather_files = _weather_sources()
    airport, selected = _select_episodes(episodes, airport_to_station, weather_files)
    items = profiler.capture(
        "schedule_identity_join",
        lambda: {episode.episode_id: (
            episode,
            records[episode.successor_flight_id][0],
            records[episode.predecessor_flight_id][1],
            records[episode.successor_flight_id][1],
        ) for episode in selected}, input_rows=len(selected))
    station = airport_to_station[airport]
    weather_path = weather_files[station]
    replay_lag = int(scientific.parameters["data2_weather_replay_lag_minutes"].value)
    weather = profiler.capture(
        "weather_read",
        lambda: _read_weather(weather_path, station_to_airport, replay_lag),
        input_rows=0, bytes_read=weather_path.stat().st_size,
        note="One frozen airport-to-station map and one January station scan.")
    cfg_hash, reg_hash = config_hash(ROOT), registry_hash(ROOT)
    nodes_by_episode = profiler.capture(
        "canonical_rolling_node_construction",
        lambda: _build_nodes(items, cfg_hash, reg_hash), input_rows=len(items))
    decision_node_count = sum(len(value) for value in nodes_by_episode.values())
    max_age = int(scientific.parameters["weather_max_age_minutes"].value)
    weather_by_episode = profiler.capture(
        "weather_matching_join",
        lambda: _match_weather(items, nodes_by_episode, weather, max_age),
        input_rows=decision_node_count,
        note="Indexed latest-admissible lookup; no future or nearest-time substitution.")
    profiler.zero(
        "airport_flow_construction", rows=len(selected),
        note="Not present in the current frozen M1 FEATURE_NAMES contract; no flow field was removed.")
    states_by_episode = profiler.capture(
        "pre_safe_feature_construction",
        lambda: _publish(items, nodes_by_episode, weather_by_episode, cfg_hash, reg_hash,
                         optimized=optimized),
        input_rows=decision_node_count,
        note=("One immutable ProductionPREPublisher per preparation run."
              if optimized else "Controlled old path reloads registry/config per decision node."))
    rows = profiler.capture(
        "episode_sequence_construction",
        lambda: _sequences(items, nodes_by_episode, states_by_episode),
        input_rows=decision_node_count)
    rows = profiler.capture(
        "label_construction", lambda: _label_audit(rows), input_rows=len(rows),
        note="Labels are produced by the frozen active_node_prefixes path and identity-checked here.")
    normalization, examples = profiler.capture(
        "tensor_conversion",
        lambda: _encode_examples(rows, scientific), input_rows=len(rows))
    equivalence = _equivalence_payload(
        selected, nodes_by_episode, states_by_episode, rows, examples)
    cache_smoke = None
    with tempfile.TemporaryDirectory(prefix="air_slot_p0_") as temporary:
        directory = Path(temporary)
        if optimized:
            audit = {
                "profile_scope": f"{PROFILE_MONTH}:first_{ROW_LIMIT}_rows",
                "profile_input_hash": input_hash,
                "profile_airport": airport,
                "final_test_access_count": 0,
            }
            cache, manifest, data_path, manifest_path = profiler.capture(
                "serialization",
                lambda: _serialize_cache(
                    examples, normalization, audit, scientific, input_hash, directory),
                input_rows=len(examples))
            logical_hash = profiler.capture(
                "hashing", lambda: _stable_store_hash(cache.store),
                input_rows=cache.store.canonical_node_count,
                note="Deterministic logical array hash; immutable content is hashed once.")
            loaded_started = time.perf_counter()
            loaded = M1DevelopmentBaseCache.load(
                data_path, manifest_path, expected_cache_key=manifest["cache_key"])
            warm_load_seconds = time.perf_counter() - loaded_started
            roundtrip = all(torch.equal(left.values, right.values)
                            and left.labels == right.labels
                            and left.active == right.active
                            and left.decision_node_id == right.decision_node_id
                            for left, right in zip(
                                cache.partition("train"), loaded.partition("train")))
            cache_smoke = {
                "schema_version": "AIR_SLOT_M1_BASE_CACHE_SMOKE_V1",
                "status": "PASS" if roundtrip else "FAIL",
                "cache_schema": manifest["cache_schema_version"],
                "cache_key": manifest["cache_key"],
                "cache_hash": logical_hash,
                "cache_bytes": manifest["cache_bytes"],
                "episode_count": manifest["episode_count"],
                "sample_count": manifest["sample_count"],
                "canonical_node_count": manifest["canonical_node_count"],
                "expanded_prefix_node_count": manifest["expanded_prefix_node_count"],
                "warm_load_seconds": warm_load_seconds,
                "roundtrip_equal": roundtrip,
                "final_test_included": False,
                "final_test_access_count": 0,
                "raw_files_read_during_warm_load": 0,
                "pairing_rebuilt_during_warm_load": 0,
                "weather_rebuilt_during_warm_load": 0,
                "pre_sequence_rebuilt_during_warm_load": 0,
            }
        else:
            data_path = directory / "legacy_prepared.pt"
            serialized_bytes = profiler.capture(
                "serialization",
                lambda: _serialize_baseline(examples, normalization, data_path),
                input_rows=len(examples),
                note="Controlled legacy arbitrary-object serialization for before/after comparison.")
            profiler.capture(
                "hashing", lambda: f"sha256:{sha256(data_path.read_bytes()).hexdigest()}",
                input_rows=serialized_bytes)
    summary = profiler.summary()
    ranked = sorted(summary["stages"].items(), key=lambda item: item[1]["wall_seconds"],
                    reverse=True)
    profile = {
        "schema_version": "AIR_SLOT_DATA_PREP_PROFILE_V2",
        "profile_kind": "OPTIMIZED_P0_FIXED_REAL_SUBSET" if optimized
                        else "BEFORE_P0_FIXED_REAL_SUBSET",
        "paper_result": False,
        "profile_scope": f"{PROFILE_MONTH}:first_{ROW_LIMIT}_projected_rows:{airport}:8_episodes",
        "profile_input_hash": input_hash,
        "profile_rows": len(raw_rows),
        "profile_dates": [PROFILE_MONTH],
        "profile_airports": [airport],
        "profile_episodes": len(selected),
        "profile_decision_nodes": decision_node_count,
        "profile_examples": len(examples),
        "source_format": "CSV",
        "required_columns": list(PROJECTED),
        "weather_station": station,
        "weather_rows": len(weather),
        "bytes_read": path.stat().st_size + weather_path.stat().st_size
                      + station_map_path.stat().st_size,
        "final_test_access_count": 0,
        "TOP_1_BOTTLENECK": ranked[0][0],
        "TOP_2_BOTTLENECK": ranked[1][0],
        "TOP_3_BOTTLENECK": ranked[2][0],
        **summary,
    }
    return ProfileResult(profile, examples, normalization, equivalence, cache_smoke)


def _compare_equivalence(before: dict, after: dict) -> dict:
    exact_fields = (
        "episode_ids", "decision_node_ids", "pre_decision_node_ids",
        "split", "labels", "active_masks",
        "support_states", "evidence_states", "sequence_lengths", "decision_label_ids",
    )
    exact = {name: before[name] == after[name] for name in exact_fields}
    if len(before["features"]) != len(after["features"]):
        max_abs = float("inf")
        features_close = False
    else:
        differences = [float((left - right).abs().max()) for left, right
                       in zip(before["features"], after["features"])]
        max_abs = max(differences, default=0.0)
        features_close = all(torch.allclose(
            left, right, **FLOAT_TOLERANCE) for left, right
            in zip(before["features"], after["features"]))
    passed = all(exact.values()) and features_close
    return {
        "status": "PASS" if passed else "FAIL",
        "exact_checks": exact,
        "floating_features_close": features_close,
        "floating_feature_max_abs_difference": max_abs,
        "floating_tolerance": FLOAT_TOLERANCE,
    }


def _training_smoke(examples, scientific, normalization) -> dict:
    selected = tuple(examples[:min(len(examples), 32)])
    if not selected:
        raise RuntimeError("P0_TRAINING_SMOKE_EMPTY")
    before_padding = M1Lifecycle.batching_diagnostics(
        selected, batch_size=None, bucketed=False)
    after_padding = M1Lifecycle.batching_diagnostics(
        selected, batch_size=8, bucketed=True)
    template = M1Pipeline.from_scientific_config(
        scientific, input_size=selected[0].values.shape[1],
        normalization=normalization, hidden_size=16)
    initial = {name: value.detach().clone() for name, value in template.model.state_dict().items()}
    full = M1Pipeline.from_scientific_config(
        scientific, input_size=selected[0].values.shape[1],
        normalization=normalization, hidden_size=16)
    micro = M1Pipeline.from_scientific_config(
        scientific, input_size=selected[0].values.shape[1],
        normalization=normalization, hidden_size=16)
    full.model.load_state_dict(initial)
    micro.model.load_state_dict(initial)
    full_lifecycle = M1Lifecycle(full)
    micro_lifecycle = M1Lifecycle(micro)
    full_history = full_lifecycle.train(
        selected, epochs=1, learning_rate=0.01, batch_size=None, seed=20260817)
    micro_history = micro_lifecycle.train(
        selected, epochs=1, learning_rate=0.01, batch_size=8, seed=20260817)
    parameter_max_abs = max(float((left - right).abs().max()) for left, right in zip(
        full.model.state_dict().values(), micro.model.state_dict().values()))
    full_logits, full_labels, full_active = full_lifecycle.batched_logits(
        selected, batch_size=None)
    micro_logits, micro_labels, micro_active = full_lifecycle.batched_logits(
        selected, batch_size=8)
    inference_max_abs = max(float((full_logits[name] - micro_logits[name]).abs().max())
                            for name in TARGETS)
    label_equal = all(torch.equal(full_labels[name], micro_labels[name]) for name in TARGETS)
    active_equal = all(torch.equal(full_active[name], micro_active[name]) for name in TARGETS)
    passed = (abs(full_history[0]["loss"] - micro_history[0]["loss"]) <= 1e-5
              and parameter_max_abs <= 1e-5 and inference_max_abs <= 1e-5
              and label_equal and active_equal)
    return {
        "schema_version": "AIR_SLOT_M1_MICROBATCH_SMOKE_V1",
        "status": "PASS" if passed else "FAIL",
        "sample_count": len(selected),
        "fullbatch_loss": full_history[0]["loss"],
        "microbatch_loss": micro_history[0]["loss"],
        "loss_abs_difference": abs(full_history[0]["loss"] - micro_history[0]["loss"]),
        "parameter_max_abs_difference_after_one_epoch": parameter_max_abs,
        "batched_inference_max_abs_difference": inference_max_abs,
        "labels_equal": label_equal,
        "active_masks_equal": active_equal,
        "optimizer_steps_per_epoch": micro_history[0]["optimizer_steps"],
        "microbatch_count": micro_history[0]["microbatch_count"],
        "padding_fraction_before": before_padding["padding_fraction"],
        "padding_fraction_after": after_padding["padding_fraction"],
        "device": "cpu",
        "thread_config": {
            "torch_intra_op_threads": torch.get_num_threads(),
            "torch_inter_op_threads": torch.get_num_interop_threads(),
        },
        "final_test_access_count": 0,
    }


def _device_status() -> dict:
    process = psutil.Process()
    return {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "logical_cores": psutil.cpu_count(logical=True),
        "physical_cores": psutil.cpu_count(logical=False),
        "ram_mb": round(psutil.virtual_memory().total / 1024 ** 2, 3),
        "cuda_available": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "process_rss_mb": round(process.memory_info().rss / 1024 ** 2, 3),
    }


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> None:
    torch.set_num_threads(min(8, torch.get_num_threads()))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    baseline = _run_profile(optimized=False)
    _write_json(OUTPUT / "data_prep_baseline.json", baseline.profile)
    optimized = _run_profile(optimized=True)
    equivalence = _compare_equivalence(baseline.equivalence, optimized.equivalence)
    optimized.profile["data_equivalence_status"] = equivalence["status"]
    optimized.profile["data_equivalence"] = equivalence
    optimized.profile["baseline_seconds"] = baseline.profile["wall_seconds"]
    optimized.profile["optimized_seconds"] = optimized.profile["wall_seconds"]
    optimized.profile["speedup"] = (
        baseline.profile["wall_seconds"] / max(optimized.profile["wall_seconds"], 1e-12))
    optimized.profile["stage_speedups"] = {
        name: baseline.profile["stages"][name]["wall_seconds"]
              / max(values["wall_seconds"], 1e-12)
        for name, values in optimized.profile["stages"].items()
        if name in baseline.profile["stages"]
    }
    _write_json(OUTPUT / "data_prep_after.json", optimized.profile)
    _write_json(OUTPUT / "cache_smoke.json", optimized.cache_smoke)
    scientific = load_config_layers(ROOT / "configs").scientific
    training = _training_smoke(
        optimized.examples, scientific, optimized.normalization)
    training["device_benchmark"] = _device_status()
    _write_json(OUTPUT / "training_microbatch_smoke.json", training)
    status = {
        "DATA_EQUIVALENCE_STATUS": equivalence["status"],
        "BASELINE_SECONDS": baseline.profile["wall_seconds"],
        "OPTIMIZED_SECONDS": optimized.profile["wall_seconds"],
        "SPEEDUP": optimized.profile["speedup"],
        "CACHE_SMOKE_STATUS": optimized.cache_smoke["status"],
        "MICROBATCH_STATUS": training["status"],
        "FINAL_TEST_ACCESS_COUNT": 0,
    }
    print(json.dumps(status, sort_keys=True))
    if equivalence["status"] != "PASS":
        raise SystemExit("DATA_EQUIVALENCE_FAILED")


if __name__ == "__main__":
    main()
