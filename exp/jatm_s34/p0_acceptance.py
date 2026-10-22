"""Bounded P0 acceptance on the existing two-episode, five-node real cache.

No M1 inference, training, annual run, protected split or cloud operation.
The cached source retains its original (legacy tail) identity.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time

import numpy as np

from .shared_science import load_scores
from .shared_store import atomic_json, file_hash
from .shared_actions import run_actions


def direct_ratio_check(rows, observed, *, replicates=2000, seed=20261011,
                       numerator='reference_regret', denominator='V'):
    rows=[r for r in rows if r.get(numerator) is not None and r.get(denominator) is not None
          and np.isfinite(r[numerator]) and np.isfinite(r[denominator])]
    episodes=sorted({r['episode_id'] for r in rows})
    def ratio(sample):
        valid=[r for r in sample if r.get(numerator) is not None and r.get(denominator) is not None
               and np.isfinite(r[numerator]) and np.isfinite(r[denominator])]
        a=sum(r[numerator] for r in valid);b=sum(r[denominator] for r in valid)
        return (None if b<=0 else a/b),a,b
    point,a,b=ratio(rows)
    assert observed['L_rec']==point
    assert observed['delta_rec_sum']==a and observed['V_ref_sum']==b
    rng=np.random.default_rng(seed);samples=[]
    if episodes:
        for _ in range(replicates):
            draw=rng.integers(0,len(episodes),size=len(episodes))
            sample=[r for i in draw for r in rows if r['episode_id']==episodes[i]]
            value,_,_=ratio(sample)
            if value is not None:samples.append(value)
    assert observed['valid_replicates']==len(samples)
    for name,q in (('ci_low',.025),('ci_high',.975)):
        expected=None if not samples else float(np.quantile(samples,q))
        if expected is None:assert observed[name] is None
        else:assert np.isclose(observed[name],expected,rtol=1e-12,atol=1e-12)


def run(source_root, output_root):
    started=time.monotonic();root=Path(source_root);out=Path(output_root)
    source_manifest=json.loads((root/'CACHE_MANIFEST.json').read_text())
    rows=list(load_scores(root));canonical={r['node_id'] for r in rows if r.get('is_canonical',True)}
    assert len({r['episode_id'] for r in rows})==2 and len(canonical)==5,'BOUNDED_FIXTURE_REQUIRED'
    assert source_manifest['identity'].get('episode_limit')==2
    source_hash=file_hash(root/'CACHE_MANIFEST.json')
    from model.M1.pipeline import M1Pipeline
    original=M1Pipeline.sample_from_pre
    def forbidden(*_,**__):raise AssertionError('P0_ACCEPTANCE_UNEXPECTED_MODEL_INFERENCE_OR_RECOMPUTE')
    M1Pipeline.sample_from_pre=forbidden
    try:
        result=run_actions(root,out/'evaluation',replicates=2000)
        import exp.jatm_s34.shared_actions as actions
        calculate=actions.calculate_node;actions.calculate_node=forbidden
        try:restored=run_actions(root,out/'evaluation',replicates=2000)
        finally:actions.calculate_node=calculate
        assert result==restored,'P0_RESUME_SUMMARY_CHANGED'
    finally:M1Pipeline.sample_from_pre=original
    assert set(result['populations']['C1'])<=canonical
    counts={};checked=0
    for track,atomic_key,summary_key,groups in (
            ('YEAR_LOCAL','recovery_atomic','recovery_summary',result['populations']['C2']),
            ('FIXED_COMMON','fixed_common_recovery_atomic','fixed_common_recovery_summary',result['fixed_common_C2_groups'])):
        atomic=result[atomic_key]
        ids=result['populations'] if track=='YEAR_LOCAL' else result['fixed_common_population_ids']
        for summary in result[summary_key]:
            population=summary['population']
            if population.startswith('C2::'):
                descriptor=groups[population[4:]]
                assert descriptor['cu_track']==track and descriptor['family']=='E2'
                allowed=set(descriptor['node_ids'])
            elif population=='ANNUAL_HJ_SHORTLIST' and track=='YEAR_LOCAL':
                allowed={nid for values in ids[population].values() for nid in values}
            else:allowed=set(ids[population])
            selected=[r for r in atomic if r['node_id'] in allowed and r['stage']==summary['stage']
                      and r['representation']==summary['representation']]
            direct_ratio_check(selected,summary['recovery_loss']);checked+=1
        counts[track]=dict(canonical_C1=len(ids['C1']),rolling_C3=len(ids['C3']),C2_groups=len(groups))
    for rows_key,summary_key in (('e3_rows','e3_summary'),('fixed_common_e3_rows','fixed_common_e3_summary')):
        joint={(r['node_id'],r['profile']):r for r in result[rows_key] if r['representation']=='HISTORY_JOINT'}
        for summary in result[summary_key]:
            selected=[]
            for row in result[rows_key]:
                if row['representation']!='HISTORY_MARGINAL_EXACT' or row['profile']!=summary['profile'] or row['stage']!=summary['stage']:continue
                ref=joint[row['node_id'],row['profile']]
                selected.append(dict(row,reference_V=ref['J_zero']-ref['J_star']))
            direct_ratio_check(selected,summary['recovery_loss'],numerator='joint_reference_loss_at_marginal_action',denominator='reference_V')
            checked+=1
    assert file_hash(root/'CACHE_MANIFEST.json')==source_hash
    receipt=dict(status='PASS_BOUNDED_P0_REAL_CACHE_ACCEPTANCE',episodes=2,canonical_nodes=5,
        source_cache_sha256=source_hash,source_identity=source_manifest['identity'],populations=counts,
        bootstrap_replicates=2000,ratio_and_ci_summaries_checked=checked,
        fresh_resume_identical=True,model_inference_calls=0,final_test_access_count=0,
        full_development_experiment=False,scope='LEGACY_TAIL_CACHED_STATES_COMPUTATIONAL_ACCEPTANCE_ONLY',
        current_tail_numerical_evidence='SEPARATE_SHARED_GOLDEN_TWO_EPISODE_FIVE_NODE_CHECK',
        git_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        wall_seconds=time.monotonic()-started)
    atomic_json(out/'P0_REAL_CACHE_ACCEPTANCE.json',receipt)
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--output-root',type=Path,required=True)
    args=parser.parse_args();run(args.source_root,args.output_root)
