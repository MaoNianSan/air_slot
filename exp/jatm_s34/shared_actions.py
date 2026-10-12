"""Per-node M3 enumeration with one M2 result per unique post-action scenario.

Every objective still goes through model.M3.objective_by_grid. The cache is
below the aggregator, preserving scenario order and nonlinear operations.
"""
from dataclasses import replace
import json
from collections import OrderedDict
from pathlib import Path

from model.M2.consequence_service import M2ConsequenceService, ConsequenceReferenceBinding
from model.M3.stage2 import RecoveryPolicy, objective_by_grid
from model.common.decision_contracts import StateScenarioSet, RecoveryDecision
from model.common.enums import OperationalStage
from model.M4.evaluation import evaluate_recovery_loss
from exp.jatm_section5.contracts import (ReferenceRecoveryCohort,ReferenceRecoveryNode,ComparatorRecoveryResult)
from exp.jatm_section5.recovery_value import prepare_reference_recovery, comparator_recovery, transition_context
from exp.jatm_section5.information_value import information_value_main
from .annual_cu import load_annual_cu
from .e2_e3_exact import (_source_shortlists,_stage1_rows,_headroom,_exact_projection,
                         _replace_with_exact,_mechanism_rows,PROFILES)
from .shared_science import load_scores, unpack_node
from .shared_store import SharedStore, atomic_json, digest, file_hash, code_hash
from .shared_populations import population_views,c2_recovery_populations,ACTIONABLE,POPULATION_CONTRACT


class CachedConsequenceService:
    def __init__(self, service):
        self.service = service
        self.cache = OrderedDict()
        self.calls = 0
        self.hits = 0

    def __getattr__(self,name):
        return getattr(self.service,name)

    def consequence_scenario(self,state,*,node_id,support):
        key = digest(dict(state=state.model_dump(mode='json'),node_id=node_id,support=support.value))
        self.calls += 1
        if key not in self.cache:
            self.cache[key] = self.service.consequence_scenario(state,node_id=node_id,support=support)
            if len(self.cache)>20000:self.cache.popitem(last=False)
        else:
            self.hits += 1
        self.cache.move_to_end(key)
        return self.cache[key]


class RevaluedConsequenceService:
    """Reuse identical native scenario outcomes with a different CU registry."""
    def __init__(self, service, native_source):
        self.service = service
        self.native_source = native_source

    def __getattr__(self, name):
        return getattr(self.service, name)

    def consequence_scenario(self, state, *, node_id, support):
        native = self.native_source.consequence_scenario(state,node_id=node_id,support=support)
        return native.model_copy(update={'cu_components':self.service.to_cu(native.native_components)})


def calculate_node(node,service,headroom,shortlists):
    cached = service if isinstance(service,CachedConsequenceService) else CachedConsequenceService(service)
    cohort = prepare_reference_recovery((node,),source_shortlists=shortlists,service=cached,headroom=headroom)
    if not cohort.nodes:
        return dict(node_id=node.node_id,status='EXCLUDED_REFERENCE_SUPPORT',rows=[],recoveries={})
    reference = cohort.nodes[0]
    recoveries = {}
    for rep in ('CURRENT_JOINT','HISTORY_POINT','HISTORY_MARGINAL'):
        if not node.support_full.get(rep,False):
            recoveries[rep]=dict(action=0.,fallback='ABSTAIN_NO_FULL_RECOVERY_SUPPORT',decision=None)
            continue
        value = comparator_recovery(cohort,representation=rep,service=cached,headroom=headroom)
        recoveries[rep] = dict(action=value.actions[node.node_id],fallback=value.typed_fallbacks.get(node.node_id),
            decision=None if node.node_id not in value.decisions else value.decisions[node.node_id].model_dump(mode='json'))
    context = transition_context(node,headroom)
    from model.M3.transition import scenario_headroom
    distribution=node.state('HISTORY_JOINT').scenarios
    mechanism_context=dict(expected_headroom_minutes=sum(s.scenario_weight*scenario_headroom(s,context) for s in distribution),
        itinerary_threshold_probability=sum(s.scenario_weight for s in distribution if s.d_to_minutes>45),
        service_threshold_probability=sum(s.scenario_weight for s in distribution if s.d_to_minutes>=180))
    rows, curves = [], {}
    for profile,view in PROFILES.items():
        curves[profile] = {}
        for rep in ('HISTORY_JOINT','HISTORY_MARGINAL_EXACT'):
            if not node.support_full.get(rep,False):continue
            table = objective_by_grid(node.state(rep),context=context,service=cached,
                u_max=headroom.u_max,policy=RecoveryPolicy(lambda_policy=.25,aggregation_view=view),
                floor_to_minutes=headroom.floor_to_minutes)
            curves[profile][rep] = table
            best_u,best_j = min(table,key=lambda p:(p[1],p[0]))
            ordered = sorted(j for u,j in table)
            rows.append(dict(profile=profile,representation=rep,node_id=node.node_id,
                episode_id=node.episode_id,stage=node.stage.value,u_star=best_u,J_zero=table[0][1],
                J_star=best_j,recoverable_value=table[0][1]-best_j,
                decision_margin=None if len(ordered)<2 else ordered[1]-best_j,
                objective_by_grid=table))
        joint = dict(curves[profile]['HISTORY_JOINT'])
        if 'HISTORY_MARGINAL_EXACT' not in curves[profile]:continue
        marginal = min(curves[profile]['HISTORY_MARGINAL_EXACT'],key=lambda p:(p[1],p[0]))
        jbest = min(joint.values())
        for row in rows[-2:]:
            row['joint_reference_loss_at_marginal_action'] = joint[marginal[0]]-jbest
            denominator=joint[0.0]-jbest
            row['relative_reference_loss_at_marginal_action']=None if denominator<=0 else (joint[marginal[0]]-jbest)/denominator
            reference_u=min(joint,key=lambda u:(joint[u],u))
            difference={u:j-joint[u] for u,j in curves[profile]['HISTORY_MARGINAL_EXACT']}
            row['fixed_target_perturbations']=difference
            row['relative_objective_perturbation']=max((abs(v-difference[reference_u]) for u,v in difference.items() if u!=reference_u),default=0.0)
            row['choice_agreement']=marginal[0]==reference_u
    return dict(node_id=node.node_id,status='ACTION_TABLE_COMPLETE',
        reference_decision=reference.reference_decision.model_dump(mode='json'),
        mechanism_context=mechanism_context,
        reference_objectives=[[u,v] for (_,u),v in reference.reference_objectives.items()],
        recoveries=recoveries,rows=rows,mechanisms=[],
        consequence_requests=cached.calls,consequence_computations=cached.calls-cached.hits,cache_hits=cached.hits)


def run_actions(shared_root, output_root, *, replicates=2000):
    root,out = Path(shared_root),Path(output_root)
    manifest=json.loads((root/'CACHE_MANIFEST.json').read_text())
    identity=manifest['identity'];year=identity['year']
    records=list(load_scores(root))
    light=tuple(unpack_node(row) for row in records)
    canonical_ids={row['node_id'] for row in records if row.get('is_canonical',True)}
    exposure_by_node={row['node_id']:tuple(row['exposure']) for row in records if row.get('exposure') is not None}
    populations=population_views(light,canonical_ids,year=year,q=.10,exposure_by_node=exposure_by_node)
    shortlists=populations['shortlists']['HISTORY_JOINT']
    c1_ids={node.node_id for node in populations['C1']}
    e3_ids={node.node_id for node in populations['e3']}
    rolling_ids={node.node_id for node in populations['C3']}
    selected=[node for node in light if node.node_id in c1_ids|rolling_ids]
    full_eligible_lists={stage:tuple(node.node_id for node in selected if node.stage is stage) for stage in ACTIONABLE}
    del records
    states=SharedStore(root/'states',identity)
    from .scientific_tracks import nominal_headroom
    headroom=nominal_headroom(year)
    source_root=Path(__file__).resolve().parents[2]
    action_sources=[p for folder in ('model/M3','model/M4','exp/jatm_section5')
                    for p in (source_root/folder).rglob('*.py')]
    action_sources.extend(Path(__file__).with_name(name) for name in
        ('shared_actions.py','shared_populations.py','scientific_tracks.py','mechanisms.py',
         'exact_stream.py','e2_e3_exact.py','annual_cu.py','shared_store.py','shared_statistics.py'))
    action_sources.append(Path(__file__).with_name('shared_revaluation.py'))
    action_identity=dict(identity,headroom=headroom.model_dump(mode='json'),shortlists={k.value:list(v) for k,v in shortlists.items()},
        headroom_source_hash=file_hash(source_root/'data2/reports/paper_formal'/str(year)/str(year)/'M2_TRAIN_HEADROOM_SUMMARY.json'),
        action_algorithm_hash=digest({p.relative_to(source_root).as_posix():code_hash(p) for p in action_sources}),
        fixed_common_contract=load_annual_cu(year,track='FIXED_COMMON').provenance)
    store=SharedStore(out/'actions',action_identity)
    compact=[]; fixed_records=[]; fixed_rows=[]
    with store.writer():
        for index,node in enumerate(selected):
            key=node.node_id.replace(':','_')
            saved=store.read(key)
            if saved is None:
                source=states.read(key)
                binding=ConsequenceReferenceBinding.model_validate(source['binding']) if source['binding'] is not None else None
                service=M2ConsequenceService(load_annual_cu(year),{} if binding is None else {node.node_id:binding})
                original=unpack_node(source['node'],{k:StateScenarioSet.model_validate(v) for k,v in source['states'].items()})
                values,state,consequence,support,audit=_exact_projection(original,service,preserve_metadata=True,streaming=True)
                full=_replace_with_exact(original,(state,consequence,support,values))
                native_cache=CachedConsequenceService(service)
                saved=calculate_node(full,native_cache,headroom,full_eligible_lists)
                if saved['status']=='ACTION_TABLE_COMPLETE':
                    fixed_service=M2ConsequenceService(load_annual_cu(year,track='FIXED_COMMON'),service.references)
                    saved['fixed_common']=calculate_node(full,RevaluedConsequenceService(fixed_service,native_cache),headroom,full_eligible_lists)
                    # Native outcomes are identical; store them only on the main track.
                    saved['fixed_common'].pop('scenario_outcomes',None)
                    saved['native_computations_both_tracks']=native_cache.calls-native_cache.hits
                    if node.node_id in e3_ids:
                        import gzip
                        from .mechanisms import compare
                        ledger_path=out/'actions'/(key+'.native.jsonl.gz')
                        temporary=ledger_path.with_suffix('.tmp')
                        with gzip.open(temporary,'wt',encoding='utf-8') as stream:
                            saved['mechanisms']=compare(full,transition_context(full,headroom),service,headroom,
                                ledger=lambda row:stream.write(json.dumps(row)+'\n'))
                        temporary.replace(ledger_path)
                        saved['native_response_ledger']=dict(path=ledger_path.name,sha256=file_hash(ledger_path))
                store.commit(key,saved)
                del original,full,state,consequence,source,native_cache
            ledger=saved.get('native_response_ledger')
            if ledger is not None:
                ledger_path=out/'actions'/ledger['path']
                if not ledger_path.is_file() or file_hash(ledger_path)!=ledger['sha256']:
                    raise ValueError('NATIVE_RESPONSE_LEDGER_MISSING_OR_CORRUPT:'+key)
            compact.append({k:v for k,v in saved.items() if k not in ('scenario_outcomes','fixed_common')})
            if saved.get('fixed_common'):
                fixed_records.append({k:v for k,v in saved['fixed_common'].items() if k!='scenario_outcomes'})
            fixed_rows.extend(saved.get('fixed_common',{}).get('rows',[]))
            atomic_json(out/'PROGRESS.json',dict(phase='STAGE_II',year=year,completed_nodes=index+1,total_nodes=len(selected)))
            print(json.dumps(dict(phase='STAGE_II',completed_nodes=index+1,total_nodes=len(selected))),flush=True)
            del saved
            if (root/'STOP_REQUESTED').exists():
                raise InterruptedError('PAUSED_AFTER_ATOMIC_ACTION_NODE')
    by_id={node.node_id:node for node in light}
    items=[]
    for record in compact:
        if record['status']!='ACTION_TABLE_COMPLETE' or record['node_id'] not in c1_ids:continue
        nid=record['node_id']; decision=RecoveryDecision.model_validate(record['reference_decision'])
        items.append(ReferenceRecoveryNode(by_id[nid],decision,{(nid,u):v for u,v in record['reference_objectives']},
            max(0.0,float(decision.recoverable_value)),tuple(decision.action_grid)))
    annual_shortlist_ids={nid for ids in shortlists.values() for nid in ids}
    annual_items=[item for item in items if item.node.node_id in annual_shortlist_ids]
    cohort=ReferenceRecoveryCohort(tuple(annual_items),shortlists)
    results={}
    usable={row['node_id']:row for row in compact if row['status']=='ACTION_TABLE_COMPLETE' and row['node_id'] in annual_shortlist_ids}
    for rep in ('CURRENT_JOINT','HISTORY_POINT','HISTORY_MARGINAL'):
        actions={nid:r['recoveries'][rep]['action'] for nid,r in usable.items()}
        decisions={nid:RecoveryDecision.model_validate(r['recoveries'][rep]['decision']) for nid,r in usable.items() if r['recoveries'][rep]['decision'] is not None}
        fallbacks={nid:r['recoveries'][rep]['fallback'] for nid,r in usable.items() if r['recoveries'][rep]['fallback'] is not None}
        evaluation=evaluate_recovery_loss(cohort_id=f'RSTAR_{rep}',reference_id='HISTORY_JOINT',comparator_id=rep,
            fixed_cohort=tuple(usable),reference_actions={i.node.node_id:float(i.reference_decision.u_star or 0) for i in annual_items},
            comparator_actions=actions,reference_objectives={k:v for i in annual_items for k,v in i.reference_objectives.items()},
            reference_recoverable_values={i.node.node_id:i.reference_recoverable_value for i in annual_items})
        results[rep]=ComparatorRecoveryResult(rep,actions,decisions,fallbacks,evaluation)
    information=tuple(node for node in populations['canonical'] if node.stage in (OperationalStage.PRE_IB,OperationalStage.POST_IB_PRE_OB)
                        and all(node.support(rep).included and node.consequence_scores[rep] is not None
                        for rep in ('HISTORY_JOINT','CURRENT_JOINT','HISTORY_POINT','HISTORY_MARGINAL_EXACT')))
    info,diagnostics,bootstrap=information_value_main(information,q=.10,reference_cohort=cohort,service=None,
        headroom=headroom,seed=20261011,replicates=replicates,precomputed_recovery=results)
    from .shared_statistics import summarize_actions,objective_summary,stage1_pairwise_statistics,recovery_coverage
    c2_ids,c2_metadata=c2_recovery_populations(populations['C2'])
    ids_by_population=dict(C1=c1_ids,C3=rolling_ids,
        ANNUAL_HJ_SHORTLIST={nid for ids in shortlists.values() for nid in ids})
    ids_by_population.update(c2_ids)
    recovery_atomic,recovery_summary=summarize_actions(compact,ids_by_population,by_id,replicates=replicates,
        population_metadata=c2_metadata)
    from .shared_revaluation import revalue_nodes
    fixed_light=revalue_nodes(light,load_annual_cu(year),load_annual_cu(year,track='FIXED_COMMON'))
    fixed_populations=population_views(fixed_light,canonical_ids,year=year,q=.10,
        exposure_by_node=exposure_by_node,cu_track='FIXED_COMMON')
    fixed_ids={key:{n.node_id for n in fixed_populations[key]} for key in ('C1','C3')}
    fixed_c2_ids,fixed_c2_metadata=c2_recovery_populations(fixed_populations['C2'])
    fixed_ids.update(fixed_c2_ids)
    fixed_ids['ANNUAL_HJ_SHORTLIST']={nid for ids in fixed_populations['shortlists']['HISTORY_JOINT'].values() for nid in ids}
    fixed_atomic,fixed_summary=summarize_actions(fixed_records,fixed_ids,{n.node_id:n for n in fixed_light},
        replicates=replicates,population_metadata=fixed_c2_metadata)
    e3_rows=[row for record in compact if record['node_id'] in e3_ids for row in record['rows']]
    payload=dict(schema_version='JATM_SHARED_E2_E3_V2',status='DEVELOPMENT_COMPUTED_PENDING_SCIENTIFIC_ACCEPTANCE',
        population_contract=POPULATION_CONTRACT,recovery_loss_estimand='RATIO_OF_SUMS_DELTA_REC_OVER_REFERENCE_V',
        year=year,scope='PILOT' if identity.get('episode_limit') is not None else 'FULL_DEVELOPMENT',
        bootstrap_replicates=replicates,stage1_rows=_stage1_rows(populations['canonical'],.10),information=info,diagnostics=diagnostics,bootstrap=bootstrap,
        e3_rows=e3_rows,e3_summary=objective_summary(e3_rows,replicates=replicates),
        stage1_pairwise=stage1_pairwise_statistics(populations['canonical'],replicates=replicates),
        recovery_opportunity_coverage=recovery_coverage(compact,light,canonical_ids,replicates=replicates),
        fixed_common_recovery_opportunity_coverage=recovery_coverage(fixed_records,fixed_light,canonical_ids,replicates=replicates),
        fixed_common_stage1_pairwise=stage1_pairwise_statistics(fixed_populations['canonical'],replicates=replicates),
        fixed_common_population_ids={key:sorted(value) for key,value in fixed_ids.items()},
        fixed_common_C2_groups=fixed_populations['C2'],
        information_scope='ALL_REPRESENTATION_INTERSECTION_SCREENING_AND_ANNUAL_HJ_SHORTLIST_DIAGNOSTIC',
        recovery_atomic=recovery_atomic,recovery_summary=recovery_summary,
        fixed_common_recovery_atomic=fixed_atomic,fixed_common_recovery_summary=fixed_summary,
        fixed_common_e3_rows=[row for row in fixed_rows if row['node_id'] in e3_ids],
        fixed_common_e3_summary=objective_summary([row for row in fixed_rows if row['node_id'] in e3_ids],replicates=replicates),
        mechanisms=[row for record in compact for row in record.get('mechanisms',[])],
        support_denominator=len(light),reference_cohort_count=len(annual_items),full_recovery_valid_count=len(items),information_candidate_count=len(information),
        population_counts_by_stage={stage.value:dict(
            canonical_stage1=sum(n.stage is stage for n in populations['canonical']),
            C1_canonical_stage2=sum(n.stage is stage for n in populations['C1']),
            C3_rolling_epochs=sum(n.stage is stage for n in populations['C3'])) for stage in ACTIONABLE},
        shared_identity_hash=digest(identity),action_identity=action_identity,final_test_access_count=0,
        representation_aliases={'HISTORY_MARGINAL':'HISTORY_MARGINAL_EXACT'},legacy_permutation_used=False,
        populations={'C0':{'status':'HISTORICAL_SEALED_NOT_ACCESSED'},
            'C1':sorted(c1_ids),'C2':populations['C2'],'C3':sorted(rolling_ids),'E3_COMMON':sorted(e3_ids),
            'C1_CANONICAL':[n.node_id for n in populations['C1_CANONICAL']],
            'PAIRWISE_STAGE_I':populations['pairwise_stage1'],'E1_SCREENING':populations['e1_shortlists'],
            'rolling_cluster_key':'episode_id',
            'ANNUAL_HJ_SHORTLIST':{stage.value:list(ids) for stage,ids in shortlists.items()}},
        recovery_records=compact,
        scientific_acceptance=dict(status='PENDING',mechanism_status='FOUR_APPROVED_OPERATOR_STRUCTURES_COMPUTED',
            six_year_replication='NOT_EVALUATED'))
    # JSON is the public cache contract: a fresh run and a restored run must
    # expose identical list/key types, including objective curves.
    payload=json.loads(json.dumps(payload,allow_nan=False))
    atomic_json(out/'E2_E3_SUMMARY.json',payload)
    return payload
