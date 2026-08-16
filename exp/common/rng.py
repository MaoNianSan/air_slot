from __future__ import annotations

from hashlib import sha256
from typing import Iterable

import numpy as np

from model.common.errors import ContractError


V5_RNG_STREAMS = (
    "m1_scenario",
    "m3_m4_response",
    "exp2_lineage_corruption",
    "bootstrap",
    "llm_case_selection",
    "llm_repetition",
)


def _digest(stream: str, *parts: object) -> bytes:
    if stream not in V5_RNG_STREAMS:
        raise ContractError("RNG_STREAM_UNKNOWN")
    payload = "|".join((stream, *(str(part) for part in parts)))
    return sha256(payload.encode("utf-8")).digest()


def deterministic_seed(stream: str, *parts: object) -> int:
    return int.from_bytes(_digest(stream, *parts)[:8], "big", signed=False)


def stream_generator(stream: str, *parts: object) -> np.random.Generator:
    return np.random.default_rng(deterministic_seed(stream, *parts))


def stable_uniform(stream: str, *parts: object) -> float:
    """Deterministic U(0,1) value independent of worker/order."""
    integer = int.from_bytes(_digest(stream, *parts)[:8], "big", signed=False)
    return (integer + 0.5) / 2**64


def response_rng_key(global_seed: int, episode_id: str, scenario_id: int,
                     candidate_action_id: str, response_component: str) -> tuple:
    """V5 response key; decision_time is intentionally absent."""
    return (global_seed, episode_id, scenario_id, candidate_action_id, response_component)


def corruption_rng_key(global_seed: int, episode_id: str, decision_node_id: str,
                       corruption_q: float, replicate: int, component: str) -> tuple:
    return (global_seed, episode_id, decision_node_id, corruption_q, replicate, component)


def assert_order_invariant(values: Iterable[object], stream: str, *parts: object) -> None:
    """Small guard used by contract tests to make stream ownership explicit."""
    first = tuple(values)
    second = tuple(reversed(first))
    if deterministic_seed(stream, *parts) != deterministic_seed(stream, *parts):
        raise ContractError("RNG_ORDER_DEPENDENT")
    if first == second and len(first) > 1:
        return
