from datetime import datetime, timezone

from model.M4.contracts import (
    ComponentSummary,
    DomainScoreSummary,
    PriorityScoreRecord,
)
from model.M4.priority import aggregate_domain_scores, build_domain_scores
from model.PRE.contracts.pre_state import DecisionNodeRecord
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.enums import OperationalStage


def _node(node_id="N1"):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return DecisionNodeRecord(
        decision_node_id=node_id,
        episode_id=f"E-{node_id}",
        decision_time=now,
        information_cutoff=now,
        operational_stage=OperationalStage.PRE_IB,
        roll_minutes=60,
        node_index=0,
        status="CONSTRUCTED",
        formal_eligible=True,
        config_hash="config",
        registry_manifest_hash="manifest",
        legal_record_ids=("record",),
    )


def test_fixed_seven_to_three_to_aggregate_mapping():
    components = tuple(
        ComponentSummary(component_id=name, value=value, unit="CU")
        for name, value in zip(CONSEQUENCE_COMPONENTS, (3, 6, 9, 12, 15, 18, 21))
    )
    domains = build_domain_scores(components)
    assert tuple(item.value for item in domains) == (6.0, 15.0, 21.0)
    assert aggregate_domain_scores(domains) == 14.0


def test_priority_score_record_exposes_node_identity_without_duplicate_fields():
    components = tuple(
        ComponentSummary(component_id=name, value=1.0, unit="CU")
        for name in CONSEQUENCE_COMPONENTS
    )
    domains = (
        DomainScoreSummary(domain_id="F", value=1.0, component_ids=CONSEQUENCE_COMPONENTS[:3]),
        DomainScoreSummary(domain_id="P", value=1.0, component_ids=CONSEQUENCE_COMPONENTS[3:6]),
        DomainScoreSummary(domain_id="R", value=1.0, component_ids=(CONSEQUENCE_COMPONENTS[6],)),
    )
    record = PriorityScoreRecord(
        node=_node(),
        scenario_ids=(0,),
        scenario_weights=(1.0,),
        scenario_count=1,
        scenario_lineage=("m1",),
        common_support_scenario_ids=(0,),
        common_support_count=1,
        common_support_mass=1.0,
        policy_id="FULL_COMMON_SUPPORT_100",
        summary_state="AVAILABLE",
        comparative_eligible=True,
        eligibility_reasons=(),
        support_primary=True,
        support_sensitivity=True,
        support_full=True,
        delay_mean_cs=4.0,
        native_cs=components,
        cu_cs=components,
        domain_scores=domains,
        aggregate_score=1.0,
        input_digest="input",
        cu_registry_digest="registry",
        m1_registry_lineage=("m1",),
        m2_registry_id="M2",
        m2_registry_version="V4",
        m2_registry_hash="hash",
        aggregation_contract_id="aggregation",
    )
    assert record.episode_id == "E-N1"
    assert record.decision_node_id == "N1"
