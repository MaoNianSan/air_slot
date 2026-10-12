"""Approved annual V5 structure; the sealed 2019 registry is never edited."""
from dataclasses import dataclass
import json
import math
from pathlib import Path

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from data2.scripts.build_year_references import sha256_json
from .shared_store import digest, file_hash, code_hash

ROOT = Path(__file__).resolve().parents[2]
EVENTS = ('P_itinerary', 'P_service')
PRINCIPAL = tuple(k for k in CONSEQUENCE_COMPONENTS if k not in EVENTS)
B_CONTINUITY_CONTRACT = 'JATM_F_CONTINUITY_B_V1'


@dataclass(frozen=True)
class AnnualV5CUAdapter:
    registry_id: str
    registry_hash: str
    scales: dict
    provenance: dict
    final_test_access_count: int = 0

    def scale(self, component):
        return self.scales[component]


def load_annual_cu(year, *, track='YEAR_LOCAL', continuity_contract='LEGACY_A_V1'):
    year = int(year)
    if year not in range(2017, 2023) or track not in ('YEAR_LOCAL', 'FIXED_COMMON'):
        raise ValueError('ANNUAL_CU_YEAR_OR_TRACK_INVALID')
    reference_year = year if track == 'YEAR_LOCAL' else 2017
    if continuity_contract == B_CONTINUITY_CONTRACT:
        version = 'PRE_MULTIYEAR_V1_E4_YEARLOCAL_B_V1' if track == 'YEAR_LOCAL' else 'PRE_MULTIYEAR_V1_D4_2017H1_B_V1'
    elif continuity_contract == 'LEGACY_A_V1':
        version = 'PRE_MULTIYEAR_V1_E4_YEARLOCAL_R1' if track == 'YEAR_LOCAL' else 'PRE_MULTIYEAR_V1_D4_2017H1_R2'
    else:
        raise ValueError('ANNUAL_CU_CONTINUITY_CONTRACT_UNKNOWN')
    root = ROOT/'artifacts/models/pre'/version/str(reference_year)/'M2_REFERENCES'
    manifest_path = root/'M2_REFERENCE_BUNDLE_MANIFEST.json'
    scales_path = root/'M2_SEVEN_COMPONENT_TRAIN_SCALES.json'
    manifest = json.loads(manifest_path.read_text())
    source = json.loads(scales_path.read_text())
    if (manifest['year'] != reference_year or source['experiment_year'] != reference_year
            or source['fit_period'] != f'{reference_year}-H1'
            or manifest['fit_window'] != {'start':f'{reference_year}-01-01', 'end':f'{reference_year}-06-30'}):
        raise ValueError('ANNUAL_CU_TRAIN_IDENTITY_MISMATCH')
    if source['bundle_hash'] != sha256_json({k:v for k,v in source.items() if k!='bundle_hash'}):
        raise ValueError('ANNUAL_CU_SCALE_HASH_MISMATCH')
    refs = {}
    for kind, expected in manifest['payload_hashes'].items():
        path = root/f'M2_{kind.upper()}_REFERENCE_{reference_year}-H1.json'
        payload = json.loads(path.read_text())
        if sha256_json(payload) != expected:
            raise ValueError('ANNUAL_CU_REFERENCE_HASH_MISMATCH:'+kind)
        refs[kind] = file_hash(path)
    original_turn_path = ROOT/'artifacts/models/pre/PRE_MULTIYEAR_V1'/str(reference_year)/'DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN.json'
    original_turn = json.loads(original_turn_path.read_text())
    bundle_turn = json.loads((root/f'M2_TURNAROUND_REFERENCE_{reference_year}-H1.json').read_text())
    def turn_values(payload):
        return (payload['global_value_minutes'],
                sorted((row['airport_id'], row['value_minutes'], row['fallback_level']) for row in payload['cells']))
    if turn_values(original_turn) != turn_values(bundle_turn):
        raise ValueError('ANNUAL_CU_TURNAROUND_REFERENCE_NUMERICAL_MISMATCH')
    scales = {}
    for component in PRINCIPAL:
        entry = source['scales'][component]
        value = float(entry['median'])
        if not math.isfinite(value) or value <= 0 or entry['positive_n'] <= 0:
            raise ValueError('ANNUAL_CU_POSITIVE_SUPPORT_MISSING:'+component)
        if value != manifest['scale_median_preview'][component]:
            raise ValueError('ANNUAL_CU_MANIFEST_SCALE_MISMATCH:'+component)
        scales[component] = value
    scales.update({component:1.0 for component in EVENTS})
    provenance = dict(schema_version='JATM_ANNUAL_V5_CU_ADAPTER_V1', track=track,
        reference_year=reference_year, fit_period=source['fit_period'], scales=scales,
        source_scale_sha256=file_hash(scales_path), source_manifest_sha256=file_hash(manifest_path),
        reference_sha256=refs, event_scale_rule='ONE_NATIVE_EVENT_UNIT',
        principal_rule='MEDIAN_H1_TRAIN_POSITIVE',
        continuity_definition=source['scales']['F_continuity']['definition'],
        continuity_contract=continuity_contract,
        continuity_reference_evidence='build_year_references.compute_train_scales receives the same turnaround payload written to this bundle',
        generator_sha256=code_hash(ROOT/'data2/scripts/build_year_references.py'),
        original_turnaround_sha256=file_hash(original_turn_path),
        turnaround_numeric_lookup_match=True,
        turnaround_counts_identical=({r['airport_id']:r['sample_count'] for r in original_turn['cells']}
                                      =={r['airport_id']:r['sample_count'] for r in bundle_turn['cells']}),
        final_test_access_count=0)
    return AnnualV5CUAdapter(f'JATM_V5_{track}_{reference_year}_H1_V1', digest(provenance), scales, provenance)
