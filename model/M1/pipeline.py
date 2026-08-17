from pathlib import Path
import torch
from .contracts import TargetBinContract
from .network import OrderedEventGRU
from .scenarios import aligned_sample, ancestral_sample


class M1Pipeline:
    def __init__(self, model, bins, temperatures=None, normalization=None):
        self.model=model; self.bins=bins; self.temperatures=temperatures or {n:1.0 for n in bins}
        self.normalization=normalization

    @classmethod
    def smoke(cls,input_size=4):
        """Synthetic fixture helper; never resolves formal scientific bins."""
        bins={
            "R_IB": TargetBinContract(target_name="R_IB", bin_width_minutes=5, max_finite_minutes=20),
            "DELTA_OB": TargetBinContract(target_name="DELTA_OB", bin_width_minutes=5,
                                            min_finite_minutes=-20, max_finite_minutes=20, signed=True),
            "T_TX": TargetBinContract(target_name="T_TX", bin_width_minutes=5, max_finite_minutes=20),
        }
        torch.manual_seed(0); return cls(OrderedEventGRU(input_size,16,bins),bins)

    @classmethod
    def from_scientific_config(cls, scientific, *, input_size, normalization, hidden_size=None):
        from .data import M1NormalizationArtifact
        if not isinstance(normalization, M1NormalizationArtifact) \
                or normalization.fitted_split != "train":
            raise ValueError("M1_FORMAL_TRAIN_NORMALIZATION_REQUIRED")
        names={"R_IB":"m1_r_ib_max_finite_minutes", "T_TX":"m1_t_tx_max_finite_minutes"}
        width=scientific.parameters["m1_bin_width_minutes"].value
        bins={}
        for target, parameter in names.items():
            item=scientific.parameters[parameter]
            if item.value is None:
                raise ValueError(f"M1_FORMAL_FINITE_SUPPORT_UNFROZEN:{target}")
            bins[target]=TargetBinContract(target_name=target,
                bin_width_minutes=width,max_finite_minutes=item.value)
        bins["DELTA_OB"] = TargetBinContract(
            target_name="DELTA_OB", bin_width_minutes=width,
            min_finite_minutes=-180, max_finite_minutes=180, signed=True,
        )
        selected = scientific.parameters["m1_hidden_size"].value
        candidates = scientific.parameters["m1_hidden_size_candidates"].value
        hidden = selected if hidden_size is None else hidden_size
        if hidden is None:
            raise ValueError("M1_HIDDEN_SIZE_SELECTION_REQUIRED")
        if hidden not in candidates:
            raise ValueError("M1_HIDDEN_SIZE_NOT_IN_DEVELOPMENT_CANDIDATES")
        return cls(OrderedEventGRU(input_size,hidden,bins),bins,normalization=normalization)

    def predict_distributions(self,values,lengths):
        self.model.eval()
        with torch.no_grad(): logits=self.model(values,lengths)
        return {n:torch.softmax(logits[n]/self.temperatures[n],-1) for n in logits}

    def sample_aligned(self,dist,**kwargs): return aligned_sample(dist,self.bins,**kwargs)

    def sample_from_pre(self, pre_state, values, lengths, *, observed, count, seed,
                        taxi_reference=None):
        if values.shape[0] != 1:
            raise ValueError("formal scenario generation accepts one decision node at a time")
        support={item.target_name:(item.support_state.value if hasattr(item.support_state,"value") else str(item.support_state))
                 for item in pre_state.target_support}
        stage=pre_state.decision_node.operational_stage
        stage=stage.value if hasattr(stage,"value") else str(stage)
        self.model.eval()
        with torch.no_grad(): history=self.model.encode_history(values,lengths)
        schedule = pre_state.successor_state.get("schedule_reference")
        schedule_value = None if schedule is None else schedule.value
        scheduled_ob_utc = None
        origin_airport_id = None
        if isinstance(schedule_value, dict):
            scheduled = schedule_value.get("scheduled_departure_utc")
            scheduled_ob_utc = None if scheduled is None else scheduled.isoformat()
            origin_airport_id = schedule_value.get("origin_airport_id")
        reference_context = {
            "tx_reference_minutes": None,
            "taxi_reference_id": None,
            "taxi_reference_hash": None,
            "taxi_reference_fallback_level": None,
            "taxi_reference_support_state": "ABSTAIN",
        }
        if taxi_reference is not None:
            if getattr(taxi_reference, "dataset_instance_id", None) != "data2_2019" \
                    or getattr(taxi_reference, "rule_id", None) != "DATA2_TAXI_REFERENCE":
                raise ValueError("M1_REQUIRES_TRAIN_FROZEN_DATA2_TAXI_REFERENCE")
            lookup = taxi_reference.lookup(origin_airport_id)
            state = getattr(lookup.support_state, "value", str(lookup.support_state))
            flags = set(getattr(lookup, "quality_flags", ()))
            fallback = next((flag.removeprefix("REFERENCE_LEVEL_") for flag in flags
                             if flag.startswith("REFERENCE_LEVEL_")), None)
            reference_context = {
                "tx_reference_minutes": lookup.value,
                "taxi_reference_id": taxi_reference.reference_id,
                "taxi_reference_hash": getattr(taxi_reference, "manifest_freeze_id", None),
                "taxi_reference_fallback_level": fallback,
                "taxi_reference_support_state": state,
            }
        return ancestral_sample(self.model,history,self.bins,episode_id=pre_state.decision_node.episode_id,
            decision_node_id=pre_state.decision_node.decision_node_id,stage=stage,observed=observed,
            count=count,seed=seed,target_support=support,scheduled_ob_utc=scheduled_ob_utc,
            **reference_context)

    def summarize(self,scenarios,**kwargs):
        from .summaries import horizon_summaries
        return horizon_summaries(scenarios,**kwargs)

    def save(self,path:Path):
        path.parent.mkdir(parents=True,exist_ok=True); torch.save({"state":self.model.state_dict(),"input_size":self.model.input_size,
            "hidden_size":self.model.hidden_size,"bins":{n:b.model_dump(exclude={"class_count"}) for n,b in self.bins.items()},
            "temperatures":self.temperatures,
            "normalization":None if self.normalization is None else self.normalization.model_dump(mode="json")},path)

    @classmethod
    def load(cls,path:Path):
        payload=torch.load(path,map_location="cpu",weights_only=True); bins={n:TargetBinContract(**v) for n,v in payload["bins"].items()}
        model=OrderedEventGRU(payload["input_size"],payload["hidden_size"],bins); model.load_state_dict(payload["state"])
        normalization=payload.get("normalization")
        if normalization is not None:
            from .data import M1NormalizationArtifact
            normalization=M1NormalizationArtifact.model_validate(normalization)
        return cls(model,bins,payload["temperatures"],normalization)
