"""Small, deterministic annual input gate; no model training or Test reads."""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path

from .shared_store import atomic_json, file_hash

ROOT = Path(__file__).resolve().parents[2]
ROLES = {'M1_HISTORY_PRIMARY': 'FULL_ADAPTIVE_CAUSAL_PREFIX',
         'M1_CURRENT_COMPARATOR': 'NO_HISTORY_CURRENT_OBSERVATION'}


def model_bindings(year, *, root=ROOT):
    """Bind by relative path and bytes, never a serialized Windows path."""
    bindings = {}
    for role, mode in ROLES.items():
        directory = Path(root)/'artifacts/models/m1'/f'YEAR_{year}'
        path = directory/(role+'.pt')
        metadata = directory/(role+'_MANIFEST.json')
        payload = json.loads(metadata.read_text(encoding='utf-8'))
        if (payload.get('year') != year or payload.get('scientific_model_n') != 4096
                or payload.get('train_episode_count') != 4096
                or payload.get('calibration_episode_count') != 2048
                or payload.get('history_mode') != mode or payload.get('role') != role
                or payload.get('final_test_access_count') != 0
                or payload.get('m5b_n128_pilot_reused') is not False):
            raise ValueError('ANNUAL_MODEL_CONTRACT_MISMATCH:'+role)
        if file_hash(path) != payload['checkpoint_hash']:
            raise ValueError('ANNUAL_MODEL_HASH_MISMATCH:'+role)
        bindings[role] = dict(payload, checkpoint=path.relative_to(root).as_posix(),
                              manifest_sha256=file_hash(metadata))
    return bindings


def check_year(year, *, require_tail=True, root=ROOT,
               continuity_contract='LEGACY_A_V1'):
    result = dict(year=year, status='INPUTS_VALIDATED', final_test_access_count=0,
                  scope='TRAIN_CALIBRATION_DEVELOPMENT_ONLY')
    try:
        if year not in range(2017, 2023):
            raise ValueError('UNSUPPORTED_YEAR')
        result['models'] = model_bindings(year, root=root)
        cohort = Path(root)/'data2/reports/cohort_size_stability'/str(year)/'HASH_SELECTED_COHORT_RECORDS_N4096.jsonl'
        windows = {'train':(1, 6), 'calibration':(7, 7), 'development':(8, 9)}
        counts, identities = Counter(), set()
        with cohort.open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                split = row['split']
                if split not in windows:
                    raise ValueError('PROTECTED_OR_UNKNOWN_COHORT_PARTITION')
                episode = row['episode']
                if episode['episode_id'] in identities:
                    raise ValueError('DUPLICATE_OR_CROSS_SPLIT_EPISODE')
                identities.add(episode['episode_id'])
                for field in ('episode_start_time', 'episode_end_time'):
                    stamp = datetime.fromisoformat(episode[field].replace('Z', '+00:00'))
                    low, high = windows[split]
                    if stamp.year != year or not low <= stamp.month <= high:
                        raise ValueError('ANNUAL_COHORT_SPLIT_MISMATCH')
                counts[split] += 1
        if counts['train'] < 4096 or not counts['calibration'] or not counts['development']:
            raise FileNotFoundError('ANNUAL_COHORT_SUPPORT_MISSING')
        result.update(cohort_pool_counts=dict(counts),
                      effective_model_counts=dict(train=4096,calibration=2048),
                      development_episode_count=counts['development'],cohort_sha256=file_hash(cohort))
        from .annual_cu import load_annual_cu
        from .annual_tail import annual_tail_path, load_annual_tail, tail_manifest_summary
        from .scientific_tracks import nominal_headroom
        result['cu'] = {track:load_annual_cu(year, track=track,
                                             continuity_contract=continuity_contract).provenance
                        for track in ('YEAR_LOCAL', 'FIXED_COMMON')}
        result['continuity_contract'] = continuity_contract
        result['nominal_policy'] = nominal_headroom(year).model_dump(mode='json')
        if annual_tail_path(year).exists():
            load_annual_tail(year)
            result['tail'] = tail_manifest_summary(year)
        elif require_tail:
            raise FileNotFoundError('ANNUAL_TRAIN_TAIL_REFERENCE_REQUIRED')
        else:
            result['tail_status'] = 'APPROVED_TRAIN_PREPARATION_REQUIRED'
    except FileNotFoundError as error:
        result.update(status='DATA_INSUFFICIENT', reason=str(error))
    except (ValueError, KeyError, RuntimeError) as error:
        result.update(status='SCIENTIFIC_BLOCKED', reason=str(error))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--years', type=int, nargs='+', default=list(range(2017,2023)))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    atomic_json(args.output, [check_year(year) for year in args.years])
