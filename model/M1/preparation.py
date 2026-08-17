from __future__ import annotations

from collections import Counter

from model.M1.coverage import active_node_prefixes
from model.M1.data import encode_pre_sequence
from model.M1.history import adaptive_history
from model.M1.lifecycle import M1TrainingExample


def active_rows(partition) -> tuple[tuple, dict[str, int]]:
    """Construct legal adaptive M1 histories and labels from PRE episodes."""
    output = []
    stages = Counter()
    for prepared in partition:
        for _, prefix, labels in active_node_prefixes(
            episode=prepared.episode,
            nodes=prepared.nodes,
            states=prepared.states,
            successor_schedule=prepared.successor_schedule,
            predecessor_outcome=prepared.predecessor_outcome,
            successor_outcome=prepared.successor_outcome,
        ):
            history = adaptive_history(prefix)
            output.append((prepared.episode, history, labels))
            stages[history[-1].decision_node.operational_stage.value] += 1
    return tuple(output), dict(stages)


def build_training_examples(rows, normalization, bins):
    """Encode legal M1 histories into model-owned training examples."""
    return tuple(
        M1TrainingExample.from_target_labels(
            values=encode_pre_sequence(prefix, normalization), labels=labels, bins=bins
        )
        for _, prefix, labels in rows
    )


def normalization_rows(prefixes):
    """Extract M1 normalization inputs from legal PRE-state sequences."""
    rows = []
    for states in prefixes:
        previous = None
        for state in states:
            row = {}
            schedule = state.successor_state.get("schedule_reference")
            if schedule and isinstance(schedule.value, dict):
                departure = schedule.value.get("scheduled_departure_utc")
                if departure is not None:
                    row["schedule.signed_minutes_to_crs_departure"] = (
                        departure - state.decision_node.decision_time
                    ).total_seconds() / 60
            for variable, name in (
                ("predecessor_motion", "motion.observation_age_minutes"),
                ("current_weather", "weather.observation_age_minutes"),
            ):
                lineage = next(
                    (
                        entry
                        for entry in state.variable_lineage
                        if entry.scientific_variable == variable
                    ),
                    None,
                )
                if lineage and lineage.age_seconds is not None:
                    row[name] = lineage.age_seconds / 60
            row["node.spacing_minutes"] = (
                0.0
                if previous is None
                else (
                    state.decision_node.decision_time - previous
                ).total_seconds()
                / 60
            )
            previous = state.decision_node.decision_time
            rows.append(row)
    return rows
