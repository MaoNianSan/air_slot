from __future__ import annotations

from model.M2.contracts import (
    AvailableComponentSumDiagnostic,
    ComponentVector,
    FormalEstimandValue,
    M2ScenarioInput,
    M2ScientificContext,
    ScenarioConsequenceDistribution,
    ScenarioConsequence,
)
from model.M2.consequences.engine import native_quantities
from model.common.cu_normalization import CUNormalizationStatus
from model.common.enums import SupportState
from model.common.estimand import FormalEstimandStatus, ScopeStatus


class M2Mapper:
    def __init__(self, registry, consequence_scope):
        self.registry = registry
        self.consequence_scope = consequence_scope
        if registry.registry_id != consequence_scope.cu_normalization_registry_id:
            raise ValueError("M2_SCOPE_CU_NORMALIZATION_REGISTRY_MISMATCH")

    def map_m1_scenarios(
        self,
        scenarios: tuple[M2ScenarioInput, ...],
        context: M2ScientificContext,
    ) -> tuple[ScenarioConsequence, ...]:
        """Principal V2 path over strict M1 scenario envelopes."""
        if not scenarios:
            return ()
        if any(not isinstance(item, M2ScenarioInput) for item in scenarios):
            raise TypeError("M2_V2_REQUIRES_TYPED_M1_SCENARIO_INPUT")
        identities = {(item.decision_node_id, item.scenario_id) for item in scenarios}
        if len(identities) != len(scenarios):
            raise ValueError("M2_DUPLICATE_SCENARIO_ID_WITHIN_NODE")
        by_node: dict[tuple[str, str], float] = {}
        for item in scenarios:
            node_key = (item.episode_id, item.decision_node_id)
            by_node[node_key] = by_node.get(node_key, 0.0) + item.scenario_weight
        if any(abs(total - 1.0) > 1e-6 for total in by_node.values()):
            raise ValueError("M2_SCENARIO_WEIGHTS_MUST_SUM_TO_ONE_PER_NODE")
        return self._map_scenarios(scenarios, context)

    def map_m1_distribution(
        self,
        scenarios: tuple[M2ScenarioInput, ...],
        context: M2ScientificContext,
    ) -> ScenarioConsequenceDistribution:
        """Return the immutable, unfiltered scenario distribution for one node."""
        return ScenarioConsequenceDistribution(
            consequences=self.map_m1_scenarios(scenarios, context)
        )

    def map_scenarios(self, scenarios, context: M2ScientificContext):
        """Historical dictionary compatibility path.

        New scientific code must call :meth:`map_m1_scenarios`; this path is
        retained so historical V1 consumers remain reproducible.
        """
        return self._map_scenarios(scenarios, context)

    def _map_scenarios(self, scenarios, context: M2ScientificContext):
        outputs = []
        included = self.consequence_scope.included_components
        for scenario in scenarios:
            rows = tuple(
                self.registry.value(quantity)
                for quantity in native_quantities(scenario, context)
            )
            vector = ComponentVector(rows=rows)
            valued = tuple(row for row in rows if row.constructed_value_cu is not None)
            diagnostic = AvailableComponentSumDiagnostic(
                value_cu=(
                    sum(row.constructed_value_cu for row in valued) if valued else None
                ),
                included_components=tuple(row.component_id for row in valued),
                status=("DIAGNOSTIC_AVAILABLE" if valued else "NO_VALUED_COMPONENTS"),
            )
            selected = tuple(row for row in rows if row.component_id in included)
            if self.consequence_scope.scope_status is not ScopeStatus.FORMAL_READY:
                status = FormalEstimandStatus.FORMAL_AGGREGATE_UNRESOLVED
                value = None
                reason = "CONSEQUENCE_SCOPE_NOT_FORMAL_READY"
            elif any(row.support_state is SupportState.ABSTAIN for row in selected):
                status = FormalEstimandStatus.FORMAL_AGGREGATE_UNRESOLVED
                value = None
                reason = "INCLUDED_COMPONENT_ABSTAIN"
            elif any(
                row.cu_status is not CUNormalizationStatus.CU_FROZEN for row in selected
            ):
                status = FormalEstimandStatus.VALUATION_NOT_FROZEN
                value = None
                reason = "INCLUDED_COMPONENT_CU_NORMALIZATION_NOT_FROZEN"
            else:
                status = FormalEstimandStatus.FORMAL_AVAILABLE
                value = sum(row.constructed_value_cu for row in selected)
                reason = None
            formal = FormalEstimandValue(
                value_cu=value,
                status=status,
                estimand_id=self.consequence_scope.estimand_id,
                estimand_version=self.consequence_scope.estimand_version,
                scope_hash=self.consequence_scope.scope_hash,
                cu_normalization_registry_id=self.consequence_scope.cu_normalization_registry_id,
                aggregation_rule_id=self.consequence_scope.aggregation_rule_id,
                included_components=included,
                reason_code=reason,
            )
            outputs.append(
                ScenarioConsequence(
                    episode_id=(
                        scenario.episode_id
                        if isinstance(scenario, M2ScenarioInput)
                        else scenario.get("episode_id", "LEGACY_UNSPECIFIED")
                    ),
                    decision_node_id=(
                        scenario.decision_node_id
                        if isinstance(scenario, M2ScenarioInput)
                        else scenario["decision_node_id"]
                    ),
                    scenario_id=(
                        scenario.scenario_id
                        if isinstance(scenario, M2ScenarioInput)
                        else scenario["scenario_id"]
                    ),
                    scenario_weight=(
                        scenario.scenario_weight
                        if isinstance(scenario, M2ScenarioInput)
                        else scenario["scenario_weight"]
                    ),
                    consequence_scope=self.consequence_scope,
                    component_vector=vector,
                    available_component_sum_diagnostic=diagnostic,
                    formal_estimand_value=formal,
                    pre_lineage=(
                        scenario.pre_lineage
                        if isinstance(scenario, M2ScenarioInput)
                        else ()
                    ),
                    reference_lineage=(
                        scenario.reference_lineage
                        if isinstance(scenario, M2ScenarioInput)
                        else ()
                    ),
                    m1_scenario_seed_key=(
                        scenario.m1_scenario_seed_key
                        if isinstance(scenario, M2ScenarioInput)
                        else None
                    ),
                )
            )
        return tuple(outputs)
