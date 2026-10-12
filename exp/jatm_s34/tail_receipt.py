"""Verify a completed annual tail from committed labels without raw-data replay."""
import argparse
import json
from pathlib import Path
import numpy as np

from model.M1.tail import EmpiricalTailContinuation
from .annual_tail import annual_tail_path, load_annual_tail
from .cloud_inputs import model_bindings
from .shared_store import SharedStore, atomic_json, file_hash, code_hash


def verify(year, output):
    path=annual_tail_path(year)
    tails=load_annual_tail(year)
    source=json.loads(path.read_text())
    identity=source['build_identity']
    store=SharedStore(path.parent/'train_chunks',identity)
    total=(4096+identity['chunk_size']-1)//identity['chunk_size']
    positives={name:[] for name in tails}
    chunks=[]
    for index in range(total):
        key=f'chunk_{index:04d}'
        chunk=store.read(key)
        if chunk is None:raise ValueError('ANNUAL_TAIL_LABEL_CHUNK_MISSING:'+key)
        chunks.append(dict(path=key+'.json',sha256=file_hash(store.root/(key+'.json')),
                           label_identity_hash=chunk['label_identity_hash']))
        for target in positives:positives[target].extend(chunk['positive'][target])
    for target,tail in tails.items():
        reconstructed=EmpiricalTailContinuation.from_exceedances(target=target,
            positive_values=np.asarray(positives[target]),fit_start=source['fit_start'],
            fit_end=source['fit_end'],source_hashes=source['source_hashes'])
        if reconstructed.to_payload()!=tail.to_payload():
            raise ValueError('ANNUAL_TAIL_CACHED_LABEL_RECONSTRUCTION_MISMATCH:'+target)
    root=Path(__file__).resolve().parents[2]
    receipt=dict(status='PASS_COMMITTED_LABEL_RECONSTRUCTION',year=year,completed_chunks=total,
        sampling_source=source['population'],fit_period=[source['fit_start'],source['fit_end']],
        manifest_sha256=file_hash(path),targets=source['targets'],source_hashes=source['source_hashes'],
        checkpoints=model_bindings(year),chunks=chunks,
        active_n=None,active_n_status='NOT_RETAINED_BY_ORIGINAL_BUILDER_POSITIVE_AND_TAIL_COUNTS_VERIFIED',
        validation_algorithm_hashes={name:code_hash(root/name) for name in
            ('model/M1/tail.py','exp/jatm_s34/tail_receipt.py')},
        original_build_identity=identity,model_retrained=False,raw_data_replayed=False,final_test_access_count=0)
    atomic_json(output,receipt)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--year',type=int,choices=range(2017,2023),required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();verify(a.year,a.output)
