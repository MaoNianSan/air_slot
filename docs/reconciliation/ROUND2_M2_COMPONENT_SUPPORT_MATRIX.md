# Round 2 M2 Component Support Matrix

Interface HEAD baseline: `cbc4b137eb5de51a54095d77a177154e14873d2b`

The formal M2 output is the ordered vector

\[
C^{0,CU}(s)=(C_1^{0,CU}(s),\ldots,C_7^{0,CU}(s)).
\]

Vector membership does not imply numeric support. `ABSTAIN` components remain present with null native and CU quantities.

| Component | Meaning | Native quantity | CU mapping | Support level | Data/reference source | Freeze status | Classification |
|---|---|---|---|---|---|---|---|
| `F_continuity` | aircraft-turn continuity pressure | `max(0, R_IB - turnaround_reference)` minutes | native / component frozen scale | train-frozen airport/reference fallback | M1 scenario + turnaround reference | native rule frozen; V2 CU scale pending | `REFERENCE_BASED` |
| `F_execution` | off-block execution consequence | `D_OB` minutes | native / component frozen scale | scenario-specific | M1 scenario | native rule frozen; V2 CU scale pending | `SUPPORTED` |
| `F_propagation` | downstream operational propagation | `D_TO * E_down(node)` exposure-minutes | native / component frozen scale | same-aircraft > same-route > airport > global | M1 scenario + versioned exposure resolver | hierarchy frozen; same-route reference and V2 CU scale pending | `REFERENCE_BASED` |
| `P_time` | aggregate passenger time exposure | route passenger reference × `D_TO` passenger-minutes | native / component frozen scale | route-reference proxy | existing train-frozen aggregate passenger reference | reference frozen; V2 CU scale pending | `PROXY` |
| `P_itinerary` | itinerary disruption/recovery events | unavailable event count | no CU while native abstains | none | no qualifying itinerary-recovery evidence | not frozen | `ABSTAIN` |
| `P_service` | service-policy consequence events | unavailable threshold-event count | no CU while native abstains | none | no frozen scoped service-policy rule | not frozen | `ABSTAIN` |
| `R_operating` | excess taxi operating exposure | `D_TX` excess-taxi-minutes | native / component frozen scale | scenario-specific | M1 scenario | native rule frozen; V2 CU scale pending | `SUPPORTED` |

Every row now carries `scenario_id`, `scenario_weight`, `component_id`, native quantity/unit, a distinct typed CU quantity, support/evidence/source type, `reference_source`, typed `reference_lineage`, confidence, native artifact ID, and (when frozen) CU artifact ID.

The all-seven scalar aggregate remains unresolved. M2 does not drop, zero-fill, renormalize, or monetarily weight abstaining components.
