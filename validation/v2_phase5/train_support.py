"""Phase 5 Train-derived Stage-II support (turnaround, headroom, u_max).

Population: canonical Train rotations of 2019-01..06 built exactly like the
frozen ``DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1`` reference. The corrected
Data Gate A2 turnaround diagnostic is the median authority for the signed-delay
semantics; the V5 registry's ``F_continuity`` scale population is the full-H1
count authority. The A2 diagnostic is produced by a month-streaming scan and
does not include two cross-month episodes that the full-H1 build does include;
that bounded boundary difference is recorded explicitly rather than treated as
a semantic mismatch.

Definitions follow instruction rev2 section 9:

``T^{turn,lb} = Q20(T^turn | Train)`` with Q10/Q30 sensitivity, and
``U_max = floor5(Q90(H^{+,fact} | Train))`` with Q80/Q95 sensitivity.
"""

from __future__ import annotations

from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

import numpy as np

from model.M3.stage1 import ATTENTION_CAPACITY_GRID, NOMINAL_ATTENTION_CAPACITY
from model.M3.stage2 import LAMBDA_GRID, LAMBDA_NOMINAL, action_grid
from model.M3.support import (
    FLOOR_TO_MINUTES,
    HEADROOM_QUANTILE_NOMINAL,
    HEADROOM_QUANTILE_SENSITIVITY,
    QUANTILE_RULE,
    TURNAROUND_QUANTILE_NOMINAL,
    TURNAROUND_QUANTILE_SENSITIVITY,
    build_headroom_summary,
    max_recovery_minutes,
    turnaround_lower_bound_minutes,
)
from model.PRE.episode.builder import build_data2_episode_records
from model.PRE.reference.data2_m2_train_fit import collect_train_rows, ontime_paths
from model.PRE.reference.turnaround_data2 import MAX_GAP_MINUTES
from model.PRE.streaming.data2 import load_timezones
from model.common.errors import ContractError

from .common import (
    PHASE_DIR,
    PROJECT_ROOT,
    TRAIN_MONTHS,
    file_hash,
    read_json,
    write_json,
)


TURNAROUND_REFERENCE_ARTIFACT = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "m1_v2_data_gate_a2"
    / "DATA2_TURNAROUND_REFERENCE_GATE_A2_DIAGNOSTIC.json"
)
TURNAROUND_COUNT_AUTHORITY_ARTIFACT = (
    PROJECT_ROOT / "registries" / "m2_data2_formal_cu_v5.json"
)
SUPERSEDED_TURNAROUND_REFERENCE_ARTIFACT = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "v5_development_freeze"
    / "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json"
)
SEMANTIC_CORRECTION = "BTS_SIGNED_DELAY_SEMANTIC_CORRECTION"
MAX_A2_STREAMING_BOUNDARY_DELTA = 2
SAMPLES_NAME = "TRAIN_TURNAROUND_HEADROOM_SAMPLES.npz"
SUMMARY_NAME = "TRAIN_TURNAROUND_HEADROOM_SUMMARY.json"


def _integer_minutes(values: Sequence[float], label: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    rounded = np.round(array)
    if not np.all(np.isfinite(array)):
        raise ContractError(f"PHASE5_TRAIN_NON_FINITE:{label}")
    if float(np.max(np.abs(array - rounded))) > 1e-6:
        raise ContractError(f"PHASE5_TRAIN_MINUTE_RESOLUTION_EXPECTED:{label}")
    return rounded.astype(np.int32)


def build_rotation_population(
    rows: Sequence[Mapping[str, Any]],
    *,
    max_gap_minutes: int = MAX_GAP_MINUTES,
) -> dict[str, Any]:
    """Build legal Train rotations: observed gate-to-gate turnaround samples."""

    by_id = {str(row["flight_id"]): row for row in rows}
    episodes = build_data2_episode_records(list(rows), max_gap_minutes=max_gap_minutes)
    turnaround_minutes: list[float] = []
    departures: list[float] = []
    scheduled_departures: list[float] = []
    arrivals: list[float] = []
    excluded = 0
    for episode in episodes:
        predecessor = by_id[episode.predecessor_flight_id]
        successor = by_id[episode.successor_flight_id]
        gap = (
            successor["actual_departure_utc"] - predecessor["actual_arrival_utc"]
        ).total_seconds() / 60.0
        if gap <= 0 or gap > max_gap_minutes:
            excluded += 1
            continue
        turnaround_minutes.append(gap)
        departures.append(
            successor["actual_departure_utc"].timestamp() / 60.0
        )
        scheduled_departures.append(
            successor["event_start_time"].timestamp() / 60.0
        )
        arrivals.append(predecessor["actual_arrival_utc"].timestamp() / 60.0)
    if not turnaround_minutes:
        raise ContractError("PHASE5_TRAIN_ROTATION_POPULATION_EMPTY")
    return {
        "episode_count": len(episodes),
        "excluded_rotations": excluded,
        "turnaround_minutes": turnaround_minutes,
        "actual_departure_epoch_minutes": departures,
        "scheduled_departure_epoch_minutes": scheduled_departures,
        "actual_arrival_epoch_minutes": arrivals,
    }


def headroom_minutes(
    population: Mapping[str, Any], *, turnaround_lower_bound: float
) -> list[float]:
    """``H^fact = max(AOBT - max(SOBT, T_IB + T^{turn,lb}), 0)`` per rotation."""

    departures = population["actual_departure_epoch_minutes"]
    scheduled = population["scheduled_departure_epoch_minutes"]
    arrivals = population["actual_arrival_epoch_minutes"]
    values: list[float] = []
    for departure, planned, arrival in zip(
        departures, scheduled, arrivals, strict=True
    ):
        bound = max(float(planned), float(arrival) + float(turnaround_lower_bound))
        values.append(max(float(departure) - bound, 0.0))
    return values


def population_gates(
    *,
    sample_count: int,
    sample_median: float,
    reference_payload: Mapping[str, Any],
    count_authority_payload: Mapping[str, Any],
) -> dict[str, Any]:
    expected_count = int(
        count_authority_payload["train_scale_artifact"]["F_continuity"][
            "population_rows"
        ]
    )
    expected_median = float(reference_payload["global_value_minutes"])
    streaming_count = int(reference_payload["global_sample_count"])
    streaming_delta = int(sample_count) - streaming_count
    semantic_ok = (
        reference_payload.get("semantic_correction") == SEMANTIC_CORRECTION
    )
    boundary_delta_ok = 0 <= streaming_delta <= MAX_A2_STREAMING_BOUNDARY_DELTA
    gates = {
        "expected_sample_count": expected_count,
        "observed_sample_count": int(sample_count),
        "sample_count_match": int(sample_count) == expected_count,
        "expected_median_minutes": expected_median,
        "observed_median_minutes": float(sample_median),
        "median_match": abs(float(sample_median) - expected_median) <= 1e-9,
        "reference_id": reference_payload.get("reference_id"),
        "reference_artifact_hash": reference_payload.get("artifact_hash"),
        "reference_semantic_correction": reference_payload.get(
            "semantic_correction"
        ),
        "semantic_correction_match": semantic_ok,
        "a2_streaming_sample_count": streaming_count,
        "a2_streaming_boundary_delta": streaming_delta,
        "a2_streaming_boundary_delta_rule": (
            "FULL_H1_BUILD_MAY_INCLUDE_UP_TO_2_CROSS_MONTH_EPISODES"
        ),
        "a2_streaming_boundary_delta_consistent": boundary_delta_ok,
        "count_authority_path": str(TURNAROUND_COUNT_AUTHORITY_ARTIFACT),
        "count_authority_field": (
            "train_scale_artifact.F_continuity.population_rows"
        ),
    }
    if (
        not gates["sample_count_match"]
        or not gates["median_match"]
        or not gates["semantic_correction_match"]
        or not gates["a2_streaming_boundary_delta_consistent"]
    ):
        raise ContractError(
            "PHASE5_TRAIN_POPULATION_GATE_FAILED:"
            f"count={gates['observed_sample_count']}/{gates['expected_sample_count']}:"
            f"median={gates['observed_median_minutes']}/{gates['expected_median_minutes']}:"
            f"a2_streaming_delta={gates['a2_streaming_boundary_delta']}:"
            f"semantic={gates['reference_semantic_correction']}"
        )
    return gates


def materialize_train_support(
    *, root: Path = PROJECT_ROOT, output_dir: Path = PHASE_DIR
) -> dict[str, Any]:
    """Materialize Train turnaround/headroom support and its summary artifact."""

    paths = ontime_paths(root, TRAIN_MONTHS)
    zones = load_timezones(root / "data2" / "refs" / "us_airport_timezones.csv")
    rows = collect_train_rows(paths, zones)
    population = build_rotation_population(rows)
    turnaround = population["turnaround_minutes"]

    reference_payload = read_json(TURNAROUND_REFERENCE_ARTIFACT)
    count_authority_payload = read_json(TURNAROUND_COUNT_AUTHORITY_ARTIFACT)
    gates = population_gates(
        sample_count=len(turnaround),
        sample_median=median(turnaround),
        reference_payload=reference_payload,
        count_authority_payload=count_authority_payload,
    )

    turnaround_quantiles = {
        f"q{int(round(quantile * 100)):02d}": turnaround_lower_bound_minutes(
            turnaround, quantile=quantile
        )
        for quantile in (
            *TURNAROUND_QUANTILE_SENSITIVITY,
            TURNAROUND_QUANTILE_NOMINAL,
        )
    }
    nominal_bound = turnaround_quantiles["q20"]
    headroom = headroom_minutes(population, turnaround_lower_bound=nominal_bound)
    positive_headroom = float(np.count_nonzero(np.asarray(headroom) > 0.0))
    headroom_quantiles = {
        f"q{int(round(quantile * 100)):02d}": max_recovery_minutes(
            headroom, quantile=quantile, floor_to_minutes=FLOOR_TO_MINUTES
        )
        for quantile in (
            *HEADROOM_QUANTILE_SENSITIVITY,
            HEADROOM_QUANTILE_NOMINAL,
        )
    }
    raw_headroom_quantiles = {
        f"q{int(round(quantile * 100)):02d}": float(
            np.quantile(
                np.asarray(
                    [
                        float(value)
                        for value in headroom
                        if float(value) > 0.0
                    ]
                ),
                quantile,
            )
        )
        for quantile in (
            *HEADROOM_QUANTILE_SENSITIVITY,
            HEADROOM_QUANTILE_NOMINAL,
        )
    }
    u_max_nominal = headroom_quantiles["q90"]
    summary = build_headroom_summary(
        turnaround_minutes=turnaround,
        headroom_minutes=headroom,
        source_id=_source_id(paths, gates),
        turnaround_quantile=TURNAROUND_QUANTILE_NOMINAL,
        headroom_quantile=HEADROOM_QUANTILE_NOMINAL,
        floor_to_minutes=FLOOR_TO_MINUTES,
    )
    if abs(summary.u_max - u_max_nominal) > 1e-9:
        raise ContractError("PHASE5_U_MAX_SUMMARY_MISMATCH")
    grid = action_grid(summary.u_max, floor_to_minutes=FLOOR_TO_MINUTES)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    samples_path = output_dir / SAMPLES_NAME
    np.savez_compressed(
        samples_path,
        turnaround_minutes=_integer_minutes(turnaround, "turnaround"),
        headroom_nominal_minutes=_integer_minutes(headroom, "headroom"),
    )
    payload: dict[str, Any] = {
        "schema_version": "V2_PHASE5_TRAIN_SUPPORT_V1",
        "status": "PASS",
        "artifact_scope": "TRAIN_PARTITION_SUPPORT_ONLY",
        "train_partition": {
            "start": "2019-01-01",
            "end": "2019-06-30",
            "months": list(TRAIN_MONTHS),
            "fit_period": "2019-H1",
        },
        "source_paths": [str(path) for path in paths],
        "source_hashes": [file_hash(path) for path in paths],
        "population_gates": gates,
        "episode_count": population["episode_count"],
        "excluded_rotations": population["excluded_rotations"],
        "rotation_count": len(turnaround),
        "quantile_rule": QUANTILE_RULE,
        "turnaround": {
            "nominal_quantile": TURNAROUND_QUANTILE_NOMINAL,
            "sensitivity_quantiles": list(TURNAROUND_QUANTILE_SENSITIVITY),
            "quantile_minutes": turnaround_quantiles,
            "median_minutes": float(median(turnaround)),
        },
        "factual_headroom": {
            "definition": (
                "max(actual_departure - max(scheduled_departure, "
                "actual_arrival + turnaround_q20), 0)"
            ),
            "nominal_turnaround_quantile": TURNAROUND_QUANTILE_NOMINAL,
            "positive_count": int(positive_headroom),
            "zero_count": int(len(headroom) - positive_headroom),
            "positive_share": float(positive_headroom) / float(len(headroom)),
            "headroom_summary": summary.model_dump(mode="json"),
        },
        "u_max": {
            "nominal_quantile": HEADROOM_QUANTILE_NOMINAL,
            "sensitivity_quantiles": list(HEADROOM_QUANTILE_SENSITIVITY),
            "nominal_minutes": u_max_nominal,
            "sensitivity_minutes": headroom_quantiles,
            "raw_positive_quantiles_minutes": raw_headroom_quantiles,
            "floor_to_minutes": FLOOR_TO_MINUTES,
        },
        "action_grid": {
            "step_minutes": FLOOR_TO_MINUTES,
            "nominal": list(grid),
            "nominal_size": len(grid),
        },
        "stage1_capacity": {
            "nominal_q": NOMINAL_ATTENTION_CAPACITY,
            "grid": list(ATTENTION_CAPACITY_GRID),
        },
        "stage2_effort": {
            "nominal_lambda": LAMBDA_NOMINAL,
            "grid": list(LAMBDA_GRID),
        },
        "samples_artifact": {
            "path": str(samples_path),
            "hash": file_hash(samples_path),
            "arrays": [
                "turnaround_minutes",
                "headroom_nominal_minutes",
            ],
            "representation_independent": True,
        },
        "turnaround_reference_artifact": str(TURNAROUND_REFERENCE_ARTIFACT),
        "turnaround_reference_source_hash": file_hash(TURNAROUND_REFERENCE_ARTIFACT),
        "turnaround_reference": {
            "path": str(TURNAROUND_REFERENCE_ARTIFACT),
            "artifact_hash": file_hash(TURNAROUND_REFERENCE_ARTIFACT),
            "reference_id": reference_payload.get("reference_id"),
            "semantic_correction": reference_payload.get(
                "semantic_correction"
            ),
            "global_value_minutes": reference_payload.get(
                "global_value_minutes"
            ),
            "global_sample_count": reference_payload.get(
                "global_sample_count"
            ),
            "scope": "STAGE_II_TRAIN_TURNAROUND_LOWER_TAIL_ONLY",
            "superseded_uncorrected_reference": {
                "path": str(SUPERSEDED_TURNAROUND_REFERENCE_ARTIFACT),
                "artifact_hash": file_hash(
                    SUPERSEDED_TURNAROUND_REFERENCE_ARTIFACT
                ),
            },
        },
        "turnaround_count_authority": {
            "path": str(TURNAROUND_COUNT_AUTHORITY_ARTIFACT),
            "artifact_hash": file_hash(TURNAROUND_COUNT_AUTHORITY_ARTIFACT),
            "field": "train_scale_artifact.F_continuity.population_rows",
            "population_rows": gates["expected_sample_count"],
            "role": "FULL_H1_EPISODE_BUILD_COUNT_AUTHORITY",
        },
        "final_test_access_count": 0,
        "no_final_test_family_branch": True,
    }
    payload["artifact_hash"] = _payload_hash(payload)
    write_json(output_dir / SUMMARY_NAME, payload)
    return payload


def _source_id(paths: Sequence[Path], gates: Mapping[str, Any]) -> str:
    return (
        "TRAIN_DATA2_2019_H1:"
        + ",".join(path.name for path in paths)
        + f":n={gates['observed_sample_count']}"
    )


def _payload_hash(payload: Mapping[str, Any]) -> str:
    from model.common.identity import content_id

    return content_id({key: value for key, value in payload.items()})


__all__ = [
    "SAMPLES_NAME",
    "SUMMARY_NAME",
    "SUPERSEDED_TURNAROUND_REFERENCE_ARTIFACT",
    "TURNAROUND_COUNT_AUTHORITY_ARTIFACT",
    "TURNAROUND_REFERENCE_ARTIFACT",
    "build_rotation_population",
    "headroom_minutes",
    "materialize_train_support",
    "population_gates",
]
