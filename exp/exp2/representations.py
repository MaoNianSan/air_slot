from __future__ import annotations

from copy import deepcopy
import random

from model.common.errors import ContractError
from model.common.identity import content_id
from model.M1.semantics import takeoff_delay_minutes


TARGET_FIELDS = ("r_ib_minutes", "r_ob_minutes", "t_tx_minutes")


def _rows(scenarios):
    return tuple(row.model_dump(mode="json") if hasattr(row, "model_dump") else dict(row)
                 for row in scenarios)


def point_collapse(scenarios):
    if not scenarios:
        raise ContractError("EXP2_SCENARIO_ARTIFACT_EMPTY")
    rows = _rows(scenarios)
    source_hash = content_id(rows)
    weights = [float(row["scenario_weight"]) for row in rows]
    total_weight = sum(weights)
    values = {}
    for field in TARGET_FIELDS:
        observed = [(row.get(field), weight) for row, weight in zip(rows, weights)
                    if row.get(field) is not None]
        values[field] = None if not observed else sum(value * weight for value, weight in observed) / sum(
            weight for _, weight in observed)
    values["d_to_minutes"] = takeoff_delay_minutes(values["r_ob_minutes"], values["t_tx_minutes"])
    return {"representation": "POINT_COLLAPSE", "source_m1_artifact_hash": source_hash,
            "scenario_weight_sum": total_weight, **values}


def shuffle_scenario_lineage(scenarios, *, seed: int):
    if not scenarios:
        raise ContractError("EXP2_SCENARIO_ARTIFACT_EMPTY")
    rows = _rows(scenarios)
    source_hash = content_id(rows)
    output = deepcopy(list(rows))
    permutations = {}
    for offset, field in enumerate(TARGET_FIELDS):
        order = list(range(len(output)))
        random.Random(seed + offset).shuffle(order)
        original = [row.get(field) for row in rows]
        for index, source_index in enumerate(order):
            output[index][field] = original[source_index]
        permutations[field] = tuple(order)
    audit = {"seed": seed, "source_m1_artifact_hash": source_hash,
             "output_hash": content_id(output), "permutations": permutations,
             "marginals_preserved": all(
                 sorted((row.get(field) for row in rows), key=lambda value: (value is None, value)) ==
                 sorted((row.get(field) for row in output), key=lambda value: (value is None, value))
                 for field in TARGET_FIELDS)}
    if content_id(rows) != source_hash:
        raise ContractError("EXP2_MUTATED_M1_ARTIFACT")
    return tuple(output), audit
