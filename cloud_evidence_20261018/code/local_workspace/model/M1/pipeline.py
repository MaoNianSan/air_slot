from pathlib import Path
import torch
from .contracts import TargetBinContract
from .network import OrderedEventGRU
from .scenarios import aligned_sample, ancestral_sample


class M1Pipeline:
    def __init__(self, model, bins, temperatures=None):
        self.model=model; self.bins=bins; self.temperatures=temperatures or {n:1.0 for n in bins}

    @classmethod
    def smoke(cls,input_size=4):
        bins={n:TargetBinContract(target_name=n,bin_width_minutes=5,max_finite_minutes=20) for n in ("R_IB","R_OB","T_TX")}
        torch.manual_seed(0); return cls(OrderedEventGRU(input_size,8,bins),bins)

    def predict_distributions(self,values,lengths):
        self.model.eval()
        with torch.no_grad(): logits=self.model(values,lengths)
        return {n:torch.softmax(logits[n]/self.temperatures[n],-1) for n in logits}

    def sample_aligned(self,dist,**kwargs): return aligned_sample(dist,self.bins,**kwargs)

    def sample_from_pre(self, pre_state, values, lengths, *, observed, count, seed):
        if values.shape[0] != 1:
            raise ValueError("formal scenario generation accepts one decision node at a time")
        support={item.target_name:(item.support_state.value if hasattr(item.support_state,"value") else str(item.support_state))
                 for item in pre_state.target_support}
        stage=pre_state.decision_node.operational_stage
        stage=stage.value if hasattr(stage,"value") else str(stage)
        self.model.eval()
        with torch.no_grad(): history=self.model.encode_history(values,lengths)
        return ancestral_sample(self.model,history,self.bins,episode_id=pre_state.decision_node.episode_id,
            decision_node_id=pre_state.decision_node.decision_node_id,stage=stage,observed=observed,
            count=count,seed=seed,target_support=support)

    def summarize(self,scenarios,**kwargs):
        from .summaries import horizon_summaries
        return horizon_summaries(scenarios,**kwargs)

    def save(self,path:Path):
        path.parent.mkdir(parents=True,exist_ok=True); torch.save({"state":self.model.state_dict(),"input_size":self.model.input_size,
            "hidden_size":self.model.hidden_size,"bins":{n:b.model_dump(exclude={"class_count"}) for n,b in self.bins.items()},"temperatures":self.temperatures},path)

    @classmethod
    def load(cls,path:Path):
        payload=torch.load(path,map_location="cpu",weights_only=True); bins={n:TargetBinContract(**v) for n,v in payload["bins"].items()}
        model=OrderedEventGRU(payload["input_size"],payload["hidden_size"],bins); model.load_state_dict(payload["state"])
        return cls(model,bins,payload["temperatures"])
