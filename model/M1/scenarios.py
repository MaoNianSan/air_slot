from hashlib import sha256
import torch
from model.common.errors import ContractError
from .contracts import AlignedScenario, TargetBinContract


def _uniform(seed: int, episode: str, scenario: int, target: str):
    key=f"m1_scenario|{seed}|{episode}|{scenario}|{target}"; integer=int(sha256(key.encode()).hexdigest()[:16],16)
    return (integer + .5) / (2**64), f"sha256:{sha256(key.encode()).hexdigest()}"


def _sample_index(probabilities, seed, episode, scenario_id, target):
    u,key=_uniform(seed,episode,scenario_id,target)
    index=int(torch.searchsorted(torch.cumsum(probabilities,0),
        torch.tensor(u,device=probabilities.device)).clamp_max(len(probabilities)-1))
    return index,key


def aligned_sample(distributions: dict[str, torch.Tensor], bins: dict[str, TargetBinContract], *, episode_id: str,
                   decision_node_id: str, stage: str, observed: dict[str,float], count: int, seed: int,
                   target_support: dict[str,str] | None = None):
    required={"PRE_IB":set(),"POST_IB_PRE_OB":{"R_IB"},"POST_OB_PRE_TO":{"R_IB","R_OB"},
              "COMPLETED":{"R_IB","R_OB","T_TX"}}
    if stage not in required:raise ContractError("M1_OPERATIONAL_STAGE_UNKNOWN")
    if not required[stage] <= set(observed):raise ContractError("M1_STAGE_OBSERVATION_MISSING")
    support=target_support or {name:"SUPPORTED" for name in ("R_IB","R_OB","T_TX")}
    scenarios=[]
    for scenario_id in range(count):
        values={}; overflow={}; keys=[_uniform(seed,episode_id,scenario_id,target)[1]
                                      for target in ("R_IB","R_OB","T_TX")]
        for target in ("R_IB","R_OB","T_TX"):
            if support.get(target)=="ABSTAIN":values[target]=None;overflow[target]=False
            elif target in observed: values[target]=float(observed[target]); overflow[target]=False
            else:
                index,_=_sample_index(distributions[target][0],seed,episode_id,scenario_id,target)
                values[target],overflow[target]=bins[target].representative(index)
        scenarios.append(AlignedScenario(episode_id=episode_id,decision_node_id=decision_node_id,
            scenario_id=scenario_id,scenario_weight=1/count,operational_stage=stage,
            r_ib_minutes=values["R_IB"],r_ob_minutes=values["R_OB"],t_tx_minutes=values["T_TX"],
            ib_observed="R_IB" in observed,ob_observed="R_OB" in observed,
            ib_support=support.get("R_IB","ABSTAIN"),ob_support=support.get("R_OB","ABSTAIN"),tx_support=support.get("T_TX","ABSTAIN"),
            overflow_ib=overflow["R_IB"],overflow_ob=overflow["R_OB"],overflow_tx=overflow["T_TX"],
            scenario_seed_key="|".join(keys) or f"observed:{episode_id}:{scenario_id}"))
    return tuple(scenarios)


def ancestral_sample(model, history: torch.Tensor, bins: dict[str, TargetBinContract], *,
                     episode_id: str, decision_node_id: str, stage: str,
                     observed: dict[str, float], count: int, seed: int,
                     target_support: dict[str, str]):
    required={"PRE_IB":set(),"POST_IB_PRE_OB":{"R_IB"},"POST_OB_PRE_TO":{"R_IB","R_OB"},
              "COMPLETED":{"R_IB","R_OB","T_TX"}}
    if stage not in required: raise ContractError("M1_OPERATIONAL_STAGE_UNKNOWN")
    if not required[stage] <= set(observed): raise ContractError("M1_STAGE_OBSERVATION_MISSING")
    rows=[]
    for scenario_id in range(count):
        values={}; indices={}; overflow={}; keys=[_uniform(seed,episode_id,scenario_id,target)[1]
                                                  for target in ("R_IB","R_OB","T_TX")]
        for target in ("R_IB","R_OB","T_TX"):
            support=target_support.get(target,"ABSTAIN")
            if support == "ABSTAIN":
                values[target]=None; indices[target]=None; overflow[target]=False
                continue
            if target in observed:
                values[target]=float(observed[target]); indices[target]=bins[target].encode(values[target]); overflow[target]=False
                continue
            parents=(indices.get("R_IB"),indices.get("R_OB"))
            if target == "R_OB" and parents[0] is None:
                raise ContractError("M1_PARENT_TARGET_UNSUPPORTED:R_IB->R_OB")
            if target == "T_TX" and parents[0] is None:
                # TX cannot be upgraded if the first ordered parent is absent.
                values[target]=None; indices[target]=None; overflow[target]=False
                target_support={**target_support,target:"ABSTAIN"}; continue
            logits=model.conditioned_logits(history,target,ib_index=parents[0],ob_index=parents[1])
            probs=torch.softmax(logits[0],-1)
            index,_=_sample_index(probs,seed,episode_id,scenario_id,target)
            indices[target]=index; values[target],overflow[target]=bins[target].representative(index)
        rows.append(AlignedScenario(episode_id=episode_id,decision_node_id=decision_node_id,
            scenario_id=scenario_id,scenario_weight=1/count,operational_stage=stage,
            r_ib_minutes=values["R_IB"],r_ob_minutes=values["R_OB"],t_tx_minutes=values["T_TX"],
            ib_observed="R_IB" in observed,ob_observed="R_OB" in observed,
            ib_support=target_support.get("R_IB","ABSTAIN"),ob_support=target_support.get("R_OB","ABSTAIN"),
            tx_support=target_support.get("T_TX","ABSTAIN"),overflow_ib=overflow["R_IB"],
            overflow_ob=overflow["R_OB"],overflow_tx=overflow["T_TX"],
            scenario_seed_key="|".join(keys) or f"observed:{episode_id}:{scenario_id}"))
    return tuple(rows)
