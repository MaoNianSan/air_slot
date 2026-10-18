"""Compare measured worker runs; missing or incomplete runs never win."""
import argparse
import json
from pathlib import Path
from .shared_store import atomic_json,file_hash


def report(roots,output):
    rows=[]
    for root in map(Path,roots):
        progress=root/'SCHEDULER_PROGRESS.json'
        data=json.loads(progress.read_text())
        nodes=0;valid=not data['active'] and not data['pending'] and bool(data['finished'])
        worker_rows=[]
        latest={worker['year']:worker for worker in data['finished']}
        for worker in latest.values():
            manifest_path=root/str(worker['year'])/'shared/CACHE_MANIFEST.json'
            complete=worker['exit_code']==0 and manifest_path.is_file()
            count=0
            if complete:
                from .shared_science import load_scores
                count=sum(1 for row in load_scores(manifest_path.parent) if row.get('is_canonical',True))
                nodes+=count
            valid=valid and complete
            worker_rows.append(dict(year=worker['year'],canonical_nodes=count,
                complete=complete,seconds=worker['wall_seconds'],peak_rss_bytes=worker['peak_rss_bytes']))
        seconds=data['elapsed_seconds']
        rows.append(dict(root=str(root),status='MEASURED' if valid else 'INCOMPLETE_EXCLUDED',
            nodes=nodes,seconds=seconds,canonical_nodes_per_hour=nodes*3600/seconds if valid and seconds>0 else None,
            workers=worker_rows,source_hash=file_hash(progress)))
    eligible=[r for r in rows if r['status']=='MEASURED']
    result=dict(rows=rows,best_measured_root=None if not eligible else
        max(eligible,key=lambda r:r['canonical_nodes_per_hour'])['root'],
        selection_note='Compare identical phase, episode counts and scientific identity; GPU requires separate parity acceptance.',
        final_test_access_count=0)
    atomic_json(output,result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--roots',nargs='+',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();report(a.roots,a.output)
