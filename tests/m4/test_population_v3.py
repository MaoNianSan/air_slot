from datetime import datetime, timedelta, timezone

from model.M4.contracts import (
    ComponentSummary,
    DomainScoreSummary,
    PopulationScope,
    PriorityScoreRecord,
)
from model.M4.population import build_population
from model.PRE.contracts.pre_state import DecisionNodeRecord
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.enums import OperationalStage
from model.common.identity import content_id


def _record(episode, node_id, when, eligible=True):
    now = when
    node = DecisionNodeRecord(
        decision_node_id=node_id,
        episode_id=episode,
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
    components = tuple(
        ComponentSummary(component_id=item, value=1.0, unit="CU")
        for item in CONSEQUENCE_COMPONENTS
    )
    domains = (
        DomainScoreSummary(domain_id="F", value=1.0, component_ids=CONSEQUENCE_COMPONENTS[:3]),
        DomainScoreSummary(domain_id="P", value=1.0, component_ids=CONSEQUENCE_COMPONENTS[3:6]),
        DomainScoreSummary(domain_id="R", value=1.0, component_ids=(CONSEQUENCE_COMPONENTS[6],)),
    )
    return PriorityScoreRecord(
        node=node,
        scenario_ids=(0,),
        scenario_weights=(1.0,),
        scenario_count=1,
        scenario_lineage=("m1",),
        common_support_scenario_ids=(0,),
        common_support_count=1,
        common_support_mass=1.0,
        policy_id="PRIMARY_COMMON_SUPPORT_090",
        summary_state="AVAILABLE",
        comparative_eligible=eligible,
        eligibility_reasons=() if eligible else ("M4_COMMON_SUPPORT_BELOW_THRESHOLD",),
        support_primary=True,
        support_sensitivity=True,
        support_full=True,
        delay_mean_cs=1.0,
        native_cs=components,
        cu_cs=components,
        domain_scores=domains,
        aggregate_score=1.0,
        input_digest=content_id((episode, node_id, when.isoformat())),
        cu_registry_digest="registry",
        m1_registry_lineage=("m1",),
        m2_registry_id="M2",
        m2_registry_version="V4",
        m2_registry_hash="hash",
        aggregation_contract_id="aggregation",
    )


def test_retrospective_population_selects_earliest_before_eligibility():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    early = _record("E1", "N0", start, eligible=False)
    late = _record("E1", "N1", start + timedelta(minutes=10), eligible=True)
    other = _record("E2", "N2", start, eligible=True)
    population = build_population(
        (late, other, early),
        PopulationScope(
            kind="RETROSPECTIVE_STAGE",
            stage=OperationalStage.PRE_IB,
            cohort_id="synthetic",
        ),
    )
    assert tuple(item.decision_node_id for item in population.records) == ("N2",)
    assert any(item.decision_node_id == "N0" for item in population.excluded)
    assert any(item.decision_node_id == "N1" for item in population.excluded)
