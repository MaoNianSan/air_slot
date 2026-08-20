# Round 2 M2 V2 Scientific Design

Design baseline: `c4670266b4947da13952e8c951f1c97ce1379322`  
Design registry: `registries/m2_v2_design.json` (`M2_OPERATIONAL_CONSEQUENCE_V2@2.0.0`, interface `2.1.0`)

## Scientific role and boundary

M2 is an operational-consequence representation, not a delay predictor and not a monetary model. Its typed chain is:

\[
\text{M1 scenario }s
\rightarrow q_k(s)\text{ (native consequence)}
\rightarrow C_k^{0,CU}(s)=q_k(s)/c_k^{CU}
\]

where `c_k^CU` must be train-frozen or reference-frozen. Monetary mapping `L_k^m=f_k^m(C_k^{CU})` remains an M4 responsibility and is neither imported nor parameterized by the M2 mapper.

The principal V2 boundary is `M2ScenarioInput.from_m1(...)` followed by `M2Mapper.map_m1_scenarios(...)`. It copies `episode_id`, `decision_node_id`, `scenario_id`, `scenario_weight`, `T_IB_A00`, `R_IB`, `D_OB`, `D_TX`, `D_TO`, M1 seed lineage, PRE lineage, and reference lineage. The model rejects extra fields, validates `D_TO = D_OB + D_TX`, and never reconstructs any of these quantities. The dictionary API remains only for historical V1 reproducibility.

## Why seven components

The seven components are not seven arbitrary weights. They partition distinct mechanisms across three consequence aspects while keeping native units visible:

| Component | Aspect | Operational mechanism | Native definition | Source type | Current V2 support |
|---|---|---|---|---|---|
| `F_continuity` | Flight | loss of aircraft-turn continuity margin | `max(0, R_IB - turnaround_reference)` minutes | `HYBRID` | reference-based |
| `F_execution` | Flight | off-block execution delay | `D_OB` minutes | `SCENARIO_ASSUMPTION` | M1-available |
| `F_propagation` | Flight | delay propagated through exposed successor operations | `D_TO * E_down(node)` exposure-minutes | `HYBRID` | hierarchical reference |
| `P_time` | Passenger | aggregate passenger time exposure | `V_OD_reference * D_TO` passenger-minutes | `HYBRID` | reference-based domain proxy |
| `P_itinerary` | Passenger | disrupted itineraries requiring recovery | supported itinerary-event count | `DATA` | `ABSTAIN` |
| `P_service` | Passenger | scoped service-policy threshold event | policy-threshold event count | `OPERATIONAL_RULE` | `ABSTAIN` |
| `R_operating` | Resource | excess taxi operating-resource exposure | `D_TX` excess-taxi-minutes | `SCENARIO_ASSUMPTION` | M1-available |

`F_*` describes flight-operation continuity, execution, and propagation. `P_*` separates passenger time exposure from itinerary recovery and service-policy effects so a route-volume proxy cannot masquerade as either of the latter. `R_operating` retains a nonfinancial operational-resource channel. Crew cost, gate cost, compensation, and airline internal cost are not inferred.

Every native row carries `support_state`, `evidence_class`, `source_type`, and provenance. Unsupported evidence is contractually forced to null/`ABSTAIN`; it cannot become numeric zero.

## Node-specific downstream exposure

`resolve_node_specific_exposure` freezes the following ordered hierarchy:

1. `SAME_AIRCRAFT_SUCCESSOR_CHAIN`: decision-visible scheduled successor count within 360 minutes; a complete snapshot makes a count of zero a supported zero (`HIGH` confidence).
2. `SAME_ROUTE_PROPAGATION`: an explicitly supplied frozen route reference (`MEDIUM` confidence).
3. `AIRPORT_REFERENCE`: the historical train-frozen airport cell used only as a named fallback (`LOW` confidence).
4. `GLOBAL_REFERENCE`: the train-frozen global value used only as a named fallback (`LOW` confidence).

Each result records support level, reference source, confidence, horizon, and provenance. A schedule record published after the information cutoff is rejected. Realized departure/arrival fields are not part of the accepted schedule schema and are rejected as extra fields. If no level is supported, exposure is null/`ABSTAIN`; the airport median is never silently substituted.

## Passenger capability and reproducibility

Current-workspace inspection found seven local DB1B files under the configured Data2 location and the train-frozen `DATA2_PASSENGER_REFERENCE_H1_TRAIN_FROZEN_V1.json` artifact. This is a capability statement, not a claim that DB1B observes recovery behavior. The frozen aggregate route reference is scoped to `P_time` only.

- `P_time`: available as a reference-based domain proxy, with reference/freeze lineage and assumption scope `ROUTE_AGGREGATE_PASSENGER_EXPOSURE_FOR_P_TIME_ONLY`.
- `P_itinerary`: unsupported because no itinerary-recovery outcome is frozen.
- `P_service`: unsupported because no scoped service/compensation operational rule or literature reference is frozen.
- no literature proxy is activated in V2; therefore there is no invented citation or assumption scope.

## CU, uncertainty, and action separation

Native quantities and CU are distinct typed objects. `M2CUNormalizationAdapter` applies only `q_k / c_k^CU` from a typed frozen registry and records registry digest, rule/version, normalization parameter, scale freeze ID, and reference period in a version-sensitive CU artifact identity. Changing an RMB or other monetary mapping cannot change M2 output because monetary mappings are not M2 inputs.

The seven-component ontology and all-seven aggregation rule are frozen by `build_m2_v2_scope()`. The scope is intentionally `FORMAL_AGGREGATE_UNRESOLVED`: no V2 CU scale values were invented, and two native components abstain. The immutable historical `M2_DATA2_FORMAL_CU_V1` five-component registry remains untouched.

M2 returns one `ScenarioConsequence` per M1 scenario and does not collapse the distribution. `ScenarioConsequenceDistribution` packages all scenario IDs, weights, and consequence artifact identities for a node; no top-k or point-only interface exists in the formal path. `summarize_formal_consequence` can compute weighted mean, variance, upper-tail CVaR, and threshold-tail probability only when every scenario has an available formal consequence.

All mapper outputs are baseline `C^{0,CU}` with `action_id=None` and `action_adjustments_applied=False`. The contract-only `model/M3/m2_action_interface.py` accepts that immutable baseline and defines the future `C^{a,CU}` result shape. It contains no action logic and rejects native-quantity fields in action-conditioned CU records. Action effects are not native consequences and cannot enter this M2 V2 mapper.

## Human decisions still required

1. Freeze V2 train/reference normalization parameters `c_k^CU` and their registry hash after the native definitions are accepted.
2. Decide whether to acquire/freeze itinerary-capable evidence or approve a specifically cited literature proxy for `P_itinerary`.
3. Decide and freeze a scoped service-policy/reference rule for `P_service`, or retain permanent abstention.
4. Decide whether a train-frozen same-route propagation reference should be built. Until then the hierarchy moves directly from unavailable same-route evidence to the named airport/global fallbacks.

These gates do not block the typed M2 V2 design or baseline mapping, but they block a formal all-seven CU aggregate and any authoritative downstream ranking.

## Implementation and verification map

- contracts and lineage: `model/M2/contracts.py`
- native mechanisms/source classification: `model/M2/drivers.py`
- node exposure hierarchy: `model/M2/exposure.py`
- V2 context and unresolved seven scope: `model/M2/context.py`
- baseline mapper: `model/M2/mapper.py`
- native-to-CU adapter: `model/M2/valuation.py`
- mean/variance/CVaR/tail interface: `model/M2/summary.py`
- M3 contract-only boundary: `model/M3/m2_action_interface.py`
- design tests: `tests/m2/test_v2_design_alignment.py`, `tests/m2/test_interface_closure.py`
- M3 boundary tests: `tests/m3/test_m2_action_interface.py`
- integration tests: `tests/integration/test_m1_m2_interface_closure.py`

No M1, PRE, M4, Exp1-4, paper experiment, or TeX file was changed. M3 changed only by adding and exporting the contract-only M2/action boundary; no catalog, response, instantiation, or action logic changed.
