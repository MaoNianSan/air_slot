"""M1_SIGNED_DEVELOPMENT_SCENARIOS_V1 — derived downstream artifact generator.

Frozen inputs only:
- M1_SIGNED_OB_DEVELOPMENT_BASE_CACHE_V1 (normalized feature rows + labels)
- M1_SIGNED_WARNING_MODEL_V1 (signed M1 checkpoint, H=32, W=30)
- DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1 (train-frozen taxi reference)
- M1_SIGNED_OB_DEVELOPMENT_BASE_CACHE_V1_PREPARATION_STATE (episode records)

Classification: DERIVED_DOWNSTREAM_ARTIFACT_GENERATION (NOT UPSTREAM_REBUILD).
Never touches Final Test (2019-10..12); FINAL_TEST_ACCESS_COUNT stays 0.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
import subprocess
import time

import pyarrow as pa
import pyarrow.parquet as pq
import torch

from model.M1.cache import M1DevelopmentBaseCache
from model.M1.contracts import STOCHASTIC_TARGETS
from model.M1.data import FEATURE_NAMES
from model.M1.pipeline import M1Pipeline
from model.M1.scenarios import _uniform, ancestral_sample
from model.M1.warning import batched_warning_probability, scenario_uniforms
from model.PRE.reference.taxi_data2 import data2_taxi_reference_from_payload
from model.PRE.streaming.data2 import lightweight_flights, load_timezones, ontime_paths
from model.common.enums import SupportState
from model.common.identity import content_id

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "diagnostics" / "v5_development_freeze"
CACHE_DATA = OUT / "M1_SIGNED_OB_DEVELOPMENT_BASE_CACHE_V1.npz"
CACHE_MANIFEST = OUT / "M1_SIGNED_OB_DEVELOPMENT_BASE_CACHE_V1_MANIFEST.json"
PREPARATION_STATE = OUT / "M1_SIGNED_OB_DEVELOPMENT_BASE_CACHE_V1_PREPARATION_STATE.pt"
CHECKPOINT = OUT / "M1_SIGNED_WARNING_MODEL_V1.pt"
CHECKPOINT_MANIFEST = OUT / "M1_SIGNED_WARNING_MODEL_V1_MANIFEST.json"
TAXI_REFERENCE_PATH = OUT / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json"
PRE_STREAM_MANIFEST = OUT / "PRE_DEVELOPMENT_STREAM_MANIFEST_V2.json"

ARTIFACT_ID = "M1_SIGNED_DEVELOPMENT_SCENARIOS_V1"
SCHEMA_VERSION = "M1_SIGNED_DEVELOPMENT_SCENARIOS_V1"
ARTIFACT_DIR = OUT / ARTIFACT_ID
NODE_PARQUET = ARTIFACT_DIR / "node.parquet"
SCENARIO_PARQUET = ARTIFACT_DIR / "scenario.parquet"
MANIFEST_PATH = OUT / f"{ARTIFACT_ID}_MANIFEST.json"
EQUIVALENCE_PATH = OUT / "EXP234_BATCHED_WARNING_EQUIVALENCE_V1.json"

SCENARIO_COUNT = 250
SCENARIO_SEED = 20260813
HIDDEN_SIZE = 32
WINDOW_MINUTES = 30
WINDOW_NODES = WINDOW_MINUTES // 5 + 1
BATCH_NODES = 256
FLIGHT_KEY_MONTHS = (8, 9)

# Feature-row positions used for schedule recovery and support masks.
SCHEDULE_VALUE_INDEX = FEATURE_NAMES.index("schedule.signed_minutes_to_crs_departure")
SCHEDULE_MISSING_MASK = FEATURE_NAMES.index(
    "schedule.signed_minutes_to_crs_departure.missing_mask"
)
SCHEDULE_STALE_MASK = FEATURE_NAMES.index(
    "schedule.signed_minutes_to_crs_departure.stale_mask"
)
SCHEDULE_FALLBACK_MASK = FEATURE_NAMES.index(
    "schedule.signed_minutes_to_crs_departure.fallback_mask"
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash_file(path: Path) -> str:
    hasher = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def _repository_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _calibration_hash(temperatures: dict) -> str:
    return content_id({name: float(temperatures[name]) for name in STOCHASTIC_TARGETS})


def load_cache() -> M1DevelopmentBaseCache:
    manifest = _read_json(CACHE_MANIFEST)
    cache = M1DevelopmentBaseCache.load(
        CACHE_DATA, CACHE_MANIFEST, expected_cache_key=manifest["cache_key"]
    )
    if cache.manifest.get("final_test_access_count") != 0 \
            or cache.manifest.get("final_test_included") is not False:
        raise RuntimeError("EXP234_CACHE_FINAL_TEST_VIOLATION")
    return cache


def load_episode_records() -> dict[str, object]:
    """Development reservoir EpisodeRecords keyed by episode_id."""
    state = torch.load(PREPARATION_STATE, map_location="cpu", weights_only=False)
    if state.get("next_month") != 10 or state.get("pool_sizes", {}).get("test") != 0:
        raise RuntimeError("EXP234_PREPARATION_STATE_FINAL_TEST_VIOLATION")
    records = state["reservoirs"]["development"]
    if len(records) != 128:
        raise RuntimeError(f"EXP234_DEVELOPMENT_RESERVOIR_COUNT:{len(records)}")
    return {record.episode_id: record for record in records}


def load_taxi_reference():
    payload = _read_json(TAXI_REFERENCE_PATH)
    if payload.get("final_test_access_count") != 0:
        raise RuntimeError("EXP234_TAXI_REFERENCE_FINAL_TEST_VIOLATION")
    return data2_taxi_reference_from_payload(payload), payload


def load_flight_keys() -> tuple[dict[str, dict], dict[str, str]]:
    """Last-resort key resolution from the pinned BTS source (months 08-09).

    The frozen artifacts do not retain the successor destination airport or
    the exact successor scheduled departure; the M2 passenger route key and
    the derived T_OB/T_TO event times require them.  The monthly files are
    hash-verified against PRE_DEVELOPMENT_STREAM_MANIFEST_V2.json before use.
    This is NOT PRE construction and does not rebuild anything.
    """
    sources = _read_json(PRE_STREAM_MANIFEST).get("source_hashes", {})
    paths = ontime_paths(ROOT, FLIGHT_KEY_MONTHS)
    zones = load_timezones(ROOT / "data2" / "refs" / "us_airport_timezones.csv")
    rows_by_id: dict[str, dict] = {}
    used_hashes: dict[str, str] = {}
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        key = next(
            (name for name in sources
             if Path(name.replace("\\", "/")).as_posix() == relative),
            None,
        )
        if key is None:
            raise RuntimeError(f"EXP234_SOURCE_NOT_PINNED:{relative}")
        actual = f"sha256:{sha256(path.read_bytes()).hexdigest()}"
        if actual != sources[key]:
            raise RuntimeError(f"EXP234_SOURCE_HASH_MISMATCH:{relative}")
        used_hashes[key] = actual
        rows, _skipped = lightweight_flights(path, zones, include_warning_fields=True)
        for row in rows:
            rows_by_id[row["flight_id"]] = row
    return rows_by_id, used_hashes


def _stage_from_active(active: dict[str, bool]) -> str:
    pattern = (bool(active["R_IB"]), bool(active["DELTA_OB"]), bool(active["T_TX"]))
    mapping = {
        (True, True, True): "PRE_IB",
        (False, True, True): "POST_IB_PRE_OB",
        (False, False, True): "POST_OB_PRE_TO",
    }
    if pattern not in mapping:
        raise ValueError(f"EXP234_UNEXPECTED_ACTIVE_PATTERN:{pattern}")
    return mapping[pattern]


_OBSERVED_TARGETS_BY_STAGE = {
    "PRE_IB": (),
    "POST_IB_PRE_OB": ("R_IB",),
    "POST_OB_PRE_TO": ("R_IB", "DELTA_OB"),
}


def _exact_observed(record, flight_keys, decision_time, target: str):
    """Recover the exact decision-time observed value from the pinned rows."""
    row = flight_keys.get(record.successor_flight_id)
    if row is None:
        return None
    if target == "R_IB":
        predecessor = flight_keys.get(record.predecessor_flight_id)
        if predecessor is None or predecessor.get("actual_arrival_utc") is None:
            return None
        return max(0.0, (
            predecessor["actual_arrival_utc"] - decision_time
        ).total_seconds() / 60.0)
    if target == "DELTA_OB":
        if row.get("actual_departure_utc") is None or row.get("scheduled_departure_utc") is None:
            return None
        return (
            row["actual_departure_utc"] - row["scheduled_departure_utc"]
        ).total_seconds() / 60.0
    if target == "T_TX":
        value = row.get("taxi_out_minutes")
        return None if value is None else float(value)
    raise ValueError(f"EXP234_UNKNOWN_TARGET:{target}")


def _realized_stage(record, flight_keys, decision_time) -> str:
    """Realized operational stage from the pinned actuals (verification only)."""
    from model.PRE.episode.node_builder import stage_at
    predecessor = flight_keys.get(record.predecessor_flight_id)
    successor = flight_keys.get(record.successor_flight_id)
    if predecessor is None or successor is None:
        return "UNVERIFIABLE"
    pred_in_block = predecessor.get("actual_arrival_utc")
    succ_off_block = successor.get("actual_departure_utc")
    taxi = successor.get("taxi_out_minutes")
    succ_takeoff = None
    if succ_off_block is not None and taxi is not None:
        succ_takeoff = succ_off_block + timedelta(minutes=taxi)
    stage = stage_at(
        decision_time,
        predecessor_in_block=pred_in_block,
        successor_off_block=succ_off_block,
        successor_takeoff=succ_takeoff,
    )
    return stage.value
def _taxi_fields(taxi_reference, airport_id: str) -> dict:
    lookup = taxi_reference.lookup(airport_id)
    state = str(lookup.support_state.value)
    flags = set(getattr(lookup, "quality_flags", ()))
    fallback = next(
        (flag.removeprefix("REFERENCE_LEVEL_") for flag in flags
         if flag.startswith("REFERENCE_LEVEL_")),
        None,
    )
    return {
        "taxi_reference_minutes": None if state != "SUPPORTED" else float(lookup.value),
        "taxi_reference_id": taxi_reference.reference_id,
        "taxi_reference_hash": taxi_reference.manifest_freeze_id,
        "taxi_reference_support_state": state,
        "taxi_reference_fallback_level": fallback,
    }


def _node_metadata(cache, records, pipeline, taxi_reference, flight_keys):
    """Build one metadata row per Development decision node (1824 rows)."""
    store = cache.store
    development_indices = tuple(
        index for index, split in enumerate(store.sample_splits)
        if split == "development"
    )
    rows = []
    recovery_stats = {
        "unobserved": 0,
        "exact_verified": 0,
        "realized_label_verified": 0,
        "realized_label_mismatch": 0,
    }
    missing_flight_keys = 0
    for sample_index in development_indices:
        episode_id = store.sample_episode_ids[sample_index]
        record = records[episode_id]
        node_index = int(store.sample_end_offsets[sample_index]) - 1
        decision_time = record.episode_start_time + timedelta(minutes=5 * node_index)
        if decision_time > record.episode_end_time:
            raise RuntimeError(f"EXP234_NODE_GRID_OUT_OF_WINDOW:{episode_id}")
        active = {
            name: bool(store.active[name][sample_index]) for name in STOCHASTIC_TARGETS
        }
        stage = _stage_from_active(active)
        observed = {}
        recovery = {}
        for name in STOCHASTIC_TARGETS:
            label = int(store.labels[name][sample_index])
            realized = _exact_observed(record, flight_keys, decision_time, name)
            if active[name]:
                # Target unresolved at decision time: scenario draw.  The
                # realized value is a frozen training label (lookahead) and
                # must NOT enter the decision-time observed state; it is only
                # verified against the frozen cache label below.
                observed[name], recovery[name] = None, "UNOBSERVED"
                recovery_stats["unobserved"] += 1
                if realized is not None and pipeline.bins[name].encode(realized) == label:
                    recovery_stats["realized_label_verified"] += 1
                else:
                    recovery_stats["realized_label_mismatch"] += 1
                continue
            # Target already observed at decision time: point-collapse to the
            # exact decision-time value (R_IB -> 0.0 once in-block, DELTA_OB ->
            # signed departure delay, T_TX -> taxi-out), mirroring the frozen
            # Exp1 warning_preparation semantics.
            if realized is None:
                raise RuntimeError(
                    f"EXP234_OBSERVED_TARGET_UNRECOVERABLE:{episode_id}:{name}"
                )
            observed[name], recovery[name] = float(realized), "EXACT_VERIFIED"
            recovery_stats["exact_verified"] += 1
        episode_index = int(store.sample_episode_indices[sample_index])
        episode_start = int(store.episode_offsets[episode_index])
        end = int(store.sample_end_offsets[sample_index])
        features = store.values_flat[episode_start:episode_start + end]
        node_row = features[node_index]
        schedule_missing = bool(node_row[SCHEDULE_MISSING_MASK] > 0.5)
        schedule_stale = bool(node_row[SCHEDULE_STALE_MASK] > 0.5)
        schedule_fallback = bool(node_row[SCHEDULE_FALLBACK_MASK] > 0.5)
        successor_row = flight_keys.get(record.successor_flight_id)
        if successor_row is None:
            missing_flight_keys += 1
        scheduled_ob_utc = None
        if not schedule_missing and successor_row is not None \
                and successor_row.get("scheduled_departure_utc") is not None:
            scheduled_ob_utc = successor_row["scheduled_departure_utc"].isoformat()
        rows.append({
            "sample_index": sample_index,
            "episode_id": episode_id,
            "decision_node_id": store.sample_decision_node_ids[sample_index],
            "episode_date": store.sample_episode_dates[sample_index],
            "decision_time": decision_time.isoformat(),
            "node_index": node_index,
            "operational_stage": stage,
            "observed_r_ib": observed["R_IB"],
            "observed_delta_ob": observed["DELTA_OB"],
            "observed_t_tx": observed["T_TX"],
            "observed_recovery_r_ib": recovery["R_IB"],
            "observed_recovery_delta_ob": recovery["DELTA_OB"],
            "observed_recovery_t_tx": recovery["T_TX"],
            "active_r_ib": active["R_IB"],
            "active_delta_ob": active["DELTA_OB"],
            "active_t_tx": active["T_TX"],
            "connection_airport_id": record.connection_airport_id,
            "successor_destination_airport_id": (
                successor_row.get("destination_airport_id")
                if successor_row is not None else None
            ),
            "scheduled_ob_utc": scheduled_ob_utc,
            "schedule_support_state": "SUPPORTED" if not schedule_missing else "MISSING",
            "schedule_stale": schedule_stale,
            "schedule_fallback": schedule_fallback,
            "episode_start_time": record.episode_start_time.isoformat(),
            "episode_end_time": record.episode_end_time.isoformat(),
            "predecessor_flight_id": record.predecessor_flight_id,
            "successor_flight_id": record.successor_flight_id,
            "aircraft_id": record.aircraft_id,
            **_taxi_fields(taxi_reference, record.connection_airport_id),
        })
    return rows, recovery_stats, missing_flight_keys


def _history_vectors(cache, metadata, pipeline) -> torch.Tensor:
    """Frozen FIXED_HISTORY(W=30) encoding, identical to Exp1 semantics."""
    store = cache.store
    windows = torch.zeros(
        (len(metadata), WINDOW_NODES, store.values_flat.shape[1]),
        dtype=torch.float32,
    )
    lengths = torch.empty(len(metadata), dtype=torch.long)
    for position, row in enumerate(metadata):
        sample_index = row["sample_index"]
        episode_index = int(store.sample_episode_indices[sample_index])
        episode_start = int(store.episode_offsets[episode_index])
        end = int(store.sample_end_offsets[sample_index])
        start = max(0, end - WINDOW_NODES)
        values = store.values_flat[episode_start + start:episode_start + end]
        windows[position, :len(values)] = values
        lengths[position] = len(values)
    pipeline.model.eval()
    with torch.no_grad():
        return pipeline.model.encode_history(windows, lengths)

def _batched_sampling(pipeline, cache, metadata, *, count=SCENARIO_COUNT) -> dict[str, torch.Tensor]:
    """Sample category indices for every Development node x scenario."""
    histories = _history_vectors(cache, metadata, pipeline)
    node_episode_ids = [row["episode_id"] for row in metadata]
    uniforms = scenario_uniforms(node_episode_ids, count=count, seed=SCENARIO_SEED)
    all_indices = {
        name: torch.full((len(metadata), count), -1, dtype=torch.long)
        for name in STOCHASTIC_TARGETS
    }
    for start in range(0, len(metadata), BATCH_NODES):
        stop = min(start + BATCH_NODES, len(metadata))
        result = batched_warning_probability(
            pipeline,
            histories[start:stop],
            episode_ids=node_episode_ids[start:stop],
            observed_r_ib=[row["observed_r_ib"] for row in metadata[start:stop]],
            observed_delta_ob=[row["observed_delta_ob"] for row in metadata[start:stop]],
            observed_t_tx=[row["observed_t_tx"] for row in metadata[start:stop]],
            taxi_reference_minutes=[
                row["taxi_reference_minutes"] for row in metadata[start:stop]
            ],
            count=count,
            seed=SCENARIO_SEED,
            return_indices=True,
            uniforms=uniforms[start:stop],
        )
        if result.sampled_indices is None:
            raise RuntimeError("EXP234_SAMPLED_INDICES_MISSING")
        for name in STOCHASTIC_TARGETS:
            all_indices[name][start:stop] = result.sampled_indices[name]
    return all_indices


def _representative_tables(pipeline, device):
    tables = {}
    for name in STOCHASTIC_TARGETS:
        contract = pipeline.bins[name]
        values, underflow, overflow = zip(*(
            contract.representative(index) for index in range(contract.class_count)
        ))
        tables[name] = (
            torch.tensor(values, dtype=torch.float32),
            torch.tensor(underflow, dtype=torch.bool),
            torch.tensor(overflow, dtype=torch.bool),
        )
    return tables


def _scenario_rows(metadata, indices, pipeline) -> tuple[list[dict], dict]:
    """Assemble compact aligned scenario rows (node x scenario)."""
    tables = _representative_tables(pipeline, "cpu")
    rows = []
    stats = {"d_to_available": 0, "d_to_unavailable": 0}
    delta_contract = pipeline.bins["DELTA_OB"]
    tx_contract = pipeline.bins["T_TX"]
    for node_index, node in enumerate(metadata):
        taxi_supported = node["taxi_reference_support_state"] == "SUPPORTED"
        taxi_minutes = node["taxi_reference_minutes"]
        exact_observed = {
            "R_IB": node["observed_r_ib"],
            "DELTA_OB": node["observed_delta_ob"],
            "T_TX": node["observed_t_tx"],
        }
        for scenario_id in range(SCENARIO_COUNT):
            values = {}
            flags = {}
            for name in STOCHASTIC_TARGETS:
                if exact_observed[name] is not None:
                    # Point-collapsed draw: exact decision-time observed value
                    # (mirrors ancestral_sample; support remains SUPPORTED).
                    values[name], flags[name] = float(exact_observed[name]), (False, False)
                    continue
                index = int(indices[name][node_index, scenario_id])
                if index < 0:
                    values[name], flags[name] = None, (False, False)
                    continue
                value, under, over = tables[name][0][index], tables[name][1][index], tables[name][2][index]
                values[name], flags[name] = float(value), (bool(under), bool(over))
            delta = values["DELTA_OB"]
            tx = values["T_TX"]
            d_to = None
            if delta is not None and tx is not None and taxi_supported and taxi_minutes is not None:
                d_to = max(0.0, delta + tx - float(taxi_minutes))
                stats["d_to_available"] += 1
            else:
                stats["d_to_unavailable"] += 1
            t_ob_utc = None
            t_to_utc = None
            if node["scheduled_ob_utc"] is not None and delta is not None:
                t_ob_utc = (
                    datetime.fromisoformat(node["scheduled_ob_utc"]) + timedelta(minutes=delta)
                ).isoformat()
                if tx is not None:
                    t_to_utc = (
                        datetime.fromisoformat(t_ob_utc) + timedelta(minutes=tx)
                    ).isoformat()
            observed = {
                "R_IB": node["observed_r_ib"] is not None,
                "DELTA_OB": node["observed_delta_ob"] is not None,
                "T_TX": node["observed_t_tx"] is not None,
            }
            supports = {
                "R_IB": "SUPPORTED" if values["R_IB"] is not None else "ABSTAIN",
                "DELTA_OB": "SUPPORTED" if values["DELTA_OB"] is not None else "ABSTAIN",
                "T_TX": "SUPPORTED" if values["T_TX"] is not None else "ABSTAIN",
            }
            rows.append({
                "episode_id": node["episode_id"],
                "decision_node_id": node["decision_node_id"],
                "scenario_id": scenario_id,
                "scenario_weight": 1.0 / SCENARIO_COUNT,
                "operational_stage": node["operational_stage"],
                "r_ib_minutes": values["R_IB"],
                "delta_ob_minutes": values["DELTA_OB"],
                "t_tx_minutes": values["T_TX"],
                "r_ob_minutes": None if delta is None else max(0.0, delta),
                "d_to_minutes": d_to,
                "t_ob_utc": t_ob_utc,
                "t_to_utc": t_to_utc,
                "ib_observed": observed["R_IB"],
                "delta_ob_observed": observed["DELTA_OB"],
                "ib_support": supports["R_IB"],
                "delta_ob_support": supports["DELTA_OB"],
                "tx_support": supports["T_TX"],
                "overflow_ib": flags["R_IB"][1],
                "underflow_delta_ob": flags["DELTA_OB"][0],
                "overflow_delta_ob": flags["DELTA_OB"][1],
                "overflow_tx": flags["T_TX"][1],
                "scenario_seed_key": "|".join(
                    _uniform(SCENARIO_SEED, node["episode_id"], scenario_id, target)[1]
                    for target in STOCHASTIC_TARGETS
                ),
            })
    return rows, stats


def _write_parquet(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table(payload)
    temporary = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, temporary, compression="zstd", use_dictionary=True)
    temporary.replace(path)


def _support_counts(metadata) -> dict:
    """Scenario value availability per target.

    SUPPORTED covers both unresolved targets (frozen conditional draw) and
    already-observed targets (exact point collapse).  ABSTAIN would apply only
    if a frozen target distribution or observed value were unavailable.
    """
    counts = {name: {"SUPPORTED": 0, "ABSTAIN": 0} for name in STOCHASTIC_TARGETS}
    stage_counts = {"PRE_IB": 0, "POST_IB_PRE_OB": 0, "POST_OB_PRE_TO": 0}
    for node in metadata:
        for name in STOCHASTIC_TARGETS:
            counts[name]["SUPPORTED"] += 1
        stage_counts[node["operational_stage"]] += 1
    return {"target_support": counts, "stage_counts": stage_counts,
            "taxi_abstain_nodes": sum(
                1 for node in metadata
                if node["taxi_reference_support_state"] != "SUPPORTED"),
            "schedule_missing_nodes": sum(
                1 for node in metadata if node["schedule_support_state"] == "MISSING")}


def build_artifact(*, equivalence=True) -> dict:
    """Generate the shared M1 scenario artifact and its immutable manifest."""
    started = time.perf_counter()
    cache = load_cache()
    records = load_episode_records()
    pipeline = M1Pipeline.load(CHECKPOINT)
    taxi_reference, taxi_payload = load_taxi_reference()
    flight_keys, used_hashes = load_flight_keys()

    manifest = _read_json(CACHE_MANIFEST)
    checkpoint_payload = _read_json(CHECKPOINT_MANIFEST)
    taxi_payload_parsed = taxi_payload
    metadata, recovery_stats, missing_flight_keys = _node_metadata(
        cache, records, pipeline, taxi_reference, flight_keys
    )
    indices = _batched_sampling(pipeline, cache, metadata)
    scenario_rows, d_to_stats = _scenario_rows(metadata, indices, pipeline)
    support = _support_counts(metadata)

    node_payload = {name: [row[name] for row in metadata] for name in metadata[0]}
    scenario_payload = {name: [row[name] for row in scenario_rows] for name in scenario_rows[0]}
    _write_parquet(NODE_PARQUET, node_payload)
    _write_parquet(SCENARIO_PARQUET, scenario_payload)
    node_hash = _hash_file(NODE_PARQUET)
    scenario_hash = _hash_file(SCENARIO_PARQUET)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "decision_id": "AIR_SLOT_EXP234_SCENARIO_ARTIFACT_AND_LLM_EXECUTION",
        "classification": "DERIVED_DOWNSTREAM_ARTIFACT_GENERATION",
        "source_PRE_artifact": {
            "path": CACHE_DATA.relative_to(ROOT).as_posix(),
            "hash": manifest["cache_hash"],
            "cache_key": manifest["cache_key"],
            "cache_schema_version": manifest["cache_schema_version"],
        },
        "source_M1_checkpoint": {
            "path": CHECKPOINT.relative_to(ROOT).as_posix(),
            "hash": checkpoint_payload["frozen_checkpoint_hash"],
            "hidden_size": HIDDEN_SIZE,
            "training_seed": checkpoint_payload["training_seed"],
        },
        "normalization_artifact": {
            "fitted_split": "train",
            "contract_hash": manifest["contract_hashes"]["normalization_contract_hash"],
            "values": manifest["normalization"]["values"],
        },
        "calibration_artifact": {
            "temperatures": {name: float(value) for name, value in pipeline.temperatures.items()},
            "hash": _calibration_hash(pipeline.temperatures),
        },
        "taxi_reference": {
            "path": TAXI_REFERENCE_PATH.relative_to(ROOT).as_posix(),
            "hash": taxi_payload_parsed["artifact_hash"],
            "reference_id": taxi_reference.reference_id,
            "manifest_freeze_id": taxi_reference.manifest_freeze_id,
        },
        "target_contract": list(STOCHASTIC_TARGETS),
        "derived_values": ["R_OB", "T_OB", "T_TO", "D_TO"],
        "H": HIDDEN_SIZE,
        "W": WINDOW_MINUTES,
        "history_representation": "FIXED_HISTORY",
        "fixed_history_window_minutes": WINDOW_MINUTES,
        "fixed_history_nodes": WINDOW_NODES,
        "scenario_count": SCENARIO_COUNT,
        "scenario_count_provenance": {
            "source": "configs/evaluation/common.yaml",
            "development_budget": [250, 500],
            "selected": SCENARIO_COUNT,
            "selection_rule": (
                "SMALLEST_FROZEN_DEVELOPMENT_BUDGET; "
                "Exp1 EXP1_WARNING_OPERATING_POINT_PROTOCOL_V1 principal_scenarios=250"
            ),
        },
        "scenario_RNG_contract": {
            "stream": "m1_scenario",
            "key": "m1_scenario|{seed}|{episode_id}|{scenario_id}|{target}",
            "targets": list(STOCHASTIC_TARGETS),
            "seed": SCENARIO_SEED,
            "common_random_numbers": True,
            "transform": "SHA256(key)[:16] -> (integer + 0.5) / 2**64",
        },
        "episode_count": len(records),
        "node_count": len(metadata),
        "split": "DEVELOPMENT",
        "cross_split_count": 0,
        "support_counts": support,
        "abstain_counts": {
            "taxi_reference_nodes": support["taxi_abstain_nodes"],
            "schedule_missing_nodes": support["schedule_missing_nodes"],
            "d_to_unavailable_scenarios": d_to_stats["d_to_unavailable"],
        },
        "observed_recovery": {
            **recovery_stats,
            "policy": (
                "UNOBSERVED targets are scenario draws (frozen conditional); "
                "observed targets point-collapse to exact decision-time values "
                "recovered from pinned BTS rows; active-target realized labels "
                "are verified against the frozen cache categories"
            ),
        },
        "flight_key_resolution": {
            "source": "DATA2_RAW_BTS_MONTHS_08_09_LAST_RESORT_KEY_LOOKUP",
            "scope": "successor_destination_airport_id + scheduled_departure_utc only",
            "pinned_hashes": used_hashes,
            "missing_successor_rows": missing_flight_keys,
        },
        "partitions": [
            {"name": "node.parquet", "path": NODE_PARQUET.relative_to(ROOT).as_posix(),
             "rows": len(metadata), "hash": node_hash},
            {"name": "scenario.parquet", "path": SCENARIO_PARQUET.relative_to(ROOT).as_posix(),
             "rows": len(scenario_rows), "hash": scenario_hash},
        ],
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "repository_sha": _repository_sha(),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    payload["artifact_hash"] = content_id(payload)
    _write_json(MANIFEST_PATH, payload)
    if equivalence:
        run_batched_equivalence(pipeline, cache, metadata, taxi_reference, records)
    return payload


def run_batched_equivalence(pipeline, cache, metadata, taxi_reference, records) -> dict:
    """Verify batched sampling is category-identical to ancestral_sample."""
    first_by_stage = {}
    for node in metadata:
        first_by_stage.setdefault(node["operational_stage"], node)
    chosen = tuple(first_by_stage[stage] for stage in ("PRE_IB", "POST_IB_PRE_OB", "POST_OB_PRE_TO"))
    indices = _batched_sampling(pipeline, cache, chosen, count=64)
    category_identity = True
    tail_identity = True
    probability_identity = True
    maximum_difference = 0.0
    for position, node in enumerate(chosen):
        stage = node["operational_stage"]
        observed = {}
        if node["observed_r_ib"] is not None:
            observed["R_IB"] = node["observed_r_ib"]
        if node["observed_delta_ob"] is not None:
            observed["DELTA_OB"] = node["observed_delta_ob"]
        if node["observed_t_tx"] is not None:
            observed["T_TX"] = node["observed_t_tx"]
        histories = _history_vectors(cache, [node], pipeline)
        reference = ancestral_sample(
            pipeline.model, histories, pipeline.bins,
            episode_id=node["episode_id"], decision_node_id=node["decision_node_id"],
            stage=stage, observed=observed, count=64, seed=SCENARIO_SEED,
            target_support={name: "SUPPORTED" for name in STOCHASTIC_TARGETS},
            scheduled_ob_utc=node["scheduled_ob_utc"],
            tx_reference_minutes=node["taxi_reference_minutes"],
            taxi_reference_id=node["taxi_reference_id"],
            taxi_reference_hash=node["taxi_reference_hash"],
            taxi_reference_fallback_level=node["taxi_reference_fallback_level"],
            taxi_reference_support_state=node["taxi_reference_support_state"],
            temperatures=pipeline.temperatures,
        )
        for target in STOCHASTIC_TARGETS:
            expected = torch.tensor([
                pipeline.bins[target].encode(getattr(row, f"{target.lower()}_minutes"))
                for row in reference
            ])
            category_identity &= torch.equal(indices[target][position].cpu(), expected)
        for index, row in enumerate(reference):
            tail_identity &= (
                row.overflow_ib == bool(indices["R_IB"][position, index]
                                         == pipeline.bins["R_IB"].overflow_index)
            )
            tail_identity &= (
                row.underflow_delta_ob == bool(indices["DELTA_OB"][position, index]
                                               == pipeline.bins["DELTA_OB"].underflow_index)
            )
            tail_identity &= (
                row.overflow_delta_ob == bool(indices["DELTA_OB"][position, index]
                                              == pipeline.bins["DELTA_OB"].overflow_index)
            )
            tail_identity &= (
                row.overflow_tx == bool(indices["T_TX"][position, index]
                                        == pipeline.bins["T_TX"].overflow_index)
            )
            maximum_difference = max(
                maximum_difference,
                abs(float(row.d_to_minutes or 0.0) - float(
                    max(0.0, (row.delta_ob_minutes or 0.0) + (row.t_tx_minutes or 0.0)
                        - (node["taxi_reference_minutes"] or 0.0))
                )),
            )
    payload = {
        "schema_version": "EXP234_BATCHED_WARNING_EQUIVALENCE_V1",
        "status": "PASS" if (category_identity and tail_identity) else "FAIL",
        "sampled_category_identity": bool(category_identity),
        "tail_flag_identity": bool(tail_identity),
        "d_to_max_abs_difference": float(maximum_difference),
        "scenario_count": 64,
        "nodes_checked": len(chosen),
        "final_test_access_count": 0,
    }
    _write_json(EQUIVALENCE_PATH, payload)
    if payload["status"] != "PASS":
        raise RuntimeError("EXP234_BATCHED_REFERENCE_EQUIVALENCE_FAILED")
    return payload


def verify_artifact() -> dict:
    """Load the written artifact and verify counts, hashes and final-test guard."""
    manifest = _read_json(MANIFEST_PATH)
    if manifest.get("FINAL_TEST_ACCESS_COUNT") != 0 or manifest.get("PAPER_FULL_RUN"):
        raise RuntimeError("EXP234_ARTIFACT_FINAL_TEST_VIOLATION")
    node = pq.read_table(NODE_PARQUET).to_pydict()
    scenario = pq.read_table(SCENARIO_PARQUET).to_pydict()
    expected_nodes = manifest["node_count"]
    expected_scenarios = expected_nodes * manifest["scenario_count"]
    if len(node["episode_id"]) != expected_nodes or len(scenario["episode_id"]) != expected_scenarios:
        raise RuntimeError("EXP234_ARTIFACT_COUNT_MISMATCH")
    if _hash_file(NODE_PARQUET) != manifest["partitions"][0]["hash"]:
        raise RuntimeError("EXP234_NODE_PARQUET_HASH_MISMATCH")
    if _hash_file(SCENARIO_PARQUET) != manifest["partitions"][1]["hash"]:
        raise RuntimeError("EXP234_SCENARIO_PARQUET_HASH_MISMATCH")
    if len(set(scenario["episode_id"])) != 128 or len(set(node["episode_id"])) != 128:
        raise RuntimeError("EXP234_EPISODE_COUNT_MISMATCH")
    return manifest


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--skip-equivalence", action="store_true")
    args = parser.parse_args(argv)
    if args.verify_only:
        manifest = verify_artifact()
        print(json.dumps({"status": "PASS", "artifact_hash": manifest["artifact_hash"]},
                         sort_keys=True))
        return 0
    payload = build_artifact(equivalence=not args.skip_equivalence)
    print(json.dumps({"status": "PASS", "artifact_hash": payload["artifact_hash"],
                      "nodes": payload["node_count"], "scenarios": payload["scenario_count"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


