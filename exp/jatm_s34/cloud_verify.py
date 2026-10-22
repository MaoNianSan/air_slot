"""Verify uploaded files against an explicit manifest, without executing models."""
import argparse
import json
from pathlib import Path
from .shared_store import atomic_json,file_hash


def verify(root,manifest_path):
    root=Path(root).resolve();manifest=json.loads(Path(manifest_path).read_text())
    entries=manifest['files'] if isinstance(manifest,dict) else manifest
    problems=[];total=0
    for entry in entries:
        relative=entry['path'];path=(root/relative).resolve()
        if not path.is_relative_to(root) or any(s in relative.lower() for s in
                ('final_test','final-test','month=10','month=11','month=12')):
            problems.append(dict(path=relative,reason='PROTECTED_OR_OUTSIDE_PATH'));continue
        if not path.is_file():problems.append(dict(path=relative,reason='MISSING'));continue
        if file_hash(path)!=entry['sha256']:problems.append(dict(path=relative,reason='HASH_MISMATCH'));continue
        total+=1
    return dict(status='PASS_FILE_HASHES' if not problems else 'TRANSFER_INCOMPLETE_OR_CHANGED',
        verified_files=total,problems=problems,
        scientific_acceptance='NOT_IMPLIED_BY_TRANSFER_HASHES',final_test_access_count=0)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=verify(a.root,a.manifest);atomic_json(a.output,result)
    raise SystemExit(0 if result['status']=='PASS_FILE_HASHES' else 2)
