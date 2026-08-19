from hashlib import sha256

import torch

from model.common.errors import ContractError
from .contracts import (
    AlignedScenario,
    HazardBinContract,
    HurdleQuantileContract,
    M1V2Scenario,
    M1_V2_HAZARD_COORDINATE,
    STOCHASTIC_TARGETS,
    TargetBinContract,
    V2_TARGETS,
)
from .loss import hazard_pmf, monotone_positive_quantiles, quantile_value
from .semantics import (
    M1_V2_HAZARD_COORDINATE_TARGET,
    M1_V2_LEGACY_AUXILIARY_TARGETS,
    t_ib_a00_from_remaining_minutes,
)

# Public primitive name for the predecessor in-block event time; the sampled
# scenario always stores the absolute ISO UTC time under this name.
PUBLIC_T_IB_A00 = "T_IB_A00"


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
                     taxi_reference_support_state: str | None = None,
                     temperatures: dict[str, float] | None = None):
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
            temperature = 1.0 if temperatures is None else float(temperatures.get(target, 1.0))
            probabilities = torch.softmax(logits[0] / temperature, -1)
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




# ---------------------------------------------------------------------------
# V2 ancestral sampler (Round-2 M1 V2 real estimator).
# ---------------------------------------------------------------------------


def _uniform_v2(seed: int, episode: str, scenario: int, target: str):
    key = f"m1_v2_scenario|{seed}|{episode}|{scenario}|{target}"
    integer = int(sha256(key.encode()).hexdigest()[:16], 16)
    return (integer + 0.5) / (2**64), f"sha256:{sha256(key.encode()).hexdigest()}"


def required_observations_v2(stage: str) -> frozenset[str]:
    required = {
        "PRE_IB": frozenset(),
        "POST_IB_PRE_OB": frozenset({"T_IB_A00"}),
        "POST_OB_PRE_TO": frozenset({"T_IB_A00", "D_OB"}),
        "COMPLETED": frozenset({"T_IB_A00", "D_OB", "D_TX"}),
    }
    if stage not in required:
        raise ContractError("M1_OPERATIONAL_STAGE_UNKNOWN")
    return required[stage]


def _remaining_from_observed(
    t_ib_a00_utc: str, decision_time_utc: str | None
) -> float:
    """Internal hazard coordinate = max(0, T_IB_A00 - t) minutes.

    The public absolute event time is converted to the internal remaining-time
    coordinate; the absolute value itself stays in ``t_ib_a00_utc`` so past
    events with R_IB == 0 remain distinguishable.
    """
    from .semantics import remaining_hazard_coordinate_minutes
    if decision_time_utc is None:
        raise ContractError("M1_V2_DECISION_TIME_REQUIRED")
    remaining = remaining_hazard_coordinate_minutes(t_ib_a00_utc, decision_time_utc)
    if remaining is None:
        raise ContractError("M1_V2_INVALID_T_IB_A00_TIMESTAMP")
    return float(remaining)


def _sample_categorical(pmf: torch.Tensor, uniform: float) -> int:
    return int(
        torch.searchsorted(
            torch.cumsum(pmf, 0),
            torch.tensor(uniform, device=pmf.device),
        ).clamp_max(pmf.shape[0] - 1)
    )


def _sample_hurdle_quantile(
    zero_logit: torch.Tensor,
    quantile_logits: torch.Tensor,
    contract: HurdleQuantileContract,
    uniform: float,
) -> tuple[float, int, bool]:
    """One draw from P(D=0) + P(D>0) * Q_D(u | D>0).

    ``u > q_max`` follows the contract tail policy: with ``UNRESOLVED`` the
    draw raises instead of silently truncating the positive tail; smoke
    fixtures use ``TEST_ONLY_LINEAR``.
    """
    zero_probability = float(torch.sigmoid(zero_logit[0]).detach())
    quantiles = monotone_positive_quantiles(quantile_logits)[0].detach()
    if uniform < zero_probability:
        return 0.0, 0, False
    positive_uniform = (uniform - zero_probability) / max(1.0 - zero_probability, 1e-12)
    value = float(
        quantile_value(
            quantiles.unsqueeze(0), contract.quantile_levels, positive_uniform,
            upper_tail_policy=contract.upper_tail_policy,
        )[0]
    )
    index = contract.encode(value)
    overflow = bool(contract.tail_state(index) == "OVERFLOW")
    return value, index, overflow


def ancestral_sample_v2(
    model,
    history: torch.Tensor,
    contracts: dict[str, HazardBinContract | HurdleQuantileContract],
    *,
    episode_id: str,
    decision_node_id: str,
    stage: str,
    observed: dict[str, object],
    count: int,
    seed: int,
    target_support: dict[str, str],
    decision_time_utc: str | None,
    scheduled_ob_utc: str | None = None,
    taxi_reference_id: str | None = None,
    taxi_reference_hash: str | None = None,
    taxi_reference_fallback_level: str | None = None,
    taxi_reference_support_state: str | None = None,
    temperatures: dict[str, float] | None = None,
    static_features: torch.Tensor | None = None,
) -> tuple[M1V2Scenario, ...]:
    """Ancestral V2 draws in the formal order T_IB_A00 -> D_OB -> D_TX.

    ``observed`` accepts typed factual replacement with PUBLIC primitive names:
        "T_IB_A00": absolute UTC ISO event-time string,
        "D_OB"/"D_TX": nonnegative minutes.
    ``target_support`` is keyed by the same public primitive names.  The
    internal contracts/heads are addressed through
    ``M1_V2_HAZARD_COORDINATE_TARGET`` (remaining-time coordinate) while the
    scenario stores the public absolute ``t_ib_a00_utc``.  Only unresolved
    variables are drawn; upstream variables that are already decision-time
    facts are consumed as observed.  The Data2 factual availability rule
    itself is NOT decided here (Round-2 human gate).
    """
    hazard = contracts[M1_V2_HAZARD_COORDINATE_TARGET]
    d_ob_contract = contracts["D_OB"]
    d_tx_contract = contracts["D_TX"]
    if not isinstance(hazard, HazardBinContract) or not isinstance(
        d_ob_contract, HurdleQuantileContract
    ) or not isinstance(d_tx_contract, HurdleQuantileContract):
        raise ContractError("M1_V2_CONTRACT_TYPES_INVALID")
    required = required_observations_v2(stage)
    if not required <= set(observed):
        raise ContractError("M1_STAGE_OBSERVATION_MISSING")
    # Fused state representation shared by every head call in this bundle.
    state = model.state_representation(history, static_features)
    rows = []
    for scenario_id in range(count):
        keys = [
            _uniform_v2(seed, episode_id, scenario_id, target)[1]
            for target in V2_TARGETS
        ]
        supports = dict(target_support)

        # --- T_IB_A00 (public) via internal remaining-time hazard coordinate ---
        t_ib_a00_utc: str | None = None
        ib_bin: int | None = None
        t_ib_observed = PUBLIC_T_IB_A00 in observed
        overflow_t_ib = False
        if supports.get(PUBLIC_T_IB_A00) == "ABSTAIN":
            pass
        elif t_ib_observed:
            t_ib_a00_utc = str(observed[PUBLIC_T_IB_A00])
            remaining = _remaining_from_observed(t_ib_a00_utc, decision_time_utc)
            ib_bin = hazard.encode(remaining)
            overflow_t_ib = bool(hazard.tail_state(ib_bin) == "OVERFLOW")
        else:
            if decision_time_utc is None:
                raise ContractError("M1_V2_DECISION_TIME_REQUIRED")
            logits = model.hazard_logits(state)
            temperature = 1.0 if temperatures is None else float(
                temperatures.get(M1_V2_HAZARD_COORDINATE, 1.0))
            pmf = hazard_pmf(logits[0].detach() / temperature, hazard)
            uniform, _ = _uniform_v2(seed, episode_id, scenario_id,
                                     M1_V2_HAZARD_COORDINATE)
            ib_bin = _sample_categorical(pmf, uniform)
            overflow_t_ib = bool(hazard.tail_state(ib_bin) == "OVERFLOW")
            remaining = float(hazard.representative(ib_bin)[0])
            t_ib_a00_utc = t_ib_a00_from_remaining_minutes(
                decision_time_utc, remaining)

        # --- D_OB (hurdle + conditional quantile, parent T_IB_A00) ---
        d_ob_minutes: float | None = None
        d_ob_bin: int | None = None
        d_ob_observed = "D_OB" in observed
        overflow_d_ob = False
        if supports.get("D_OB") == "ABSTAIN":
            pass
        elif d_ob_observed:
            d_ob_minutes = float(observed["D_OB"])
            if d_ob_minutes < 0:
                raise ContractError("M1_V2_D_OB_NEGATIVE")
            d_ob_bin = d_ob_contract.encode(d_ob_minutes)
            overflow_d_ob = bool(d_ob_contract.tail_state(d_ob_bin) == "OVERFLOW")
        elif ib_bin is None:
            # Formal parent abstention propagates to the child scenario.
            supports["D_OB"] = "ABSTAIN"
        else:
            zero_logit, quantile_logits = model.d_ob_heads(state, ib_bin)
            temperature = 1.0 if temperatures is None else float(temperatures.get("D_OB", 1.0))
            uniform, _ = _uniform_v2(seed, episode_id, scenario_id, "D_OB")
            d_ob_minutes, d_ob_bin, overflow_d_ob = _sample_hurdle_quantile(
                zero_logit, quantile_logits / temperature, d_ob_contract, uniform
            )

        # --- D_TX (hurdle + conditional quantile, parents T_IB_A00, D_OB) ---
        d_tx_minutes: float | None = None
        d_tx_observed = "D_TX" in observed
        overflow_d_tx = False
        if supports.get("D_TX") == "ABSTAIN":
            pass
        elif d_tx_observed:
            d_tx_minutes = float(observed["D_TX"])
            if d_tx_minutes < 0:
                raise ContractError("M1_V2_D_TX_NEGATIVE")
        elif ib_bin is None or d_ob_bin is None:
            # Formal parent abstention propagates to the child scenario.
            supports["D_TX"] = "ABSTAIN"
        else:
            zero_logit, quantile_logits = model.d_tx_heads(state, ib_bin, d_ob_bin)
            temperature = 1.0 if temperatures is None else float(temperatures.get("D_TX", 1.0))
            uniform, _ = _uniform_v2(seed, episode_id, scenario_id, "D_TX")
            d_tx_minutes, d_tx_bin, overflow_d_tx = _sample_hurdle_quantile(
                zero_logit, quantile_logits / temperature, d_tx_contract, uniform
            )

        rows.append(M1V2Scenario(
            episode_id=episode_id,
            decision_node_id=decision_node_id,
            scenario_id=scenario_id,
            scenario_weight=1 / count,
            operational_stage=stage,
            decision_time_utc=decision_time_utc,
            t_ib_a00_utc=t_ib_a00_utc,
            d_ob_minutes=d_ob_minutes,
            d_tx_minutes=d_tx_minutes,
            scheduled_ob_utc=scheduled_ob_utc,
            t_ib_observed=t_ib_observed,
            d_ob_observed=d_ob_observed,
            d_tx_observed=d_tx_observed,
            t_ib_support=supports.get(PUBLIC_T_IB_A00, "ABSTAIN"),
            d_ob_support=supports.get("D_OB", "ABSTAIN"),
            d_tx_support=supports.get("D_TX", "ABSTAIN"),
            overflow_t_ib=overflow_t_ib,
            overflow_d_ob=overflow_d_ob,
            overflow_d_tx=overflow_d_tx,
            scenario_seed_key="|".join(keys) or f"observed:{episode_id}:{scenario_id}",
            taxi_reference_id=taxi_reference_id,
            taxi_reference_hash=taxi_reference_hash,
            taxi_reference_fallback_level=taxi_reference_fallback_level,
            taxi_reference_support_state=taxi_reference_support_state,
        ))
    return tuple(rows)
