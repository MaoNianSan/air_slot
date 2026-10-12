"""Resource-limited independent annual workers; supports local or cloud Linux/Windows."""
import argparse
from collections import deque
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import signal
from types import SimpleNamespace

import psutil
from .shared_store import SharedStore, atomic_json, digest


def schedule(args):
    with SharedStore(args.output_root, {'kind':'ANNUAL_SCHEDULER'}).writer():
        return _schedule(args)


def _schedule(args):
    if args.threads<1 or args.memory_per_worker_gib<=0 or args.reserve_gib<0:
        raise ValueError('INVALID_RESOURCE_BUDGET')
    if args.workers*args.threads > args.cpu_budget:
        raise ValueError('WORKER_THREADS_EXCEED_CPU_BUDGET')
    if not 1 <= args.workers <= 3 or len(args.years) != len(set(args.years)) or any(y not in range(2017,2023) for y in args.years):
        raise ValueError('INVALID_ANNUAL_SCHEDULER_CONFIGURATION')
    if getattr(args,'device','cpu') == 'cuda' and args.workers > 1:
        raise ValueError('CUDA_CONCURRENCY_REQUIRES_MEMORY_BENCHMARK_USE_ONE_WORKER')
    root=args.output_root.resolve();root.mkdir(parents=True,exist_ok=True)
    def request_stop(*_):(root/'STOP_REQUESTED').touch()
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,request_stop)
    queue=deque(args.years);active={};finished=[];start=time.monotonic()
    attempts={year:0 for year in args.years}
    max_retries=getattr(args,'max_retries',1)
    config={key:str(value) if isinstance(value,Path) else value for key,value in vars(args).items()}
    atomic_json(root/'SCHEDULER_CONFIG.json',dict(config=config,config_hash=digest(config)))
    status={}
    while queue or active:
        if (root/'STOP_REQUESTED').exists():
            queue.clear()
            for year in active:
                (root/str(year)/'shared').mkdir(exist_ok=True)
                (root/str(year)/'shared/STOP_REQUESTED').touch()
        free=psutil.virtual_memory().available/(1024**3)
        # Reserve the unconsumed part of admitted workers' peak budgets.
        for item in active.values():
            try:resident=psutil.Process(item['process'].pid).memory_info().rss/(1024**3)
            except psutil.NoSuchProcess:resident=0
            free-=max(0,args.memory_per_worker_gib-resident)
        while queue and len(active)<args.workers and free>=args.memory_per_worker_gib+args.reserve_gib:
            year=queue.popleft();out=root/str(year);out.mkdir(exist_ok=True)
            env=dict(os.environ)
            for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'):
                env[key]=str(args.threads)
            command=[sys.executable,'-u','-m','exp.jatm_s34.cloud_worker','--year',str(year),
                '--output-root',str(out),'--threads',str(args.threads),'--chunk-size',str(args.chunk_size),
                '--device',args.device,'--phase',args.phase]
            if args.episode_limit is not None:command+=['--episode-limit',str(args.episode_limit)]
            if getattr(args,'tail_decision',None):command+=['--tail-decision',str(args.tail_decision)]
            log=(out/'worker.log').open('a',encoding='utf-8')
            process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,cwd=Path(__file__).resolve().parents[2],
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            active[year]=dict(process=process,log=log,started=time.monotonic(),peak_rss=0,peak_private=0,command=command)
            attempts[year]+=1
            free-=args.memory_per_worker_gib
        for year,item in list(active.items()):
            process=item['process']
            try:
                memory=psutil.Process(process.pid).memory_info()
                item['peak_rss']=max(item['peak_rss'],memory.rss)
                item['peak_private']=max(item['peak_private'],getattr(memory,'private',0))
            except psutil.NoSuchProcess:pass
            if process.poll() is not None:
                item['log'].close()
                outcome=dict(year=year,exit_code=process.returncode,wall_seconds=time.monotonic()-item['started'],
                    peak_rss_bytes=item['peak_rss'],peak_private_bytes=item['peak_private'],command=item['command'],
                    run_manifest=None if not (root/str(year)/'RUN_MANIFEST.json').is_file() else
                        json.loads((root/str(year)/'RUN_MANIFEST.json').read_text()),attempt=attempts[year])
                finished.append(outcome)
                report=outcome['run_manifest'] or {}
                transient=report.get('status')=='IO_FAILED' or report.get('error_type') in ('OSError','TimeoutError','ConnectionError')
                if transient and attempts[year]<=max_retries and not (root/'STOP_REQUESTED').exists():
                    queue.append(year)
                del active[year]
        status=dict(active={str(y):dict(pid=i['process'].pid,peak_rss_bytes=i['peak_rss'],peak_private_bytes=i['peak_private'],
            elapsed_seconds=time.monotonic()-i['started']) for y,i in active.items()},
            pending=list(queue),finished=finished,available_gib=psutil.virtual_memory().available/(1024**3),
            elapsed_seconds=time.monotonic()-start,final_test_access_count=0,
            status='RUNNING' if active or queue else 'BENCHMARK_OR_DEVELOPMENT_EXECUTION_FINISHED')
        atomic_json(root/'SCHEDULER_PROGRESS.json',status)
        if queue and not active and free<args.memory_per_worker_gib+args.reserve_gib:
            raise RuntimeError('RESOURCE_BLOCKED_INSUFFICIENT_AVAILABLE_MEMORY')
        if (root/'STOP_REQUESTED').exists():
            queue.clear()
            for year in active:
                (root/str(year)/'shared').mkdir(exist_ok=True)
                (root/str(year)/'shared/STOP_REQUESTED').touch()
        if active:time.sleep(5)
    latest={row['year']:row for row in finished}
    status['six_year_complete']=False
    status['annual_outcomes']={str(year):latest.get(year,dict(year=year,status='NOT_REQUESTED_OR_NOT_RUN'))
                              for year in range(2017,2023)}
    if (root/'STOP_REQUESTED').exists():
        status['status']='PAUSED_AT_CHECKPOINT'
    elif getattr(args,'phase',None)=='all' and args.episode_limit is None:
        all_workers_ok=(set(args.years)==set(range(2017,2023)) and all(
            year in latest and latest[year]['exit_code']==0
            and (latest[year]['run_manifest'] or {}).get('year')==year
            and (latest[year]['run_manifest'] or {}).get('scope')=='FULL_DEVELOPMENT'
            and (latest[year]['run_manifest'] or {}).get('status')=='COMPUTED_PENDING_SCIENTIFIC_ACCEPTANCE'
            for year in range(2017,2023)))
        status['status']='SIX_YEAR_EXECUTION_BLOCKED'
        if all_workers_ok:
            from .e4_shared_aggregate import aggregate,inspect_annual_result
            checked=[inspect_annual_result(root,year)[0] for year in range(2017,2023)]
            status['annual_output_validation']=checked
            if all(row['status']=='COMPUTED_PENDING_SCIENTIFIC_ACCEPTANCE' for row in checked):
                status['e4']=aggregate(root,root/'E4')
                status['six_year_complete']=status['e4']['six_year_complete']
                if status['six_year_complete']:status['status']='WAITING_HUMAN_CONFIRMATION'
        status['scientific_acceptance']='PENDING_RESULT_REVIEW_NOT_IMPLIED_BY_PROCESS_EXIT'
    else:
        status['status']='REQUESTED_PHASE_FINISHED' if all(r['exit_code']==0 for r in latest.values()) else 'PARTIAL_DEVELOPMENT'
    atomic_json(root/'SCHEDULER_PROGRESS.json',status)
    return status


def from_config(path):
    import yaml
    source=json.loads(Path(path).read_text()) if Path(path).suffix=='.json' else yaml.safe_load(Path(path).read_text())
    if source.get('stop_before_test') is not True:raise ValueError('DEVELOPMENT_ONLY_CONFIGURATION_REQUIRED')
    defaults=dict(workers=1,threads=8,cpu_budget=32,memory_per_worker_gib=24,reserve_gib=12,
        chunk_size=32,device='cpu',episode_limit=None,phase='all',max_retries=1,tail_decision=None)
    mapping={'max_year_workers':'workers','cpu_threads_per_worker':'threads'}
    for key,value in source.items():
        if key=='stop_before_test':continue
        if key=='resume':
            if value is not True:raise ValueError('RESUME_MUST_PRESERVE_EXISTING_VALID_OUTPUTS')
            continue
        if mapping.get(key,key) not in set(defaults)|{'years','output_root'}:
            raise ValueError('UNKNOWN_SCHEDULER_CONFIG_KEY:'+key)
        defaults[mapping.get(key,key)]=value
    defaults['output_root']=Path(defaults['output_root'])
    if defaults['tail_decision'] is not None:defaults['tail_decision']=Path(defaults['tail_decision'])
    if not 1<=defaults['workers']<=3 or len(defaults['years'])!=len(set(defaults['years'])):
        raise ValueError('INVALID_ANNUAL_SCHEDULER_CONFIGURATION')
    return SimpleNamespace(**defaults)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path)
    parser.add_argument('--years',type=int,nargs='+',choices=range(2017,2023))
    parser.add_argument('--output-root',type=Path)
    parser.add_argument('--workers',type=int,choices=(1,2,3),default=1)
    parser.add_argument('--threads',type=int,default=8)
    parser.add_argument('--cpu-budget',type=int,default=32)
    parser.add_argument('--memory-per-worker-gib',type=float,default=24)
    parser.add_argument('--reserve-gib',type=float,default=12)
    parser.add_argument('--chunk-size',type=int,default=32)
    parser.add_argument('--device',choices=('cpu','cuda','auto'),default='cpu')
    parser.add_argument('--episode-limit',type=int)
    parser.add_argument('--phase',choices=('all','stage1','evaluate'),default='all')
    parser.add_argument('--tail-decision',type=Path)
    parser.add_argument('--max-retries',type=int,choices=(0,1,2),default=1)
    args=parser.parse_args()
    if args.config:args=from_config(args.config)
    if not args.years or args.output_root is None:parser.error('config or years/output-root required')
    if len(args.years)!=len(set(args.years)):parser.error('years must be unique')
    result=schedule(args)
    raise SystemExit(2 if result['status'] in ('SIX_YEAR_EXECUTION_BLOCKED','PARTIAL_DEVELOPMENT') else 0)
