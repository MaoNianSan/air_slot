"""One persisted real-state fixture exercises new evaluation/resume interfaces.

This is computational evidence only: the source fixture uses its original
tail identity and is never relabelled an annual scientific result.
"""
import argparse
import json
from pathlib import Path
import time

from .shared_store import SharedStore,atomic_json,file_hash
from .shared_science import load_scores,export_e1_table
from .shared_actions import run_actions


def run(source_root,output_root):
    source_root=Path(source_root);out=Path(output_root);started=time.monotonic()
    manifest=json.loads((source_root/'CACHE_MANIFEST.json').read_text())
    source_store=SharedStore(source_root/'states',manifest['identity'])
    row=next(row for row in load_scores(source_root)
             if row['stage']=='PRE_IB' and row['support_full'].get('HISTORY_MARGINAL_EXACT'))
    key=row['node_id'].replace(':','_');state=source_store.read(key)
    identity=dict(manifest['identity'],episode_limit=1,
        validation_scope='CACHED_REAL_STATE_ADAPTER_FIXTURE_NOT_ANNUAL_MAIN_RESULT',
        fixture_manifest_sha256=file_hash(source_root/'CACHE_MANIFEST.json'))
    shared=out/'shared';scores=SharedStore(shared/'stage1',identity);states=SharedStore(shared/'states',identity)
    states.commit(key,state);row['is_canonical']=True
    scores.commit('chunk_0000',dict(rows=[row]));scores.commit('COMPLETE',dict(chunks=1))
    atomic_json(shared/'CACHE_MANIFEST.json',dict(identity=identity,identity_hash=scores.identity_hash,chunks=1))
    export_e1_table(shared);export_e1_table(shared,track='FIXED_COMMON')
    from model.M1.pipeline import M1Pipeline
    original=M1Pipeline.sample_from_pre
    def forbidden(*_,**__):raise AssertionError('UNEXPECTED_M1_INFERENCE')
    M1Pipeline.sample_from_pre=forbidden
    try:
        first=run_actions(shared,out/'evaluation',replicates=25)
        import exp.jatm_s34.shared_actions as actions
        calculate=actions.calculate_node;actions.calculate_node=forbidden
        try:
            second=run_actions(shared,out/'evaluation',replicates=25)
            if first!=second:
                atomic_json(out/'FRESH_DIAGNOSTIC.json',first)
                atomic_json(out/'RESTORED_DIAGNOSTIC.json',second)
            assert first==second,'RESTORED_RESULTS_DIFFER'
            saved=SharedStore(out/'evaluation/actions',first['action_identity']).read(key)
            ledger=out/'evaluation/actions'/saved['native_response_ledger']['path']
            content=ledger.read_bytes()
            ledger.write_bytes(content+b'corrupt')
            try:
                try:run_actions(shared,out/'evaluation',replicates=25)
                except ValueError as error:
                    assert 'LEDGER_MISSING_OR_CORRUPT' in str(error)
                else:raise AssertionError('CORRUPT_LEDGER_ACCEPTED')
            finally:ledger.write_bytes(content)
        finally:actions.calculate_node=calculate
    finally:M1Pipeline.sample_from_pre=original
    receipt=dict(status='PASS_CACHED_REAL_STATE_ADAPTER_ACCEPTANCE',scope=identity['validation_scope'],
        source_cache_sha256=identity['fixture_manifest_sha256'],node_id=row['node_id'],
        model_inference_calls=0,full_development_experiment=False,fixture_bootstrap_replicates=25,
        checks=['both_CU_views','pairwise_support','coverage_reconstructed_bootstrap','four_objectives',
                'nominal_policy','mechanism_response_ledger','identical_fresh_resume','corrupt_ledger_rejected'],
        numerical_report='separate current-annual-tail shared_golden acceptance',
        final_test_access_count=0,wall_seconds=time.monotonic()-started)
    atomic_json(out/'ADAPTER_ACCEPTANCE.json',receipt)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True)
    a=p.parse_args();run(a.source_root,a.output_root)
