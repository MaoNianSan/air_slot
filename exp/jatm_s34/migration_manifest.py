"""Create/verify an explicit private-transfer allowlist; never copies data."""
import argparse
import json
from pathlib import Path
from .shared_store import atomic_json,file_hash


def manifest(root,allowlist,output,*,verify=False):
    root=Path(root).resolve()
    rows=[]
    for entry in json.loads(Path(allowlist).read_text()):
        relative=entry['path'].replace('\\','/')
        path=(root/relative).resolve()
        if not path.is_relative_to(root) or any(x in relative.lower() for x in ('final_test','final-test','sealed')):
            raise ValueError('PROTECTED_OR_OUTSIDE_TRANSFER_PATH:'+relative)
        if entry.get('scope') not in ('code','train','calibration','development','reference','shared-cache'):
            raise ValueError('EXPLICIT_LEGAL_SCOPE_REQUIRED:'+relative)
        if not path.is_file():raise ValueError('TRANSFER_REQUIRES_EXPLICIT_FILES:'+relative)
        actual=file_hash(path)
        if verify and actual!=entry['sha256']:raise ValueError('TRANSFER_HASH_MISMATCH:'+relative)
        rows.append(dict(path=relative,scope=entry['scope'],sha256=actual,bytes=path.stat().st_size))
    atomic_json(output,rows)
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--allowlist',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    manifest(args.root,args.allowlist,args.output,verify=args.verify)
