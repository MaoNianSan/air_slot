# Model Validation

Validation is model-contract validation. It does not authorize an experiment,
paper-result generation, Final Test access, or data writes.

## Required checks

PRE tests verify cutoff legality, future-information rejection, typed support,
lineage, schedule publication, and preservation of proxy/reference boundaries.

M1 tests verify primitive target semantics, factual state contraction, scenario
identity and weights, conditional dependency, no future leakage, and typed
output parity. Service tests additionally verify decision/cutoff/roll/model
metadata, formal horizon versus evaluation lead-time separation, and that direct
queries do not reset the scheduled-update timeline. Calibration tests verify
the July 2019 split and head-specific calibration contract without re-fitting
or reusing superseded H32 artifacts.

M2 tests verify fixed seven-component order, pure consequence definitions,
support propagation, no zero-fill, CU lineage, active-registry hash integrity,
T-100 H1 and DB1B Q1/Q2 fit boundaries, fail-closed TripBreak schema handling,
component-specific passenger abstention, context-sourced thresholds, and
separation of current quantity definitions from frozen-artifact formula
provenance. The active registry is `M2_DATA2_FORMAL_CU_V4`; all seven positive
Train medians are required.

M3 tests verify:

- every template has one instantiation record per node;
- missing required mathematical parameters produce a retained `NOT_FORMED`
  record with no candidate;
- a formed instance can independently have factual `TRUE`, `FALSE`, or
  `UNKNOWN`;
- A21 schedule-object presence remains `CONTRACT_UNDERSPECIFIED`;
- A71/A72 capability labels cannot create contemporaneous authority;
- response support is distinct from factual state;
- M3 preserves scenario identity and action-conditioned CU provenance.

M4 tests verify:

- absent or unfrozen comparison scope yields `COMPARISON_SCOPE_NOT_FROZEN`;
- frozen subset scope maps only its `K_cmp` components while preserving all
  seven ontology rows;
- common-basis mismatch rejection includes scope identity/component mismatch;
- finite, complete numerical mapping requirements for `chi_num`;
- factual `UNKNOWN` plus complete numerical inputs gives
  `chi_num=DEFINED` and `CONDITIONAL_INPUTS`;
- factual `UNKNOWN` plus incomplete numerical inputs gives
  `chi_num=UNDEFINED` and `NOT_COMPARABLE`;
- response and opportunity states remain independent metadata;
- selection state is `UNIMPLEMENTED` and the retired selector API rejects.

Registry tests verify the separate `scientific_status` and
`implementation_status` enums, require every frozen active parameter to be
`MATCH`, load the active RMB/risk registries, and reject superseded values as
runtime authority.

## Closure command

```text
python -m pytest -q tests/pre tests/m1 tests/m2 tests/m3 tests/m4 tests/contract tests/integration
```

The model-level closure result is reported with the current closure handoff.
Tests establish implementation/contract behavior only. Unresolved factual
authority, empirical response evidence, opportunity evidence, and operational
selection semantics remain explicit scientific boundaries; the CU rule, RMB
BASE mapping, and M4 risk policy are frozen model parameters.
