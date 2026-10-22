"""Single annual writer for canonical Stage-I scores and lazy Stage-II inputs."""
from dataclasses import asdict, replace
from datetime import datetime
import json
from pathlib import Path
import signal
import time

from exp.jatm_section5.contracts import RepresentationNode
from exp.jatm_section5.run_development import _iter_nodes
from model.common.decision_contracts import ComparisonSupport, StateScenarioSet
from model.common.enums import OperationalStage
from .annual_bridge import iter_annual_bridges
from .annual_cu import load_annual_cu
from .canonical_preselection import canonical_bridge,canonical_preselection
from .e1_information_gain import _exposure_factors
from .e2_e3_exact import _project_light_node
from .shared_store import SharedStore, atomic_json, digest, file_hash, code_hash
from validation.v2_phase5.families import build_consequence_service

ROOT = Path(__file__).resolve().parents[2]


def pack_node(node):
    supports={k:v.model_dump(mode='json') for k,v in node.supports.items()}
    for rep in ('HISTORY_MARGINAL','HISTORY_MARGINAL_EXACT'):
        if rep in supports:
            # Stage-I needs mass/status, not O(product) scenario IDs per node.
            # Stage-II rebuilds and validates the exact carrier from HJ states.
            supports[rep]['supported_scenario_ids']=[]
    return dict(episode_id=node.episode_id, chain_id=node.chain_id, node_id=node.node_id,
        stage=node.stage.value, decision_time=node.decision_time.isoformat(),
        sobt_minutes=node.sobt_minutes, supports=supports,
        support_full=dict(node.support_full), delay_scores=dict(node.delay_scores),
        consequence_scores=dict(node.consequence_scores), domain_scores=dict(node.domain_scores),
        component_scores=dict(node.component_scores))


def unpack_node(row, states=None):
    return RepresentationNode(**{k:row[k] for k in ('episode_id','chain_id','node_id','sobt_minutes',
        'support_full','delay_scores','consequence_scores','domain_scores','component_scores')},
        stage=OperationalStage(row['stage']), decision_time=datetime.fromisoformat(row['decision_time']),
        supports={k:ComparisonSupport.model_validate(v) for k,v in row['supports'].items()},
        state_sets={} if states is None else states, consequence_sets={})


def execution_identity(year, n, chunk_size, node_limit, device,
                       continuity_contract='LEGACY_A_V1'):
    import torch
    from data2.scripts.consequence_stability_battery import load_hash_cohort
    from .annual_bridge import load_annual_authorities
    selected = load_hash_cohort(year)['development']
    if node_limit is not None:
        selected = selected[:node_limit]
    authority = load_annual_authorities(year, continuity_contract=continuity_contract)
    paths = [ROOT/'artifacts/models/m1'/f'YEAR_{year}'/name for name in
             ('M1_HISTORY_PRIMARY.pt','M1_CURRENT_COMPARATOR.pt')]
    paths.extend((ROOT/'artifacts/models/pre/PRE_MULTIYEAR_V1'/str(year)/name) for name in
                 ('DATA2_TAXI_REFERENCE_TRAIN_FROZEN.json','DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN.json',
                  'PRE_MULTIYEAR_DEVELOPMENT_MANIFEST.json'))
    paths.append(ROOT/'data2/reports/cohort_size_stability'/str(year)/'HASH_SELECTED_COHORT_RECORDS_N4096.jsonl')
    from .annual_tail import annual_tail_path,load_annual_tail
    load_annual_tail(year)
    paths.append(annual_tail_path(year))
    paths.extend(ROOT/'artifacts/models/m1'/f'YEAR_{year}'/(role+'_MANIFEST.json')
                 for role in ('M1_HISTORY_PRIMARY','M1_CURRENT_COMPARATOR'))
    code = [path for folder in ('model/M1','model/M2','model/PRE','model/common','validation/v2_phase5')
            for path in (ROOT/folder).rglob('*.py')]
    code.extend(ROOT/name for name in ('exp/jatm_section5/run_development.py','exp/jatm_section5/cohorts.py',
        'exp/jatm_s34/shared_science.py','exp/jatm_s34/annual_bridge.py','exp/jatm_s34/annual_cu.py',
        'exp/jatm_s34/canonical_preselection.py','exp/jatm_s34/e2_e3_exact.py','exp/jatm_s34/annual_tail.py',
        'exp/jatm_s34/exact_stream.py','exp/jatm_s34/e1_information_gain.py',
        'exp/jatm_s34/shared_store.py','exp/jatm_s34/cloud_inputs.py',
        'exp/jatm_s34/annual_models.py','data2/scripts/consequence_stability_battery.py'))
    return dict(schema='JATM_SHARED_IDENTITY_V1', year=year, split='development', n=n,
        cohort_ids_hash=digest([episode.episode_id for _,episode in selected]),
        chunk_size=chunk_size, episode_limit=node_limit,
        canonical_rule='MIN_DECISION_TIME_NODE_ID_BEFORE_SUPPORT_V1',
        population_contract='CANONICAL_STAGE_I_PLUS_ALL_ACTIONABLE_ROLLING_V1',
        source_hashes={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in paths},
        scientific_config_hashes={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p)
            for p in (ROOT/'configs').rglob('*') if p.is_file()},
        algorithm_hash=digest({str(p.relative_to(ROOT)).replace('\\','/'):code_hash(p) for p in code}),
        cu_contract=load_annual_cu(year, continuity_contract=continuity_contract).provenance,
        seeds={'history':authority.h16_manifest['training_seed'], 'current':authority.current_manifest['training_seed']},
        scenario_count=64, backend=device, dtype='float32', torch_version=torch.__version__,
        final_test_access_count=0, model_retrained=False)


def materialize(year, output_root, *, n=4096, chunk_size=32, node_limit=None, device='cpu',
                continuity_contract='JATM_F_CONTINUITY_B_V1'):
    """Commit one compact chunk and one small restorable payload per canonical node."""
    import psutil
    root = Path(output_root)
    identity = execution_identity(year,n,chunk_size,node_limit,device,
        continuity_contract=continuity_contract)
    identity['continuity_contract'] = continuity_contract
    identity['stage2_time_coordinate_contract'] = 'JATM_STAGE2_SIGNED_T_IB_V1'
    store = SharedStore(root/'stage1', identity)
    states = SharedStore(root/'states', identity)
    stop = [False]
    previous = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous[sig] = signal.signal(sig, lambda *_:stop.__setitem__(0,True))
    started = time.perf_counter()
    try:
        with store.writer():
            completed = 0
            while store.read(f'chunk_{completed:04d}') is not None:
                payload = store.read(f'chunk_{completed:04d}')
                for row in payload['rows']:
                    if states.read(row['node_id'].replace(':','_')) is None:
                        raise ValueError('SHARED_STATE_COMMIT_MISSING:'+row['node_id'])
                completed += 1
            completion = store.read('COMPLETE')
            if completion is not None:
                if completion['chunks'] != completed:
                    raise ValueError('SHARED_COMPLETION_CHUNK_COUNT_MISMATCH')
                # COMPLETE can survive a crash immediately before manifest publication.
                atomic_json(root/'CACHE_MANIFEST.json',dict(identity=identity,identity_hash=store.identity_hash,
                    status='STAGE_I_COMPLETE',chunks=completed,model_retrained=False,final_test_access_count=0))
                export_e1_table(root)
                return identity
            for context in iter_annual_bridges(year=year,n=n,chunk_size=chunk_size,
                    node_limit=node_limit,start_chunk=completed,shared=True,device=device,
                    continuity_contract=continuity_contract):
                tick = time.perf_counter()
                canonical_ids=set(canonical_preselection(context['bridge']['rows']))
                # C1 uses every eligible canonical case; C3 needs all admissible
                # PRE/TURN epochs. Keep later-stage canonical diagnostics too.
                bridge=dict(context['bridge'],rows=tuple(row for row in context['bridge']['rows']
                    if row[2][-1].decision_node.decision_node_id in canonical_ids or
                    row[2][-1].decision_node.operational_stage in
                        (OperationalStage.PRE_IB,OperationalStage.POST_IB_PRE_OB)))
                layer = build_consequence_service(authorities=context['authorities'],bridge=bridge,
                    output_dir=root/'bindings'/f'chunk_{completed:04d}',
                    continuity_contract=continuity_contract)
                rows = []
                for node in _iter_nodes(authorities=context['authorities'],bridge=bridge,
                        tails=context['tails'],layer=layer,history_pipeline=context['history_pipeline'],
                        current_pipeline=context['current_pipeline'],include_legacy_marginal=False):
                    light, audit = _project_light_node(node,layer.service,preserve_metadata=True,streaming=True)
                    factors, exposure_audit = _exposure_factors(node,layer.bindings.get(node.node_id),
                        direct_reference_zero_valid=True)
                    row = pack_node(light)
                    row.update(year=year,is_canonical=node.node_id in canonical_ids,
                               exposure=None if factors is None else list(factors),
                               exposure_audit=exposure_audit, exact_audit=audit)
                    row['native_expected'] = {}
                    for rep, consequences in node.consequence_sets.items():
                        support = node.support(rep)
                        if not support.included:
                            row['native_expected'][rep] = None
                            continue
                        ids = set(support.supported_scenario_ids)
                        row['native_expected'][rep] = {key:sum(s.scenario_weight*s.native_components[key]
                            for s in consequences.scenarios if s.scenario_id in ids)/support.supported_mass
                            for key in layer.service._scales}
                    # HJ/CJ/HP each have <=64 states; exact product is reconstructed lazily.
                    state_payload = dict(node=pack_node(light), states={k:v.model_dump(mode='json')
                        for k,v in node.state_sets.items()}, binding=None if node.node_id not in layer.bindings
                        else layer.bindings[node.node_id].model_dump(mode='json'))
                    states.commit(node.node_id.replace(':','_'),state_payload)
                    rows.append(row)
                payload = dict(rows=rows, input_node_count=len(context['bridge']['rows']),
                    canonical_count=len(canonical_ids),computed_node_count=len(rows),
                    canonical_ids=sorted(canonical_ids),
                    seconds=time.perf_counter()-tick, rss_bytes=psutil.Process().memory_info().rss)
                store.commit(f'chunk_{completed:04d}',payload)
                completed += 1
                progress = dict(year=year,phase='SHARED_STAGE_I',completed_chunks=completed,
                    canonical_count=payload['canonical_count'],seconds=payload['seconds'],
                    rss_bytes=payload['rss_bytes'],elapsed_seconds=time.perf_counter()-started)
                atomic_json(root/'PROGRESS.json',progress)
                print(json.dumps(progress),flush=True)
                del rows, layer, bridge, context
                if stop[0] or (root/'STOP_REQUESTED').exists():
                    atomic_json(root/'PAUSED.json',progress)
                    return identity
            store.commit('COMPLETE',dict(chunks=completed,final_test_access_count=0))
            atomic_json(root/'CACHE_MANIFEST.json',dict(identity=identity,identity_hash=store.identity_hash,
                status='STAGE_I_COMPLETE',chunks=completed,model_retrained=False,final_test_access_count=0))
            export_e1_table(root)
            return identity
    finally:
        for sig,handler in previous.items():
            signal.signal(sig,handler)


def load_scores(root):
    root = Path(root)
    manifest = json.loads((root/'CACHE_MANIFEST.json').read_text())
    store = SharedStore(root/'stage1',manifest['identity'])
    completion = store.read('COMPLETE')
    if completion is None:
        raise ValueError('SHARED_STAGE_I_INCOMPLETE')
    for index in range(completion['chunks']):
        for row in store.read(f'chunk_{index:04d}')['rows']:
            yield row


def export_e1_table(root, *, track='YEAR_LOCAL'):
    from .e1_information_gain import STAGES
    root=Path(root)
    manifest=json.loads((root/'CACHE_MANIFEST.json').read_text())
    view_root=root if track=='YEAR_LOCAL' else root/'fixed_common'
    view_root.mkdir(parents=True,exist_ok=True)
    contract=manifest['identity']['cu_contract']
    if track=='FIXED_COMMON':
        from model.M2.comparison_support import phi_c
        from exp.jatm_section5.run_development import _domain_vector
        fixed=load_annual_cu(manifest['identity']['year'],track='FIXED_COMMON')
        contract=fixed.provenance
    elif track!='YEAR_LOCAL':raise ValueError('UNKNOWN_CU_TRACK')
    table=view_root/'SHARED_ANNUAL_NODES.jsonl'; temporary=table.with_suffix('.tmp')
    count=0
    with temporary.open('w',encoding='utf-8',newline='\n') as stream:
        for row in load_scores(root):
            if not row['is_canonical']:continue
            if row['stage'] not in {stage.value for stage in STAGES}:continue
            factors=row['exposure']
            record={k:row[k] for k in ('year','episode_id','chain_id','node_id','stage','decision_time')}
            record.update(delay_score=row['delay_scores']['HISTORY_JOINT'],
                consequence_score=row['consequence_scores']['HISTORY_JOINT'],
                domain_scores=row['domain_scores']['HISTORY_JOINT'],support=row['supports']['HISTORY_JOINT'],
                exposure=None if factors is None else dict(expected_passengers_per_flight=factors[0],
                                                           expected_downstream_exposure=factors[1]))
            if track=='FIXED_COMMON':
                native=row['native_expected']['HISTORY_JOINT']
                cu=None if native is None else {k:v/fixed.scales[k] for k,v in native.items()}
                record.update(consequence_score=None if cu is None else phi_c(cu),
                              domain_scores=None if cu is None else _domain_vector(cu))
            stream.write(json.dumps(record,sort_keys=True)+'\n');count+=1
    temporary.replace(table)
    atomic_json(view_root/'SHARED_ANNUAL_MANIFEST.json',dict(schema_version='JATM_SHARED_E1_VIEW_V1',
        year=manifest['identity']['year'],source_identity=manifest['identity_hash'],
        cu_contract=contract,
        node_table=dict(path=table.name,sha256=file_hash(table),records=count),final_test_access_count=0))
