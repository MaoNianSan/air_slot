"""One bounded real Development equivalence check for the shared execution path."""
from dataclasses import replace
import argparse
from pathlib import Path
import time

from exp.jatm_section5.run_development import _build_nodes,_iter_nodes,_canonicalize,STAGES
from exp.jatm_section5.recovery_value import transition_context
from model.M3.stage2 import RecoveryPolicy,objective_by_grid
from model.M2.consequence_service import M2ConsequenceService
from .annual_bridge import iter_annual_bridges
from .annual_cu import load_annual_cu
from .canonical_preselection import canonical_bridge
from .e2_e3_exact import _exact_projection,_headroom,_replace_with_exact,PROFILES
from .shared_actions import CachedConsequenceService
from .shared_store import atomic_json,file_hash
from .scientific_tracks import nominal_headroom
from .annual_tail import annual_tail_path
from .mechanisms import curves as mechanism_curves
from validation.v2_phase5.families import build_consequence_service


def run(output_root, *, year=2017, episodes=2):
    out=Path(output_root); started=time.perf_counter()
    context=next(iter_annual_bridges(year=year,node_limit=episodes,chunk_size=episodes,shared=True))
    old_layer=build_consequence_service(authorities=context['authorities'],bridge=context['bridge'],output_dir=out/'legacy_bindings')
    original=_build_nodes(authorities=context['authorities'],bridge=context['bridge'],tails=context['tails'],layer=old_layer,
        history_pipeline=context['history_pipeline'],current_pipeline=context['current_pipeline'])
    expected={r.node.node_id:r.node for rows in _canonicalize(original,stages=STAGES).values() for r in rows}
    bridge=canonical_bridge(context['bridge'])
    authority=replace(context['authorities'],registry=load_annual_cu(year))
    layer=build_consequence_service(authorities=authority,bridge=bridge,output_dir=out/'annual_bindings')
    ids={row[2][-1].decision_node.decision_node_id for row in bridge['rows']}
    assert ids == set(expected), 'CANONICAL_IDENTITIES_CHANGED'
    headroom=nominal_headroom(year); evidence=[]
    for node in _iter_nodes(authorities=authority,bridge=bridge,tails=context['tails'],layer=layer,
            history_pipeline=context['history_pipeline'],current_pipeline=context['current_pipeline'],include_legacy_marginal=False):
        old=expected[node.node_id]
        for rep in node.state_sets:
            assert old.state(rep).model_dump()==node.state(rep).model_dump(), 'M1_SCENARIOS_CHANGED'
            assert old.support(rep)==node.support(rep), 'SUPPORT_CHANGED'
            for before,after in zip(old.consequences(rep).scenarios,node.consequences(rep).scenarios):
                assert before.native_components==after.native_components, 'NATIVE_CONSEQUENCES_CHANGED'
                assert after.cu_components==layer.service.to_cu(before.native_components), 'ANNUAL_CU_MAPPING_CHANGED'
        values,state,consequence,support,audit=_exact_projection(node,layer.service,preserve_metadata=True)
        sv,ss,sc,sp,sa=_exact_projection(node,layer.service,preserve_metadata=True,streaming=True)
        assert support==sp, 'STREAM_SUPPORT_CHANGED'
        assert len(state.scenarios)==len(ss.scenarios)
        assert all(a.model_dump()==b.model_dump() for a,b in zip(state.scenarios,ss.scenarios)), 'STREAM_STATE_CHANGED'
        for key in ('delay','consequence'):
            assert values[key] == sv[key] or abs(values[key]-sv[key]) < 1e-10, 'STREAM_SCORE_CHANGED'
        exact=_replace_with_exact(node,(state,consequence,support,values))
        streamed=_replace_with_exact(node,(ss,sc,sp,sv))
        maximum=0.0; cached=CachedConsequenceService(layer.service)
        for rep in ('HISTORY_JOINT','HISTORY_MARGINAL_EXACT'):
            for profile,view in PROFILES.items():
                kwargs=dict(context=transition_context(node,headroom),u_max=headroom.u_max,
                    policy=RecoveryPolicy(aggregation_view=view),floor_to_minutes=headroom.floor_to_minutes)
                reference=objective_by_grid(exact.state(rep),service=layer.service,**kwargs)
                shared=objective_by_grid(streamed.state(rep),service=cached,**kwargs)
                assert reference==shared, 'ACTION_CURVES_CHANGED'
                assert min(reference,key=lambda p:(p[1],p[0]))==min(shared,key=lambda p:(p[1],p[0]))
        mechanism_error=0.0
        if node.stage in STAGES[:2] and node.support_full.get('HISTORY_JOINT',False):
            ctx=transition_context(node,headroom)
            for rep in ('HISTORY_JOINT','HISTORY_MARGINAL_EXACT'):
                materialized=mechanism_curves(exact.state(rep),ctx,cached,headroom)
                streaming=mechanism_curves(streamed.state(rep),ctx,cached,headroom)
                assert materialized==streaming, 'MECHANISM_STREAM_CHANGED'
                for profile,view in PROFILES.items():
                    authority_curve=objective_by_grid(exact.state(rep),context=ctx,service=cached,
                        u_max=headroom.u_max,policy=RecoveryPolicy(aggregation_view=view))
                    error=max(abs(a[1]-b[1]) for a,b in zip(authority_curve,streaming[True,True,profile]))
                    mechanism_error=max(mechanism_error,error)
                    assert error<1e-10, 'MECHANISM_ON_ON_DIFFERS_FROM_MODEL_AUTHORITY'
        evidence.append(dict(node_id=node.node_id,stage=node.stage.value,exact_scenarios=audit['product_scenario_count'],
            max_action_curve_error=maximum,max_mechanism_error=mechanism_error,
            consequence_requests=cached.calls,consequence_computations=cached.calls-cached.hits,hits=cached.hits))
        atomic_json(out/'PROGRESS.json',dict(completed_nodes=len(evidence),total_nodes=len(ids),seconds=time.perf_counter()-started))
        print(f'golden nodes {len(evidence)}/{len(ids)} exact={audit["product_scenario_count"]}',flush=True)
    result=dict(status='PASS_TARGETED_REAL_DEVELOPMENT_EQUIVALENCE',year=year,episodes=episodes,
        raw_nodes=len(original),canonical_nodes=len(ids),nodes=evidence,wall_seconds=time.perf_counter()-started,
        checks=['canonical_identity','M1_scenarios','support','native_seven','annual_CU_mapping',
                'exact_stream_states_and_scores','four_objective_complete_grids','argmin','four_mechanism_stream_equivalence','on_on_authority'],
        annual_tail_sha256=file_hash(annual_tail_path(year)),cu_contract=load_annual_cu(year).provenance,
        headroom=headroom.model_dump(mode='json'),
        scientific_acceptance='NOT_A_FULL_DEVELOPMENT_EXPERIMENT',gpu_status='NOT_RUN',final_test_access_count=0)
    atomic_json(out/'NUMERICAL_EQUIVALENCE.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output-root',type=Path,required=True)
    args=parser.parse_args();run(args.output_root)
