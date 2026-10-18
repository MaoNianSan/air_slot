"""Production annual shared chain. Partial runs are always labelled PILOT."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import signal
import sys
import time
import uuid

from .shared_store import SharedStore,atomic_json,file_hash,code_hash,digest


def evaluation_identity(shared_root, *, replicates=2000, seed=20261011):
    root=Path(shared_root)
    source=Path(__file__).resolve().parents[2]
    paths=[p for folder in ('model/M3','model/M4','exp/jatm_section5')
           for p in (source/folder).rglob('*.py')]
    paths.extend(Path(__file__).with_name(name) for name in
                 ('shared_actions.py','e1_shared_evaluation.py','e2_e3_exact.py','annual_cu.py',
                  'shared_statistics.py','scientific_tracks.py','mechanisms.py','exact_stream.py',
                  'shared_populations.py','shared_store.py','shared_science.py','e1_information_gain.py',
                  'shared_revaluation.py','policy_sensitivity.py','shared_run.py'))
    return dict(cache_manifest=file_hash(root/'CACHE_MANIFEST.json'),
        score_manifest=file_hash(root/'SHARED_ANNUAL_MANIFEST.json'),
        replicates=replicates,seed=seed,algorithm_hash=digest({p.relative_to(source).as_posix():code_hash(p) for p in paths}))


def evaluation_is_current(output_root, identity):
    root=Path(output_root)
    for stage, folder, summary in EVALUATION_STAGES:
        stage_id=evaluation_stage_identity(root,identity,stage)
        if not stage_receipt_is_current(root,stage,stage_id,folder,summary):
            return False
    receipt=root/'EVALUATION_COMPLETE.json'
    if not receipt.is_file():return False
    try:saved=json.loads(receipt.read_text(encoding='utf-8'))
    except (OSError,ValueError):return False
    if saved.get('identity')!=identity:return False
    expected={stage:stage_receipt_hash(root,stage) for stage,_,_ in EVALUATION_STAGES}
    summary_paths=('E1/E1_PAIRED_SUMMARY.json','E1_FIXED_COMMON/E1_PAIRED_SUMMARY.json',
                   'E2_E3/E2_E3_SUMMARY.json')
    output_hashes={name:file_hash(root/name) for name in summary_paths
                   if (root/name).is_file()}
    return (saved.get('stage_receipts')==expected
            and set(output_hashes)==set(summary_paths)
            and saved.get('outputs')==output_hashes)


EVALUATION_STAGES=(
    ('E1_YEAR_LOCAL','E1','E1_PAIRED_SUMMARY.json'),
    ('E1_FIXED_COMMON','E1_FIXED_COMMON','E1_PAIRED_SUMMARY.json'),
    ('E2_E3','E2_E3','E2_E3_SUMMARY.json'),
)


def stage_identity(base_identity,stage,dependencies):
    return dict(schema_version='JATM_EVALUATION_STAGE_IDENTITY_V1',stage=stage,
        evaluation_identity=base_identity,dependencies=dependencies)


def evaluation_stage_identity(root,base_identity,stage):
    dependencies={}
    if stage=='E1_FIXED_COMMON':
        fixed=Path(root)/'shared/fixed_common'
        try:
            dependencies={
                'fixed_cache_manifest':file_hash(fixed/'CACHE_MANIFEST.json'),
                'fixed_score_manifest':file_hash(fixed/'SHARED_ANNUAL_MANIFEST.json')}
        except FileNotFoundError:
            return stage_identity(base_identity,stage,{'missing_fixed_shared_identity':True})
    return stage_identity(base_identity,stage,dependencies)


def _stage_paths(root,stage):
    receipts=Path(root)/'receipts_v2'
    safe=stage.replace('/','_')
    return receipts/'attempts'/safe,receipts/'current'/f'{safe}.json'


def _output_inventory(root,folder):
    directory=Path(root)/folder
    if not directory.is_dir():
        raise FileNotFoundError(f'EVALUATION_STAGE_OUTPUT_DIRECTORY_MISSING:{folder}')
    files=sorted(path for path in directory.rglob('*') if path.is_file())
    if not files:
        raise FileNotFoundError(f'EVALUATION_STAGE_OUTPUTS_MISSING:{folder}')
    if any(path.name.endswith('.tmp') for path in files):
        raise ValueError(f'EVALUATION_STAGE_TEMPORARY_OUTPUT_PRESENT:{folder}')
    return [dict(path=path.relative_to(Path(root)).as_posix(),size_bytes=path.stat().st_size,
                 sha256=file_hash(path)) for path in files]


def stage_receipt_hash(root,stage):
    _,pointer=_stage_paths(root,stage)
    if not pointer.is_file():return None
    return file_hash(pointer)


def stage_receipt_is_current(root,stage,identity,folder,summary):
    attempts,pointer=_stage_paths(root,stage)
    if not pointer.is_file():return False
    try:
        selected=json.loads(pointer.read_text(encoding='utf-8'))
        if (selected.get('schema_version')!='JATM_STAGE_RECEIPT_POINTER_V2'
                or selected.get('stage')!=stage
                or selected.get('identity_hash')!=digest(identity)):
            return False
        receipt_path=(attempts/selected['attempt_file']).resolve()
        if receipt_path.parent!=attempts.resolve() or not receipt_path.is_file():return False
        if file_hash(receipt_path)!=selected.get('receipt_sha256'):return False
        receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
        if (receipt.get('schema_version')!='JATM_STAGE_RECEIPT_V2'
                or receipt.get('status')!='COMPLETE' or receipt.get('stage')!=stage
                or receipt.get('identity')!=identity
                or receipt.get('identity_hash')!=digest(identity)
                or receipt.get('validation',{}).get('status')!='PASS'
                or receipt.get('provenance',{}).get('final_test_access_count')!=0):
            return False
        outputs=receipt.get('outputs',[])
        if not outputs or not any(row.get('path')==(Path(folder)/summary).as_posix() for row in outputs):
            return False
        root_path=Path(root).resolve()
        for row in outputs:
            path=(root_path/row['path']).resolve()
            if root_path not in path.parents or not path.is_file():return False
            if path.stat().st_size!=row['size_bytes'] or file_hash(path)!=row['sha256']:
                return False
        return True
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError):
        return False


def publish_stage_receipt(root,stage,identity,folder,summary):
    attempts,pointer=_stage_paths(root,stage)
    attempts.mkdir(parents=True,exist_ok=True);pointer.parent.mkdir(parents=True,exist_ok=True)
    outputs=_output_inventory(root,folder)
    summary_path=(Path(folder)/summary).as_posix()
    if not any(row['path']==summary_path for row in outputs):
        raise FileNotFoundError(f'EVALUATION_STAGE_REQUIRED_SUMMARY_MISSING:{summary_path}')
    summary_payload=json.loads((Path(root)/summary_path).read_text(encoding='utf-8'))
    if not isinstance(summary_payload,dict) or summary_payload.get('final_test_access_count')!=0:
        raise ValueError(f'EVALUATION_STAGE_SUMMARY_CONTRACT_INVALID:{summary_path}')
    identity_hash=digest(identity)
    attempt_id=f"{uuid.uuid4().hex}"
    receipt=dict(schema_version='JATM_STAGE_RECEIPT_V2',stage=stage,attempt_id=attempt_id,
        status='COMPLETE',identity=identity,identity_hash=identity_hash,outputs=outputs,
        validation=dict(status='PASS',contract_version='JATM_STAGE_RECEIPT_VALIDATOR_V2'),
        provenance=dict(git_head=__import__('exp.jatm_s34.runtime_provenance',fromlist=['code_revision']).code_revision(),
                        final_test_access_count=0))
    receipt_path=attempts/f'{attempt_id}.json'
    atomic_json(receipt_path,receipt)
    atomic_json(pointer,dict(schema_version='JATM_STAGE_RECEIPT_POINTER_V2',stage=stage,
        attempt_file=receipt_path.name,identity_hash=identity_hash,receipt_sha256=file_hash(receipt_path)))
    return file_hash(pointer)


def _run_evaluation_stages(root,shared_root,identity,*,e1_runner,fixed_prepare,fixed_runner,e2e3_runner):
    root=Path(root);shared_root=Path(shared_root)
    fixed_shared=shared_root/'fixed_common'
    by_stage={stage:(folder,summary) for stage,folder,summary in EVALUATION_STAGES}
    stage_hashes={}
    stage='E1_YEAR_LOCAL';folder,summary=by_stage[stage]
    stage_id=evaluation_stage_identity(root,identity,stage)
    if not stage_receipt_is_current(root,stage,stage_id,folder,summary):
        e1_runner(shared_root,root/folder)
        publish_stage_receipt(root,stage,stage_id,folder,summary)
    stage_hashes[stage]=stage_receipt_hash(root,stage)

    stage='E1_FIXED_COMMON';folder,summary=by_stage[stage]
    stage_id=evaluation_stage_identity(root,identity,stage)
    if not stage_receipt_is_current(root,stage,stage_id,folder,summary):
        fixed_prepare()
        stage_id=evaluation_stage_identity(root,identity,stage)
        fixed_runner(fixed_shared,root/folder)
        publish_stage_receipt(root,stage,stage_id,folder,summary)
    stage_hashes[stage]=stage_receipt_hash(root,stage)

    stage='E2_E3';folder,summary=by_stage[stage]
    stage_id=evaluation_stage_identity(root,identity,stage)
    if not stage_receipt_is_current(root,stage,stage_id,folder,summary):
        e2e3_runner(shared_root,root/folder)
        publish_stage_receipt(root,stage,stage_id,folder,summary)
    stage_hashes[stage]=stage_receipt_hash(root,stage)
    if any(value is None for value in stage_hashes.values()):
        raise RuntimeError('EVALUATION_STAGE_RECEIPT_MISSING_AFTER_RUN')
    atomic_json(root/'EVALUATION_COMPLETE.json',dict(schema_version='JATM_EVALUATION_COMPLETE_V2',
        identity=identity,stage_receipts=stage_hashes,
        outputs={name:file_hash(root/name) for name in (
            'E1/E1_PAIRED_SUMMARY.json','E1_FIXED_COMMON/E1_PAIRED_SUMMARY.json',
            'E2_E3/E2_E3_SUMMARY.json')}))


def run(year,output_root,*,device='cpu',threads=1,chunk_size=32,episode_limit=None,phase='all',
        continuity_contract='JATM_F_CONTINUITY_B_V1'):
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
                        episode_limit=episode_limit,phase=phase,continuity_contract=continuity_contract)
        finally:
            for sig,handler in previous.items():signal.signal(sig,handler)


def _run(year,output_root,*,device,threads,chunk_size,episode_limit,phase,continuity_contract):
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
        continuity_contract=continuity_contract,
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
            materialize(year,out/'shared',chunk_size=chunk_size,node_limit=episode_limit,device=device,
                        continuity_contract=continuity_contract)
        if not (out/'shared/CACHE_MANIFEST.json').is_file():
            manifest['status']='PAUSED_AT_CHECKPOINT'
        else:
            cached=json.loads((out/'shared/CACHE_MANIFEST.json').read_text())
            expected=execution_identity(year,4096,chunk_size,episode_limit,device,
                                        continuity_contract=continuity_contract)
            if cached['identity_hash']!=digest(expected):
                raise ValueError('EVALUATION_SHARED_INPUT_OR_ALGORITHM_MISMATCH')
            if phase in ('all','evaluate'):
                from .e1_shared_evaluation import run as e1
                from .shared_actions import run_actions
                identity=evaluation_identity(out/'shared')
                if not evaluation_is_current(out,identity):
                    from .shared_science import export_e1_table
                    def prepare_fixed():
                        export_e1_table(out/'shared',track='FIXED_COMMON')
                    _run_evaluation_stages(out,out/'shared',identity,
                        e1_runner=e1,fixed_prepare=prepare_fixed,fixed_runner=e1,
                        e2e3_runner=lambda src,dst:run_actions(
                            src,dst,continuity_contract=continuity_contract))
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
    parser.add_argument('--continuity-contract', choices=('LEGACY_A_V1','JATM_F_CONTINUITY_B_V1'),
                        default='JATM_F_CONTINUITY_B_V1')
    args=parser.parse_args()
    run(args.year,args.output_root,device=args.device,threads=args.threads,chunk_size=args.chunk_size,
        episode_limit=args.episode_limit,phase=args.phase,continuity_contract=args.continuity_contract)
