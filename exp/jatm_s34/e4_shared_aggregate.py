"""Read-only cross-year consumer. Never invokes M1--M3 or the M5-b battery."""
import argparse
import json
from pathlib import Path
from .shared_store import atomic_json, file_hash


def rolling_analysis(rows, allowed_ids, *, replicates=2000):
    """Within the approved episode chain; aircraft-day keys never merge chains."""
    from collections import defaultdict
    from .shared_statistics import clustered_summary
    groups=defaultdict(list)
    for row in rows:
        if row['node_id'] in allowed_ids:
            groups[row['episode_id'],row['representation']].append(row)
    changes=[]; trajectories=[]
    for (episode,representation),values in sorted(groups.items()):
        ordered=sorted(values,key=lambda row:(row['decision_time'],row['node_id']))
        if len(ordered)<2:continue
        first,last=ordered[0],ordered[-1]
        def difference(key):
            return None if first.get(key) is None or last.get(key) is None else last[key]-first[key]
        changes.append(dict(episode_id=episode,representation=representation,epochs=len(ordered),
            first_node=first['node_id'],last_node=last['node_id'],
            first_stage=first['stage'],last_stage=last['stage'],
            delta_u_joint=difference('u_joint'),delta_u_comparator=difference('u_comparator'),
            delta_normalized_regret=difference('normalized_regret'),
            delta_recoverable_value=difference('V')))
        trajectories.extend(ordered)
    summaries=[dict(representation=rep,**clustered_summary([r for r in changes if r['representation']==rep],
        ('delta_u_joint','delta_u_comparator','delta_normalized_regret','delta_recoverable_value'),replicates=replicates))
        for rep in sorted({r['representation'] for r in changes})]
    return dict(estimand='LAST_MINUS_FIRST_ADMISSIBLE_EPOCH_WITHIN_EPISODE',cluster_key='episode_id',
        interpretation='JOINT_EVOLUTION_OF_INFORMATION_AND_FEASIBILITY_NOT_CAUSAL_INFORMATION_EFFECT',
        changes=changes,summaries=summaries,trajectories=trajectories)


def inspect_annual_result(annual_root, year):
    """Fail closed on failed runs, old estimands, stale inputs/code and receipts."""
    directory=Path(annual_root)/str(year)
    paths={key:directory/path for key,path in dict(run='RUN_MANIFEST.json',
        cache='shared/CACHE_MANIFEST.json',scores='shared/SHARED_ANNUAL_MANIFEST.json',
        e1='E1/E1_PAIRED_SUMMARY.json',e1_fixed='E1_FIXED_COMMON/E1_PAIRED_SUMMARY.json',
        e2e3='E2_E3/E2_E3_SUMMARY.json',receipt='EVALUATION_COMPLETE.json').items()}
    missing=[key for key,path in paths.items() if not path.is_file()]
    if missing:return dict(year=year,status='NOT_RUN_OR_INCOMPLETE',missing=missing),None,paths
    try:
        data={key:json.loads(path.read_text()) for key,path in paths.items()}
        run=data['run']
        if run.get('year')!=year or run.get('status')!='COMPUTED_PENDING_SCIENTIFIC_ACCEPTANCE':
            return dict(year=year,status='ANNUAL_RUN_NOT_COMPLETE',run_status=run.get('status')),None,paths
        if run.get('scope')!='FULL_DEVELOPMENT':
            return dict(year=year,status='PILOT_EXCLUDED'),None,paths
        from .shared_run import evaluation_is_current,evaluation_identity
        if not evaluation_is_current(directory,evaluation_identity(directory/'shared')):
            return dict(year=year,status='EVALUATION_RECEIPT_MISSING_OR_OUTPUT_HASH_MISMATCH'),None,paths
        from .shared_populations import POPULATION_CONTRACT
        e=data['e2e3'];cu=data['cache']['identity']['cu_contract']
        fixed=e['action_identity']['fixed_common_contract']
        if (data['e1'].get('cu_reference_label')!='YEAR_LOCAL_V5' or data['e1'].get('replicates')!=2000
            or data['e1_fixed'].get('cu_reference_label')!='FIXED_COMMON_2017_H1_V5'
            or data['e1_fixed'].get('replicates')!=2000 or e.get('bootstrap_replicates')!=2000
            or e.get('scope')!='FULL_DEVELOPMENT' or e.get('year')!=year
            or e.get('status')!='DEVELOPMENT_COMPUTED_PENDING_SCIENTIFIC_ACCEPTANCE'
            or e.get('schema_version')!='JATM_SHARED_E2_E3_V2'
            or e.get('population_contract')!=POPULATION_CONTRACT
            or e.get('recovery_loss_estimand')!='RATIO_OF_SUMS_DELTA_REC_OVER_REFERENCE_V'):
            return dict(year=year,status='STATISTICS_OR_REFERENCE_INCOMPLETE'),None,paths
        if (cu['track']!='YEAR_LOCAL' or cu['reference_year']!=year
            or data['cache']['identity']['year']!=year
            or fixed['reference_year']!=2017 or fixed['track']!='FIXED_COMMON'):
            return dict(year=year,status='CU_OR_ANNUAL_IDENTITY_MISMATCH'),None,paths
        if any(payload.get('final_test_access_count',0)!=0 for payload in data.values()):
            return dict(year=year,status='PROTECTED_ACCESS_PROVENANCE'),None,paths
        return dict(year=year,status='COMPUTED_PENDING_SCIENTIFIC_ACCEPTANCE',
            regime='PRE_PANDEMIC' if year<=2019 else 'PANDEMIC_DISRUPTION' if year==2020 else 'OPERATING_RECOVERY',
            input_hashes={key:file_hash(path) for key,path in paths.items()},cu_contract=cu,
            shared_node_n=e['support_denominator'],reference_recovery_n=e['reference_cohort_count'],
            population_counts_by_stage=e['population_counts_by_stage'],
            information=e['information']),data,paths
    except (OSError,ValueError,KeyError,TypeError) as error:
        return dict(year=year,status='INVALID_ANNUAL_ARTIFACT',reason=str(error)),None,paths


def aggregate(annual_root, output_root):
    root=Path(annual_root);out=Path(output_root)
    years=[];chart=[];rolling=[];heterogeneity=[]
    for year in range(2017,2023):
        status,data,paths=inspect_annual_result(root,year)
        years.append(status)
        if data is None:continue
        for row in data['e1']['rows']:
            chart.append(dict(year=year,track='YEAR_LOCAL',experiment='E1',**row))
        for row in data['e1_fixed']['rows']:
            chart.append(dict(year=year,track='FIXED_COMMON',experiment='E1',**row))
        for row in data['e2e3']['e3_summary']:
            chart.append(dict(year=year,track='YEAR_LOCAL',experiment='E3',**row))
        fixed=data['e2e3']['action_identity']['fixed_common_contract']
        for row in data['e2e3'].get('fixed_common_e3_summary',[]):
            chart.append(dict(year=year,track='FIXED_COMMON',experiment='E3',**row))
        ids=set(data['e2e3']['populations']['C3'])
        for track,key,summary_key in (
                ('YEAR_LOCAL','recovery_atomic','recovery_summary'),
                ('FIXED_COMMON','fixed_common_recovery_atomic','fixed_common_recovery_summary')):
            atomic=data['e2e3'].get(key,[])
            result=rolling_analysis(atomic,ids,replicates=2000)
            atomic_json(out/f'ROLLING_{year}_{track}.json',result)
            rolling.append(dict(year=year,track=track,episode_n=len({r['episode_id'] for r in result['changes']}),
                                path=f'ROLLING_{year}_{track}.json',summaries=result['summaries']))
            for row in data['e2e3'].get(summary_key,[]):
                chart.append(dict(year=year,track=track,experiment='E2',**row))
            heterogeneity.extend(dict(year=year,track=track,**row) for row in atomic)
    completed=[r['year'] for r in years if r['status']=='COMPUTED_PENDING_SCIENTIFIC_ACCEPTANCE']
    complete=completed==list(range(2017,2023))
    payload=dict(schema_version='JATM_E4_SHARED_AGGREGATE_V2',
        status='COMPUTED_PENDING_SCIENTIFIC_ACCEPTANCE' if complete else
            'PARTIAL_DEVELOPMENT' if completed else 'SIX_YEAR_EXECUTION_BLOCKED',
        six_year_complete=complete,completed_years=completed,
        blocked_years=[r for r in years if r['year'] not in completed],
        scientific_acceptance='PENDING_NOT_IMPLIED_BY_COMPUTATION',years=years,rolling=rolling,
        cross_year_pooling='NOT_PERFORMED_WITHOUT_EXPLICIT_WEIGHTING_CONTRACT',
        year_local_absolute_values_poolable=False,fixed_common_status='REVALUED_SCREENING_AND_ACTION_COMPARISON',
        final_test_access_count=0)
    atomic_json(out/'E4_YEAR_MATRIX.json',payload);atomic_json(out/'SECTION5_CHART_SOURCE.json',chart)
    atomic_json(out/'STAGE_HEADROOM_THRESHOLD_SOURCE.json',heterogeneity)
    return payload


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--annual-root',type=Path,required=True)
    parser.add_argument('--output-root',type=Path,required=True)
    args=parser.parse_args();aggregate(args.annual_root,args.output_root)
