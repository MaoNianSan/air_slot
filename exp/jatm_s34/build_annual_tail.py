"""Prepare an approved annual Train empirical tail without training M1.

Execution requires a decision record approving the N=4096 active-label
population. No decision is inferred from a missing annual artifact.
"""
import argparse
from datetime import date
import json
from pathlib import Path
import numpy as np

from model.M1.tail import EmpiricalTailContinuation
from model.M1.preparation import active_rows
from model.PRE.development import materialize_preselected_cohorts
from model.PRE.cohort import split_for_date_multiyear
from model.common.config import load_config_layers
from data2.scripts.consequence_stability_battery import load_hash_cohort,year_references
from .annual_tail import ROOT,annual_tail_path,load_annual_tail
from .shared_store import SharedStore,atomic_json,digest,file_hash,code_hash

POPULATION='ANNUAL_N4096_TRAIN_ACTIVE_POSITIVE_LABELS'


def build(year,decision_path,*,chunk_size=128):
    decision_path=Path(decision_path)
    decision=json.loads(decision_path.read_text())
    if (decision.get('status')!='USER_APPROVED' or decision.get('population')!=POPULATION
            or year not in decision.get('years',[])):
        raise ValueError('ANNUAL_TAIL_POPULATION_DECISION_REQUIRED')
    cohort_path=ROOT/'data2/reports/cohort_size_stability'/str(year)/'HASH_SELECTED_COHORT_RECORDS_N4096.jsonl'
    references=ROOT/'artifacts/models/pre/PRE_MULTIYEAR_V1'/str(year)
    paths=[cohort_path]+[references/name for name in
        ('DATA2_TAXI_REFERENCE_TRAIN_FROZEN.json','DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN.json')]
    sources={p.relative_to(ROOT).as_posix():file_hash(p) for p in paths}
    selected=load_hash_cohort(year)['train'][:4096]
    if len(selected)!=4096:raise ValueError('ANNUAL_TAIL_TRAIN_N4096_UNAVAILABLE')
    cohort=[episode for _,episode in selected]
    identity=dict(year=year,population=POPULATION,source_hashes=sources,
        cohort_ids_hash=digest([ep.episode_id for ep in cohort]),chunk_size=chunk_size,
        decision_sha256=file_hash(decision_path),algorithm=code_hash(__file__))
    output=annual_tail_path(year)
    store=SharedStore(output.parent/'train_chunks',identity)
    scientific=load_config_layers(ROOT/'configs').scientific
    taxi,turnaround=year_references(year)
    with store.writer():
        if output.exists():
            load_annual_tail(year)
            previous=json.loads(output.read_text())
            if previous.get('build_identity')!=identity:raise ValueError('ANNUAL_TAIL_EXISTING_IDENTITY_CONFLICT')
            return previous
        positives={name:[] for name in ('D_OB','D_TX')}
        for index,offset in enumerate(range(0,len(cohort),chunk_size)):
            key=f'chunk_{index:04d}'
            payload=store.read(key)
            if payload is None:
                prepared=materialize_preselected_cohorts(scientific,root=ROOT,
                    partitions={'train':tuple(cohort[offset:offset+chunk_size]),'calibration':(),'development':()},
                    year=year,dataset_instance_id='data2_2017_2022',split_resolver=split_for_date_multiyear,
                    taxi_reference=taxi,turnaround_reference=turnaround)
                rows,_=active_rows(prepared.train,taxi_reference=taxi)
                positive={name:[] for name in positives}; label_ids=[]
                for ep,prefix,labels in rows:
                    for label in labels:
                        if not date(year,1,1)<=label.episode_date<=date(year,6,30):
                            raise ValueError('ANNUAL_TAIL_LABEL_OUTSIDE_H1')
                        if label.target_name in positive and label.active and label.exact_minutes>0:
                            positive[label.target_name].append(float(label.exact_minutes))
                            label_ids.append((label.decision_node_id,label.target_name,float(label.exact_minutes)))
                payload=dict(positive=positive,label_identity_hash=digest(label_ids),node_count=len(rows))
                store.commit(key,payload)
                del prepared,rows
            for target,values in payload['positive'].items():positives[target].extend(values)
            atomic_json(output.parent/'PROGRESS.json',dict(year=year,completed_chunks=index+1,
                total_chunks=(len(cohort)+chunk_size-1)//chunk_size,positive_n={k:len(v) for k,v in positives.items()}))
        targets={name:EmpiricalTailContinuation.from_exceedances(target=name,positive_values=np.array(values),
            fit_start=f'{year}-01-01',fit_end=f'{year}-06-30',source_hashes=sources).to_payload()
            for name,values in positives.items()}
        payload=dict(schema_version='JATM_ANNUAL_TAIL_REFERENCE_V1',year=year,fit_partition='train',
            fit_start=f'{year}-01-01',fit_end=f'{year}-06-30',population=POPULATION,
            source_hashes=sources,build_identity=identity,targets=targets,
            final_test_access_count=0,model_retrained=False,parameter_reselected=False)
        payload['artifact_hash']=digest(payload)
        atomic_json(output,payload)
    load_annual_tail(year)
    return payload


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--year',type=int,choices=range(2017,2023),required=True)
    p.add_argument('--decision',type=Path,required=True);p.add_argument('--chunk-size',type=int,default=128)
    a=p.parse_args();build(a.year,a.decision,chunk_size=a.chunk_size)
