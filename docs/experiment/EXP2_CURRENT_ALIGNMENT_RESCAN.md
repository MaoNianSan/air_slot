# Exp2 Current Alignment Rescan

## Rescan identity and scope

Rescan date: 2026-08-20

Repository state before this task made any modification:

```text
HEAD = 9ba4835590718265110d6b5d99be720a0fd712ad
LAST_COMMIT = 9ba4835 feat(exp2): Implement execution artifacts and downstream binding for Exp2
PREEXISTING_WORKTREE =
  ?? docs/experiment/EXP2_SCIENTIFIC_EXECUTION_PROTOCOL.md
  ?? docs/experiment/M3_M4_EXP_EXECUTION_GATE_AUDIT.md
```

Inspected read-only before implementation:

- `model/M1/`, `model/M2/`, `model/M3/`, and `model/M4/`;
- `registries/`;
- `exp/exp2/` and `exp/common/`;
- `docs/experiment/EXP2_SCIENTIFIC_EXECUTION_PROTOCOL.md`;
- current manuscript and reconciliation documents concerning Exp2/M3/M4.

This rescan does not treat the prior gate audit as current evidence without verification.

## Current Exp2 implementation status

`EXP2_IMPLEMENTATION_STATUS = CODE_READY_ARTIFACT_VALUES_NOT_SUPPLIED`

The current implementation still provides:

- six representation-only variants: `JOINT`, `MARGINAL`, `COLLAPSED`, `COMPONENT`, `CHANNEL`, and `SCALAR`;
- frozen reference pairing (`JOINT` for Exp2A and `COMPONENT` for Exp2B);
- immutable M1/M2 representation adapters without M1 retraining or M2 reconstruction;
- the same M3-then-M4 interface for reference and comparison variants;
- action-set, response-rule, monetary-mapping, and risk-policy identity guards;
- decision metrics over M4 residual-risk envelopes;
- an execution loader and fixed-binding manifest that fail on missing/unfrozen summary artifacts.

The existing execution artifact layer validates M1 scenario/cutoff content and M2 seven-component/CU lineage content. Its existing M3 and M4 payloads remain summary identities: M3 carries action IDs and two registry hashes; M4 carries mapping/policy hashes and statuses. Those summaries do not by themselves prove per-action response support or the complete contents of the mapping and policy.

No concrete scientific Exp2 execution bundle is present or selected by this rescan.

## Current M1/M2 compatibility

### M1

The current M1 typed path preserves scenario identity, weight, decision-time cutoff, and lineage. Unsupported targets abstain, and formal hidden-size selection remains an independent unresolved M1 issue. Exp2 can consume a separately frozen M1 scenario artifact through its adapter, but this task has not supplied or executed such an artifact.

`M1_INTERFACE_COMPATIBILITY = READY`

`M1_EXECUTION_ARTIFACT = NOT_SUPPLIED`

### M2

The current M2 V2 interface emits the exact seven-component ontology and preserves all scenario IDs, weights, CU identity, support, and reference lineage. It explicitly keeps CU separate from money. The repository also contains `M2_DATA2_FORMAL_CU_V1`, while `m2_v2_design.json` still records unresolved formal aggregate/CU design decisions. A future Exp2 run must bind one exact M2 artifact compatible with the execution cohort; registry existence alone is insufficient.

`M2_INTERFACE_COMPATIBILITY = READY`

`M2_EXECUTION_ARTIFACT = NOT_SUPPLIED`

## Current M3 compatibility

Runtime registry revalidation produced:

```text
ACTION_REGISTRY_ID = ACTION_TEMPLATES_V1
ACTION_REGISTRY_SCHEMA = 1.1.0
ACTION_REGISTRY_HASH = sha256:2057a4fc274eb9eb7b820365f5b85ff1d0d3f9ea96549e8618842c740f987716
ACTION_TEMPLATE_COUNT = 23

RESPONSE_REGISTRY_ID = M3_RESPONSE_SCENARIO_V1
RESPONSE_REGISTRY_HASH = sha256:ff8adb3034603ec225930ed9187bc296b46d58637a974c9de64b341248755ce0
RESPONSE_REGISTRY_STATUS = HUMAN_APPROVED_SCENARIO_SPECIFICATION
FORMAL_SUPPORT_UPGRADE = false
```

`A00` remains the deterministic identity baseline. The other 22 registry entries remain reproducible `PURE_SCENARIO` specifications. That is compatible with the frozen Exp2 claim lane only when represented explicitly as `SCENARIO_ASSUMPTION`; it is not empirical effectiveness or causal support.

The current V2 M3 action-response module still exposes only the A00 identity construction directly. A concrete, typed, executable non-A00 response-rule bundle has not been supplied. The existing Exp2 M3 artifact payload also lacks per-action rule hashes, source references, support classes, parameter versions, and freeze IDs.

`M3_REGISTRY_COMPATIBILITY = CONDITIONAL_ENGINEERING_READY`

`M3_EXECUTION_ARTIFACT = BLOCKED_UNTIL_TYPED_NON_A00_RESPONSE_BUNDLE_EXISTS`

## Current M4 compatibility

The current M4 implementation preserves scenario weights and seven-component lineage, implements weighted expectation/VaR/CVaR and residual-risk contracts, and separates authoritative, conditional, and not-ranked outputs.

The current design registry remains unchanged:

```text
REGISTRY_ID = M4_MONETARY_MAPPING_DESIGN_V2
SCIENTIFIC_STATUS = SCIENTIFIC_DECISION_REQUIRED
PRODUCTION_MAPPING_ENABLED = false
HUMAN_GATE = MONETARY_MAPPING_FREEZE_REQUIRED
SEVEN_COMPONENT_STATUS = ABSTAIN
```

No production monetary mapping or frozen residual-risk/CVaR policy is present. Test-only mappings cannot close this gate. A future mapping for this Exp2 protocol is limited to a constructed internal loss unit and cannot be represented as RMB, realized cost, saving, or benefit.

`M4_CODE_COMPATIBILITY = ENGINEERING_READY`

`M4_EXECUTION_ARTIFACT = BLOCKED_MISSING_FROZEN_MAPPING_AND_POLICY`

## Remaining blockers

1. A concrete frozen M1 scenario artifact and cohort/cutoff identity are not supplied.
2. A concrete aligned M2 seven-component consequence artifact is not supplied.
3. No frozen action manifest yet names `A00` plus at least one exact non-A00 action for the execution cohort.
4. No complete typed non-A00 M3 response-rule bundle is available at the V2 execution boundary.
5. Existing M3 execution artifacts do not bind per-action support and provenance.
6. No complete frozen, non-test seven-component M4 mapping exists.
7. No frozen residual-risk/CVaR policy or positive-tail decision exists.
8. Existing M4 execution artifacts do not bind and validate the full mapping/policy contents.
9. Dataset, split, cohort, seed, and an explicit execution authorization remain required.

No numerical response, monetary, tail, or risk-policy value is selected here.

## Manuscript claim alignment

`MANUSCRIPT_CLAIM_SCOPE_ALIGNMENT = YES_WITH_STALE_EXPERIMENT_TERMINOLOGY`

The current manuscript-related documents still support the narrow statement that Exp2 studies representation sensitivity. They also explicitly block:

- optimal-action claims;
- best-policy claims;
- causal action-effect claims;
- authoritative ranking claims from scenario responses;
- real-cost, RMB, saving, or benefit claims from internal/test scales.

That scientific boundary matches `SCENARIO_CONDITIONED_REPRESENTATION_SENSITIVITY`.

There is, however, a documented terminology/design mismatch: the current manuscript draft primarily describes the historical `DISTRIBUTIONAL` versus `POINT COLLAPSE` and lineage-corruption Development analysis, whereas the current V1 implementation freezes `JOINT/MARGINAL/COLLAPSED` and `COMPONENT/CHANNEL/SCALAR`. Historical Development results must not be relabelled as results from the new six-variant implementation. No TeX or manuscript source is edited by this task.

## Rescan conclusion

```text
EXP2_ALIGNMENT_STATUS = ALIGNED_FOR_CONDITIONAL_ARTIFACT_PREPARATION
EXP2_ENGINEERING_EXECUTION = BLOCKED_PENDING_CONCRETE_ARTIFACTS
EXP2_SCIENTIFIC_AUTHORITY = NON_AUTHORITATIVE
EXP2_RESULTS = NOT_RUN
```
