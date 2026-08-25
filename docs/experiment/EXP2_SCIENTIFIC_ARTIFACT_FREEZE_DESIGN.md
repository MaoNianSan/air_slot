# Exp2 Scientific Artifact Freeze Preparation Design

Status: `PREPARATION_COMPLETE_EXECUTION_BLOCKED`

This design prepares a real-data Exp2 artifact declaration. It does not run Exp2, open a dataset, create a checkpoint, materialize M2 consequences, choose actions, freeze scientific parameters, or generate metrics or paper output.

## Artifact hierarchy

```text
dataset capability registry
  -> frozen dataset version / split / episode selector
    -> M1 frozen scenario artifact and checkpoint
      -> M2 frozen seven-component consequence artifact and CU lineage
        -> M3 exact action set and typed per-action response bundle
          -> M4 complete mapping registry and residual-risk policy
            -> future Exp2 execution manifest
```

`configs/experiment/exp2_scientific_manifest.yaml` is the preparation declaration at the top of this chain. It binds only existing registry identities and records every absent concrete artifact as `REQUIRED_*`. `ScientificManifestValidator` validates registry existence, source/semantic hashes, dataset capability compatibility, component-schema identity, and shared `dataset_id`; it returns an explicit blocked state instead of supplying a fallback.

The present declaration binds logical Exp2 dataset `DATA2` to source instance `data2_2019` through `registries/dataset_capabilities.yaml`. This proves that the named source profile and the requested `realized_events`/`weather` roles exist in the registry. It does not claim that a frozen dataset version, split, episode selector, cohort, or data artifact exists.

## Frozen inputs that are already identity-bound

| Layer | Current identity-bound input | State |
| --- | --- | --- |
| Dataset | `DATA2` binding to `data2_2019` capability profile, registry schema `1.0.0` | Registry compatible; dataset freeze still required |
| M2 CU | `M2_DATA2_FORMAL_CU_V1` registry and hash | Registry validated; compatible seven-component execution artifact still required |
| M2 schema | Seven-component ontology (`F_continuity` through `R_operating`) | Hash validated |
| M3 actions | `ACTION_TEMPLATES_V1` source and semantic registry hashes | Structural registry validated; no comparison set frozen |
| M3 responses | `M3_RESPONSE_SCENARIO_V1` source and semantic registry hashes | Scenario registry validated; no typed executable non-A00 bundle supplied |
| M4 mapping design | `M4_MONETARY_MAPPING_DESIGN_V2` source hash | Design is explicitly unresolved and production mapping is disabled |

The manifest does not reuse smoke fixtures. The `TEST_ONLY_SMOKE` route remains isolated from scientific preparation and the M4 gate rejects `TEST_ONLY` mapping or policy status.

## Action freeze preparation

`exp.exp2.artifacts.action_manifest` accepts only a caller-declared exact action set with a corresponding support record for every action. It requires:

- `A00` as the first action;
- at least one non-`A00` action;
- deterministic ascending order after `A00`;
- a supported typed response record for every included action.

It never chooses membership, omits an unsupported action, or upgrades scenario assumptions into support. If no supported non-`A00` action is supplied, the result is `BLOCKED` with `NO_SUPPORTED_NON_A00_ACTION`.

## M4 scientific gate

`M4ScientificGate` is validation-only. A ready result requires a non-test frozen mapping and policy, `support_status=SUPPORTED`, a resolved mapping, mapping provenance, policy provenance, and non-placeholder artifact identities. It rejects:

- `TEST_ONLY` mapping or risk-policy status;
- `NOT_FROZEN` or other non-frozen status;
- unsupported/abstained support status;
- unresolved mapping;
- missing mapping or policy provenance;
- missing risk-policy or combined M4 artifact identity.

The current preparation manifest intentionally fails this gate because the repository has no production mapping or frozen residual-risk policy. The top-level manifest reports `BLOCKED_MISSING_ARTIFACT` while its nested M4 gate reports `BLOCKED_UNSUPPORTED_MAPPING`, preserving both independent blockers.

## Remaining scientific decisions

Human scientific gates must still supply, approve, and content-address:

1. the Data2 version, split, episode selector, and cohort/decision-node manifest;
2. the M1 checkpoint and scenario artifact for that exact cohort;
3. the M2 seven-component consequence artifact and its exact M1 lineage;
4. the exact M3 comparison action set and executable non-A00 response rules with support/provenance;
5. complete seven-component M4 constructed-internal-loss mapping provenance and policy;
6. the residual-risk/CVaR values, tail decision, policy provenance, and hashes.

No decision above may be closed with a registry name alone, a test fixture, a historical result, an inferred fallback, or post-hoc tuning. Preparing this declaration is not authorization to execute Exp2 or create a scientific/paper result.

## Validation scope

The tests under `tests/experiments/test_exp2_scientific_manifest/` cover manifest shape, registry hash consistency, required M1 checkpoint reporting, M4 `TEST_ONLY` rejection, and action-freeze blocking. They create no scientific artifact and consume no real-data rows.
