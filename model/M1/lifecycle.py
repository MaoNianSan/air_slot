from dataclasses import dataclass
from datetime import date
from pathlib import Path

import torch

from .calibration import fit_temperature
from .loss import exact_nll
from .pipeline import M1Pipeline
from .contracts import M1TargetLabel
from model.PRE.contracts.pre_state import TargetSupportState


@dataclass(frozen=True)
class M1TrainingExample:
    episode_id: str
    episode_date: date
    values: torch.Tensor
    labels: dict[str, int]
    active: dict[str, bool]

    @classmethod
    def from_pre_support(cls, *, episode_id, episode_date, values, labels,
                         target_support: tuple[TargetSupportState, ...]):
        active={item.target_name:item.active and str(item.support_state.value)!="ABSTAIN"
                for item in target_support}
        return cls(episode_id=episode_id,episode_date=episode_date,values=values,
                   labels=labels,active=active)

    @classmethod
    def from_target_labels(cls, *, values: torch.Tensor,
                           labels: tuple[M1TargetLabel, ...], bins):
        if {item.target_name for item in labels} != {"R_IB", "R_OB", "T_TX"}:
            raise ValueError("M1_TYPED_TARGET_SET_INCOMPLETE")
        episodes={item.episode_id for item in labels}; dates={item.episode_date for item in labels}
        if len(episodes)!=1 or len(dates)!=1:
            raise ValueError("M1_TYPED_TARGET_IDENTITY_MISMATCH")
        categorical={}
        active={}
        for item in labels:
            if item.label_status == "INTERVAL":
                raise ValueError("M1_INTERVAL_LABEL_REQUIRES_INTERVAL_LOSS_PATH")
            active[item.target_name]=item.active
            categorical[item.target_name]=bins[item.target_name].encode(item.exact_minutes) \
                if item.active else 0
        return cls(episode_id=next(iter(episodes)),episode_date=next(iter(dates)),
            values=values,labels=categorical,active=active)


def chronological_split(examples):
    boundaries=(("train",date(2019,6,30)),("calibration",date(2019,7,31)),
                ("development",date(2019,9,30)),("test",date.max))
    output={name:[] for name,_ in boundaries}; membership={}
    for example in sorted(examples,key=lambda row:(row.episode_date,row.episode_id)):
        split=next(name for name,end in boundaries if example.episode_date<=end)
        previous=membership.setdefault(example.episode_id,split)
        if previous!=split: raise ValueError("episode crosses chronological split")
        output[split].append(example)
    return output


class M1Lifecycle:
    def __init__(self,pipeline): self.pipeline=pipeline

    @staticmethod
    def _batch(examples):
        lengths=torch.tensor([row.values.shape[0] for row in examples])
        values=torch.nn.utils.rnn.pad_sequence([row.values for row in examples],batch_first=True)
        labels={name:torch.tensor([row.labels[name] for row in examples]) for name in ("R_IB","R_OB","T_TX")}
        active={name:torch.tensor([row.active[name] for row in examples],dtype=torch.bool) for name in labels}
        return values,lengths,labels,active

    def train(self,examples,*,epochs,learning_rate):
        if not examples: raise ValueError("empty chronological training split")
        values,lengths,labels,active=self._batch(examples); optimizer=torch.optim.Adam(self.pipeline.model.parameters(),lr=learning_rate); history=[]
        for _ in range(epochs):
            optimizer.zero_grad(); logits=self.pipeline.model(values,lengths,teacher={"R_IB":labels["R_IB"],"R_OB":labels["R_OB"],"_active":active})
            losses=[exact_nll(logits[name],labels[name],active[name]) for name in logits]
            loss=sum(losses); loss.backward(); optimizer.step()
            history.append({"loss":float(loss.detach()),"active_counts":{name:int(mask.sum()) for name,mask in active.items()}})
        return tuple(history)

    def calibrate(self,examples):
        if not examples: raise ValueError("empty calibration split")
        values,lengths,labels,active=self._batch(examples); self.pipeline.model.eval()
        with torch.no_grad(): logits=self.pipeline.model(values,lengths,teacher={"R_IB":labels["R_IB"],"R_OB":labels["R_OB"],"_active":active})
        self.pipeline.temperatures={name:fit_temperature(logits[name],labels[name],active[name]) for name in logits}
        return dict(self.pipeline.temperatures)

    def infer(self,values,lengths): return self.pipeline.predict_distributions(values,lengths)
    def sample(self,pre_state,values,lengths,**kwargs): return self.pipeline.sample_from_pre(pre_state,values,lengths,**kwargs)
    def save(self,path:Path): self.pipeline.save(path)

    @classmethod
    def load(cls,path:Path): return cls(M1Pipeline.load(path))
