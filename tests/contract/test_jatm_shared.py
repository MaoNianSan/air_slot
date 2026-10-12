from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
import json
import pytest

from exp.jatm_s34.canonical_preselection import canonical_preselection
from exp.jatm_s34.shared_store import SharedStore
from exp.jatm_s34.e1_shared_evaluation import replicate_metrics
from exp.jatm_s34.e1_information_gain import (_CompactNode,_CompactSupport,_clone_instance,_summarize_stage,STAGES,Q_GRID,VIEWS)
from model.common.decision_contracts import TypedStatus


def test_identity_is_selected_before_support():
    nodes = [SimpleNamespace(episode_id='a',decision_node_id=nid,operational_stage=STAGES[0],
        decision_time=datetime(2017,8,1,hour,tzinfo=timezone.utc),support=False)
        for nid,hour in [('z',2),('b',1),('a',1)]]
    assert canonical_preselection([(None,None,[SimpleNamespace(decision_node=n)]) for n in nodes]) == ('a',)


def test_commits_reject_corruption_and_identity_drift(tmp_path):
    store=SharedStore(tmp_path,{'year':2017})
    with store.writer():
        store.commit('c',{'rows':[1,2]})
        with pytest.raises(RuntimeError,match='ALREADY_ACTIVE'):
            with store.writer(): pass
    assert store.read('c') == {'rows':[1,2]}
    with pytest.raises(ValueError,match='IDENTITY_MISMATCH'):
        SharedStore(tmp_path,{'year':2018}).read('c')
    saved=json.loads((tmp_path/'c.json').read_text());saved['payload']['rows']=[9]
    (tmp_path/'c.json').write_text(json.dumps(saved))
    with pytest.raises(ValueError,match='CORRUPT'):store.read('c')


def test_evaluation_resume_requires_identity_and_output_hashes(tmp_path):
    from exp.jatm_s34.shared_run import evaluation_is_current
    from exp.jatm_s34.shared_store import atomic_json,file_hash
    names=('E1/E1_PAIRED_SUMMARY.json','E1_FIXED_COMMON/E1_PAIRED_SUMMARY.json','E2_E3/E2_E3_SUMMARY.json')
    for name in names:atomic_json(tmp_path/name,{'complete':True})
    identity={'replicates':2000,'algorithm':'a'}
    atomic_json(tmp_path/'EVALUATION_COMPLETE.json',dict(identity=identity,
        outputs={name:file_hash(tmp_path/name) for name in names}))
    assert evaluation_is_current(tmp_path,identity)
    assert not evaluation_is_current(tmp_path,dict(identity,replicates=25))
    atomic_json(tmp_path/names[0],{'complete':False})
    assert not evaluation_is_current(tmp_path,identity)


def test_annual_tail_rejects_other_year_before_loading_targets(tmp_path,monkeypatch):
    import exp.jatm_s34.annual_tail as tail
    from exp.jatm_s34.shared_store import atomic_json,digest
    monkeypatch.setattr(tail,'ROOT',tmp_path)
    payload=dict(year=2019,fit_partition='train',fit_start='2019-01-01',fit_end='2019-06-30',final_test_access_count=0)
    atomic_json(tail.annual_tail_path(2017),dict(payload,artifact_hash=digest(payload)))
    with pytest.raises(ValueError,match='FIT_IDENTITY_MISMATCH'):tail.load_annual_tail(2017)


def test_scheduler_stop_marker_starts_no_worker(tmp_path,monkeypatch):
    import exp.jatm_s34.cloud_schedule as scheduler
    (tmp_path/'STOP_REQUESTED').touch()
    monkeypatch.setattr(scheduler.signal,'signal',lambda *_:None)
    def forbidden(*args,**kwargs):raise AssertionError('WORKER_STARTED_AFTER_STOP')
    monkeypatch.setattr(scheduler.subprocess,'Popen',forbidden)
    args=SimpleNamespace(output_root=tmp_path,years=[2017,2018],threads=8,workers=2,
        cpu_budget=32,memory_per_worker_gib=24,reserve_gib=12)
    result=scheduler.schedule(args)
    assert result['active']=={} and result['pending']==[] and result['finished']==[]


def test_annual_cu_approved_event_structure():
    from exp.jatm_s34.annual_cu import load_annual_cu
    adapter=load_annual_cu(2017)
    assert adapter.scales['P_itinerary']==adapter.scales['P_service']==1
    assert adapter.scales['F_continuity']==40
    assert adapter.scales['F_execution']==17
    assert adapter.scales['F_propagation']==10
    assert adapter.scales['R_operating']==5
    assert adapter.provenance['track']=='YEAR_LOCAL'
    assert adapter.provenance['reference_year']==2017
    assert adapter.provenance['turnaround_numeric_lookup_match']


@pytest.mark.parametrize('zero',[False,True])
def test_paired_reducer_matches_authority_with_repeated_episodes_and_ties(zero):
    nodes=[];factors={}
    for i in range(4):
        for stage in STAGES:
            nid=f'{i}-{stage.value}'
            nodes.append(_CompactNode(str(i),str(i),nid,stage,datetime(2017,8,1),
                {'HISTORY_JOINT':1.0}, {'HISTORY_JOINT':0.0 if zero else float(i+1)},
                {'HISTORY_JOINT':{'F':1,'P':1,'R':1}},
                _CompactSupport(True,1,.9,TypedStatus.SUPPORTED)))
            factors[nid]=(i+1,1)
    draw=['0','0','3','1','0','2','3']
    actual=replicate_metrics(nodes,factors,draw,replicate=7)
    clones=[_clone_instance(n,replicate=7,occurrence=j) for j,ep in enumerate(draw) for n in nodes if n.episode_id==ep]
    cloned_factors={n.node_id:factors[n.node_id.split('::BOOT')[0]] for n in clones}
    for stage in STAGES:
        for q in Q_GRID:
            for view in VIEWS:
                expected=_summarize_stage([n for n in clones if n.stage is stage],view=view,q=q,factor_by_node=cloned_factors)
                for metric,value in actual[stage.value,q,view].items():
                    if value is None: assert expected[metric] is None
                    else: assert value == pytest.approx(expected[metric],abs=1e-12)
