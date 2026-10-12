"""Canonical Stage-II populations and contrast-specific shortlist unions."""
from dataclasses import replace
import json
from model.common.enums import OperationalStage
from model.M3.stage1 import select_attention
from exp.jatm_section5.information_value import common_candidates, _signal

ACTIONABLE=(OperationalStage.PRE_IB,OperationalStage.POST_IB_PRE_OB)
REPRESENTATIONS=('HISTORY_JOINT','CURRENT_JOINT','HISTORY_POINT','HISTORY_MARGINAL_EXACT')
POPULATION_CONTRACT='CANONICAL_C1_CONTRAST_C2_ROLLING_C3_V2'


def c2_key(*,year,stage,q,contrast,reference_objective,cu_track):
    return json.dumps(dict(year=int(year),stage=stage,q=float(q),contrast=contrast,
        reference_objective=reference_objective,cu_track=cu_track),sort_keys=True,separators=(',',':'))


def population_views(nodes,canonical_ids,*,year,q=.10,exposure_by_node=None,
                     reference_objective='BALANCED',cu_track='YEAR_LOCAL'):
    from .e2_e3_exact import PROFILES
    if year not in range(2017,2023) or cu_track not in ('YEAR_LOCAL','FIXED_COMMON'):
        raise ValueError('POPULATION_YEAR_OR_CU_TRACK_INVALID')
    if reference_objective not in PROFILES:raise ValueError('UNKNOWN_REFERENCE_OBJECTIVE')
    nodes=tuple(nodes)
    if reference_objective!='BALANCED':
        from model.M2.comparison_support import phi_c
        nodes=tuple(replace(n,consequence_scores={rep:None if vector is None else
            phi_c(vector,view=PROFILES[reference_objective]) for rep,vector in n.component_scores.items()}) for n in nodes)
    canonical=tuple(n for n in nodes if n.node_id in canonical_ids)
    eligible=tuple(n for n in nodes if n.stage in ACTIONABLE and n.support_full.get('HISTORY_JOINT',False))
    # Main chain-stage cases are fixed before support. No later replacement.
    c1=tuple(n for n in eligible if n.node_id in canonical_ids)
    c1_ids={n.node_id for n in c1}
    common=tuple(n for n in canonical if n.stage in ACTIONABLE and all(
        n.support(rep).included and n.consequence_scores.get(rep) is not None for rep in REPRESENTATIONS))
    shortlists={};pairwise={};c2={}

    def add_group(stage,contrast,family,reference_ids,comparator_ids,candidates,paired_ids,comparator):
        key=c2_key(year=year,stage=stage.value,q=q,contrast=contrast,
                   reference_objective=reference_objective,cu_track=cu_track)
        union=set(reference_ids)|set(comparator_ids)
        c2[key]=dict(year=year,stage=stage.value,q=float(q),contrast=contrast,family=family,
            reference_objective=reference_objective,cu_track=cu_track,comparator=comparator,
            candidate_ids=sorted(candidates),candidate_n=len(candidates),
            reference_shortlist=sorted(reference_ids),comparator_shortlist=sorted(comparator_ids),
            shortlist_union=sorted(union),shortlist_union_n=len(union),
            node_ids=sorted(union & paired_ids),paired_n=len(union & paired_ids),
            excluded_from_recovery=sorted(union-paired_ids),
            support_rule='CANONICAL_C1_INTERSECT_CONTRAST_STAGE_II_COMMON_SUPPORT')

    for rep in REPRESENTATIONS:
        candidates=common_candidates(canonical,comparator=rep,require_complete=False)
        shortlists[rep]={};pairwise[rep]={}
        for stage in ACTIONABLE:
            stage_candidates=tuple(row for row in candidates if row.stage is stage)
            signals=tuple(_signal(row,comparator=True,representation_id=rep) for row in stage_candidates)
            ref_signals=tuple(_signal(row,comparator=False,representation_id='HISTORY_JOINT') for row in stage_candidates)
            decision=select_attention(signals,q=q) if signals else None
            reference=select_attention(ref_signals,q=q) if signals else None
            ids=() if decision is None else tuple(e.node_id for e in decision.entries if e.selected)
            ref_ids=() if reference is None else tuple(e.node_id for e in reference.entries if e.selected)
            shortlists[rep][stage]=ids
            pairwise[rep][stage.value]=dict(q=q,n=len(signals),k=0 if decision is None else decision.k,
                candidate_ids=[r.node_id for r in stage_candidates],reference_shortlist=list(ref_ids),
                comparator_shortlist=list(ids),union=sorted(set(ref_ids)|set(ids)))
            if rep!='HISTORY_JOINT':
                paired={n.node_id for n in c1 if n.stage is stage and n.support_full.get(rep,False)}
                add_group(stage,'E2:HISTORY_JOINT_vs_'+rep,'E2',ref_ids,ids,
                          {r.node_id for r in stage_candidates},paired,rep)
    e1_shortlists={}
    if exposure_by_node is not None:
        from .e1_information_gain import VIEWS,_summarize_stage
        supported=[n for n in canonical if n.node_id in exposure_by_node and
                   n.support('HISTORY_JOINT').included and n.delay_scores.get('HISTORY_JOINT') is not None
                   and n.consequence_scores.get('HISTORY_JOINT') is not None]
        for stage in ACTIONABLE:
            values=[n for n in supported if n.stage is stage]
            for view in VIEWS:
                row=_summarize_stage(values,view=view,q=q,factor_by_node=exposure_by_node)
                e1_shortlists[stage.value+':'+view]=dict(q=q,n=row['n'],k=row['k'],nodes=row['selected_view'])
                if view!='CONSEQUENCE':
                    add_group(stage,'E1:CONSEQUENCE_vs_'+view,'E1',row['selected_reference'],row['selected_view'],
                        {n.node_id for n in values},c1_ids,view)
    chains={}
    for n in eligible:chains.setdefault(n.episode_id,[]).append(n)
    rolling=tuple(n for group in chains.values() if len(group)>1 for n in group)
    return dict(contract=POPULATION_CONTRACT,canonical=canonical,C1=c1,C2=c2,C3=rolling,
        common=common,shortlists=shortlists,pairwise_stage1=pairwise,e1_shortlists=e1_shortlists,
        C1_CANONICAL=c1,
        e3=tuple(n for n in c1 if all(n.support_full.get(rep,False) for rep in
                                     ('HISTORY_JOINT','HISTORY_MARGINAL_EXACT'))))


def c2_recovery_populations(groups):
    """E1 unions remain separate screening descriptors, never E2 loss cohorts."""
    metadata={'C2::'+key:value for key,value in groups.items() if value['family']=='E2'}
    return {key:set(value['node_ids']) for key,value in metadata.items()},metadata
