"""Statistics and temporal diagnostics for M1 V2 Data Gate A."""

from __future__ import annotations

from collections import Counter
import random

import torch

from model.M1.contracts import V2_TARGETS, static_reference_context_from_pre
from model.M1.data import (
    FEATURE_NAMES_V2,
    V2_WEATHER_FIELDS,
    encode_pre_sequence,
    fast_features_from_sequence,
)
from model.M1.preparation import normalization_rows
from model.M1.static_features import static_reference_features_from_pre

SPLITS = ("train", "calibration", "development")
LABEL_SUPPORT = {
    "T_IB_REMAINING_HAZARD": 360.0,
    "D_OB": 180.0,
    "D_TX": 60.0,
}


def _mask_name(feature: str) -> str | None:
    if (
        feature.startswith("weather.")
        and not feature.startswith(("weather.observation_age",))
        and not feature.endswith((".sin", ".cos", "_mask"))
    ):
        return f"{feature}.missing_mask"
    if feature == "schedule.signed_minutes_to_crs_departure":
        return f"{feature}.missing_mask"
    if feature.startswith("state.") and not feature.endswith("_mask"):
        return f"{feature}.missing_mask"
    if feature.startswith(("delta.weather.", "ar.weather.")):
        field = feature.split(".", 2)[2]
        return f"weather.{field}.missing_mask"
    return None


def numeric_statistics(matrices: dict[str, torch.Tensor]) -> dict:
    train = matrices["train"].to(torch.float64)
    mask_indices = {name: index for index, name in enumerate(FEATURE_NAMES_V2)}
    train_bounds = []
    for index, name in enumerate(FEATURE_NAMES_V2):
        column = train[:, index]
        mask = _mask_name(name)
        missing = torch.zeros(len(column), dtype=torch.bool)
        if mask in mask_indices:
            missing = train[:, mask_indices[mask]] > 0.5
        observed = column[torch.isfinite(column) & ~missing]
        if not len(observed):
            train_bounds.append(None)
            continue
        q1 = torch.quantile(observed, 0.25)
        q3 = torch.quantile(observed, 0.75)
        iqr = q3 - q1
        train_bounds.append(
            None
            if float(iqr) <= 1e-12
            else (float(q1 - 3.0 * iqr), float(q3 + 3.0 * iqr))
        )

    output = {}
    for split, raw in matrices.items():
        values = raw.to(torch.float64)
        records = []
        for index, name in enumerate(FEATURE_NAMES_V2):
            column = values[:, index]
            finite = torch.isfinite(column)
            usable = column[finite]
            mask = _mask_name(name)
            missing = torch.zeros(len(column), dtype=torch.bool)
            if mask in mask_indices:
                missing = values[:, mask_indices[mask]] > 0.5
            observed = usable[~missing[finite]]
            basis = observed if len(observed) else usable
            quantiles = (
                torch.quantile(
                    basis,
                    torch.tensor(
                        [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99],
                        dtype=torch.float64,
                    ),
                ).tolist()
                if len(basis)
                else [None] * 7
            )
            bounds = train_bounds[index]
            outlier_fraction = 0.0
            if bounds is not None and len(observed):
                lower, upper = bounds
                outlier_fraction = float(
                    ((observed < lower) | (observed > upper)).float().mean()
                )
            unique = (
                torch.unique(usable, return_counts=True)[1] if len(usable) else None
            )
            dominant = float(unique.max() / len(usable)) if unique is not None else None
            std = float(basis.std(unbiased=False)) if len(basis) else None
            records.append(
                {
                    "feature": name,
                    "count": int(len(column)),
                    "observed_count": int((~missing & finite).sum()),
                    "missing_pct": float(missing.float().mean() * 100),
                    "mean": float(basis.mean()) if len(basis) else None,
                    "std": std,
                    "min": float(basis.min()) if len(basis) else None,
                    "p1": quantiles[0],
                    "p5": quantiles[1],
                    "p25": quantiles[2],
                    "p50": quantiles[3],
                    "p75": quantiles[4],
                    "p95": quantiles[5],
                    "p99": quantiles[6],
                    "max": float(basis.max()) if len(basis) else None,
                    "constant": bool(std is not None and std <= 1e-12),
                    "near_constant": bool(dominant is not None and dominant >= 0.995),
                    "dominant_fraction": dominant,
                    "extreme_outlier_fraction": outlier_fraction,
                    "outlier_rule": "TRAIN_OBSERVED_3_IQR",
                    "clip_fraction": 0.0,
                    "overflow_fraction": 0.0,
                    "non_finite_count": int((~finite).sum()),
                    "missing_proxy": mask,
                }
            )
        output[split] = records
    return output


def raw_preprocessing_statistics(rows: dict[str, tuple]) -> dict:
    output = {}
    for split in SPLITS:
        extracted = normalization_rows([prefix for _, prefix, _ in rows[split]])
        names = sorted({name for row in extracted for name in row})
        output[split] = {}
        for name in names:
            values = torch.tensor(
                [float(row[name]) for row in extracted if name in row],
                dtype=torch.float64,
            )
            output[split][name] = {
                "count": len(values),
                "missing_pct": 100.0 * (1.0 - len(values) / max(len(extracted), 1)),
                "mean": float(values.mean()),
                "std": float(values.std(unbiased=False)),
                "min": float(values.min()),
                "p1": float(torch.quantile(values, 0.01)),
                "p5": float(torch.quantile(values, 0.05)),
                "p25": float(torch.quantile(values, 0.25)),
                "p50": float(torch.quantile(values, 0.50)),
                "p75": float(torch.quantile(values, 0.75)),
                "p95": float(torch.quantile(values, 0.95)),
                "p99": float(torch.quantile(values, 0.99)),
                "max": float(values.max()),
            }
    return output


def identity_statistics(examples: dict[str, tuple]) -> dict:
    names = ("airport", "route", "carrier", "aircraft")
    categories = {split: {name: set() for name in names} for split in SPLITS}
    for split in SPLITS:
        for example in examples[split]:
            lineage = example.static_context_lineage or {}
            route = lineage.get("route_context", {})
            carrier = lineage.get("carrier_context", {})
            aircraft = lineage.get("aircraft_identity", {})
            route_key = route.get("route_key")
            if route_key:
                categories[split]["route"].add(str(route_key))
            for key in ("origin_airport_id", "destination_airport_id"):
                if route.get(key):
                    categories[split]["airport"].add(str(route[key]))
            if carrier.get("carrier_id"):
                categories[split]["carrier"].add(str(carrier["carrier_id"]))
            if aircraft.get("aircraft_id"):
                categories[split]["aircraft"].add(str(aircraft["aircraft_id"]))
    output = {}
    for name in names:
        train = categories["train"][name]
        calibration = categories["calibration"][name]
        development = categories["development"][name]
        output[name] = {
            "unique_count": {split: len(categories[split][name]) for split in SPLITS},
            "train_only_count": len(train - calibration - development),
            "calibration_unseen_count": len(calibration - train),
            "development_unseen_count": len(development - train),
            "calibration_unseen": sorted(calibration - train),
            "development_unseen": sorted(development - train),
            "role": "IDENTITY_CONTEXT_ONLY",
            "ordinal_encoded": False,
        }
    return output


def label_statistics(rows: dict[str, tuple]) -> dict:
    output = {}
    for split in SPLITS:
        result = {}
        for name in V2_TARGETS:
            labels = [
                label
                for _, _, node_labels in rows[split]
                for label in node_labels
                if label.target_name == name
            ]
            active = [label for label in labels if label.active]
            values = [float(label.exact_minutes) for label in active]
            result[name] = {
                "active_count": len(active),
                "inactive_count": len(labels) - len(active),
                "zero_count": sum(value == 0.0 for value in values),
                "positive_count": sum(value > 0.0 for value in values),
                "overflow_count": sum(value >= LABEL_SUPPORT[name] for value in values),
                "abstain_count": sum(label.support == "ABSTAIN" for label in labels),
                "abstention_reasons": dict(
                    Counter(
                        label.abstention_reason
                        for label in labels
                        if label.abstention_reason is not None
                    )
                ),
            }
        output[split] = result
    return output


def history_diagnostics(
    rows: dict[str, tuple], normalization, static_normalization
) -> dict:
    episode_ids = sorted({episode.episode_id for episode, _, _ in rows["train"]})
    selected_ids = set(
        random.Random(20260821).sample(episode_ids, min(3, len(episode_ids)))
    )
    records = []
    violations = Counter()
    for episode, prefix, _ in rows["train"]:
        if episode.episode_id not in selected_ids:
            continue
        current = prefix[-1]
        context = static_reference_context_from_pre(
            current.static_reference_publication
        )
        static_values, _ = static_reference_features_from_pre(
            current, context, static_normalization
        )
        for state in prefix:
            node = state.decision_node
            if node.information_cutoff > node.decision_time:
                violations["cutoff_after_decision"] += 1
            for item in state.evidence_ledger:
                if (
                    item.availability_time is not None
                    and item.availability_time > node.information_cutoff
                ):
                    violations["future_evidence"] += 1
                if item.decision_time_role in {"TRAIN_LABEL", "EVAL_OUTCOME"}:
                    violations["posthoc_ledger_role"] += 1
        values = encode_pre_sequence(prefix, normalization)
        r_fast = fast_features_from_sequence(
            values.unsqueeze(0), torch.tensor([len(values)])
        )[0]
        records.append(
            {
                "episode_id": episode.episode_id,
                "decision_node_id": current.decision_node.decision_node_id,
                "decision_time": current.decision_node.decision_time.isoformat(),
                "history_length": len(prefix),
                "history_start": prefix[0].decision_node.decision_time.isoformat(),
                "history_end": current.decision_node.decision_time.isoformat(),
                "current_row": values[-1].tolist(),
                "r_fast_row": r_fast.tolist(),
                "current_equals_r_fast": torch.equal(values[-1], r_fast),
                "static_values": (
                    None
                    if static_values is None
                    else static_values.reshape(-1).tolist()
                ),
                "operational_stage": current.decision_node.operational_stage.value,
            }
        )
    return {
        "seed": 20260821,
        "selected_episode_ids": sorted(selected_ids),
        "records": records,
        "causal_ledger_violations": dict(violations),
        "posthoc_stage_construction": "CLOSED_BY_DECLARED_REPLAY_CUTOFF_GATE",
    }


def time_diagnostics(cohorts) -> dict:
    counts = Counter()
    for split in SPLITS:
        for prepared in getattr(cohorts, split):
            schedule = prepared.successor_schedule
            predecessor = prepared.predecessor_outcome
            successor = prepared.successor_outcome
            timestamps = (
                schedule.scheduled_departure_utc,
                schedule.scheduled_arrival_utc,
                predecessor.actual_departure_utc,
                predecessor.actual_arrival_utc,
                successor.actual_departure_utc,
                successor.actual_arrival_utc,
                successor.wheels_off_utc,
            )
            counts["timestamps_checked"] += sum(
                value is not None for value in timestamps
            )
            counts["timezone_violations"] += sum(
                value is not None
                and (value.tzinfo is None or value.utcoffset() is None)
                for value in timestamps
            )
            counts["negative_schedule_duration"] += int(
                schedule.scheduled_arrival_utc < schedule.scheduled_departure_utc
            )
            if (
                successor.actual_departure_utc is not None
                and successor.actual_arrival_utc is not None
            ):
                counts["negative_actual_duration"] += int(
                    successor.actual_arrival_utc < successor.actual_departure_utc
                )
                counts["actual_cross_midnight"] += int(
                    successor.actual_arrival_utc.date()
                    > successor.actual_departure_utc.date()
                )
            if (
                predecessor.actual_arrival_utc is not None
                and successor.actual_departure_utc is not None
            ):
                counts["nonpositive_gate_gap"] += int(
                    successor.actual_departure_utc <= predecessor.actual_arrival_utc
                )
            counts["scheduled_cross_midnight"] += int(
                schedule.scheduled_arrival_utc.date()
                > schedule.scheduled_departure_utc.date()
            )
            for index, state in enumerate(prepared.states):
                node = state.decision_node
                counts["nodes_checked"] += 1
                counts["cutoff_after_decision"] += int(
                    node.information_cutoff > node.decision_time
                )
                counts["roll_minutes_not_five"] += int(node.roll_minutes != 5)
                if index:
                    spacing = (
                        node.decision_time
                        - prepared.states[index - 1].decision_node.decision_time
                    ).total_seconds() / 60.0
                    counts["rolling_spacing_not_five"] += int(spacing != 5.0)
                counts["posthoc_stage_feature_nodes"] += int(
                    node.operational_stage.value != "PRE_IB"
                )
                counts["factual_replay_values_published"] += sum(
                    name in state.current_state or name in state.successor_state
                    for name in (
                        "predecessor_operational_fact",
                        "successor_operational_fact",
                    )
                )
    return {
        **dict(counts),
        "timezone": "PASS" if counts["timezone_violations"] == 0 else "FAIL",
        "cross_midnight": (
            "PASS" if not counts["negative_schedule_duration"] else "FAIL"
        ),
        "planned_actual_time": "DIRECT_PRIMARY_WITH_DECLARED_REPLAY_FOR_STAGE",
        "rolling_time": ("PASS" if not counts["rolling_spacing_not_five"] else "FAIL"),
        "hhmm_parser": "STRING_HHMM_NOT_DECIMAL",
    }
