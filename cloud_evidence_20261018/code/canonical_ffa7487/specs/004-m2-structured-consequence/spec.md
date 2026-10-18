# Feature Specification: M2 Structured Consequence

## User Scenarios

1. Map every M1 scenario deterministically to seven fixed native consequence components.
2. Apply versioned valuation rules to produce Constructed Units while preserving evidence/support.
3. Publish long-form scenario consequences and summaries without mixing formal and realized evaluation objects.

## Requirements

- Fixed components: F_continuity, F_execution, F_propagation, P_time, P_itinerary, P_service, R_operating.
- Each row retains scenario ID, native value/unit/driver, valuation rule/version, CU, evidence, support and provenance.
- Missing critical input yields null/ABSTAIN, never zero; all seven columns remain present.
- Formal total is null when critical scope is unsupported; available-component sum may remain diagnostic.
- Formal mapping reads only M1 scenarios, PRE context and frozen references. Realized reconstruction is a separate evaluation interface.
- Scenario identity/weight is preserved; M2 performs no sampling or prediction.
- CU is a constructed decision-value scale, never labeled audited/causal/true monetary cost.

## Success Criteria

Seven-component shape, deterministic scenario preservation, support propagation, valuation identity, total rules and formal/evaluation separation tests pass.
