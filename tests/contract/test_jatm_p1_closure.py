"""Targeted P1 export checks; no model training or annual execution."""
from types import SimpleNamespace

import pytest

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.enums import OperationalStage


def _node(nid, delay, consequence, *, stage=OperationalStage.PRE_IB):
    return SimpleNamespace(node_id=nid,episode_id=nid,chain_id=nid,stage=stage,
        delay_scores={'HISTORY_JOINT':delay},
        component_scores={'HISTORY_JOINT':{k:consequence for k in CONSEQUENCE_COMPONENTS}},
        support=lambda _:SimpleNamespace(included=True))


def _record(nid,value):
    return dict(node_id=nid,status='ACTION_TABLE_COMPLETE',rows=[
        dict(profile=profile,representation='HISTORY_JOINT',J_zero=value,J_star=0.)
        for profile in ('BALANCED','FLIGHT','PASSENGER','RESOURCE')])


def test_e1_four_view_recovery_coverage_uses_one_full_c1_denominator():
    from exp.jatm_s34.shared_statistics import e1_recovery_coverage
    nodes=[_node('a',10,1),_node('b',8,2),_node('c',1,4)]
    factors={'a':(1,1),'b':(10,1),'c':(1,100)}
    rows=e1_recovery_coverage([_record('a',1),_record('b',2),_record('c',4)],nodes,
        {'a','b','c'},factors,c1_ids={'a','b','c'},q_grid=(.30,),replicates=29,seed=3)
    pre={row['view']:row for row in rows if row['profile']=='BALANCED' and row['stage']=='PRE_IB'}
    assert set(pre)=={'DELAY','DELAY_PASSENGER','DELAY_DOWNSTREAM','CONSEQUENCE'}
    assert {row['k'] for row in pre.values()}=={1}
    assert {row['screening_candidate_n'] for row in pre.values()}=={3}
    assert {row['reference_recoverable_value_sum'] for row in pre.values()}=={7.}
    assert pre['DELAY']['coverage']==pytest.approx(1/7)
    assert pre['DELAY_PASSENGER']['coverage']==pytest.approx(2/7)
    assert pre['DELAY_DOWNSTREAM']['coverage']==pytest.approx(4/7)
    assert pre['CONSEQUENCE']['coverage']==pytest.approx(4/7)
    assert pre['DELAY_PASSENGER']['paired_delta_vs_delay']==pytest.approx(1/7)
    assert pre['DELAY_PASSENGER']['valid_replicates']==29


def test_e1_coverage_does_not_replace_missing_c1_action_with_zero():
    from exp.jatm_s34.shared_statistics import e1_recovery_coverage
    nodes=[_node('a',10,1),_node('b',8,2)]
    rows=e1_recovery_coverage([_record('a',1)],nodes,{'a','b'},
        {'a':(1,1),'b':(2,2)},c1_ids={'a','b'},q_grid=(.5,),replicates=7)
    row=next(row for row in rows if row['stage']=='PRE_IB' and row['profile']=='BALANCED')
    assert row['status']=='INCOMPLETE_C1_REFERENCE_ACTIONS'
    assert row['coverage'] is None and row['valid_replicates']==0
    assert row['missing_reference_node_ids']==['b']


def test_mechanism_export_has_paper_sign_without_changing_legacy_difference(monkeypatch):
    import exp.jatm_s34.mechanisms as mod
    tables={'HISTORY_JOINT':{(True,True,'BALANCED'):[[0.,3.],[5.,1.]]},
            'HISTORY_MARGINAL_EXACT':{(True,True,'BALANCED'):[[0.,4.],[5.,2.]]}}
    monkeypatch.setattr(mod,'curves',lambda state,*_args,**_kwargs:tables[state])
    node=SimpleNamespace(node_id='n',episode_id='e',stage=OperationalStage.PRE_IB,state=lambda rep:rep)
    row=mod.compare(node,None,None,None)[0]
    assert row['joint_curve']==[[0.,3.],[5.,1.]]
    assert row['fixed_target_difference']=={0.:1.,5.:1.}
    assert row['e_joint_minus_marginal']=={0.:-1.,5.:-1.}
    assert row['reference_regret']==0.


def test_nominal_policy_does_not_load_annual_train_fit(monkeypatch):
    import exp.jatm_s34.scientific_tracks as tracks
    monkeypatch.setattr(tracks,'_headroom',lambda *_:pytest.fail('ANNUAL_FIT_LOADED_FOR_NOMINAL'))
    policy=tracks.nominal_headroom(2017)
    assert (policy.turnaround_lower_bound_q,policy.u_max,policy.floor_to_minutes)==(41.,45.,5.)
    assert policy.headroom_positive_n==0
    assert tracks.nominal_policy_metadata()['fit_status']=='NOT_ANNUAL_TRAIN_ESTIMATE'


def test_policy_grid_is_one_factor_and_range_slope_tracks_are_distinct(monkeypatch):
    from exp.jatm_s34 import policy_sensitivity as mod
    from model.M3.stage2 import action_grid
    from exp.jatm_s34.e2_e3_exact import PROFILES
    settings=mod.policy_settings()
    assert len(settings)==10 and len({s['policy_id'] for s in settings})==10
    assert settings[0]==dict(policy_id='NOMINAL',variation='MAIN',turnaround=41.,
                             u_max=45.,lambda_policy=.25)
    assert all(sum((s['turnaround']!=41.,s['u_max']!=45.,s['lambda_policy']!=.25))<=2
               for s in settings)
    assert next(s for s in settings if s['policy_id']=='UMAX_75_FIXED_SLOPE')['lambda_policy']==pytest.approx(.25*75/45)

    def native(rep,view,turnaround,u):
        return .01*(u-10)**2+turnaround/100+(.05 if rep=='HISTORY_MARGINAL_EXACT' else 0)+len(view)/1000
    def direct(rep,view,turnaround,u,lam,u_max):
        return native(rep,view,turnaround,u)+lam*u/u_max
    def objective(state,*,context,u,u_max,lambda_policy,view,**_):
        return direct(state,view,context.turnaround_lower_bound_minutes,u,lambda_policy,u_max)
    def grid(state,*,context,u_max,policy,**_):
        return tuple((u,objective(state,context=context,u=u,u_max=u_max,
            lambda_policy=policy.lambda_policy,view=policy.aggregation_view)) for u in action_grid(u_max))
    monkeypatch.setattr(mod,'expected_objective',objective)
    monkeypatch.setattr(mod,'objective_by_grid',grid)
    node=SimpleNamespace(node_id='n',episode_id='e',stage=OperationalStage.PRE_IB,
        sobt_minutes=100.,state=lambda rep:rep)
    nominal={profile:{rep:grid(rep,context=SimpleNamespace(turnaround_lower_bound_minutes=41.),
        u_max=45.,policy=SimpleNamespace(lambda_policy=.25,aggregation_view=view))
        for rep in mod.REPRESENTATIONS} for profile,view in PROFILES.items()}
    rows=mod.evaluate_policy_sensitivity(node,None,nominal,cu_track='YEAR_LOCAL')
    assert len(rows)==len(settings)*len(PROFILES)
    for row in rows:
        view=PROFILES[row['profile']]
        expected={u:direct('HISTORY_JOINT',view,row['turnaround'],u,
                           row['lambda_policy'],row['u_max']) for u in action_grid(row['u_max'])}
        assert dict(row['joint_curve'])==pytest.approx(expected)
        assert row['e_joint_minus_marginal'][0.]==pytest.approx(-.05)
    assert next(r for r in rows if r['policy_id']=='NOMINAL' and r['profile']=='BALANCED')['joint_curve']==nominal['BALANCED']['HISTORY_JOINT']


def test_e2_activation_and_ratio_of_sums_keep_paired_denominators():
    from exp.jatm_s34.shared_statistics import summarize_actions
    nodes={nid:SimpleNamespace(node_id=nid,episode_id=nid,chain_id=nid,
        stage=OperationalStage.PRE_IB,decision_time=SimpleNamespace(isoformat=lambda:'2017-08-01'))
        for nid in ('a','b')}
    def record(nid,decision,fallback=None):
        return dict(node_id=nid,status='ACTION_TABLE_COMPLETE',
            reference_decision={'u_star':5.},reference_objectives=[[0.,10.],[5.,5.],[10.,7.]],
            recoveries={name:dict(action=decision,fallback=fallback) for name in
                ('CURRENT_JOINT','HISTORY_POINT','HISTORY_MARGINAL')})
    atomic,summaries=summarize_actions([record('a',10.),record('b',0.,'ABSTAIN')],
        {'C1':{'a','b'}},nodes,replicates=23)
    summary=next(row for row in summaries if row['population']=='C1' and row['representation']=='CURRENT_JOINT')
    assert summary['metrics']['activation_joint']['n']==2
    assert summary['metrics']['activation_comparator']['n']==1
    assert summary['metrics']['target_agreement']['n']==1
    assert summary['recovery_loss']['paired_n']==1
    assert summary['recovery_loss']['L_rec']==pytest.approx(2/5)


def test_e4_chart_export_contains_separate_coverage_tracks_and_provenance(tmp_path,monkeypatch):
    import exp.jatm_s34.e4_shared_aggregate as mod
    source={'e1':{'rows':[{'view':'DELAY'}]},'e1_fixed':{'rows':[{'view':'DELAY'}]},
        'e2e3':dict(e3_summary=[],fixed_common_e3_summary=[],e3_rows=[],mechanisms=[],
            e1_recovery_opportunity_coverage=[{'view':'DELAY','coverage':.2}],
            fixed_common_e1_recovery_opportunity_coverage=[{'view':'DELAY','coverage':.3}],
            recovery_opportunity_coverage=[{'representation':'HISTORY_JOINT','coverage':.4}],
            fixed_common_recovery_opportunity_coverage=[{'representation':'HISTORY_JOINT','coverage':.5}],
            policy_sensitivity_rows=[{'policy_id':'NOMINAL','u_joint':5}],
            fixed_common_policy_sensitivity_rows=[{'policy_id':'NOMINAL','u_joint':0}],
            populations={'C3':[]},recovery_atomic=[],fixed_common_recovery_atomic=[],
            recovery_summary=[],fixed_common_recovery_summary=[])}
    def inspect(_root,year):
        if year!=2017:return dict(year=year,status='NOT_RUN_OR_INCOMPLETE'),None,{}
        return dict(year=year,status='COMPUTED_PENDING_SCIENTIFIC_ACCEPTANCE',regime='PRE_PANDEMIC',
            input_hashes={'e1':'sha256:e1','e1_fixed':'sha256:e1fixed','e2e3':'sha256:e2e3'}),source,{}
    monkeypatch.setattr(mod,'inspect_annual_result',inspect)
    result=mod.aggregate(tmp_path,tmp_path/'out')
    import json
    chart=json.loads((tmp_path/'out/SECTION5_CHART_SOURCE.json').read_text())
    coverage=[r for r in chart if r['experiment']=='E1_RECOVERY_OPPORTUNITY']
    assert {(r['track'],r['coverage']) for r in coverage}=={('YEAR_LOCAL',.2),('FIXED_COMMON',.3)}
    assert all(r['source_sha256']=='sha256:e2e3' for r in coverage)
    sensitivity=[r for r in chart if r['experiment']=='E3_POLICY_SENSITIVITY']
    assert {(r['track'],r['u_joint']) for r in sensitivity}=={('YEAR_LOCAL',5),('FIXED_COMMON',0)}
    assert result['status']=='PARTIAL_DEVELOPMENT' and not result['six_year_complete']


def test_evaluation_identity_includes_policy_sensitivity_code(tmp_path, monkeypatch):
    from exp.jatm_s34 import shared_run

    shared = tmp_path / 'shared'
    shared.mkdir()
    (shared / 'CACHE_MANIFEST.json').write_text('{}')
    (shared / 'SHARED_ANNUAL_MANIFEST.json').write_text('{}')
    original = shared_run.code_hash

    def changed_policy_hash(path):
        if path.name == 'policy_sensitivity.py':
            return 'sha256:changed-policy-code'
        return original(path)

    before = shared_run.evaluation_identity(shared)['algorithm_hash']
    monkeypatch.setattr(shared_run, 'code_hash', changed_policy_hash)
    after = shared_run.evaluation_identity(shared)['algorithm_hash']
    assert before != after
