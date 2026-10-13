"""Explicitly authorized, isolated N=4096 annual M1 training stage.

This entry is intentionally not called by cloud_schedule or cloud_worker.
"""
import argparse
import json
from pathlib import Path

from .cloud_inputs import ROOT, model_bindings
from .shared_store import atomic_json, file_hash

SCHEMA = 'JATM_ANNUAL_M1_TRAINING_AUTHORIZATION_V1'
ROLES = ['M1_HISTORY_PRIMARY', 'M1_CURRENT_COMPARATOR']


def validate_authorization(payload, year):
    expected = {
        'schema': SCHEMA,
        'status': 'USER_APPROVED',
        'n': 4096,
        'roles': ROLES,
        'train_months': [1, 2, 3, 4, 5, 6],
        'calibration_months': [7],
        'development_used_for_fit': False,
        'final_test_access_count': 0,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError('ANNUAL_M1_TRAINING_AUTHORIZATION_INVALID:' + key)
    if year not in payload.get('years', []):
        raise ValueError('ANNUAL_M1_TRAINING_YEAR_NOT_AUTHORIZED')


def train_year(year, approval_path, *, root=ROOT):
    year = int(year)
    if year not in range(2017, 2023):
        raise ValueError('ANNUAL_M1_TRAINING_YEAR_INVALID')
    approval_path = Path(approval_path)
    approval = json.loads(approval_path.read_text(encoding='utf-8'))
    validate_authorization(approval, year)
    model_dir = Path(root) / 'artifacts/models/m1' / f'YEAR_{year}'
    if model_dir.exists() and any(model_dir.iterdir()):
        raise FileExistsError('ANNUAL_M1_OUTPUT_EXISTS_REFUSE_OVERWRITE')
    from .annual_models import build_annual_models
    result = build_annual_models(year=year, n=4096, output_root=model_dir)
    bindings = model_bindings(year, root=root)
    receipt = dict(schema_version='JATM_ANNUAL_M1_TRAINING_RECEIPT_V1',
        status='TRAINED_AND_HASH_VALIDATED', year=year, n=4096, roles=ROLES,
        approval_sha256=file_hash(approval_path), models=bindings,
        training_summary=result, model_retrained=True,
        final_test_access_count=0)
    atomic_json(model_dir / 'ANNUAL_M1_TRAINING_RECEIPT.json', receipt)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, choices=range(2017, 2023), required=True)
    parser.add_argument('--approval', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(train_year(args.year, args.approval), indent=2, sort_keys=True))
