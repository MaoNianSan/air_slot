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
    decision_node_id: str | None = None

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
        node_ids={item.decision_node_id for item in labels}
        if len(node_ids)!=1:
            raise ValueError("M1_TYPED_TARGET_NODE_IDENTITY_MISMATCH")
        return cls(episode_id=next(iter(episodes)),episode_date=next(iter(dates)),
            values=values,labels=categorical,active=active,
            decision_node_id=next(iter(node_ids)))


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
    def __init__(self,pipeline, *, device="cpu"):
        self.pipeline=pipeline
        self.device=self._resolve_device(device)
        self.pipeline.model.to(self.device)

    @staticmethod
    def _resolve_device(device):
        if device == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        resolved=torch.device(device)
        if resolved.type == "cuda" and not torch.cuda.is_available():
            raise ValueError("M1_CUDA_REQUESTED_BUT_UNAVAILABLE")
        if resolved.type not in {"cpu","cuda"}:
            raise ValueError(f"M1_DEVICE_UNSUPPORTED:{resolved.type}")
        return resolved

    @staticmethod
    def _batch(examples, *, device=None):
        target=torch.device("cpu") if device is None else torch.device(device)
        lengths=torch.tensor([row.values.shape[0] for row in examples],dtype=torch.long)
        values=torch.nn.utils.rnn.pad_sequence(
            [row.values for row in examples],batch_first=True).to(target)
        labels={name:torch.tensor([row.labels[name] for row in examples],
                                  dtype=torch.long,device=target)
                for name in ("R_IB","R_OB","T_TX")}
        active={name:torch.tensor([row.active[name] for row in examples],
                                  dtype=torch.bool,device=target) for name in labels}
        return values,lengths,labels,active

    @staticmethod
    def _batch_indices(examples, batch_size, *, bucketed):
        if batch_size is None:
            return (tuple(range(len(examples))),)
        if batch_size <= 0:
            raise ValueError("M1_BATCH_SIZE_MUST_BE_POSITIVE")
        order=list(range(len(examples)))
        if bucketed:
            order.sort(key=lambda index:(examples[index].values.shape[0],index))
        return tuple(tuple(order[start:start+batch_size])
                     for start in range(0,len(order),batch_size))

    @classmethod
    def batching_diagnostics(cls, examples, *, batch_size, bucketed=True):
        batches=cls._batch_indices(examples,batch_size,bucketed=bucketed)
        actual=sum(int(examples[index].values.shape[0])
                   for batch in batches for index in batch)
        padded=sum(max(int(examples[index].values.shape[0]) for index in batch)*len(batch)
                   for batch in batches if batch)
        return {"sample_count":len(examples),"batch_count":len(batches),
                "actual_nodes":actual,"padded_nodes":padded,
                "padding_fraction":0.0 if padded==0 else 1.0-actual/padded}

    def train(self,examples,*,epochs,learning_rate,batch_size=None,seed=None,
              progress_callback=None):
        if not examples: raise ValueError("empty chronological training split")
        batches=self._batch_indices(examples,batch_size,bucketed=batch_size is not None)
        optimizer=torch.optim.Adam(self.pipeline.model.parameters(),lr=learning_rate); history=[]
        totals={name:sum(int(examples[index].active[name]) for index in range(len(examples)))
                for name in ("R_IB","R_OB","T_TX")}
        diagnostics=self.batching_diagnostics(
            examples,batch_size=batch_size,bucketed=batch_size is not None)
        for epoch_index in range(epochs):
            self.pipeline.model.train(); optimizer.zero_grad()
            target_losses={name:0.0 for name in totals}
            for indices in batches:
                batch=[examples[index] for index in indices]
                values,lengths,labels,active=self._batch(batch,device=self.device)
                logits=self.pipeline.model(values,lengths,teacher={
                    "R_IB":labels["R_IB"],"R_OB":labels["R_OB"],"_active":active})
                contributions=[]
                for name in logits:
                    losses=torch.nn.functional.cross_entropy(
                        logits[name],labels[name],reduction="none")*active[name].float()
                    numerator=losses.sum()
                    contribution=numerator/max(totals[name],1)
                    contributions.append(contribution)
                    target_losses[name]+=float(contribution.detach())
                sum(contributions).backward()
            optimizer.step()
            row={"epoch":epoch_index + 1,
                 "loss":sum(target_losses.values()),
                 "target_losses":target_losses,
                 "active_counts":dict(totals),
                 "microbatch_count":len(batches),
                 "optimizer_steps":1,
                 "padding_fraction":diagnostics["padding_fraction"],
                 "seed":seed}
            history.append(row)
            if progress_callback is not None:
                progress_callback(row)
        return tuple(history)

    def batched_logits(self,examples,*,batch_size=None,teacher_forcing=True):
        if not examples: raise ValueError("empty M1 inference split")
        batches=self._batch_indices(examples,batch_size,bucketed=batch_size is not None)
        output={name:None for name in ("R_IB","R_OB","T_TX")}
        all_labels={name:torch.empty(len(examples),dtype=torch.long) for name in output}
        all_active={name:torch.empty(len(examples),dtype=torch.bool) for name in output}
        self.pipeline.model.eval()
        with torch.no_grad():
            for indices in batches:
                batch=[examples[index] for index in indices]
                values,lengths,labels,active=self._batch(batch,device=self.device)
                teacher=None if not teacher_forcing else {
                    "R_IB":labels["R_IB"],"R_OB":labels["R_OB"],"_active":active}
                logits=self.pipeline.model(values,lengths,teacher=teacher)
                target_indices=torch.tensor(indices,dtype=torch.long)
                for name,value in logits.items():
                    value=value.detach().cpu()
                    if output[name] is None:
                        output[name]=torch.empty((len(examples),value.shape[1]),dtype=value.dtype)
                    output[name][target_indices]=value
                    all_labels[name][target_indices]=labels[name].detach().cpu()
                    all_active[name][target_indices]=active[name].detach().cpu()
        return output,all_labels,all_active

    def calibrate(self,examples,*,batch_size=None):
        if not examples: raise ValueError("empty calibration split")
        logits,labels,active=self.batched_logits(
            examples,batch_size=batch_size,teacher_forcing=True)
        self.pipeline.temperatures={name:fit_temperature(logits[name],labels[name],active[name]) for name in logits}
        return dict(self.pipeline.temperatures)

    def infer(self,values,lengths): return self.pipeline.predict_distributions(values,lengths)
    def sample(self,pre_state,values,lengths,**kwargs): return self.pipeline.sample_from_pre(pre_state,values,lengths,**kwargs)
    def save(self,path:Path): self.pipeline.save(path)

    @classmethod
    def load(cls,path:Path,*,device="cpu"): return cls(M1Pipeline.load(path),device=device)
