import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from exp.jatm_s34.shared_store import SharedStore, atomic_json, digest


def test_numeric_objective_keys_survive_atomic_roundtrip(tmp_path):
    store=SharedStore(tmp_path,{'year':2017})
    payload={'differences':{0.:0.,5.:.3,10.:.8,15.:1.1}}
    store.commit('node',payload)
    restored=store.read('node')
    assert digest(restored)==digest(payload)
    store.commit('node',payload)


def test_revaluation_uses_distinct_scales_without_changing_support():
    from dataclasses import dataclass
    from exp.jatm_s34.shared_revaluation import revalue_nodes
    from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
    @dataclass
    class Node:
        component_scores: dict
        consequence_scores: dict
        domain_scores: dict
        support: str = 'unchanged'
    keys = tuple(CONSEQUENCE_COMPONENTS)
    source = SimpleNamespace(scales={k:float(i+1) for i,k in enumerate(keys)})
    target = SimpleNamespace(scales={k:float(2*i+3) for i,k in enumerate(keys)})
    native = {k:float(i+4) for i,k in enumerate(keys)}
    node = Node({'HJ':{k:native[k]/source.scales[k] for k in keys},'HM':None},{},{})
    result, = revalue_nodes((node,),source,target)
    assert result.component_scores['HJ'] == pytest.approx({k:native[k]/target.scales[k] for k in keys})
    assert result.component_scores['HM'] is None
    assert result.support == node.support
    assert node.component_scores['HJ'] != result.component_scores['HJ']


def test_rolling_analysis_keeps_episode_and_admissible_epoch_identity():
    from exp.jatm_s34.e4_shared_aggregate import rolling_analysis
    def row(nid,episode,time,value):
        return dict(node_id=nid,episode_id=episode,decision_time=time,representation='HM',stage='PRE',
                    u_joint=value,u_comparator=value+5,normalized_regret=value/10,V=value*2)
    rows=[row('a2','a','02',10),row('b1','b','01',99),row('a1','a','01',5),row('a3','a','03',200)]
    result=rolling_analysis(rows,{'a1','a2','b1'},replicates=25)
    assert len(result['changes'])==1
    change=result['changes'][0]
    assert (change['first_node'],change['last_node'],change['epochs'])==('a1','a2',2)
    assert change['delta_u_joint']==5
    assert change['delta_recoverable_value']==10
    assert len(result['trajectories'])==2


def test_gpu_fallback_is_explicit_and_full_cuda_stays_gated():
    from exp.jatm_s34.runtime_provenance import select_device
    assert select_device('cuda',cuda_available=False)==('cpu','CUDA_UNAVAILABLE_CPU_FALLBACK')
    assert select_device('auto',cuda_available=True)[0]=='cpu'
    assert select_device('cuda',cuda_available=True,pilot=True)[0]=='cuda'
    with pytest.raises(RuntimeError,match='EQUIVALENCE'):select_device('cuda',cuda_available=True)


def test_annual_authorities_have_no_legacy_cache_dependency(monkeypatch):
    import validation.v2_phase5.common as legacy
    monkeypatch.setattr(legacy,'load_authorities',lambda:pytest.fail('LOADED_2019_AUTHORITY'))
    from exp.jatm_s34.annual_bridge import load_annual_authorities
    authority=load_annual_authorities(2017)
    assert authority.cache is None
    assert authority.h16_manifest['year']==authority.current_manifest['year']==2017
    assert authority.h16_manifest['training_seed']==authority.current_manifest['training_seed']==20260813
    assert authority.registry.provenance['reference_year']==2017


def test_streaming_bootstrap_matches_dense_paired_draws():
    from exp.jatm_s34.shared_statistics import clustered_summary
    rows=[dict(episode_id=ep,a=a,b=b) for ep,a,b in
          [('a',1.,None),('a',3.,4.),('b',8.,2.),('c',None,0.)]]
    actual=clustered_summary(rows,('a','b'),replicates=83,seed=31)
    draws=np.random.default_rng(31).integers(0,3,size=(83,3))
    for metric in ('a','b'):
        values=[]
        for draw in draws:
            sample=[r[metric] for i in draw for r in rows if r['episode_id']==['a','b','c'][i] and r[metric] is not None]
            if sample:values.append(np.mean(sample))
        assert actual['metrics'][metric]['valid_replicates']==len(values)
        assert actual['metrics'][metric]['ci_low']==np.quantile(values,.025)
        assert actual['metrics'][metric]['ci_high']==np.quantile(values,.975)


def test_direct_exposure_reference_keeps_zero_delay_case():
    from exp.jatm_s34.e1_information_gain import _exposure_factors
    scenario=SimpleNamespace(scenario_id=0,d_to_minutes=0.)
    consequence=SimpleNamespace(scenario_id=0,native_components={'P_time':0.,'F_propagation':0.})
    node=SimpleNamespace(node_id='zero',state=lambda _:SimpleNamespace(scenarios=[scenario]),
                         consequences=lambda _:SimpleNamespace(scenarios=[consequence]))
    binding=SimpleNamespace(expected_pax=150.,downstream_exposure=2.)
    factors,audit=_exposure_factors(node,binding,direct_reference_zero_valid=True)
    assert factors==(150.,2.)
    assert audit['status']=='PASS_DIRECT_REFERENCE_ZERO_DELAY_NO_RATIO'
    assert _exposure_factors(node,None,direct_reference_zero_valid=True)[0] is None


def test_scheduler_isolates_scientific_failure_and_continues(tmp_path,monkeypatch):
    import exp.jatm_s34.cloud_schedule as mod
    starts=[]
    class Worker:
        def __init__(self,cmd,**kwargs):
            year=int(cmd[cmd.index('--year')+1]);starts.append(year)
            self.pid=os.getpid();self.returncode=2 if year==2017 else 0
            atomic_json(tmp_path/str(year)/'RUN_MANIFEST.json',dict(year=year,
                status='SCIENTIFIC_BLOCKED' if year==2017 else 'STAGE_I_COMPLETE'))
        def poll(self):return self.returncode
    monkeypatch.setattr(mod.subprocess,'Popen',Worker)
    monkeypatch.setattr(mod.signal,'signal',lambda *_:None)
    monkeypatch.setattr(mod.psutil,'virtual_memory',lambda:SimpleNamespace(available=128*1024**3))
    monkeypatch.setattr(mod.time,'sleep',lambda *_:None)
    args=SimpleNamespace(output_root=tmp_path,years=[2017,2018],threads=1,workers=2,cpu_budget=32,
        memory_per_worker_gib=24,reserve_gib=12,chunk_size=2,device='cpu',phase='stage1',episode_limit=2)
    result=mod.schedule(args)
    assert starts==[2017,2018]
    assert [r['run_manifest']['status'] for r in result['finished']]==['SCIENTIFIC_BLOCKED','STAGE_I_COMPLETE']
    assert not (tmp_path/'WRITER.json').exists()


def test_config_rejects_test_or_unrecognized_overrides(tmp_path):
    from exp.jatm_s34.cloud_schedule import from_config
    path=tmp_path/'config.json'
    base=dict(years=[2017],output_root=str(tmp_path/'out'),stop_before_test=True,resume=True)
    path.write_text(json.dumps(dict(base,stop_before_test=False)))
    with pytest.raises(ValueError,match='DEVELOPMENT_ONLY'):from_config(path)
    path.write_text(json.dumps(dict(base,test=True)))
    with pytest.raises(ValueError,match='UNKNOWN'):from_config(path)


def test_population_views_keep_full_eligible_and_pairwise_support():
    from exp.jatm_s34.shared_populations import population_views,REPRESENTATIONS,ACTIONABLE
    def node(nid,episode,*,supported=True,current=True):
        flags={rep:supported and (current or rep!='CURRENT_JOINT') for rep in REPRESENTATIONS}
        return SimpleNamespace(node_id=nid,episode_id=episode,chain_id='engineering-day',stage=ACTIONABLE[0],
            support_full=flags,support=lambda rep:SimpleNamespace(included=flags[rep],supported_mass=float(flags[rep]),threshold=.9),
            consequence_scores={rep:1. if flags[rep] else None for rep in flags},
            domain_scores={rep:{'F':1.,'P':1.,'R':1.} if flags[rep] else None for rep in flags})
    nodes=[node('a0','a',supported=False),node('a1','a',current=False),node('a2','a',current=False),
           node('b0','b'),node('c0','c',current=False)]
    view=population_views(nodes,{'a0','b0','c0'})
    assert {n.node_id for n in view['C1']}=={'a1','a2','b0','c0'}
    assert {n.node_id for n in view['C1_CANONICAL']}=={'b0','c0'}
    assert {n.node_id for n in view['C3']}=={'a1','a2'}
    assert {n.node_id for n in view['e3']}=={'a1','a2','b0','c0'}
    assert view['pairwise_stage1']['CURRENT_JOINT'][ACTIONABLE[0].value]['candidate_ids']==['b0']
    assert view['pairwise_stage1']['HISTORY_POINT'][ACTIONABLE[0].value]['candidate_ids']==['b0','c0']


def test_missing_primitive_blocks_only_exact_projection():
    from model.common.decision_contracts import StateScenario,StateScenarioSet,StateRepresentationSpec,TemporalKind,UncertaintyKind
    from model.common.enums import OperationalStage,SupportState
    from exp.jatm_s34.exact_stream import project
    stage=OperationalStage.PRE_IB
    source=StateScenarioSet(episode_id='a',chain_id='c',node_id='n',stage=stage,
        representation=StateRepresentationSpec(temporal=TemporalKind.HISTORY,uncertainty=UncertaintyKind.JOINT,history_capacity=16,history_scope='FULL_PREFIX'),
        scenarios=(StateScenario(scenario_id=0,scenario_weight=1,stage=stage,support=SupportState.ABSTAIN),))
    node=SimpleNamespace(episode_id='a',chain_id='c',node_id='n',stage=stage,state=lambda _:source)
    values,state,consequence,support,audit=project(node,None)
    assert values['consequence'] is None and not support.included
    assert audit['status']=='UNKNOWN_INSUFFICIENT_PAYLOAD'
    assert source.scenarios[0].support is SupportState.ABSTAIN


def test_weather_overlay_keeps_legal_prefix_and_restores_by_hash(tmp_path):
    from exp.jatm_s34.prepare_transfer import weather_prefix
    source=tmp_path/'weather.csv';out=tmp_path/'overlay/weather.csv'
    source.write_text('DATE,VALUE\n2017-01-02,1\n2017-09-30,2\n2017-10-01,PROTECTED\n')
    before=source.read_bytes()
    receipt=weather_prefix(source,out,2017)
    assert receipt['rows']==2
    assert 'PROTECTED' not in out.read_text()
    assert weather_prefix(source,out,2017)==receipt
    assert source.read_bytes()==before
    out.write_text('corrupt')
    with pytest.raises(ValueError,match='IDENTITY_CONFLICT'):weather_prefix(source,out,2017)


def test_mechanism_operators_keep_baseline_components_and_ob_constraint():
    from model.common.decision_contracts import StateScenario
    from model.common.enums import OperationalStage
    from model.M3.transition import TransitionContext
    from exp.jatm_s34.mechanisms import curves
    from exp.jatm_s34.scientific_tracks import nominal_headroom
    class Service:
        def consequence_scenario(self,s,**kwargs):
            return SimpleNamespace(native_components=dict(F_continuity=s.t_ib_minutes,
                F_execution=s.d_ob_minutes,F_propagation=s.d_tx_minutes,
                P_time=s.d_to_minutes,P_itinerary=float(s.d_to_minutes>=45),
                P_service=float(s.d_to_minutes>=180),R_operating=s.d_ob_minutes))
        def to_cu(self,native):return native
    scenario=StateScenario(scenario_id=0,scenario_weight=1,stage=OperationalStage.PRE_IB,
        t_ib_minutes=60,d_ob_minutes=20,d_tx_minutes=30,d_to_minutes=50)
    state=SimpleNamespace(scenarios=(scenario,),node_id='x',representation=SimpleNamespace(representation_id='HJ'))
    ledger=[]
    curves(state,TransitionContext(sobt_minutes=70,turnaround_lower_bound_minutes=41),
        Service(),nominal_headroom(2017),ledger=ledger.append)
    for row in ledger:
        if not row['threshold_on']:
            assert row['native']['P_itinerary']==1
            assert row['native']['P_service']==0
        if not row['headroom_on']:
            assert row['native']['F_execution']==max(20-row['u'],0)
            assert row['native']['P_time']==max(20-row['u'],0)+30
