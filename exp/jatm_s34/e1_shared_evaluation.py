"""Evaluate persisted E1 scores without invoking PRE/M1/M2.

One episode draw feeds every stage/view/q. M3 owns ranking and K. Duplicate
episode draws receive independent instance IDs before ranking or evaluation.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import argparse
import json
from pathlib import Path
import time

import numpy as np

from model.M3.stage1 import rank_signals, attention_capacity_k
from model.common.decision_contracts import TypedStatus
from model.common.enums import OperationalStage
from .annual_shared import load_shared_nodes
from .e1_information_gain import (Q_GRID, VIEWS, STAGES, _CompactNode,
    _CompactSupport, _summarize_stage)
from .shared_store import atomic_json, file_hash

METRICS = ('overlap', 'replacement', 'retained_consequence',
           'absolute_consequence_gap', 'attention_loss')


def load_candidates(shared_root):
    nodes, factors, excluded = [], {}, defaultdict(int)
    for row in load_shared_nodes(shared_root):
        s = row['support']
        if (not s['included'] or row['delay_score'] is None
                or row['consequence_score'] is None or row['exposure'] is None):
            excluded['BASE_COMMON_SUPPORT_OR_SCORE'] += 1
            continue
        node = _CompactNode(row['episode_id'], row['chain_id'], row['node_id'],
            OperationalStage(row['stage']), datetime.fromisoformat(row['decision_time']),
            {'HISTORY_JOINT': row['delay_score']}, {'HISTORY_JOINT': row['consequence_score']},
            {'HISTORY_JOINT': row['domain_scores']},
            _CompactSupport(s['included'], s['supported_mass'], s['threshold'], TypedStatus(s['status'])))
        nodes.append(node)
        factors[node.node_id] = (row['exposure']['expected_passengers_per_flight'],
                                 row['exposure']['expected_downstream_exposure'])
    return nodes, factors, dict(excluded)


@dataclass(frozen=True)
class RankRow:
    episode_id: str
    node_id: str
    score: float
    consequence: float


def replicate_metrics(nodes, factors, draw, replicate):
    groups = defaultdict(list)
    for node in nodes:
        groups[node.episode_id].append(node)
    stage_views = {stage: {v: [] for v in VIEWS} for stage in STAGES}
    for occurrence, episode in enumerate(draw):
        suffix = f'::BOOT{replicate}:{occurrence}'
        for node in groups[episode]:
            d = node.delay_scores['HISTORY_JOINT']
            c = node.consequence_scores['HISTORY_JOINT']
            pax, downstream = factors[node.node_id]
            for view, score in zip(VIEWS, (d, d*pax, d*downstream, c)):
                stage_views[node.stage][view].append(RankRow(
                    episode+suffix, node.node_id+suffix, score, c))
    results = {}
    for stage, views in stage_views.items():
        ranked = {view: rank_signals(rows) for view, rows in views.items()}
        for q in Q_GRID:
            if not ranked['DELAY']:
                for view in VIEWS:results[stage.value,q,view]={metric:None for metric in METRICS}
                continue
            k = attention_capacity_k(q, len(ranked['DELAY']))
            ref = ranked['CONSEQUENCE'][:k]
            ref_ids = {row.node_id for row in ref}
            ref_sum = sum(row.consequence for row in ref)
            for view in VIEWS:
                chosen = ranked[view][:k]
                chosen_ids = {row.node_id for row in chosen}
                kept = sum(row.consequence for row in chosen)
                gap = None if ref_sum == 0 else ref_sum-kept
                results[stage.value, q, view] = dict(
                    overlap=len(chosen_ids & ref_ids), replacement=len(chosen_ids-ref_ids),
                    retained_consequence=None if ref_sum == 0 else kept/ref_sum,
                    absolute_consequence_gap=gap,
                    attention_loss=None if ref_sum == 0 else gap/ref_sum)
    return results


def run(shared_root, output_root, *, original_summary=None, replicates=2000, seed=20261011):
    started = time.perf_counter()
    nodes, factors, excluded = load_candidates(shared_root)
    stage_support={stage.value:dict(canonical=0,common_supported=0,abstain=0,reasons={}) for stage in STAGES}
    accepted_ids={node.node_id for node in nodes}
    for item in load_shared_nodes(shared_root):
        counts=stage_support[item['stage']];counts['canonical']+=1
        if item['node_id'] in accepted_ids:counts['common_supported']+=1
        else:
            counts['abstain']+=1
            reason=(item['support'].get('status','UNKNOWN') if not item['support']['included'] else
                    'EXPOSURE_MISSING' if item['exposure'] is None else 'SCORE_MISSING')
            counts['reasons'][reason]=counts['reasons'].get(reason,0)+1
    source_manifest=json.loads((Path(shared_root)/'SHARED_ANNUAL_MANIFEST.json').read_text())
    contract=source_manifest.get('cu_contract')
    cu_label='LEGACY_2019_CU_REFERENCE'
    if contract is not None:
        if contract['track']=='YEAR_LOCAL' and contract['reference_year']==source_manifest['year']:
            cu_label='YEAR_LOCAL_V5'
        elif contract['track']=='FIXED_COMMON' and contract['reference_year']==2017:
            cu_label='FIXED_COMMON_2017_H1_V5'
        else:raise ValueError('E1_ANNUAL_CU_IDENTITY_MISMATCH')
    rows = []
    original = None if original_summary is None else json.loads(Path(original_summary).read_text())
    original_by_key = {} if original is None else {
        (r['stage'], r['q'], r['view']): r for r in original['summary_rows']}
    max_error = 0.0
    for stage in STAGES:
        cohort = [node for node in nodes if node.stage is stage]
        for q in Q_GRID:
            for view in VIEWS:
                row = _summarize_stage(cohort, view=view, q=q, factor_by_node=factors)
                row['stage'] = stage.value
                row['support_denominator'] = len(cohort)
                key = (stage.value, q, view)
                if original is not None:
                    old = original_by_key[key]
                    for name in ('selected_view', 'selected_reference', 'n', 'k', 'abstain'):
                        if row.get(name) != old.get(name):
                            raise ValueError(f'E1_SHARED_IDENTITY_MISMATCH:{key}:{name}')
                    for name in METRICS:
                        a, b = row.get(name), old.get(name)
                        if (a is None) != (b is None):
                            raise ValueError(f'E1_SHARED_MISSING_MISMATCH:{key}:{name}')
                        if a is not None:
                            error = abs(a-b)
                            max_error = max(max_error, error)
                            if error > 1e-9 * max(1.0, abs(b)):
                                raise ValueError(f'E1_SHARED_VALUE_MISMATCH:{key}:{name}')
                rows.append(row)
    out = Path(output_root)
    atomic_json(out / 'E1_POINT_EQUIVALENCE.json', dict(status='PASS' if original is not None else 'POINT_ESTIMATES_COMPUTED_NO_LEGACY_COMPARISON', rows=len(rows),
        max_absolute_error=max_error, source_summary_sha256=None if original is None else file_hash(original_summary),
        shared_manifest_sha256=file_hash(Path(shared_root)/'SHARED_ANNUAL_MANIFEST.json'),
        model_inference_calls=0, final_test_access_count=0))
    episodes = sorted({node.episode_id for node in nodes})
    rng = np.random.default_rng(seed)
    values = {(row['stage'], row['q'], row['view']): {m: [] for m in METRICS} for row in rows}
    absolute_values = {key:{m:[] for m in METRICS} for key in values}
    for replicate in range(replicates):
        draw = rng.choice(episodes, size=len(episodes), replace=True)
        estimates = replicate_metrics(nodes, factors, draw, replicate)
        for key, metrics in estimates.items():
            baseline = estimates[key[0], key[1], 'DELAY']
            for metric in METRICS:
                if metrics[metric] is not None and baseline[metric] is not None:
                    values[key][metric].append(metrics[metric]-baseline[metric])
                if metrics[metric] is not None:
                    absolute_values[key][metric].append(metrics[metric])
        if (replicate+1) % 100 == 0:
            if (Path(shared_root)/'STOP_REQUESTED').exists() or (Path(shared_root).parent/'STOP_REQUESTED').exists():
                raise InterruptedError('PAUSED_DURING_E1_STATISTICS_SHARED_SCORES_RETAINED')
            elapsed = time.perf_counter()-started
            progress = dict(completed_replicates=replicate+1, total_replicates=replicates,
                            elapsed_seconds=elapsed, estimated_remaining_seconds=elapsed*(replicates-replicate-1)/(replicate+1))
            atomic_json(out/'E1_PAIRED_PROGRESS.json', progress)
            print(json.dumps(progress), flush=True)
    for row in rows:
        baseline = next(r for r in rows if r['stage']==row['stage'] and r['q']==row['q'] and r['view']=='DELAY')
        row['paired_increment_vs_delay'] = {metric:None if row.get(metric) is None or baseline.get(metric) is None
            else row[metric]-baseline[metric] for metric in METRICS}
        row['bootstrap_ci'] = {metric:dict(valid_replicates=len(v),
            ci_low=None if not v else float(np.quantile(v,.025)),
            ci_high=None if not v else float(np.quantile(v,.975)))
            for metric,v in absolute_values[row['stage'],row['q'],row['view']].items()}
        row['paired_delta_ci_vs_delay'] = {
            metric: dict(valid_replicates=len(v), ci_low=None if not v else float(np.quantile(v,.025)),
                         ci_high=None if not v else float(np.quantile(v,.975)))
            for metric,v in values[row['stage'],row['q'],row['view']].items()}
    payload = dict(schema_version='JATM_E1_PAIRED_EPISODE_V1', status='STATISTICS_COMPLETE',
        cu_reference_label=cu_label,
        seed=seed, replicates=replicates, episode_count=len(episodes), rows=rows,
        exclusions=excluded,stage_support=stage_support,paired_draw_across_stages_views_q=True,
        shared_manifest_sha256=file_hash(Path(shared_root)/'SHARED_ANNUAL_MANIFEST.json'),
        original_summary_sha256=None if original is None else file_hash(original_summary),
        wall_seconds=time.perf_counter()-started, model_inference_calls=0, final_test_access_count=0)
    atomic_json(out/'E1_PAIRED_SUMMARY.json', payload)
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--shared-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--original-summary', type=Path)
    args = parser.parse_args()
    run(args.shared_root, args.output_root, original_summary=args.original_summary)
