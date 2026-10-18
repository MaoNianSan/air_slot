"""Noninteractive status for an isolated annual Development queue."""
import argparse,json
from pathlib import Path


def status(root):
    root=Path(root);output={}
    for year in range(2017,2023):
        output[year]={}
        for name,relative in (('run','RUN_MANIFEST.json'),('stage1','shared/PROGRESS.json'),
                              ('e1','E1/E1_PAIRED_PROGRESS.json'),('stage2','E2_E3/PROGRESS.json')):
            path=root/str(year)/relative
            if path.exists():output[year][name]=json.loads(path.read_text())
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output-root',required=True,type=Path)
    print(json.dumps(status(p.parse_args().output_root),indent=2))
