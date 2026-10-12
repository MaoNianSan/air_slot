"""Unattended annual preparation/execution. No LLM and no training fallback."""
import argparse
from pathlib import Path

from .cloud_inputs import check_year
from .shared_store import atomic_json


def run(args):
    out = args.output_root
    gate = check_year(args.year, require_tail=args.tail_decision is None)
    atomic_json(out/'INPUT_GATE.json', gate)
    if gate['status'] != 'INPUTS_VALIDATED':
        atomic_json(out/'RUN_MANIFEST.json', gate)
        return 2
    if gate.get('tail_status') == 'APPROVED_TRAIN_PREPARATION_REQUIRED':
        from .build_annual_tail import build
        try:
            build(args.year, args.tail_decision)
        except Exception as error:
            atomic_json(out/'RUN_MANIFEST.json', dict(year=args.year,
                status='SCIENTIFIC_BLOCKED' if not isinstance(error, OSError) else 'IO_FAILED',
                reason=str(error), final_test_access_count=0))
            return 2
        gate = check_year(args.year)
        atomic_json(out/'INPUT_GATE.json', gate)
        if gate['status'] != 'INPUTS_VALIDATED':
            atomic_json(out/'RUN_MANIFEST.json', gate)
            return 2
    from .shared_run import run as execute
    result = execute(args.year, out, device=args.device, threads=args.threads,
        chunk_size=args.chunk_size, episode_limit=args.episode_limit, phase=args.phase)
    return 0 if result['status'] not in ('FAILED', 'PAUSED_AT_CHECKPOINT') else 3


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--year', type=int, choices=range(2017,2023), required=True)
    p.add_argument('--output-root', type=Path, required=True)
    p.add_argument('--tail-decision', type=Path)
    p.add_argument('--device', choices=('cpu','auto','cuda'), default='cpu')
    p.add_argument('--threads', type=int, default=8)
    p.add_argument('--chunk-size', type=int, default=32)
    p.add_argument('--episode-limit', type=int)
    p.add_argument('--phase', choices=('all','stage1','evaluate'), default='all')
    raise SystemExit(run(p.parse_args()))
