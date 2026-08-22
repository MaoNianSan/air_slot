"""M1 V2 training example preparation from PRE episodes.

Builds legal adaptive V2 histories and stage-gated labels
(T_IB_A00 / D_OB / D_TX); D_TX labels require the train-frozen taxi reference
at label construction.
"""

from __future__ import annotations

from collections import Counter

from model.M1.coverage import active_node_prefixes
from model.M1.contracts import static_reference_context_from_pre
from model.M1.data import (
    V2_WEATHER_FIELDS,
    encode_pre_sequence,
)
from model.M1.history import adaptive_history
from model.M1.lifecycle import M1TrainingExample
from model.M1.static_features import (
    M1StaticNormalizationArtifact,
    fit_static_normalization,
    raw_static_values_from_pre,
    static_reference_features_from_pre,
)


def active_rows(partition, *, taxi_reference=None, taxi_reference_minutes=None,
                taxi_reference_id=None, taxi_reference_hash=None) -> tuple[tuple, dict[str, int]]:
    """Construct legal adaptive M1 V2 histories and labels from PRE episodes."""
    output = []
    stages = Counter()
    for prepared in partition:
        reference_minutes = taxi_reference_minutes
        reference_id = taxi_reference_id
        reference_hash = taxi_reference_hash
        if taxi_reference is not None:
            lookup = taxi_reference.lookup(prepared.episode.connection_airport_id)
            reference_minutes = (
                float(lookup.value)
                if getattr(lookup, "value", None) is not None
                and getattr(getattr(lookup, "support_state", None), "value", None) == "SUPPORTED"
                else None
            )
            reference_id = (
                getattr(taxi_reference, "reference_id", None)
                if reference_minutes is not None else None
            )
            reference_hash = (
                getattr(taxi_reference, "manifest_freeze_id", None)
                if reference_minutes is not None else None
            )
        for _, prefix, labels in active_node_prefixes(
            episode=prepared.episode,
            nodes=prepared.nodes,
            states=prepared.states,
            successor_schedule=prepared.successor_schedule,
            predecessor_outcome=prepared.predecessor_outcome,
            successor_outcome=prepared.successor_outcome,
            taxi_reference_minutes=reference_minutes,
            taxi_reference_id=reference_id,
            taxi_reference_hash=reference_hash,
        ):
            history = adaptive_history(prefix)
            output.append((prepared.episode, history, labels))
            stages[history[-1].decision_node.operational_stage.value] += 1
    return tuple(output), dict(stages)


def build_training_examples(rows, normalization, bins, *, static_normalization):
    """Encode legal M1 V2 histories into model-owned training examples."""
    if not isinstance(static_normalization, M1StaticNormalizationArtifact):
        raise ValueError("M1_STATIC_NORMALIZATION_REQUIRED")
    return tuple(
        M1TrainingExample.from_v2_target_labels(
            values=encode_pre_sequence(prefix, normalization), labels=labels,
            static_values=_static_values(prefix, static_normalization),
            static_context_lineage=_static_lineage(prefix),
        )
        for _, prefix, labels in rows
    )


def _static_values(prefix, normalization):
    context = static_reference_context_from_pre(prefix[-1].static_reference_publication)
    values, _ = static_reference_features_from_pre(
        prefix[-1], context, normalization
    )
    return values.reshape(-1)


def _static_lineage(prefix):
    context = static_reference_context_from_pre(prefix[-1].static_reference_publication)
    _, lineage = raw_static_values_from_pre(prefix[-1], context)
    return lineage


def _static_raw_values(prefix):
    context = static_reference_context_from_pre(prefix[-1].static_reference_publication)
    values, _ = raw_static_values_from_pre(prefix[-1], context)
    return values


def fit_static_normalization_from_rows(rows) -> M1StaticNormalizationArtifact:
    """Fit static scaling once per unique Train episode."""
    return fit_static_normalization(
        (
            (episode.episode_id, _static_raw_values(prefix))
            for episode, prefix, _ in rows
        ),
        split="train",
    )


def normalization_rows(prefixes):
    """Extract V2 normalization inputs from legal PRE-state sequences."""
    rows = []
    for states in prefixes:
        for state in states:
            row = {}
            schedule = state.successor_state.get("schedule_reference")
            if schedule and isinstance(schedule.value, dict):
                departure = schedule.value.get("scheduled_departure_utc")
                if departure is not None:
                    row["schedule.signed_minutes_to_crs_departure"] = (
                        departure - state.decision_node.decision_time
                    ).total_seconds() / 60
            weather_lineage = next(
                (
                    entry
                    for entry in state.variable_lineage
                    if entry.scientific_variable == "current_weather"
                ),
                None,
            )
            if weather_lineage and weather_lineage.age_seconds is not None:
                row["weather.observation_age_minutes"] = weather_lineage.age_seconds / 60
            weather = state.current_state.get("current_weather")
            if weather and isinstance(weather.value, dict):
                for field in V2_WEATHER_FIELDS:
                    if field == "wind_direction_deg":
                        continue
                    value = weather.value.get(field)
                    if value is not None:
                        row[f"weather.{field}"] = float(value)
            rows.append(row)
    return rows
