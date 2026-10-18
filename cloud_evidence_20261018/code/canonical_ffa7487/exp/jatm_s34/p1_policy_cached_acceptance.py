"""One-node real Development cache parity for the P1 Stage-II policy grid."""
import argparse
import json
from pathlib import Path
from time import perf_counter

from model.M1.marginal_distribution import ExactWeightedMarginalDistribution
from model.M2.consequence_service import ConsequenceReferenceBinding, M2ConsequenceService
from model.M3.stage2 import expected_objective, action_grid
from model.common.decision_contracts import StateScenarioSet
from exp.jatm_section5.recovery_value import transition_context

from .annual_cu import load_annual_cu
from .e2_e3_exact import _exact_projection, _replace_with_exact, PROFILES
from .policy_sensitivity import evaluate_policy_sensitivity, REPRESENTATIONS
from .shared_actions import CachedConsequenceService
from .shared_science import unpack_node
from .shared_store import SharedStore, atomic_json, code_hash, file_hash


def verify(shared_root, prior_path):
    root=Path(shared_root);prior_path=Path(prior_path)
    cache=json.loads((root/'CACHE_MANIFEST.json').read_text())
    prior=json.loads(prior_path.read_text())
    if cache['identity_hash']!=prior['shared_identity_hash'] or prior['scope']!='PILOT':
        raise ValueError('P1_POLICY_CACHE_IDENTITY_OR_SCOPE_MISMATCH')
    states=SharedStore(root/'states',cache['identity'])
    options=[]
    for nid in prior['populations']['C1']:
        saved=states.read(nid.replace(':','_'))
        count=ExactWeightedMarginalDistribution.from_source(
            StateScenarioSet.model_validate(saved['states']['HISTORY_JOINT'])).scenario_count
        options.append((count,nid,saved))
    count,nid,saved=min(options,key=lambda value:(value[0],value[1]))
    binding=ConsequenceReferenceBinding.model_validate(saved['binding'])
    service=CachedConsequenceService(M2ConsequenceService(load_annual_cu(prior['year']),{nid:binding}))
    original=unpack_node(saved['node'],{rep:StateScenarioSet.model_validate(row)
                                        for rep,row in saved['states'].items()})
    values,exact,consequences,support,_=_exact_projection(original,service,
        preserve_metadata=True,streaming=True)
    full=_replace_with_exact(original,(exact,consequences,support,values))
    if not full.support_full['HISTORY_MARGINAL_EXACT']:
        raise ValueError('P1_POLICY_EXACT_MARGINAL_UNSUPPORTED')
    record=next(r for r in prior['recovery_records'] if r['node_id']==nid)
    nominal={profile:{row['representation']:row['objective_by_grid'] for row in record['rows']
                      if row['profile']==profile and row['representation'] in REPRESENTATIONS}
             for profile in PROFILES}
    if any(set(nominal[p])!=set(REPRESENTATIONS) for p in PROFILES):
        raise ValueError('P1_POLICY_NOMINAL_CURVES_INCOMPLETE')
    start=perf_counter()
    rows=evaluate_policy_sensitivity(full,service,nominal,cu_track='YEAR_LOCAL')
    elapsed=perf_counter()-start
    # Independent direct calls to the model authority test both recomputed
    # turnaround outcomes and the non-grid effort slope in the decoupled range.
    maximum=0.
    checked=0
    for policy_id in ('NOMINAL','LAMBDA_0.10','TURNAROUND_34','UMAX_75_FIXED_SLOPE'):
        row=next(r for r in rows if r['policy_id']==policy_id and r['profile']=='BALANCED')
        context=transition_context(full,type('Bound',(),{
            'turnaround_lower_bound_q':row['turnaround']})())
        for rep,field in (('HISTORY_JOINT','joint_curve'),
                          ('HISTORY_MARGINAL_EXACT','marginal_curve')):
            expected=[expected_objective(full.state(rep),context=context,service=service,
                u=u,u_max=row['u_max'],lambda_policy=row['lambda_policy'],
                view=PROFILES['BALANCED']) for u in action_grid(row['u_max'])]
            observed=[value for _,value in row[field]]
            maximum=max(maximum,*(abs(a-b) for a,b in zip(expected,observed)))
            checked+=len(expected)
    if maximum>1e-9:raise ValueError('P1_POLICY_EXACT_OBJECTIVE_PARITY_FAILED')
    return dict(status='PASS_REAL_DEVELOPMENT_ONE_NODE_EXACT_PARITY',year=prior['year'],
        scope='TWO_EPISODE_PILOT_ONE_NODE_NOT_FULL_YEAR',node_id=nid,
        joint_scenarios=len(full.state('HISTORY_JOINT').scenarios),
        exact_marginal_product_scenarios=count,settings_n=len({r['policy_id'] for r in rows}),
        objective_rows_n=len(rows),direct_authority_action_values_checked=checked,
        max_absolute_error=maximum,elapsed_seconds=elapsed,
        source=dict(cache_manifest_sha256=file_hash(root/'CACHE_MANIFEST.json'),
            prior_summary_sha256=file_hash(prior_path),state_payload_sha256=file_hash(
                root/'states'/(nid.replace(':','_')+'.json')),
            algorithm_sha256=code_hash(Path(__file__).with_name('policy_sensitivity.py'))),
        model_inference_calls=0,full_annual_execution=False,final_test_access_count=0)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shared-root',type=Path,required=True)
    parser.add_argument('--prior-e2e3',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=verify(args.shared_root,args.prior_e2e3)
    atomic_json(args.output,result)
    print(json.dumps(dict(status=result['status'],node_id=result['node_id'],
        max_absolute_error=result['max_absolute_error'],elapsed_seconds=result['elapsed_seconds'])))
