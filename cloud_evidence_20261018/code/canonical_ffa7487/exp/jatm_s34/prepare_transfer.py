"""Build a local upload manifest and Development-only weather overlay.

No network operation, model fit, or experiment execution is performed.
The original data tree is read-only. Weather follows PRE's ordered prefix
rule and stops at the first October boundary; Q4 is never exported.
"""
import argparse
import csv
from datetime import datetime,timezone
import json
from pathlib import Path
import time

from .shared_store import atomic_json,file_hash

ROOT=Path(__file__).resolve().parents[2]


def weather_prefix(source,destination,year):
    destination.parent.mkdir(parents=True,exist_ok=True)
    receipt=destination.with_suffix('.scope.json')
    stat=source.stat()
    identity=dict(source_bytes=stat.st_size,source_mtime_ns=stat.st_mtime_ns,year=year)
    if destination.is_file() and receipt.is_file():
        prior=json.loads(receipt.read_text())
        if prior['identity']==identity and prior['sha256']==file_hash(destination):return prior
        raise ValueError('WEATHER_OVERLAY_IDENTITY_CONFLICT_USE_NEW_OUTPUT')
    temporary=destination.with_suffix('.tmp')
    count=0;first=last=None
    with source.open(encoding='utf-8-sig',newline='') as inp, temporary.open('w',encoding='utf-8',newline='') as out:
        reader=csv.DictReader(inp);writer=csv.DictWriter(out,fieldnames=reader.fieldnames,lineterminator='\n')
        writer.writeheader()
        for row in reader:
            stamp=str(row.get('DATE',''))
            if stamp>=f'{year}-10-01':break
            if not stamp.startswith(f'{year}-'):continue
            if last is not None and stamp<last:
                raise ValueError('WEATHER_INPUT_NOT_ORDERED:'+str(source))
            writer.writerow(row);count+=1;first=first or stamp;last=stamp
    temporary.replace(destination)
    record=dict(identity=identity,sha256=file_hash(destination),rows=count,first=first,last=last,
        scope='TRAIN_CALIBRATION_DEVELOPMENT_ONLY',rule='SAME_ORDERED_PREFIX_AS_PRE_WEATHER_INDEX',
        original_not_modified=True,final_test_access_count=0)
    atomic_json(receipt,record)
    return record


def prepare(output,years):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    overlay=output/'overlay';rows=[];missing=[];started=time.monotonic()
    def add(path,scope,*,target=None,source_root=ROOT,metadata=None):
        path=Path(path)
        if not path.is_file():missing.append(str(path.relative_to(source_root)));return
        relative=(target or path.relative_to(source_root).as_posix())
        if '..' in Path(relative).parts or any(x in relative.lower() for x in ('final_test','final-test','month=10','month=11','month=12')):
            raise ValueError('PROTECTED_TRANSFER_TARGET:'+relative)
        entry=dict(path=relative,source_root='overlay' if source_root==overlay else 'repository',
                   scope=scope,sha256=file_hash(path),bytes=path.stat().st_size)
        if metadata is not None:entry['scope_evidence']=metadata
        rows.append(entry)
    for year in years:
        model=ROOT/'artifacts/models/m1'/f'YEAR_{year}'
        for role in ('M1_HISTORY_PRIMARY','M1_CURRENT_COMPARATOR'):
            for suffix in ('.pt','_MANIFEST.json'):add(model/(role+suffix),'train-calibrated-model')
        tail=model/'TAIL_REFERENCE_V1/MANIFEST.json'
        add(tail,'train-reference')
        cohort=ROOT/'data2/reports/cohort_size_stability'/str(year)/'HASH_SELECTED_COHORT_RECORDS_N4096.jsonl'
        add(cohort,'legal-cohort-manifest')
        pre=ROOT/'artifacts/models/pre/PRE_MULTIYEAR_V1'/str(year)
        for name in ('DATA2_TAXI_REFERENCE_TRAIN_FROZEN.json','DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN.json',
                     'PRE_MULTIYEAR_DEVELOPMENT_MANIFEST.json'):
            add(pre/name,'train-reference' if 'REFERENCE' in name else 'development')
        bundle=ROOT/'artifacts/models/pre/PRE_MULTIYEAR_V1_E4_YEARLOCAL_R1'/str(year)/'M2_REFERENCES'
        for path in sorted(bundle.glob('*.json')):add(path,'train-reference')
        add(ROOT/'data2/reports/paper_formal'/str(year)/str(year)/'M2_TRAIN_HEADROOM_SUMMARY.json','train-reference')
        for month in range(1,10):
            paths=list((ROOT/'data2/raw/bts/ontime'/str(year)/f'month={month:02d}').glob('*.csv'))
            if len(paths)!=1:raise ValueError(f'AMBIGUOUS_OR_MISSING_BTS_MONTH:{year}:{month}')
            add(paths[0],'train' if month<=6 else 'calibration' if month==7 else 'development')
        for path in sorted((ROOT/'data2/raw/weather/noaa'/str(year)).glob('*.csv')):
            relative=path.relative_to(ROOT)
            admitted=overlay/relative
            evidence=weather_prefix(path,admitted,year)
            add(admitted,'train-calibration-development',source_root=overlay,metadata=evidence)
        atomic_json(output/'TRANSFER_PROGRESS.json',dict(completed_year=year,files=len(rows),
            bytes=sum(r['bytes'] for r in rows),elapsed_seconds=time.monotonic()-started))
        print(json.dumps(dict(year=year,files=len(rows),elapsed_seconds=time.monotonic()-started)),flush=True)
    common=ROOT/'artifacts/models/pre/PRE_MULTIYEAR_V1_D4_2017H1_R2/2017/M2_REFERENCES'
    for path in sorted(common.glob('*.json')):add(path,'train-reference')
    for name in ('us_airport_timezones.csv','weather_station_map.csv'):
        add(ROOT/'data2/refs'/name,'reference')
    manifest=dict(schema='JATM_PRIVATE_DATA_TRANSFER_V1',created_at=datetime.now(timezone.utc).isoformat(),
        status='PREPARED_WITH_EXPLICIT_MISSING_INPUTS' if missing else 'PREPARED',years=years,files=rows,
        missing=missing,bytes=sum(row['bytes'] for row in rows),model_training_performed=False,
        final_test_access_count=0,network_transfer_performed=False)
    atomic_json(output/'DATA_TRANSFER_MANIFEST.json',manifest)
    for source_root in ('repository','overlay'):
        (output/(source_root+'.files.txt')).write_text(''.join(r['path']+'\n' for r in rows if r['source_root']==source_root),encoding='utf-8')
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-root',type=Path,required=True)
    p.add_argument('--years',type=int,nargs='+',choices=range(2017,2023),default=list(range(2017,2023)))
    a=p.parse_args();prepare(a.output_root,a.years)
