"""Annual tail reference binding; never substitute another year's tail."""
import json
from pathlib import Path
from model.M1.tail import load_tail_continuations
from .shared_store import file_hash,digest

ROOT=Path(__file__).resolve().parents[2]


def annual_tail_path(year):
    return ROOT/'artifacts/models/m1'/f'YEAR_{int(year)}'/'TAIL_REFERENCE_V1/MANIFEST.json'


def load_annual_tail(year):
    path=annual_tail_path(year)
    if not path.is_file():
        raise FileNotFoundError(f'ANNUAL_TRAIN_TAIL_REFERENCE_REQUIRED:{year}:{path}')
    payload=json.loads(path.read_text())
    expected=digest({k:v for k,v in payload.items() if k!='artifact_hash'})
    if payload.get('artifact_hash')!=expected:
        raise ValueError('ANNUAL_TAIL_MANIFEST_HASH_MISMATCH')
    if (payload.get('year')!=year or payload.get('fit_partition')!='train'
        or payload.get('fit_start')!=f'{year}-01-01' or payload.get('fit_end')!=f'{year}-06-30'
        or payload.get('final_test_access_count')!=0):
        raise ValueError('ANNUAL_TAIL_FIT_IDENTITY_MISMATCH')
    for name,sha in payload['source_hashes'].items():
        if file_hash(ROOT/name)!=sha:raise ValueError('ANNUAL_TAIL_SOURCE_HASH_MISMATCH:'+name)
    tails=load_tail_continuations(path)
    if set(tails)!={'D_OB','D_TX'}:raise ValueError('ANNUAL_TAIL_TARGETS_MISSING')
    for tail in tails.values():
        if tail.fit_start!=payload['fit_start'] or tail.fit_end!=payload['fit_end']:
            raise ValueError('ANNUAL_TAIL_TARGET_PERIOD_MISMATCH')
        if tail.tail_n < 30:
            raise ValueError('SCIENTIFIC_BLOCKED_TAIL_SUPPORT:'+tail.target)
    if payload.get('population') != 'ANNUAL_N4096_TRAIN_ACTIVE_POSITIVE_LABELS':
        raise ValueError('ANNUAL_TAIL_POPULATION_MISMATCH')
    return tails


def tail_manifest_summary(year):
    path=annual_tail_path(year)
    payload=json.loads(path.read_text())
    return dict(year=year,tail_id=payload.get('artifact_hash'),fit_period=[payload.get('fit_start'),payload.get('fit_end')],
        targets={name:dict(positive_n=value.get('positive_n'),tail_n=value.get('tail_n'),q90=value.get('train_positive_q90'),
                           artifact_hash=value.get('artifact_hash')) for name,value in payload.get('targets',{}).items()},
        source_hashes=payload.get('source_hashes',{}),final_test_access_count=payload.get('final_test_access_count',0))
