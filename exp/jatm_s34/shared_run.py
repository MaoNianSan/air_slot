"""Production annual shared chain. Partial runs are always labelled PILOT."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import signal
import sys
import time

from .shared_store import SharedStore,atomic_json,file_hash,code_hash,digest


def evaluation_identity(shared_root, *, replicates=2000, seed=20261011):
    root=Path(shared_root)
    source=Path(__file__).resolve().parents[2]
    paths=[p for folder in ('model/M3','model/M4','exp/jatm_section5')
           for p in (source/folder).rglob('*.py')]
    paths.extend(Path(__file__).with_name(name) for name in
                 ('shared_actions.py','e1_shared_evaluation.py','e2_e3_exact.py','annual_cu.py',
                  'shared_statistics.py','scientific_tracks.py','mechanisms.py','exact_stream.py',
                  'shared_populations.py','shared_store.py','shared_science.py','e1_information_gain.py','shared_revaluation.py'))
    return dict(cache_manifest=file_hash(root/'CACHE_MANIFEST.json'),
        score_manifest=file_hash(root/'SHARED_ANNUAL_MANIFEST.json'),
        replicates=replicates,seed=seed,algorithm_hash=digest({p.relative_to(source).as_posix():code_hash(p) for p in paths}))


def evaluation_is_current(output_root, identity):
    root=Path(output_root);receipt=root/'EVALUATION_COMPLETE.json'
    if not receipt.is_file():return False
    saved=json.loads(receipt.read_text())
    if saved.get('identity')!=identity:return False
    return all((root/name).is_file() and file_hash(root/name)==sha
               for name,sha in saved['outputs'].items()) and set(saved['outputs'])=={
                   'E1/E1_PAIRED_SUMMARY.json','E1_FIXED_COMMON/E1_PAIRED_SUMMARY.json','E2_E3/E2_E3_SUMMARY.json'}


def run(year,output_root,*,device='cpu',threads=1,chunk_size=32,episode_limit=None,phase='all'):
    if threads<1 or chunk_size<1 or (episode_limit is not None and episode_limit<1):
        raise ValueError('POSITIVE_RESOURCE_AND_EPISODE_COUNTS_REQUIRED')
    with SharedStore(output_root,{'year':year}).writer():
        marker=Path(output_root)/'shared/STOP_REQUESTED'
        def request_stop(*_):
            marker.parent.mkdir(parents=True,exist_ok=True)
            marker.touch()
        previous={sig:signal.signal(sig,request_stop) for sig in (signal.SIGINT,signal.SIGTERM)}
        try:
            return _run(year,output_root,device=device,threads=threads,chunk_size=chunk_size,
                        episode_limit=episode_limit,phase=phase)
        finally:
            for sig,handler in previous.items():signal.signal(sig,handler)


def _run(year,output_root,*,device,threads,chunk_size,episode_limit,phase):
    import torch
    import psutil
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    from .runtime_provenance import select_device
    requested_device=device
    device,device_reason=select_device(device,cuda_available=torch.cuda.is_available(),pilot=episode_limit is not None)
    out=Path(output_root);out.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter()
    manifest=dict(schema_version='JATM_SHARED_RUN_V1',year=year,split='development',device=device,
        requested_device=requested_device,device_selection_reason=device_reason,
        threads=threads,chunk_size=chunk_size,episode_limit=episode_limit,
        scope='PILOT' if episode_limit is not None else 'FULL_DEVELOPMENT',
        git_head=__import__('exp.jatm_s34.runtime_provenance',fromlist=['code_revision']).code_revision(),
        created_at=datetime.now(timezone.utc).isoformat(),final_test_access_count=0,
        python=sys.version,torch=torch.__version__,cuda=torch.version.cuda,model_retrained=False)
    atomic_json(out/'RUN_MANIFEST.json',dict(manifest,status='RUNNING'))
    try:
        from .runtime_provenance import record
        record(out/'runtime')
        from .shared_science import materialize, execution_identity
        if (out/'shared/STOP_REQUESTED').exists():
            raise InterruptedError('EXPLICIT_STOP_MARKER_PRESENT')
        if phase in ('all','stage1'):
            materialize(year,out/'shared',chunk_size=chunk_size,node_limit=episode_limit,device=device)
        if not (out/'shared/CACHE_MANIFEST.json').is_file():
            manifest['status']='PAUSED_AT_CHECKPOINT'
        else:
            cached=json.loads((out/'shared/CACHE_MANIFEST.json').read_text())
            expected=execution_identity(year,4096,chunk_size,episode_limit,device)
            if cached['identity_hash']!=digest(expected):
                raise ValueError('EVALUATION_SHARED_INPUT_OR_ALGORITHM_MISMATCH')
            if phase in ('all','evaluate'):
                from .e1_shared_evaluation import run as e1
                from .shared_actions import run_actions
                identity=evaluation_identity(out/'shared')
                if not evaluation_is_current(out,identity):
                    e1(out/'shared',out/'E1')
                    from .shared_science import export_e1_table
                    export_e1_table(out/'shared',track='FIXED_COMMON')
                    e1(out/'shared/fixed_common',out/'E1_FIXED_COMMON')
                    run_actions(out/'shared',out/'E2_E3')
                    atomic_json(out/'EVALUATION_COMPLETE.json',dict(identity=identity,outputs={
                        name:file_hash(out/name) for name in ('E1/E1_PAIRED_SUMMARY.json','E1_FIXED_COMMON/E1_PAIRED_SUMMARY.json','E2_E3/E2_E3_SUMMARY.json')}))
            manifest['status']=('STAGE_I_COMPLETE' if phase=='stage1' else
                'PILOT_COMPLETE' if episode_limit is not None else 'COMPUTED_PENDING_SCIENTIFIC_ACCEPTANCE')
    except InterruptedError as error:
        manifest.update(status='PAUSED_AT_CHECKPOINT',reason=str(error))
    except Exception as error:
        manifest.update(status='FAILED',error_type=type(error).__name__,error=str(error))
        raise
    finally:
        manifest.update(wall_seconds=time.perf_counter()-started,rss_bytes=psutil.Process().memory_info().rss)
        atomic_json(out/'RUN_MANIFEST.json',manifest)
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year',type=int,choices=range(2017,2023),required=True)
    parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--device',choices=('cpu','cuda','auto'),default='cpu')
    parser.add_argument('--threads',type=int,default=1)
    parser.add_argument('--chunk-size',type=int,default=32)
    parser.add_argument('--episode-limit',type=int)
    parser.add_argument('--phase',choices=('all','stage1','evaluate'),default='all')
    args=parser.parse_args()
    run(args.year,args.output_root,device=args.device,threads=args.threads,chunk_size=args.chunk_size,
        episode_limit=args.episode_limit,phase=args.phase)
