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


def aggregate(annual_root, output_root):
    root=Path(annual_root);out=Path(output_root)
    years=[];chart=[];rolling=[];heterogeneity=[]
    for year in range(2017,2023):
        directory=root/str(year)
        paths={key:directory/path for key,path in dict(run='RUN_MANIFEST.json',
            cache='shared/CACHE_MANIFEST.json',e1='E1/E1_PAIRED_SUMMARY.json',
            e1_fixed='E1_FIXED_COMMON/E1_PAIRED_SUMMARY.json',e2e3='E2_E3/E2_E3_SUMMARY.json').items()}
        missing=[key for key,path in paths.items() if not path.is_file()]
        if missing:
            years.append(dict(year=year,status='NOT_RUN_OR_INCOMPLETE',missing=missing));continue
        data={key:json.loads(path.read_text()) for key,path in paths.items()}
        if data['run']['scope']!='FULL_DEVELOPMENT':
            years.append(dict(year=year,status='PILOT_EXCLUDED'));continue
        from .shared_run import evaluation_is_current
        receipt=directory/'EVALUATION_COMPLETE.json'
        if not receipt.is_file() or not evaluation_is_current(directory,json.loads(receipt.read_text())['identity']):
            years.append(dict(year=year,status='EVALUATION_RECEIPT_MISSING_OR_OUTPUT_HASH_MISMATCH'));continue
        if (data['e1']['cu_reference_label']!='YEAR_LOCAL_V5' or data['e1']['replicates']!=2000
            or data['e2e3']['bootstrap_replicates']!=2000 or data['e2e3']['scope']!='FULL_DEVELOPMENT'):
            years.append(dict(year=year,status='STATISTICS_OR_REFERENCE_INCOMPLETE'));continue
        if any(payload.get('final_test_access_count',0)!=0 for payload in data.values()):
            raise ValueError('E4_PROTECTED_ACCESS_PROVENANCE')
        contract=data['cache']['identity']['cu_contract']
        if contract['track']!='YEAR_LOCAL' or contract['reference_year']!=year:
            raise ValueError('E4_YEAR_LOCAL_SCALE_MISMATCH')
        years.append(dict(year=year,status='COMPUTED_PENDING_SCIENTIFIC_ACCEPTANCE',
            regime='PRE_PANDEMIC' if year<=2019 else 'PANDEMIC_DISRUPTION' if year==2020 else 'OPERATING_RECOVERY',
            input_hashes={key:file_hash(path) for key,path in paths.items()},cu_contract=contract,
            effective_candidates=data['e2e3']['support_denominator'],reference_recovery_n=data['e2e3']['reference_cohort_count'],
            information=data['e2e3']['information']))
        for row in data['e1']['rows']:
            chart.append(dict(year=year,track='YEAR_LOCAL',experiment='E1',**row))
        if data['e1_fixed']['cu_reference_label']!='FIXED_COMMON_2017_H1_V5' or data['e1_fixed']['replicates']!=2000:
            raise ValueError('E4_FIXED_COMMON_E1_CONTRACT_MISMATCH')
        for row in data['e1_fixed']['rows']:
            chart.append(dict(year=year,track='FIXED_COMMON',experiment='E1',**row))
        for row in data['e2e3']['e3_summary']:
            chart.append(dict(year=year,track='YEAR_LOCAL',experiment='E3',**row))
        fixed=data['e2e3']['action_identity']['fixed_common_contract']
        if fixed['reference_year']!=2017 or fixed['track']!='FIXED_COMMON':
            raise ValueError('E4_FIXED_COMMON_IDENTITY_MISMATCH')
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
    payload=dict(schema_version='JATM_E4_SHARED_AGGREGATE_V1',
        status='PENDING_SCIENTIFIC_ACCEPTANCE',years=years,rolling=rolling,
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
