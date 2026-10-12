"""Paired chain-cluster inference from persisted decisions, without inference."""
from collections import defaultdict
import numpy as np


def clustered_summary(rows,metrics,*,replicates=2000,seed=20261011):
    """Mean estimands; duplicate cluster draws retain their full multiplicity."""
    episodes=sorted({r['episode_id'] for r in rows})
    indices={ep:i for i,ep in enumerate(episodes)}
    rng=np.random.default_rng(seed)
    accumulators={}
    for metric in metrics:
        sums=np.zeros(len(episodes));counts=np.zeros(len(episodes))
        for row in rows:
            value=row.get(metric)
            if value is None or not np.isfinite(value):continue
            i=indices[row['episode_id']];sums[i]+=value;counts[i]+=1
        accumulators[metric]=(sums,counts,[])
    # A single paired draw feeds all metrics. Memory is O(clusters + B*M),
    # not O(B*clusters), and RNG draw order matches the former dense array.
    if episodes:
        for _ in range(replicates):
            draw=rng.integers(0,len(episodes),size=len(episodes))
            for sums,counts,values in accumulators.values():
                n=counts[draw].sum()
                if n>0:values.append(float(sums[draw].sum()/n))
    result={}
    for metric,(sums,counts,values) in accumulators.items():
        total=counts.sum()
        result[metric]=dict(mean=None if total==0 else float(sums.sum()/total),n=int(total),
            missing=len(rows)-int(total),valid_replicates=len(values),
            ci_low=None if not values else float(np.quantile(values,.025)),
            ci_high=None if not values else float(np.quantile(values,.975)))
    return dict(estimand='NODE_MEAN_WITH_PAIRED_CHAIN_CLUSTER_RESAMPLING',episode_n=len(episodes),
        node_n=len(rows),replicates=replicates,seed=seed,metrics=result)


def recovery_loss_summary(rows, *, numerator='reference_regret', denominator='V',
                          replicates=2000, seed=20261011):
    """Paper L_rec: ratio of paired sums, recomputed on every episode draw."""
    episodes=sorted({r['episode_id'] for r in rows})
    indices={ep:i for i,ep in enumerate(episodes)}
    losses=np.zeros(len(episodes));values=np.zeros(len(episodes))
    valid=[]
    for row in rows:
        loss,value=row.get(numerator),row.get(denominator)
        if loss is None or value is None or not np.isfinite(loss) or not np.isfinite(value):continue
        if value<0:raise ValueError('NEGATIVE_REFERENCE_RECOVERABLE_VALUE')
        valid.append(row)
        index=indices[row['episode_id']];losses[index]+=loss;values[index]+=value
    rng=np.random.default_rng(seed);samples=[]
    if episodes:
        for _ in range(replicates):
            draw=rng.integers(0,len(episodes),size=len(episodes))
            ref=values[draw].sum()
            if ref>0:samples.append(float(losses[draw].sum()/ref))
    loss_sum=float(losses.sum());value_sum=float(values.sum())
    return dict(estimand='RATIO_OF_SUMS_DELTA_REC_OVER_REFERENCE_V',
        L_rec=None if value_sum<=0 else loss_sum/value_sum,
        delta_rec_sum=loss_sum,V_ref_sum=value_sum,
        candidate_n=len(rows),paired_n=len(valid),excluded_n=len(rows)-len(valid),
        zero_reference_value_n=sum(r[denominator]==0 for r in valid),
        episode_n=len(episodes),paired_episode_n=len({r['episode_id'] for r in valid}),
        replicates=replicates,valid_replicates=len(samples),seed=seed,
        ci_low=None if not samples else float(np.quantile(samples,.025)),
        ci_high=None if not samples else float(np.quantile(samples,.975)),
        status='DEFINED' if value_sum>0 else 'UNDEFINED_ZERO_REFERENCE_DENOMINATOR')


def summarize_actions(records,populations,node_metadata,*,replicates=2000,population_metadata=None):
    atomic=[]
    for record in records:
        if record['status']!='ACTION_TABLE_COMPLETE':continue
        node=node_metadata[record['node_id']]
        ref=record['reference_decision'];curves=dict(record['reference_objectives'])
        best=curves[float(ref['u_star'])];denominator=curves[0.0]-best
        for representation in ('CURRENT_JOINT','HISTORY_POINT','HISTORY_MARGINAL'):
            recovery=record['recoveries'][representation]
            if recovery['fallback'] is not None:
                loss=None;relative=None;agreement=None
            else:
                loss=curves[float(recovery['action'])]-best
                relative=None if denominator<=0 else loss/denominator
                agreement=float(recovery['action']==ref['u_star'])
            atomic.append(dict(node_id=node.node_id,episode_id=node.episode_id,chain_id=node.chain_id,
                stage=node.stage.value,decision_time=node.decision_time.isoformat(),representation=representation,
                u_joint=ref['u_star'],u_comparator=recovery['action'],J_zero=curves[0.0],V=denominator,
                activation_joint=float(ref['u_star']>0),target_agreement=agreement,
                reference_regret=loss,normalized_regret=relative,
                node_normalized_regret_diagnostic=relative,exclusion=recovery['fallback'],
                **record.get('mechanism_context',{})))
    summaries=[]
    for population,ids in populations.items():
        allowed=set(ids)
        contract=(population_metadata or {}).get(population)
        for stage in sorted({r['stage'] for r in atomic}):
            for rep in ('CURRENT_JOINT','HISTORY_POINT','HISTORY_MARGINAL'):
                exact_rep='HISTORY_MARGINAL_EXACT' if rep=='HISTORY_MARGINAL' else rep
                if contract and (contract['stage']!=stage or contract['comparator']!=exact_rep):continue
                rows=[r for r in atomic if r['node_id'] in allowed and r['stage']==stage and r['representation']==rep]
                summaries.append(dict(population=population,stage=stage,representation=rep,
                    contrast_contract=contract,
                    recovery_loss=recovery_loss_summary(rows,replicates=replicates),
                    **clustered_summary(rows,('activation_joint','target_agreement','reference_regret',
                        'node_normalized_regret_diagnostic','V'),replicates=replicates)))
    return atomic,summaries


def objective_summary(rows,*,replicates=2000):
    joint={(r['profile'],r['node_id']):r for r in rows if r['representation']=='HISTORY_JOINT'}
    groups=defaultdict(list)
    for row in rows:
        if row['representation']=='HISTORY_MARGINAL_EXACT':
            reference=joint.get((row['profile'],row['node_id']))
            if reference is None:raise ValueError('E3_JOINT_REFERENCE_ROW_MISSING')
            value=reference['J_zero']-reference['J_star']
            groups[row['profile'],row['stage']].append(dict(row,reference_V=value,
                node_relative_reference_loss_diagnostic=row.get('relative_reference_loss_at_marginal_action')))
    return [dict(profile=profile,stage=stage,population='CANONICAL_C1_HJ_HM_COMMON_SUPPORT',
        recovery_loss=recovery_loss_summary(values,numerator='joint_reference_loss_at_marginal_action',
            denominator='reference_V',replicates=replicates),**clustered_summary(values,
        ('joint_reference_loss_at_marginal_action','node_relative_reference_loss_diagnostic',
         'choice_agreement','decision_margin','relative_objective_perturbation'),replicates=replicates))
        for (profile,stage),values in sorted(groups.items())]


def stage1_pairwise_statistics(nodes, *, q=.10, replicates=2000, seed=20261011):
    """Use the established ranking/bootstrap on each valid HJ-comparator pair."""
    from exp.jatm_section5.information_value import (COMPONENTS, common_candidates,
        _component_estimates, _component_bootstrap)
    from .shared_populations import ACTIONABLE
    output=[]
    for component,(rep,_) in COMPONENTS.items():
        candidates=common_candidates(nodes,comparator=rep,require_complete=False)
        for stage in ACTIONABLE:
            values=tuple(r for r in candidates if r.stage is stage)
            table={stage:values}
            _,loss,reassigned,selected=_component_estimates(table,q=q,component=component)
            boot=_component_bootstrap({component:table},episodes=sorted({r.episode_id for r in values}),
                q=q,seed=seed,replicates=replicates)[component]
            finite=boot[np.isfinite(boot)]
            output.append(dict(component=component,comparator=rep,stage=stage.value,q=q,
                n=len(values),reassigned=reassigned,selected=selected,attention_loss=loss,
                replicates=replicates,valid_replicates=len(finite),seed=seed,
                ci_low=None if not len(finite) else float(np.quantile(finite,.025)),
                ci_high=None if not len(finite) else float(np.quantile(finite,.975)),
                support='PAIRWISE_HJ_COMPARATOR_CANONICAL',candidate_ids=[r.node_id for r in values]))
    return output


def recovery_coverage(records, nodes, canonical_ids, *, replicates=2000, seed=20261011, q=.10):
    """Balanced-objective Coverage@K; reconstruct ranks/K on each episode draw."""
    from collections import defaultdict
    from types import SimpleNamespace
    from model.M3.stage1 import rank_signals,attention_capacity_k
    from exp.jatm_section5.information_value import common_candidates
    from .shared_populations import ACTIONABLE,REPRESENTATIONS
    by_id={n.node_id:n for n in nodes}
    values={r['node_id']:float(r['reference_decision']['recoverable_value']) for r in records
            if r['status']=='ACTION_TABLE_COMPLETE'}
    canonical=[n for n in nodes if n.node_id in canonical_ids]
    descriptors=[]
    for rep in REPRESENTATIONS:
        pair=common_candidates(canonical,comparator=rep,require_complete=False)
        for stage in ACTIONABLE:
            candidates=[r for r in pair if r.stage is stage]
            eligible={nid:v for nid,v in values.items() if nid in canonical_ids
                      and by_id[nid].stage is stage and by_id[nid].support_full.get('HISTORY_JOINT',False)}
            episodes=sorted({r.episode_id for r in candidates}|{by_id[n].episode_id for n in eligible})
            groups=defaultdict(list);denominator_by_episode=defaultdict(float)
            for row in candidates:groups[row.episode_id].append(row)
            for nid,value in eligible.items():denominator_by_episode[by_id[nid].episode_id]+=value
            def estimate(draw):
                signals=[];value_by_instance={};denominator=0.
                for occurrence,episode in enumerate(draw):
                    denominator+=denominator_by_episode[episode]
                    suffix=f'::COVERAGE_BOOT{occurrence}'
                    for row in groups[episode]:
                        nid=row.node_id+suffix
                        signals.append(SimpleNamespace(episode_id=row.episode_id+suffix,node_id=nid,score=row.comparator_score))
                        value_by_instance[nid]=eligible.get(row.node_id,0.)
                k=attention_capacity_k(q,len(signals))
                numerator=sum(value_by_instance[r.node_id] for r in rank_signals(signals)[:k])
                return numerator,denominator,k
            numerator,denominator,k=estimate(episodes)
            rng=np.random.default_rng(seed);samples=[]
            if episodes:
                for _ in range(replicates):
                    draw=[episodes[i] for i in rng.integers(0,len(episodes),size=len(episodes))]
                    a,b,_=estimate(draw)
                    if b>0:samples.append(a/b)
            descriptors.append(dict(profile='BALANCED',representation=rep,stage=stage.value,q=q,
                candidate_n=len(candidates),recovery_eligible_n=len(eligible),k=k,episode_n=len(episodes),
                recoverable_value_in_shortlist=numerator,full_eligible_recoverable_value=denominator,
                coverage=None if denominator<=0 else numerator/denominator,
                replicates=replicates,valid_replicates=len(samples),seed=seed,
                ci_low=None if not samples else float(np.quantile(samples,.025)),
                ci_high=None if not samples else float(np.quantile(samples,.975)),
                inference='EPISODE_CLUSTER_RECONSTRUCT_CANDIDATES_K_AND_RANK',
                denominator='FULL_CANONICAL_HJ_SUPPORTED_STAGE_II_CASES'))
    return descriptors
