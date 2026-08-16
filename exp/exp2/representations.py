from __future__ import annotations

from copy import deepcopy

from model.common.errors import ContractError
from model.common.identity import content_id
from model.M1.semantics import total_takeoff_delay_minutes
from exp.common.rng import corruption_rng_key, stream_generator


TARGET_FIELDS = ("r_ib_minutes", "r_ob_minutes", "t_tx_minutes")


def _rows(scenarios):
    return tuple(row.model_dump(mode="json") if hasattr(row, "model_dump") else dict(row)
                 for row in scenarios)


def point_collapse(scenarios):
    """Select one coherent weighted joint scenario (never component-wise means)."""
    if not scenarios:
        raise ContractError("EXP2_SCENARIO_ARTIFACT_EMPTY")
    rows = _rows(scenarios)
    source_hash = content_id(rows)
    weights = [float(row.get("scenario_weight", 1.0)) for row in rows]
    total_weight = sum(weights)
    finite_fields = [field for field in TARGET_FIELDS if any(row.get(field) is not None for row in rows)]
    def distance(candidate):
        score = 0.0
        for row, weight in zip(rows, weights):
            squared = 0.0
            for field in finite_fields:
                left, right = candidate.get(field), row.get(field)
                if left is not None and right is not None:
                    squared += (float(left) - float(right)) ** 2
            score += weight * squared
        return score
    selected = min(enumerate(rows), key=lambda item: (distance(item[1]), item[0]))[1]
    values = {field: selected.get(field) for field in TARGET_FIELDS}
    if selected.get("d_to_minutes") is not None:
        values["d_to_minutes"] = float(selected["d_to_minutes"])
        d_to_status = "FROZEN_SCENARIO_VALUE"
    elif all(selected.get(name) is not None for name in (
        "t_ob_minutes", "t_tx_minutes", "scheduled_ob_minutes", "taxi_reference_minutes")):
        values["d_to_minutes"] = total_takeoff_delay_minutes(
            t_ob_minutes=selected["t_ob_minutes"], t_tx_minutes=selected["t_tx_minutes"],
            scheduled_ob_minutes=selected["scheduled_ob_minutes"],
            taxi_reference_minutes=selected["taxi_reference_minutes"])
        d_to_status = "DERIVED_FROM_EVENT_TIME_AND_REFERENCE"
    else:
        values["d_to_minutes"] = None
        d_to_status = "REFERENCE_TERMS_REQUIRED"
    return {"representation": "POINT_COLLAPSE", "point_rule": "WEIGHTED_JOINT_SCENARIO_MEDOID",
            "source_m1_artifact_hash": source_hash, "scenario_weight_sum": total_weight,
            "selected_scenario_id": selected.get("scenario_id"), "d_to_status": d_to_status, **values}


def shuffle_scenario_lineage(scenarios, *, seed: int):
    """Backward-compatible q=1 corruption wrapper."""
    episode_id = str(_rows(scenarios)[0].get("episode_id", "episode"))
    node_id = str(_rows(scenarios)[0].get("decision_node_id", "node"))
    return corrupt_scenario_lineage(scenarios, global_seed=seed, episode_id=episode_id,
                                   decision_node_id=node_id, corruption_q=1.0, replicate=0)


def corrupt_scenario_lineage(scenarios, *, global_seed: int, episode_id: str,
                             decision_node_id: str, corruption_q: float, replicate: int = 0):
    if not 0.0 <= corruption_q <= 1.0:
        raise ContractError("EXP2_CORRUPTION_Q_INVALID")
    if not scenarios:
        raise ContractError("EXP2_SCENARIO_ARTIFACT_EMPTY")
    rows = _rows(scenarios)
    source_hash = content_id(rows)
    output = deepcopy(list(rows))
    permutations = {}
    for field in TARGET_FIELDS:
        order = list(range(len(output)))
        rng = stream_generator("exp2_lineage_corruption", *corruption_rng_key(
            global_seed, episode_id, decision_node_id, corruption_q, replicate, field))
        # q is the corruption intensity: q=0 is exactly aligned, q=1 is fully shuffled.
        count = int(round(corruption_q * len(order)))
        mapping = list(order)
        if count > 1:
            selected = sorted(int(value) for value in rng.choice(order, size=count, replace=False))
            sources = list(rng.permutation(selected))
            for position, source_index in zip(selected, sources):
                output[position][field] = rows[source_index].get(field)
                mapping[position] = source_index
        permutations[field] = tuple(mapping)
    audit = {"global_seed": global_seed, "episode_id": episode_id,
             "decision_node_id": decision_node_id, "corruption_q": corruption_q,
             "replicate": replicate, "source_m1_artifact_hash": source_hash,
             "output_hash": content_id(output), "permutations": permutations,
             "marginals_preserved": all(
                 sorted((row.get(field) for row in rows), key=lambda value: (value is None, value)) ==
                 sorted((row.get(field) for row in output), key=lambda value: (value is None, value))
                 for field in TARGET_FIELDS)}
    if content_id(rows) != source_hash:
        raise ContractError("EXP2_MUTATED_M1_ARTIFACT")
    return tuple(output), audit
