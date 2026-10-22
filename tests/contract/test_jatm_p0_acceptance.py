from dataclasses import dataclass, replace
from datetime import datetime
from types import SimpleNamespace
import json
import os

import numpy as np
import pytest

from exp.jatm_s34.shared_populations import (
    population_views, c2_key, ACTIONABLE, REPRESENTATIONS, POPULATION_CONTRACT,
)
from exp.jatm_s34.shared_statistics import recovery_loss_summary, objective_summary, recovery_coverage
from exp.jatm_s34.shared_store import atomic_json, file_hash


@dataclass
class Node:
    node_id: str
    episode_id: str
    stage: object
    consequence_scores: dict
    delay_scores: dict
    domain_scores: dict
    support_full: dict
    component_scores: dict
    chain_id: str = 'engineering-key'
    decision_time: datetime = datetime(2017, 8, 1)

    def support(self, rep):
        from model.common.decision_contracts import TypedStatus
        valid=self.support_full[rep]
        return SimpleNamespace(included=valid,supported_mass=float(valid),threshold=.9,
                               status=TypedStatus.SUPPORTED if valid else TypedStatus.ABSTAIN_NO_COMMON_SUPPORT)


def nodes():
    output=[]
    for i in range(5):
        scores={rep:float(10 if i==j else 1) for j,rep in enumerate(REPRESENTATIONS)}
        output.append(Node(str(i),str(i),ACTIONABLE[0],scores,{'HISTORY_JOINT':float(i+1)},
            {r:dict(F=1.,P=1.,R=1.) for r in REPRESENTATIONS},{r:True for r in REPRESENTATIONS},
            {r:dict(F_continuity=1.,F_execution=2.,F_propagation=3.,P_time=4.,P_itinerary=1.,P_service=0.,R_operating=5.) for r in REPRESENTATIONS}))
    return output


def test_canonical_c1_and_coverage_ignore_added_rolling_epochs():
    base=nodes();ids={n.node_id for n in base}
    extended=base+[replace(base[0],node_id='rolling'+str(i)) for i in range(7)]
    a=population_views(base,ids,year=2017)
    b=population_views(extended,ids,year=2017)
    assert [n.node_id for n in a['C1']]==[n.node_id for n in b['C1']]
    assert len(a['C3'])==0 and len(b['C3'])==8
    def records(ns):
        return [dict(node_id=n.node_id,status='ACTION_TABLE_COMPLETE',reference_decision={'recoverable_value':1.}) for n in ns]
    before=recovery_coverage(records(base),base,ids,replicates=25)
    after=recovery_coverage(records(extended),extended,ids,replicates=25)
    assert before==after
    assert before[0]['full_eligible_recoverable_value']==5


def test_unsupported_canonical_not_replaced_by_supported_rolling():
    first=replace(nodes()[0],support_full={r:False for r in REPRESENTATIONS})
    later=replace(nodes()[0],node_id='later')
    view=population_views([first,later],{first.node_id},year=2017)
    assert view['C1']==() and view['e3']==()


def test_c2_keeps_contrasts_families_and_paired_support_separate():
    ns=nodes();ids={n.node_id for n in ns}
    view=population_views(ns,ids,year=2017,q=.2,exposure_by_node={n.node_id:(1.,1.) for n in ns})
    groups=list(view['C2'].values())
    cj=next(g for g in groups if g['contrast']=='E2:HISTORY_JOINT_vs_CURRENT_JOINT' and g['stage']==ACTIONABLE[0].value)
    hp=next(g for g in groups if g['contrast']=='E2:HISTORY_JOINT_vs_HISTORY_POINT' and g['stage']==ACTIONABLE[0].value)
    delay=next(g for g in groups if g['contrast']=='E1:CONSEQUENCE_vs_DELAY' and g['stage']==ACTIONABLE[0].value)
    assert cj['node_ids']==['0','1']
    assert hp['node_ids']==['0','2']
    assert delay['node_ids']==['0','4']
    assert cj['candidate_ids']==hp['candidate_ids']==delay['candidate_ids']
    ns[4].support_full['CURRENT_JOINT']=False
    changed=population_views(ns,ids,year=2017,q=.2)
    pair=changed['pairwise_stage1']['CURRENT_JOINT'][ACTIONABLE[0].value]
    assert pair['candidate_ids']==['0','1','2','3']


@pytest.mark.parametrize('key,value',[
    ('year',2018),('stage','POST_IB_PRE_OB'),('q',.2),('contrast','E1:DELAY'),
    ('reference_objective','FLIGHT'),('cu_track','FIXED_COMMON'),
])
def test_every_c2_scientific_key_dimension_is_part_of_identity(key,value):
    base=dict(year=2017,stage='PRE_IB',q=.1,contrast='E2:HJ_CJ',reference_objective='BALANCED',cu_track='YEAR_LOCAL')
    assert c2_key(**base)!=c2_key(**dict(base,**{key:value}))


def test_ratio_of_sums_and_cluster_bootstrap_not_mean_of_ratios():
    rows=[dict(episode_id='a',reference_regret=1.,V=1.),dict(episode_id='b',reference_regret=0.,V=9.)]
    result=recovery_loss_summary(rows,replicates=2000,seed=7)
    assert result['L_rec']==.1 and result['L_rec']!=.5
    draws=np.random.default_rng(7).integers(0,2,size=(2000,2))
    expected=[sum(rows[i]['reference_regret'] for i in draw)/sum(rows[i]['V'] for i in draw) for draw in draws]
    assert result['ci_low']==np.quantile(expected,.025)
    assert result['ci_high']==np.quantile(expected,.975)
    assert result['valid_replicates']==2000


def test_ratio_zero_denominator_missing_and_duplicate_episode_multiplicity():
    rows=[dict(episode_id='a',reference_regret=1.,V=0.),dict(episode_id='a',reference_regret=0.,V=9.),
          dict(episode_id='b',reference_regret=None,V=100.)]
    result=recovery_loss_summary(rows,replicates=80,seed=3)
    assert result['L_rec']==pytest.approx(1/9)
    assert result['paired_n']==2 and result['excluded_n']==1
    assert result['zero_reference_value_n']==1
    assert result['valid_replicates']==80
    assert result['candidate_episode_n']==2 and result['episode_n']==1
    mixed=recovery_loss_summary([dict(episode_id='a',reference_regret=1.,V=0.),
                                  dict(episode_id='b',reference_regret=0.,V=9.)],replicates=80,seed=3)
    assert 0<mixed['valid_replicates']<80
    zero=recovery_loss_summary([dict(episode_id='a',reference_regret=1.,V=0.)],replicates=25)
    assert zero['L_rec'] is None and zero['ci_low'] is None and zero['valid_replicates']==0
    assert recovery_loss_summary([],replicates=25)['L_rec'] is None


def test_objective_summary_uses_joint_denominator_not_marginal_value():
    rows=[]
    for i,(loss,value) in enumerate(((1.,1.),(0.,9.))):
        base=dict(profile='FLIGHT',stage='PRE_IB',node_id=str(i),episode_id=str(i),
            J_zero=value,J_star=0.,joint_reference_loss_at_marginal_action=loss,
            relative_reference_loss_at_marginal_action=loss/value,choice_agreement=0.,
            decision_margin=1.,relative_objective_perturbation=1.)
        rows += [dict(base,representation='HISTORY_JOINT'),
                 dict(base,representation='HISTORY_MARGINAL_EXACT',J_zero=1000.)]
    summary=objective_summary(rows,replicates=25)[0]
    assert summary['recovery_loss']['L_rec']==.1
    assert summary['metrics']['node_relative_reference_loss_diagnostic']['mean']==.5
    assert 'relative_reference_loss_at_marginal_action' not in summary['metrics']


def test_c2_recovery_summary_cannot_mix_other_representations_or_fallback_denominators():
    from exp.jatm_s34.shared_statistics import summarize_actions
    ns=nodes()[:2]
    records=[]
    for i,n in enumerate(ns):
        recoveries={rep:dict(action=0.,fallback='UNSUPPORTED' if i else None)
                    for rep in ('CURRENT_JOINT','HISTORY_POINT','HISTORY_MARGINAL')}
        records.append(dict(node_id=n.node_id,status='ACTION_TABLE_COMPLETE',
            reference_decision=dict(u_star=5.),reference_objectives=[[0.,1. if i==0 else 99.],[5.,0.]],
            recoveries=recoveries))
    metadata={'C2::fixed':dict(stage=ACTIONABLE[0].value,comparator='CURRENT_JOINT')}
    _,summaries=summarize_actions(records,{'C2::fixed':{'0','1'}},{n.node_id:n for n in ns},
                                 replicates=25,population_metadata=metadata)
    assert len(summaries)==1 and summaries[0]['representation']=='CURRENT_JOINT'
    result=summaries[0]['recovery_loss']
    assert result['L_rec']==1. and result['V_ref_sum']==1.
    assert result['excluded_n']==1


EVALUATION_SUMMARIES=('E1/E1_PAIRED_SUMMARY.json','E1_FIXED_COMMON/E1_PAIRED_SUMMARY.json',
                     'E2_E3/E2_E3_SUMMARY.json')


def publish_receipts(directory,identity,stages=None):
    """Publish the v2 per-stage receipts through the production writer.

    valid_annual used to hand-write a single EVALUATION_COMPLETE receipt, which
    stopped being a valid annual result once evaluation_is_current moved to
    per-stage receipts (receipts_v2 pointers + JATM_STAGE_RECEIPT_V2 attempts).
    Building them with publish_stage_receipt keeps this fixture on the real
    contract instead of a stale approximation of it.
    """
    from exp.jatm_s34.shared_run import (
        EVALUATION_STAGES,evaluation_stage_identity,publish_stage_receipt)
    published={}
    for stage,folder,summary in EVALUATION_STAGES:
        if stages is not None and stage not in stages:
            continue
        stage_id=evaluation_stage_identity(directory,identity,stage)
        published[stage]=publish_stage_receipt(directory,stage,stage_id,folder,summary)
    return published


def valid_annual(root,year):
    directory=root/str(year)
    atomic_json(directory/'RUN_MANIFEST.json',dict(year=year,scope='FULL_DEVELOPMENT',status='COMPUTED_PENDING_SCIENTIFIC_ACCEPTANCE'))
    atomic_json(directory/'shared/CACHE_MANIFEST.json',dict(identity=dict(year=year,cu_contract=dict(track='YEAR_LOCAL',reference_year=year))))
    atomic_json(directory/'shared/SHARED_ANNUAL_MANIFEST.json',{'fixture':True})
    e1=dict(replicates=2000,rows=[],final_test_access_count=0)
    atomic_json(directory/'E1/E1_PAIRED_SUMMARY.json',dict(e1,cu_reference_label='YEAR_LOCAL_V5'))
    atomic_json(directory/'E1_FIXED_COMMON/E1_PAIRED_SUMMARY.json',dict(e1,cu_reference_label='FIXED_COMMON_2017_H1_V5'))
    payload=dict(year=year,scope='FULL_DEVELOPMENT',schema_version='JATM_SHARED_E2_E3_V3_P1',
        status='DEVELOPMENT_COMPUTED_PENDING_SCIENTIFIC_ACCEPTANCE',
        bootstrap_replicates=2000,population_contract=POPULATION_CONTRACT,
        recovery_loss_estimand='RATIO_OF_SUMS_DELTA_REC_OVER_REFERENCE_V',
        action_identity=dict(fixed_common_contract=dict(track='FIXED_COMMON',reference_year=2017)),
        support_denominator=1,reference_cohort_count=1,population_counts_by_stage={},
        information=[],e3_summary=[],populations={'C3':[]},
        e1_recovery_opportunity_coverage=[{} for _ in range(128)],
        fixed_common_e1_recovery_opportunity_coverage=[{} for _ in range(128)],
        policy_sensitivity_settings=[{'policy_id':'NOMINAL'}],
        policy_sensitivity_rows=[],fixed_common_policy_sensitivity_rows=[],
        policy_sensitivity_missing_nodes=[],fixed_common_policy_sensitivity_missing_nodes=[],
        final_test_access_count=0)
    atomic_json(directory/'E2_E3/E2_E3_SUMMARY.json',payload)
    identity={'fixture':'expected-current-code-and-inputs'}
    atomic_json(directory/'EVALUATION_COMPLETE.json',dict(identity=identity,
        outputs={n:file_hash(directory/n) for n in EVALUATION_SUMMARIES},
        stage_receipts=publish_receipts(directory,identity)))
    return identity


def test_e4_missing_year_is_partial_and_failed_run_cannot_reuse_stale_success(tmp_path,monkeypatch):
    from exp.jatm_s34.e4_shared_aggregate import aggregate,inspect_annual_result
    import exp.jatm_s34.shared_run as shared
    identity=valid_annual(tmp_path,2017)
    monkeypatch.setattr(shared,'evaluation_identity',lambda _:identity)
    result=aggregate(tmp_path,tmp_path/'E4')
    assert result['status']=='PARTIAL_DEVELOPMENT' and not result['six_year_complete']
    assert len(result['blocked_years'])==5
    atomic_json(tmp_path/'2017/RUN_MANIFEST.json',dict(year=2017,status='FAILED',scope='FULL_DEVELOPMENT'))
    assert inspect_annual_result(tmp_path,2017)[0]['status']=='ANNUAL_RUN_NOT_COMPLETE'
    assert aggregate(tmp_path,tmp_path/'E4_2')['status']=='SIX_YEAR_EXECUTION_BLOCKED'


def test_e4_rejects_stale_receipt_and_old_estimand_even_when_output_hashes_match(tmp_path,monkeypatch):
    import exp.jatm_s34.shared_run as shared
    from exp.jatm_s34.e4_shared_aggregate import inspect_annual_result
    identity=valid_annual(tmp_path,2017)
    monkeypatch.setattr(shared,'evaluation_identity',lambda _:dict(identity,algorithm='changed'))
    assert inspect_annual_result(tmp_path,2017)[0]['status']=='EVALUATION_RECEIPT_MISSING_OR_OUTPUT_HASH_MISMATCH'
    monkeypatch.setattr(shared,'evaluation_identity',lambda _:identity)
    path=tmp_path/'2017/E2_E3/E2_E3_SUMMARY.json'
    payload=json.loads(path.read_text());payload['recovery_loss_estimand']='NODE_MEAN'
    atomic_json(path,payload)
    receipt=tmp_path/'2017/EVALUATION_COMPLETE.json';data=json.loads(receipt.read_text())
    data['outputs']['E2_E3/E2_E3_SUMMARY.json']=file_hash(path)
    # Keep the receipt internally consistent, so the only thing wrong is the
    # estimand: re-publish the E2_E3 stage receipt for the tampered summary.
    data['stage_receipts'].update(publish_receipts(tmp_path/'2017',identity,stages={'E2_E3'}))
    atomic_json(receipt,data)
    assert inspect_annual_result(tmp_path,2017)[0]['status']=='STATISTICS_OR_REFERENCE_INCOMPLETE'


def fake_scheduler(monkeypatch,tmp_path,successful_years):
    import exp.jatm_s34.cloud_schedule as mod
    started=[]
    class Worker:
        def __init__(self,cmd,**kwargs):
            year=int(cmd[cmd.index('--year')+1]);started.append(year);self.pid=os.getpid()
            self.returncode=0 if year in successful_years else 2
            atomic_json(tmp_path/str(year)/'RUN_MANIFEST.json',dict(year=year,scope='FULL_DEVELOPMENT',
                status='COMPUTED_PENDING_SCIENTIFIC_ACCEPTANCE' if self.returncode==0 else 'DATA_INSUFFICIENT',
                reason=None if self.returncode==0 else 'TAIL_MISSING' if year==2018 else 'ANNUAL_MODELS_MISSING'))
        def poll(self):return self.returncode
    monkeypatch.setattr(mod.subprocess,'Popen',Worker)
    monkeypatch.setattr(mod.signal,'signal',lambda *_:None)
    monkeypatch.setattr(mod.psutil,'virtual_memory',lambda:SimpleNamespace(available=128*1024**3))
    monkeypatch.setattr(mod.time,'sleep',lambda *_:None)
    args=SimpleNamespace(output_root=tmp_path,years=list(range(2017,2023)),threads=1,workers=2,
        cpu_budget=32,memory_per_worker_gib=24,reserve_gib=12,chunk_size=2,device='cpu',phase='all',episode_limit=None)
    return mod,args,started


def test_scheduler_partial_input_failure_never_enters_full_e4(tmp_path,monkeypatch):
    mod,args,started=fake_scheduler(monkeypatch,tmp_path,{2017})
    import exp.jatm_s34.e4_shared_aggregate as e4
    monkeypatch.setattr(e4,'aggregate',lambda *_:pytest.fail('FULL_E4_STARTED_WITH_FAILED_YEARS'))
    result=mod.schedule(args)
    assert started==list(range(2017,2023))
    assert result['status']=='SIX_YEAR_EXECUTION_BLOCKED' and not result['six_year_complete']
    assert result['annual_outcomes']['2018']['run_manifest']['reason']=='TAIL_MISSING'


def test_scheduler_successful_exit_without_valid_outputs_stays_blocked(tmp_path,monkeypatch):
    mod,args,_=fake_scheduler(monkeypatch,tmp_path,set(range(2017,2023)))
    result=mod.schedule(args)
    assert result['status']=='SIX_YEAR_EXECUTION_BLOCKED' and not result['six_year_complete']


def test_all_six_validated_outputs_allow_human_review_but_not_scientific_pass(tmp_path,monkeypatch):
    import exp.jatm_s34.shared_run as shared
    for year in range(2017,2023):identity=valid_annual(tmp_path,year)
    monkeypatch.setattr(shared,'evaluation_identity',lambda _:identity)
    mod,args,_=fake_scheduler(monkeypatch,tmp_path,set(range(2017,2023)))
    result=mod.schedule(args)
    assert result['status']=='WAITING_HUMAN_CONFIRMATION' and result['six_year_complete']
    assert result['e4']['scientific_acceptance']=='PENDING_NOT_IMPLIED_BY_COMPUTATION'
