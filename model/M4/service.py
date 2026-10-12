from __future__ import annotations

from math import isfinite

from model.M2.contracts import M2ScenarioInput, ScenarioConsequence
from model.M2.cu.registry import FrozenData2CUNormalizationRegistry
from model.PRE.contracts.pre_state import DecisionNodeRecord
from model.common.enums import OperationalStage
from model.common.errors import ContractError
from model.common.identity import content_id
from model.common.estimand import FormalEstimandStatus

from .alignment import compare_priority_representations
from .common_support import (
    common_support_mass,
    common_support_records,
    conditional_mean,
    support_flags,
    validate_node_inputs,
)
from .contracts import (
    CommonSupportPolicy,
    ComponentSummary,
    DomainScoreSummary,
    PopulationScope,
    PriorityOrdering,
    PriorityPopulation,
    PriorityRepresentation,
    PriorityScoreRecord,
    ScreeningCapacity,
    ScreeningShortlist,
    PriorityAlignmentRecord,
)
from .population import build_population
from .priority import AGGREGATION_CONTRACT_ID, aggregate_domain_scores, build_domain_scores
from .screening import build_shortlist


class M4Service:
    def summarize_node(
        self,
        *,
        node: DecisionNodeRecord,
        scenarios: tuple[M2ScenarioInput, ...],
        consequences: tuple[ScenarioConsequence, ...],
        registry: FrozenData2CUNormalizationRegistry,
        policy: CommonSupportPolicy,
    ) -> PriorityScoreRecord:
        scenarios = tuple(scenarios)
        consequences = tuple(consequences)
        validate_node_inputs(node, scenarios, consequences)
        records = common_support_records(scenarios, consequences, registry)
        mass = common_support_mass(records)
        primary, sensitivity, full = support_flags(mass)
        selected = tuple(item for item in records if item["common_supported"])
        native = []
        cu = []
        for index, component_id in enumerate(
            ("F_continuity", "F_execution", "F_propagation",
             "P_time", "P_itinerary", "P_service", "R_operating")
        ):
            native_value = conditional_mean(
                records,
                lambda item, i=index: item["rows"][i].native_quantity,
                mass,
            )
            cu_value = conditional_mean(
                records,
                lambda item, i=index: item["rows"][i].constructed_value_cu,
                mass,
            )
            native.append(
                ComponentSummary(
                    component_id=component_id,
                    value=native_value,
                    unit=(selected[0]["rows"][index].native_unit if selected else "unknown"),
                    reason_code=None if native_value is not None else "M4_EMPTY_COMMON_SUPPORT",
                )
            )
            cu.append(
                ComponentSummary(
                    component_id=component_id,
                    value=cu_value,
                    unit="CU",
                    reason_code=None if cu_value is not None else "M4_EMPTY_COMMON_SUPPORT",
                )
            )
        domains = build_domain_scores(tuple(cu))
        aggregate = aggregate_domain_scores(domains) if mass > 0 else None
        reasons: list[str] = []
        policy_supported = {
            "PRIMARY_COMMON_SUPPORT_090": primary,
            "SENSITIVITY_COMMON_SUPPORT_050": sensitivity,
            "FULL_COMMON_SUPPORT_100": full,
        }[policy.policy_id]
        if mass == 0:
            reasons.append("M4_EMPTY_COMMON_SUPPORT")
        if not policy_supported and mass > 0:
            reasons.append("M4_COMMON_SUPPORT_BELOW_THRESHOLD")
        if not node.formal_eligible:
            reasons.append("M4_NODE_NOT_FORMALLY_ELIGIBLE")
        if node.operational_stage is OperationalStage.COMPLETED:
            reasons.append("M4_COMPLETED_STAGE_EXCLUDED")
        comparative = (
            node.formal_eligible
            and node.operational_stage is not OperationalStage.COMPLETED
            and policy_supported
        )
        cu_registry = getattr(registry, "registry", registry)
        registry_digest = cu_registry.digest()
        scenario_lineage = tuple(
            lineage
            for item in scenarios
            for lineage in (item.pre_lineage + item.reference_lineage)
        )
        input_digest = content_id(
            {
                "node": node.model_dump(mode="json"),
                "scenarios": tuple(item.model_dump(mode="json") for item in scenarios),
                "consequences": tuple(item.model_dump(mode="json") for item in consequences),
            }
        )
        for consequence, item in zip(consequences, records, strict=True):
            component_supported = all(
                str(getattr(row.support_state, "value", row.support_state))
                != "ABSTAIN"
                and row.native_quantity is not None
                and isfinite(float(row.native_quantity))
                and str(getattr(row.cu_status, "value", row.cu_status))
                == "CU_FROZEN"
                and row.constructed_value_cu is not None
                and isfinite(float(row.constructed_value_cu))
                and row.cu_quantity.compatible_with_registry(cu_registry)
                for row in consequence.component_vector.rows
            )
            formal_available = (
                FormalEstimandStatus(consequence.formal_estimand_value.status)
                is FormalEstimandStatus.FORMAL_AVAILABLE
            )
            if formal_available != component_supported:
                raise ContractError("M4_FORMAL_COMPONENT_SUPPORT_MISMATCH")
        m2_registry_hash = getattr(cu_registry, "registry_hash", "") or registry_digest
        m2_registry_version = getattr(
            cu_registry,
            "schema_version",
            getattr(cu_registry, "version", "UNKNOWN"),
        )
        return PriorityScoreRecord(
            node=node,
            scenario_ids=tuple(item.scenario_id for item in scenarios),
            scenario_weights=tuple(float(item.scenario_weight) for item in scenarios),
            scenario_count=len(scenarios),
            scenario_lineage=tuple(sorted(set(scenario_lineage))),
            common_support_scenario_ids=tuple(int(item["scenario_id"]) for item in selected),
            common_support_count=len(selected),
            common_support_mass=mass,
            policy_id=policy.policy_id,
            summary_state="AVAILABLE" if mass > 0 else "EMPTY_COMMON_SUPPORT",
            comparative_eligible=comparative,
            eligibility_reasons=tuple(sorted(set(reasons))),
            support_primary=primary,
            support_sensitivity=sensitivity,
            support_full=full,
            delay_mean_cs=conditional_mean(records, lambda item: item["delay"], mass),
            native_cs=tuple(native),
            cu_cs=tuple(cu),
            domain_scores=domains,
            aggregate_score=aggregate,
            input_digest=input_digest,
            cu_registry_digest=registry_digest,
            m1_registry_lineage=tuple(sorted(set(scenario_lineage))),
            m2_registry_id=getattr(cu_registry, "registry_id", "UNKNOWN"),
            m2_registry_version=m2_registry_version,
            m2_registry_hash=m2_registry_hash,
            aggregation_contract_id=AGGREGATION_CONTRACT_ID,
        )

    def build_population(
        self,
        *,
        records: tuple[PriorityScoreRecord, ...],
        scope: PopulationScope,
    ) -> PriorityPopulation:
        return build_population(tuple(records), scope)

    def rank_nodes(
        self,
        *,
        population: PriorityPopulation,
        representation: PriorityRepresentation,
    ) -> PriorityOrdering:
        rows = []
        for record in population.records:
            score = (
                record.delay_mean_cs
                if representation is PriorityRepresentation.DELAY
                else record.aggregate_score
            )
            if score is None or not isfinite(float(score)):
                raise ContractError("M4_ORDERING_SCORE_INVALID")
            rows.append((record.decision_node_id, float(score)))
        rows.sort(key=lambda item: (-item[1], item[0]))
        return PriorityOrdering(
            population_digest=population.population_digest,
            representation=representation,
            entries=tuple((node_id, score, rank) for rank, (node_id, score) in enumerate(rows, 1)),
            excluded=population.excluded,
            provenance=("M4_PRIORITY_STABLE_DESCENDING_SCORE_NODE_ID_ASCENDING",),
        )

    def build_shortlist(
        self,
        *,
        ordering: PriorityOrdering,
        capacity: ScreeningCapacity,
    ) -> ScreeningShortlist:
        return build_shortlist(ordering, capacity)

    def compare_priority_representations(
        self,
        *,
        delay: PriorityOrdering,
        consequence: PriorityOrdering,
        capacity: ScreeningCapacity,
    ) -> PriorityAlignmentRecord:
        return compare_priority_representations(delay, consequence, capacity)


__all__ = ["M4Service"]
