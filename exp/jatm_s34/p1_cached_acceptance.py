"""Read-only P1 numerical check on a hashed Development pilot cache."""
import argparse
import json
from math import isclose
from pathlib import Path

from .shared_science import load_scores, unpack_node
from .shared_statistics import e1_recovery_coverage
from .shared_store import SharedStore, atomic_json, file_hash


def verify(shared_root, prior_e2e3, *, replicates=2000):
    shared_root=Path(shared_root);prior_e2e3=Path(prior_e2e3)
    cache=json.loads((shared_root/'CACHE_MANIFEST.json').read_text())
    prior=json.loads(prior_e2e3.read_text())
    if prior['shared_identity_hash']!=cache['identity_hash']:
        raise ValueError('P1_ACCEPTANCE_CACHE_IDENTITY_MISMATCH')
    if prior['year']!=cache['identity']['year'] or prior['scope']!='PILOT':
        raise ValueError('P1_ACCEPTANCE_REQUIRES_MATCHED_DEVELOPMENT_PILOT')
    source=list(load_scores(shared_root))
    nodes=[unpack_node(row) for row in source]
    stage1=SharedStore(shared_root/'stage1',cache['identity'])
    canonical={nid for i in range(cache['chunks'])
               for nid in stage1.read(f'chunk_{i:04d}')['canonical_ids']}
    exposure={row['node_id']:tuple(row['exposure']) for row in source if row.get('exposure') is not None}
    c1=set(prior['populations']['C1'])
    coverage=e1_recovery_coverage(prior['recovery_records'],nodes,canonical,exposure,
        c1_ids=c1,replicates=replicates)
    if len(coverage)!=128:raise ValueError('P1_ACCEPTANCE_COVERAGE_ROW_COUNT')
    balanced_values={}
    for record in prior['recovery_records']:
        if record['status']!='ACTION_TABLE_COMPLETE':continue
        rows=[row for row in record['rows'] if row['representation']=='HISTORY_JOINT'
              and row['profile']=='BALANCED']
        if len(rows)!=1:raise ValueError('P1_ACCEPTANCE_BALANCED_REFERENCE_MISSING')
        balanced_values[record['node_id']]=rows[0]['J_zero']-rows[0]['J_star']
    if not c1 <= balanced_values.keys():
        raise ValueError('P1_ACCEPTANCE_C1_REFERENCE_INCOMPLETE')
    shortlist_checked=0;max_numerator_error=0.;max_denominator_error=0.
    by_stage={node.node_id:node.stage.value for node in nodes}
    delay_rows={(row['stage'],row['q']):row for row in coverage
                if row['profile']=='BALANCED' and row['view']=='DELAY'}
    for row in coverage:
        if row['profile']!='BALANCED' or row['q']!=.10:continue
        key=row['stage']+':'+row['view']
        prior_selection=prior['populations']['E1_SCREENING'].get(key)
        if prior_selection is None:continue
        if (row['screening_candidate_n'],row['k'])!=(prior_selection['n'],prior_selection['k']):
            raise ValueError('P1_ACCEPTANCE_E1_N_K_MISMATCH:'+key)
        if len(prior_selection['nodes'])!=row['k']:
            raise ValueError('P1_ACCEPTANCE_OLD_SHORTLIST_SIZE_MISMATCH:'+key)
        direct_numerator=sum(balanced_values.get(nid,0.) for nid in prior_selection['nodes']
                             if nid in c1)
        direct_denominator=sum(balanced_values[nid] for nid in c1
                               if by_stage[nid]==row['stage'])
        numerator_error=abs(row['numerator']-direct_numerator)
        denominator_error=abs(row['reference_recoverable_value_sum']-direct_denominator)
        max_numerator_error=max(max_numerator_error,numerator_error)
        max_denominator_error=max(max_denominator_error,denominator_error)
        if not isclose(row['numerator'],direct_numerator,abs_tol=1e-10,rel_tol=0):
            raise ValueError('P1_ACCEPTANCE_E1_NUMERATOR_MISMATCH:'+key)
        if not isclose(row['reference_recoverable_value_sum'],direct_denominator,
                       abs_tol=1e-10,rel_tol=0):
            raise ValueError('P1_ACCEPTANCE_E1_DENOMINATOR_MISMATCH:'+key)
        if direct_denominator>0:
            delay=delay_rows[row['stage'],row['q']]
            delta=(direct_numerator-delay['numerator'])/direct_denominator
            if not isclose(row['paired_delta_vs_delay'],delta,abs_tol=1e-10,rel_tol=0):
                raise ValueError('P1_ACCEPTANCE_E1_PAIRED_DELTA_MISMATCH:'+key)
        shortlist_checked+=1
    max_difference_error=0.
    for row in prior['mechanisms']:
        joint=dict(row['joint_curve']);marginal=dict(row['marginal_curve'])
        for action,old in row['fixed_target_difference'].items():
            value=joint[float(action)]-marginal[float(action)]
            max_difference_error=max(max_difference_error,abs(value+old))
    if max_difference_error>1e-10:raise ValueError('P1_ACCEPTANCE_E3_SIGN_MISMATCH')
    from .scientific_tracks import nominal_headroom,nominal_policy_metadata
    nominal=nominal_headroom(prior['year'])
    if (nominal.turnaround_lower_bound_q,nominal.u_max,nominal.headroom_positive_n)!=(41.,45.,0):
        raise ValueError('P1_ACCEPTANCE_NOMINAL_POLICY_MISMATCH')
    return dict(status='PASS_TARGETED_REAL_DEVELOPMENT_CACHE',scope='PILOT_NOT_FULL_DEVELOPMENT',
        year=prior['year'],episode_limit=cache['identity']['episode_limit'],
        source=dict(shared_cache_sha256=file_hash(shared_root/'CACHE_MANIFEST.json'),
            prior_e2e3_sha256=file_hash(prior_e2e3),shared_identity_hash=cache['identity_hash']),
        canonical_n=len(canonical),c1_n=len(c1),coverage_rows=len(coverage),
        balanced_nominal_shortlists_checked=shortlist_checked,
        e1_numerator_max_absolute_error=max_numerator_error,
        e1_denominator_max_absolute_error=max_denominator_error,
        coverage_defined_n=sum(row['status']=='DEFINED' for row in coverage),
        coverage_nondefined_reasons=sorted({row['status'] for row in coverage if row['status']!='DEFINED'}),
        e3_mechanism_rows_checked=len(prior['mechanisms']),
        e3_sign_max_absolute_error=max_difference_error,
        nominal_policy=nominal_policy_metadata(),bootstrap_replicates=replicates,
        model_inference_calls=0,full_annual_execution=False,final_test_access_count=0,
        sample_coverage=[row for row in coverage if row['profile']=='BALANCED' and row['q']==.10])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shared-root',type=Path,required=True)
    parser.add_argument('--prior-e2e3',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=verify(args.shared_root,args.prior_e2e3)
    atomic_json(args.output,result)
    print(json.dumps(dict(status=result['status'],coverage_rows=result['coverage_rows'],
        e3_mechanism_rows_checked=result['e3_mechanism_rows_checked'])))
