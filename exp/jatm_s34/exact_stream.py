"""Replayable exact product and online model-owned M2 reduction."""
from types import SimpleNamespace
from model.M1.marginal_distribution import ExactWeightedMarginalDistribution
from model.M2.comparison_support import _scenario_exclusion_reasons,ComparisonSupportRule,phi_c
from model.common.decision_contracts import ComparisonSupport,TypedStatus,WEIGHT_TOLERANCE
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.enums import SupportState
from model.common.errors import ContractError


def unavailable(node, service, reason):
    """A missing distribution is not an empty or approximate exact coupling."""
    source=node.state('HISTORY_JOINT')
    rule=ComparisonSupportRule()
    support=ComparisonSupport(episode_id=node.episode_id,chain_id=node.chain_id,node_id=node.node_id,
        rule_id=rule.rule_id,estimand=rule.estimand,supported_mass=0,scenario_count_total=0,
        threshold=rule.threshold,included=False,status=TypedStatus.ABSTAIN_NO_COMMON_SUPPORT,
        reason_codes=(reason,))
    state=SimpleNamespace(episode_id=node.episode_id,chain_id=node.chain_id,node_id=node.node_id,
        stage=node.stage,representation=source.representation,scenarios=())
    values=dict(delay=None,consequence=None,domain=None,components=None)
    audit=dict(node_id=node.node_id,status='UNKNOWN_INSUFFICIENT_PAYLOAD',reason=reason,
        product_scenario_count=None,source_scenario_count=len(source.scenarios),
        support_included=False,computation='NOT_RUN_NO_VALID_DISTRIBUTION',scores=values)
    return values,state,None,support,audit


class Replay:
    def __init__(self,factory,count):self.factory,self.count=factory,count
    def __iter__(self):return self.factory()
    def __len__(self):return self.count


def project(node,service, *, time_coordinate_contract: str = "R_IB_LEGACY_V1"):
    source=node.state('HISTORY_JOINT')
    try:
        adapter=ExactWeightedMarginalDistribution.from_source(source, time_coordinate_contract=time_coordinate_contract)
    except ContractError as error:
        if str(error).startswith('M1_SCENARIO_COORDINATE_MISSING:'):
            return unavailable(node,service,str(error))
        raise
    inherited={}
    for field in ('ib_observed','ob_observed','tx_observed','tx_reference_minutes'):
        values={getattr(s,field) for s in source.scenarios}
        if len(values)!=1:return unavailable(node,service,'EXACT_CONTEXT_NOT_CONSTANT:'+field)
        inherited[field]=next(iter(values))
    def states():
        for s in adapter.iter_scenarios():yield s.model_copy(update=inherited)
    state=SimpleNamespace(episode_id=source.episode_id,chain_id=source.chain_id,node_id=source.node_id,
        stage=source.stage,representation=adapter.representation,scenarios=Replay(states,adapter.scenario_count))
    def consequences():
        from model.common.decision_contracts import ConsequenceScenario
        for s in state.scenarios:
            yield (service.consequence_scenario(s,node_id=node.node_id,support=s.support) if node.node_id in service.references
                   else ConsequenceScenario(scenario_id=s.scenario_id,scenario_weight=s.scenario_weight,support=SupportState.ABSTAIN))
    consequence=SimpleNamespace(episode_id=state.episode_id,chain_id=state.chain_id,node_id=state.node_id,
        stage=state.stage,representation=state.representation,registry_id=service.registry_id,registry_hash=service.registry_hash,
        scenarios=Replay(consequences,adapter.scenario_count))
    mass=0.;weight=0.;delay=0.;totals={k:0. for k in CONSEQUENCE_COMPONENTS};ids=[];reasons=set();degraded=False
    for s,c in zip(state.scenarios,consequence.scenarios):
        weight+=s.scenario_weight
        excluded=_scenario_exclusion_reasons(s,c)
        if excluded:reasons.update(excluded);continue
        ids.append(s.scenario_id);mass+=s.scenario_weight;delay+=s.scenario_weight*s.d_to_minutes
        degraded=degraded or s.support is SupportState.DEGRADED or c.support is SupportState.DEGRADED
        for k in totals:totals[k]+=c.scenario_weight*c.cu_components[k]
    if abs(weight-1)>WEIGHT_TOLERANCE:raise ValueError('EXACT_STREAM_WEIGHT_SUM')
    rule=ComparisonSupportRule();included=mass+WEIGHT_TOLERANCE>=rule.threshold
    if not included:reasons.add('M2_CS_BELOW_NOMINAL_THRESHOLD')
    support=ComparisonSupport(episode_id=state.episode_id,chain_id=state.chain_id,node_id=state.node_id,
        rule_id=rule.rule_id,estimand=rule.estimand,supported_mass=mass,supported_scenario_ids=tuple(ids),
        scenario_count_total=adapter.scenario_count,threshold=rule.threshold,included=included,
        status=(TypedStatus.DEGRADED if degraded else TypedStatus.SUPPORTED) if included else TypedStatus.ABSTAIN_NO_COMMON_SUPPORT,
        reason_codes=tuple(sorted(reasons)))
    expected={k:v/mass for k,v in totals.items()} if included else None
    from exp.jatm_section5.run_development import _domain_vector
    values=dict(delay=delay/mass if included else None,consequence=phi_c(expected) if included else None,
        domain=_domain_vector(expected) if included else None,components=expected)
    audit=dict(node_id=node.node_id,product_scenario_count=adapter.scenario_count,source_scenario_count=len(source.scenarios),
        support_mass=mass,support_included=included,physical_feasibility='NOT_ASSERTED_PRODUCT_COUPLING',
        identity_note=adapter.identity_note,status='PASS_EXACT_MARGINAL' if included else 'ABSTAIN_COMMON_SUPPORT',
        computation='EXACT_REPLAYABLE_STREAM',scores=values)
    return values,state,consequence,support,audit
