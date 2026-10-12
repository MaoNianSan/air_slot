"""Export the actually used environment rather than assuming requirements match."""
from importlib.metadata import version
import argparse
import json
import platform
from pathlib import Path
import subprocess
import sys

from .shared_store import atomic_json


def code_revision(root=None):
    root=Path(root or Path(__file__).resolve().parents[2])
    try:
        top=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=root,text=True,stderr=subprocess.DEVNULL).strip())
        if top.resolve()==root.resolve():
            return subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    except (FileNotFoundError,subprocess.CalledProcessError):pass
    snapshot=root/'CODE_SNAPSHOT.json'
    if snapshot.is_file():return json.loads(snapshot.read_text())['git_head']
    raise RuntimeError('CODE_REVISION_OR_PACKAGED_SNAPSHOT_REQUIRED')


def select_device(requested, *, cuda_available, pilot=False):
    if requested not in ('cpu','auto','cuda'):raise ValueError('UNKNOWN_DEVICE')
    if requested=='cuda' and cuda_available:
        if not pilot:raise RuntimeError('CUDA_FULL_RUN_REQUIRES_REAL_DEVICE_EQUIVALENCE_ACCEPTANCE')
        return 'cuda','EXPLICIT_GPU_BENCHMARK_ONLY'
    if requested=='cuda':return 'cpu','CUDA_UNAVAILABLE_CPU_FALLBACK'
    return 'cpu','CPU_DEFAULT_PENDING_GPU_BENCHMARK' if requested=='auto' else 'EXPLICIT_CPU'


def record(output_root):
    import torch
    import psutil
    root=Path(output_root);root.mkdir(parents=True,exist_ok=True)
    names=('pydantic','PyYAML','pytest','numpy','pandas','pyarrow','scipy','scikit-learn',
           'torch','tqdm','rich','psutil','matplotlib','pyomo','highspy')
    packages={name:version(name) for name in names}
    (root/'ENVIRONMENT_LOCK.txt').write_text(''.join(f'{name}=={v}\n' for name,v in packages.items()),encoding='utf-8')
    runtime=dict(python=sys.version,platform=platform.platform(),packages=packages,
        logical_cpus=psutil.cpu_count(),physical_cpus=psutil.cpu_count(logical=False),
        memory_bytes=psutil.virtual_memory().total,cuda_available=torch.cuda.is_available(),
        torch_cuda=torch.version.cuda,torch_version=torch.__version__,
        gpu=[] if not torch.cuda.is_available() else [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())])
    try:runtime['nvidia_smi']=subprocess.check_output(['nvidia-smi','--query-gpu=name,driver_version,memory.total','--format=csv'],text=True)
    except (FileNotFoundError,subprocess.CalledProcessError):runtime['nvidia_smi']=None
    atomic_json(root/'RUNTIME_PROVENANCE.json',runtime)
    return runtime


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output-root',type=Path,required=True)
    record(p.parse_args().output_root)
