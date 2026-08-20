# Exp2 Artifact Gate Design V1

## Purpose

The artifact layer under `exp/exp2/artifacts/` defines the minimum content-addressed contracts required before a future Exp2 invocation. It prepares and validates artifact identities; it does not create scientific values, select parameters, execute M1-M4, or run Exp2.

The gate is fail-closed and has no fallback path.

## Artifact hierarchy

```text
M1 loaded scenario artifact
 |
M2 loaded seven-component consequence artifact
 |
M3 Exp2ActionManifest
 |
M3 ordered Exp2ResponseBundle set
 |
M4 Exp2MonetaryMappingBundle
 |
M4 Exp2RiskPolicyBundle
 |
Exp2ExecutionGate
```

M1 and M2 enter the new gate only after the existing execution loader has validated their typed content, provenance, and hashes. The new contracts add the M3/M4 detail missing from the earlier summary payloads.

## M3 action manifest

`Exp2ActionManifest` freezes one dataset/split/cohort action set. It requires:

- an explicit manifest/schema identity;
- a cohort SHA-256;
- `A00` first;
- at least one non-A00 action;
- unique non-A00 IDs in deterministic lexical order;
- exact action- and response-registry IDs and hashes.

There is intentionally no `variant_id` field. The same manifest must be bound to every reference/comparison variant; action selection cannot depend on variant outputs.

The computed `manifest_hash` is content-derived. The full 23-action structural catalog is not required by this schema.

## M3 response bundle

One `Exp2ResponseBundle` is required for every manifest action, in manifest order. It records the response rule, support class, source type/reference, parameter version, freeze ID, and a content-derived rule hash.

The schema admits the four explicit support states:

- `SUPPORTED`;
- `REFERENCE_BASED`;
- `SCENARIO_ASSUMPTION`;
- `ABSTAIN`.

It never infers or upgrades support. Scenario support must declare a scenario source, and scenario/expert sources cannot be labelled `SUPPORTED`.

For the currently frozen Exp2 protocol, every non-A00 action must be `SCENARIO_ASSUMPTION`. `ABSTAIN`, missing responses, changed order, or a different action set returns `BLOCKED_UNSUPPORTED_RESPONSE`.

## M4 monetary mapping bundle

`Exp2MonetaryMappingBundle` requires the exact canonical seven-component order and complete component-keyed mapping-function/source references. The bundle hash covers every field other than the hash itself.

The schema rejects:

- `TEST_ONLY` support;
- missing or extra component coverage;
- empty component source coverage;
- any declared fallback mapping;
- a mismatched content hash.

The only permitted interpretation for this protocol is `CONSTRUCTED_INTERNAL_LOSS_UNIT`. This is a scope rule, not a numerical mapping choice. The values may not be called RMB, real costs, savings, or benefits.

## M4 risk-policy bundle

`Exp2RiskPolicyBundle` requires an explicit tail policy, CVaR policy, version, support status, content hash, and explicit numerical parameters. It has no alpha or coefficient defaults. The schema requires the named alpha, expected-loss coefficient, and CVaR coefficient, validates the implemented ranges/sum contract, and rejects test-only or implicit default/fallback policy declarations.

The schema validates supplied values but does not choose them. Supplying and scientifically approving the values remains a human gate.

## Execution gate statuses

`Exp2ExecutionGate` returns exactly one of:

| Status | Meaning |
| --- | --- |
| `READY` | All six artifact roles are present and satisfy this structural/frozen-status contract |
| `BLOCKED_MISSING_ARTIFACT` | M1/M2 loader-validated content or another required bundle is absent |
| `BLOCKED_UNSUPPORTED_MAPPING` | M4 mapping/policy is invalid, incomplete, test-only, fallback, hash-invalid, or not frozen |
| `BLOCKED_UNSUPPORTED_RESPONSE` | Action manifest or response coverage/order/support violates the frozen scenario protocol |

`READY` is an engineering execution-gate state. It is not scientific authority, run authorization, or a paper-result status.

## Why Exp2 remains conditional and non-authoritative

The current M3 registry declares non-A00 responses as `PURE_SCENARIO` and explicitly sets `formal_support_upgrade=false`. The new schema preserves those responses as `SCENARIO_ASSUMPTION`; it does not transform them into observed effectiveness.

Consequently, even with a complete frozen internal-unit mapping and risk policy:

- numerical residual-risk values are conditional on the response assumptions;
- action disagreement and ranking change measure representation sensitivity only;
- the result cannot become an optimal-action or best-policy recommendation;
- the result cannot establish a causal action effect;
- an individual deterministic A00 identity does not upgrade the multi-action comparison;
- the result must remain `CONDITIONAL_NON_AUTHORITATIVE`.

Authoritative ranking would require a different, explicitly approved scientific protocol and supported M3 response evidence.

## No-fallback and identity rules

- Missing artifacts remain missing.
- Missing action responses remain unsupported.
- Missing component mappings remain blocked.
- No null is converted to zero.
- No risk parameter is defaulted.
- No alpha is chosen automatically.
- No action, mapping, or policy varies by Exp2 representation.
- Every response, mapping, and policy hash is verified from canonical content.
- Existing M1/M2 loader checks remain mandatory upstream of this gate.

## Current readiness

The schemas and validator can be engineering-tested with explicit test fixtures. The repository does not currently contain the scientific M3/M4 bundle values required for a real gate evaluation.

```text
ARTIFACT_SCHEMA_IMPLEMENTATION = READY
CONCRETE_M3_ARTIFACT = BLOCKED
CONCRETE_M4_ARTIFACT = BLOCKED
EXP2_EXECUTION_GATE = BLOCKED_MISSING_SCIENTIFIC_ARTIFACTS
EXP2_RUN = NOT_AUTHORIZED
```
