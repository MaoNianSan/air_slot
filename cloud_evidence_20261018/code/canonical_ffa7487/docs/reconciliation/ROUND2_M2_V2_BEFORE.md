# Round 2 M2 V2 Before Audit

Audit baseline: `c4670266b4947da13952e8c951f1c97ce1379322`  
Focused baseline: `32 passed, 1 skipped` (`tests/m2`, named reconciliation tests, and the scientific-chain smoke test).

## Boundary finding

The current M2 is already a scenario-to-consequence mapper and does not train a second delay model. It exposes the seven manuscript component identifiers and separates `NativeQuantity` from `ConsequenceRow.constructed_value_cu`. The implementation is nevertheless not yet an M2 V2 closure:

- the runtime accepts untyped dictionaries rather than a frozen M1-scenario boundary carrying PRE and reference lineage;
- output drops `episode_id`, PRE lineage, reference lineage, and the baseline/action state;
- the formal scope remains the historical five-component `M2_DATA2_FORMAL_CU_V1`;
- downstream exposure is an airport-level training median, not a node-specific operational exposure;
- component records have evidence/support but no required `source_type`;
- no distribution interface exposes weighted mean, variance, CVaR, or tail probability;
- `P_itinerary` and `P_service` correctly abstain, but that limitation is not frozen as an explicit V2 support matrix.

## Component audit before V2

| Component | Operational meaning | Current inputs | Current native quantity | Current source/provenance | CU transformation | Uncertainty source | Before support state |
|---|---|---|---|---|---|---|---|
| `F_continuity` | aircraft-turn continuity pressure | M1 `R_IB`; turnaround reference | positive turnaround compression minutes | M1 scenario plus train-frozen airport turnaround reference | registry normalization if present | M1 scenario and reference fallback | reference-supported |
| `F_execution` | inability to execute off-block on time | M1 `D_OB` | off-block delay minutes | M1 scenario | registry normalization if present | M1 scenario | available |
| `F_propagation` | downstream operational propagation | M1 `D_TO`; `E_down` | delay-exposure minutes | M1 scenario plus airport-median exposure | registry normalization if present | M1 scenario and exposure reference | available but exposure design insufficient |
| `P_time` | passenger time exposure | M1 `D_TO`; route passenger reference | passenger-minutes | M1 scenario plus train-frozen aggregate passenger proxy | registry normalization if present | M1 scenario and route-reference fallback | reference-based proxy |
| `P_itinerary` | disrupted passenger itineraries | disruption-event evidence | event count | no qualifying itinerary/recovery evidence | none while abstaining | unavailable | `ABSTAIN` |
| `P_service` | service-policy consequence | M1 `D_TO`; service threshold | threshold-event count | no frozen carrier/service policy | none while abstaining | unavailable | `ABSTAIN` |
| `R_operating` | excess operating resource exposure | M1 `D_TX` | excess taxi minutes | M1 scenario | registry normalization if present | M1 scenario | available |

## Data capability classification

The repository contains a local, train-frozen Data2 passenger aggregate reference backed by the configured passenger source. That supports a route-level passenger-exposure proxy for `P_time` only. It does **not** identify itinerary recovery, compensation, crew disruption, gate-resource cost, or airline internal cost. Consequently:

- `P_time`: `REFERENCE_BASED`, with reference and freeze lineage required;
- `P_itinerary`: `UNSUPPORTED/ABSTAIN` until an itinerary-capable source or explicitly approved literature proxy is frozen;
- `P_service`: `UNSUPPORTED/ABSTAIN` until a scoped operational rule or literature reference is frozen;
- financial, crew, gate, and internal-cost quantities: outside M2 V2 and not fabricated.

## Required V2 changes

1. Add a strict M1 scenario envelope that copies, validates, and preserves `T_IB_A00`, `R_IB`, `D_OB`, `D_TX`, `D_TO`, weights, PRE lineage, and reference lineage without reconstructing state.
2. Require source type and provenance on every native component.
3. Add a node-specific exposure resolver with explicit `same-aircraft -> same-route -> airport -> global` fallbacks, support level, reference source, and confidence.
4. Freeze the exact seven-component ontology while leaving the formal seven-component aggregate unresolved until every included native quantity and CU normalization is scientifically frozen.
5. Mark all M2 output as baseline `C^{0,CU}`; action response remains downstream of this native mapping.
6. Add scenario-distribution summaries without collapsing scenarios inside the mapper.

No M1, PRE, M3, M4, experiment, or manuscript source change is authorized by this tranche.
