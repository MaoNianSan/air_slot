# Exp2 Readiness

Scientific contract: determine how much information structure is sufficient while reusing the same frozen M1 scenario artifact.

## Exp2A: `COLLAPSED`, `MARGINAL`, `JOINT`

| Variant | Reusable current capability | Gap | Status |
| --- | --- | --- | --- |
| `JOINT` | immutable source hash and q=0 identity behavior | no typed V2 transform/artifact contract | `REUSE_WITH_ADAPTATION` |
| `COLLAPSED` | `point_collapse` selects one coherent weighted joint medoid | operates on legacy `r_ib_minutes/r_ob_minutes/t_tx_minutes`; does not accept `M1V2Scenario` | `REUSE_WITH_ADAPTATION` |
| `MARGINAL` | `corrupt_scenario_lineage(q=1)` preserves target marginals while breaking within-scenario association | legacy field set, partial-shuffle protocol, and old variant name do not define the new marginal representation | `REUSE_WITH_ADAPTATION` |

The current algorithmic pieces can support the new contrast, but only after they are converted to the current M1 V2 scenario schema and wrapped by an immutable source-artifact contract. All three variants must carry the same source M1 artifact hash, node set, scenario weights, scenario count, and M1 model/calibration identity. The variant transform must not train or load a different model.

The existing `Exp2Runner` only names P-F/P-C/D-F/D-C/LINEAGE_CORRUPTION and consumes precomputed metrics; it does not run any transformation. It is therefore a rewrite target.

## Exp2B: `SCALAR`, `CHANNEL`, `COMPONENT`

| Resolution | Current capability | Status |
| --- | --- | --- |
| `COMPONENT` | `ScenarioConsequence.component_vector.rows` exposes seven typed component values/support/lineage | `ALIGNED` interface |
| `CHANNEL` | component rows carry aspect labels `Flight`, `Passenger`, `Resource` | `PARTIAL`; no channel aggregation adapter or support rule |
| `SCALAR` | `FormalEstimandValue` and M2 summaries provide an all-included-component aggregate when formally available | `BLOCKED` for current V2 seven-component formal aggregate |

Experiment code must aggregate M2 output; it must not reproduce `model/M2/drivers.py` or CU normalization arithmetic. Each resolution must retain scenario identity and weights. A channel/scalar value is unavailable if its declared required components are unsupported; missing components cannot be treated as zero.

## Downstream decision comparison

The existing distortion metrics are reusable only after the action-value mapping is supplied by the current chain:

- M2 supplies baseline `C0_CU`;
- M3 supplies action-conditioned `Ca_CU`;
- M4 supplies supported or conditional risk values and ranking authority.

The old Exp234 executor instead computes five-component raw-CU action maps with legacy M3 response code. Those values cannot be used as the reference evaluator for the new Exp2.

## Tests required

- every variant has the identical source M1 artifact hash and no training event;
- `JOINT` is byte/identity preserving;
- `COLLAPSED` selects one complete coherent V2 scenario and preserves source lineage;
- `MARGINAL` preserves each declared marginal multiset/weighted distribution and changes only association;
- scenario weights remain valid and normalized;
- COMPONENT -> CHANNEL -> SCALAR aggregation uses one frozen mapping and explicit support propagation;
- no dictionary compatibility M2 API, manual CU arithmetic, legacy M3 response, or raw-CU ranking is imported;
- decision/risk metrics abstain when M3/M4 are blocked.

`EXP2_STATUS = PARTIAL_INFRASTRUCTURE_BLOCKED_BY_TYPED_MIGRATION_AND_SCIENTIFIC_GATES`

