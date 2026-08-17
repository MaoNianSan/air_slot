from hashlib import sha256

import torch

from model.common.errors import ContractError
from .contracts import AlignedScenario, STOCHASTIC_TARGETS, TargetBinContract


def _uniform(seed: int, episode: str, scenario: int, target: str):
    key = f"m1_scenario|{seed}|{episode}|{scenario}|{target}"
    integer = int(sha256(key.encode()).hexdigest()[:16], 16)
    return (integer + 0.5) / (2**64), f"sha256:{sha256(key.encode()).hexdigest()}"


def _sample_index(probabilities, seed, episode, scenario_id, target):
    uniform, key = _uniform(seed, episode, scenario_id, target)
    index = int(torch.searchsorted(
        torch.cumsum(probabilities, 0),
        torch.tensor(uniform, device=probabilities.device),
    ).clamp_max(len(probabilities) - 1))
    return index, key


def _required_observations(stage: str) -> set[str]:
    required = {
        "PRE_IB": set(),
        "POST_IB_PRE_OB": {"R_IB"},
        "POST_OB_PRE_TO": {"R_IB", "DELTA_OB"},
        "COMPLETED": {"R_IB", "DELTA_OB", "T_TX"},
    }
    if stage not in required:
        raise ContractError("M1_OPERATIONAL_STAGE_UNKNOWN")
    return required[stage]


def aligned_sample(distributions: dict[str, torch.Tensor], bins: dict[str, TargetBinContract], *, episode_id: str,
                   decision_node_id: str, stage: str, observed: dict[str, float], count: int, seed: int,
                   target_support: dict[str, str] | None = None, scheduled_ob_utc: str | None = None,
                   tx_reference_minutes: float | None = None, taxi_reference_id: str | None = None,
                   taxi_reference_hash: str | None = None, taxi_reference_fallback_level: str | None = None,
                   taxi_reference_support_state: str | None = None):
    required = _required_observations(stage)
    if not required <= set(observed):
        raise ContractError("M1_STAGE_OBSERVATION_MISSING")
    support = target_support or {name: "SUPPORTED" for name in STOCHASTIC_TARGETS}
    scenarios = []
    for scenario_id in range(count):
        values, underflow, overflow = {}, {}, {}
        keys = [_uniform(seed, episode_id, scenario_id, target)[1] for target in STOCHASTIC_TARGETS]
        for target in STOCHASTIC_TARGETS:
            if support.get(target) == "ABSTAIN":
                values[target], underflow[target], overflow[target] = None, False, False
            elif target in observed:
                values[target], underflow[target], overflow[target] = float(observed[target]), False, False
            else:
                index, _ = _sample_index(distributions[target][0], seed, episode_id, scenario_id, target)
                values[target], underflow[target], overflow[target] = bins[target].representative(index)
        scenarios.append(AlignedScenario(
            episode_id=episode_id,
            decision_node_id=decision_node_id,
            scenario_id=scenario_id,
            scenario_weight=1 / count,
            operational_stage=stage,
            r_ib_minutes=values["R_IB"],
            delta_ob_minutes=values["DELTA_OB"],
            t_tx_minutes=values["T_TX"],
            scheduled_ob_utc=scheduled_ob_utc,
            tx_reference_minutes=tx_reference_minutes,
            taxi_reference_id=taxi_reference_id,
            taxi_reference_hash=taxi_reference_hash,
            taxi_reference_fallback_level=taxi_reference_fallback_level,
            taxi_reference_support_state=taxi_reference_support_state,
            ib_observed="R_IB" in observed,
            delta_ob_observed="DELTA_OB" in observed,
            ib_support=support.get("R_IB", "ABSTAIN"),
            delta_ob_support=support.get("DELTA_OB", "ABSTAIN"),
            tx_support=support.get("T_TX", "ABSTAIN"),
            overflow_ib=overflow["R_IB"],
            underflow_delta_ob=underflow["DELTA_OB"],
            overflow_delta_ob=overflow["DELTA_OB"],
            overflow_tx=overflow["T_TX"],
            scenario_seed_key="|".join(keys) or f"observed:{episode_id}:{scenario_id}",
        ))
    return tuple(scenarios)


def ancestral_sample(model, history: torch.Tensor, bins: dict[str, TargetBinContract], *,
                     episode_id: str, decision_node_id: str, stage: str,
                     observed: dict[str, float], count: int, seed: int,
                     target_support: dict[str, str], scheduled_ob_utc: str | None = None,
                     tx_reference_minutes: float | None = None, taxi_reference_id: str | None = None,
                     taxi_reference_hash: str | None = None, taxi_reference_fallback_level: str | None = None,
                     taxi_reference_support_state: str | None = None):
    required = _required_observations(stage)
    if not required <= set(observed):
        raise ContractError("M1_STAGE_OBSERVATION_MISSING")
    rows = []
    for scenario_id in range(count):
        values, indices, underflow, overflow = {}, {}, {}, {}
        keys = [_uniform(seed, episode_id, scenario_id, target)[1] for target in STOCHASTIC_TARGETS]
        supports = dict(target_support)
        for target in STOCHASTIC_TARGETS:
            target_state = supports.get(target, "ABSTAIN")
            if target_state == "ABSTAIN":
                values[target], indices[target], underflow[target], overflow[target] = None, None, False, False
                continue
            if target in observed:
                values[target] = float(observed[target])
                indices[target] = bins[target].encode(values[target])
                underflow[target] = overflow[target] = False
                continue
            ib_index, delta_ob_index = indices.get("R_IB"), indices.get("DELTA_OB")
            if target == "DELTA_OB" and ib_index is None:
                raise ContractError("M1_PARENT_TARGET_UNSUPPORTED:R_IB->DELTA_OB")
            if target == "T_TX" and ib_index is None:
                values[target], indices[target], underflow[target], overflow[target] = None, None, False, False
                supports[target] = "ABSTAIN"
                continue
            logits = model.conditioned_logits(
                history, target, ib_index=ib_index, delta_ob_index=delta_ob_index
            )
            probabilities = torch.softmax(logits[0], -1)
            index, _ = _sample_index(probabilities, seed, episode_id, scenario_id, target)
            indices[target] = index
            values[target], underflow[target], overflow[target] = bins[target].representative(index)
        rows.append(AlignedScenario(
            episode_id=episode_id,
            decision_node_id=decision_node_id,
            scenario_id=scenario_id,
            scenario_weight=1 / count,
            operational_stage=stage,
            r_ib_minutes=values["R_IB"],
            delta_ob_minutes=values["DELTA_OB"],
            t_tx_minutes=values["T_TX"],
            scheduled_ob_utc=scheduled_ob_utc,
            tx_reference_minutes=tx_reference_minutes,
            taxi_reference_id=taxi_reference_id,
            taxi_reference_hash=taxi_reference_hash,
            taxi_reference_fallback_level=taxi_reference_fallback_level,
            taxi_reference_support_state=taxi_reference_support_state,
            ib_observed="R_IB" in observed,
            delta_ob_observed="DELTA_OB" in observed,
            ib_support=supports.get("R_IB", "ABSTAIN"),
            delta_ob_support=supports.get("DELTA_OB", "ABSTAIN"),
            tx_support=supports.get("T_TX", "ABSTAIN"),
            overflow_ib=overflow["R_IB"],
            underflow_delta_ob=underflow["DELTA_OB"],
            overflow_delta_ob=overflow["DELTA_OB"],
            overflow_tx=overflow["T_TX"],
            scenario_seed_key="|".join(keys) or f"observed:{episode_id}:{scenario_id}",
        ))
    return tuple(rows)
