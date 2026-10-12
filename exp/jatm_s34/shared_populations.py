"""Distinct manuscript populations over one shared annual scientific table."""
from model.common.enums import OperationalStage
from model.M3.stage1 import select_attention
from exp.jatm_section5.information_value import common_candidates,_signal

ACTIONABLE=(OperationalStage.PRE_IB,OperationalStage.POST_IB_PRE_OB)
REPRESENTATIONS=('HISTORY_JOINT','CURRENT_JOINT','HISTORY_POINT','HISTORY_MARGINAL_EXACT')


def population_views(nodes,canonical_ids,*,q=.10,exposure_by_node=None):
    canonical=tuple(n for n in nodes if n.node_id in canonical_ids)
    eligible=tuple(n for n in nodes if n.stage in ACTIONABLE and n.support_full.get('HISTORY_JOINT',False))
    # C1 is the full valid Stage-II population; canonical identities are only
    # the fixed Stage-I view and must not shrink recovery eligibility.
    c1=eligible
    common=tuple(n for n in canonical if n.stage in ACTIONABLE and all(
        n.support(rep).included and n.consequence_scores.get(rep) is not None for rep in REPRESENTATIONS))
    shortlists={}; pairwise={}; union=set()
    for rep in REPRESENTATIONS:
        candidates=common_candidates(canonical,comparator=rep,require_complete=False)
        shortlists[rep]={}
        pairwise[rep]={}
        for stage in ACTIONABLE:
            stage_candidates=tuple(row for row in candidates if row.stage is stage)
            signals=tuple(_signal(row,comparator=True,representation_id=rep) for row in stage_candidates)
            reference_signals=tuple(_signal(row,comparator=False,representation_id='HISTORY_JOINT') for row in stage_candidates)
            decision=select_attention(signals,q=q) if signals else None
            reference=select_attention(reference_signals,q=q) if signals else None
            shortlists[rep][stage]=() if decision is None else tuple(e.node_id for e in decision.entries if e.selected)
            reference_ids=() if reference is None else tuple(e.node_id for e in reference.entries if e.selected)
            union.update(reference_ids);union.update(shortlists[rep][stage])
            pairwise[rep][stage.value]=dict(q=q,n=len(signals),k=0 if decision is None else decision.k,
                candidate_ids=[r.node_id for r in stage_candidates],reference_shortlist=list(reference_ids),
                comparator_shortlist=list(shortlists[rep][stage]),union=sorted(set(reference_ids)|set(shortlists[rep][stage])))
    e1_shortlists={}
    if exposure_by_node is not None:
        from .e1_information_gain import VIEWS,_summarize_stage
        supported=[n for n in canonical if n.node_id in exposure_by_node and
                   n.support('HISTORY_JOINT').included and n.delay_scores.get('HISTORY_JOINT') is not None
                   and n.consequence_scores.get('HISTORY_JOINT') is not None]
        for stage in ACTIONABLE:
            for view in VIEWS:
                row=_summarize_stage([n for n in supported if n.stage is stage],view=view,q=q,factor_by_node=exposure_by_node)
                e1_shortlists[stage.value+':'+view]=dict(q=q,n=row['n'],k=row['k'],nodes=row['selected_view'])
                union.update(row['selected_view'])
    chains={}
    # episode_id is the approved aircraft-linked predecessor/successor chain.
    # node.chain_id is an older aircraft-day engineering key, not a resampling unit.
    for n in eligible:chains.setdefault(n.episode_id,[]).append(n)
    rolling=tuple(n for group in chains.values() if len(group)>1 for n in group)
    return dict(canonical=canonical,C1=c1,C2=tuple(n for n in c1 if n.node_id in union),C3=rolling,
        common=common,shortlists=shortlists,pairwise_stage1=pairwise,e1_shortlists=e1_shortlists,
        C1_CANONICAL=tuple(n for n in c1 if n.node_id in canonical_ids),
        e3=tuple(n for n in c1 if all(n.support_full.get(rep,False) for rep in
                                     ('HISTORY_JOINT','HISTORY_MARGINAL_EXACT'))))
