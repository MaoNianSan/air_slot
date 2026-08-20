# Exp2 Readiness

Scientific contract: determine how much information structure is sufficient while reusing the same frozen M1 scenario artifact.

## Exp2A: `COLLAPSED`, `MARGINAL`, `JOINT`

| Variant | Reusable current capability | Gap | Status |
| --- | --- | --- | --- |
| `JOINT` | `ScenarioRepresentationAdapter` preserves the typed V2 source hash, identity, weights, joint values, and lineage | scientific downstream artifacts remain blocked | `CODE_READY` |
| `COLLAPSED` | adapter returns one weighted expected `D_OB`/`D_TX`/`D_TO` state with complete source lineage | scientific downstream artifacts remain blocked | `CODE_READY` |
| `MARGINAL` | adapter preserves every weighted marginal and records field-source identity while breaking association | nontrivial exact permutation requires equal-weight strata | `CODE_READY` |

The V2 experiment-layer conversion and immutable source-artifact guard are now implemented in `exp/exp2/representation.py`. All three variants carry the same source M1 artifact hash and model/artifact identity. `JOINT` and `MARGINAL` preserve scenario count and weights; `COLLAPSED` intentionally reduces the distribution to one weight-one summary. No transform trains or loads a different model.

`Exp2Runner.execute` now uses the typed `Exp2Protocol`. The old arbitrary precomputed-metric route is rejected outside smoke mode.

## Exp2B: `SCALAR`, `CHANNEL`, `COMPONENT`

| Resolution | Current capability | Status |
| --- | --- | --- |
| `COMPONENT` | seven typed component values/support/lineage are preserved | `CODE_READY` |
| `CHANNEL` | fixed `Flight`/`Passenger`/`Resource` aggregation with complete-support propagation | `CODE_READY`; scientific downstream blocked |
| `SCALAR` | experiment-layer all-component aggregate with complete-support propagation | `CODE_READY_AS_REPRESENTATION`; not a new formal M2 estimand |

The implementation aggregates only M2-emitted CU output; it does not reproduce `model/M2/drivers.py` or CU normalization arithmetic. Each resolution retains scenario identity and weights. A channel/scalar value is unavailable if any required component is unsupported; missing components are never treated as zero.

## Downstream decision comparison

The typed common evaluator is implemented but produces supported decision/risk metrics only after the action-value mapping is supplied by the current chain:

- M2 supplies baseline `C0_CU`;
- M3 supplies action-conditioned `Ca_CU`;
- M4 supplies supported or conditional risk values and ranking authority.

`Exp2Protocol` requires current typed M3 and M4 envelopes and rejects M4 bypass, action-set changes, response-rule changes, and mapping/policy changes. The old Exp234 five-component raw-CU action maps remain invalid for this Exp2.

## Tests required

- every variant has the identical source M1 artifact hash and no training event;
- `JOINT` is byte/identity preserving;
- `COLLAPSED` selects one complete coherent V2 scenario and preserves source lineage;
- `MARGINAL` preserves each declared marginal multiset/weighted distribution and changes only association;
- scenario weights remain valid and normalized;
- COMPONENT -> CHANNEL -> SCALAR aggregation uses one frozen mapping and explicit support propagation;
- no dictionary compatibility M2 API, manual CU arithmetic, legacy M3 response, or raw-CU ranking is imported;
- decision/risk metrics abstain when M3/M4 are blocked.

`EXP2_STATUS = CODE_READY_SCIENTIFIC_EXECUTION_BLOCKED_BY_M3_M4_FREEZES`
