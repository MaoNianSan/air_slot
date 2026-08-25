# Exp2 Smoke Execution Report

Status: `TEST_ONLY_SMOKE_PASS`

HEAD at preparation start: `9660e30a65425bff5354b0ca1611bb6119500aba`

## Purpose

This package validates only the end-to-end execution mechanics of Exp2. It exercises artifact loading, representation transformation, a fixed downstream M3-to-M4 binding, `ExperimentResult` construction, and lineage propagation without using a real dataset or producing scientific evidence.

The smoke path is explicitly isolated by `TEST_ONLY_SMOKE`. The production entry rejects these artifacts. The smoke entry requires dataset `TEST_ONLY_SMOKE`, split `SMOKE`, `TEST_ONLY_SMOKE*` artifact versions, and an explicit `artifact_scope` marker on every execution artifact.

## Fixtures

All files under `tests/fixtures/exp2_smoke/` are controlled mechanics-only fixtures:

| Fixture | Role |
|---|---|
| `m1_scenario_fixture.json` | Three synthetic M1 scenarios for JOINT, MARGINAL, and COLLAPSED transformation |
| `m2_consequence_fixture.json` | Three synthetic seven-component M2 consequences for COMPONENT, CHANNEL, and SCALAR transformation |
| `m3_action_manifest_fixture.json` | Fixed `A00`/`A11` action order plus a content-linked response registry identity |
| `m3_response_bundle_fixture.json` | Fixed test-only response-rule identities consumed by the smoke M3 adapter |
| `m4_mapping_fixture.json` | Test-only M4 mapping identity and content-linked risk-policy identity |
| `m4_risk_policy_fixture.json` | Mechanics-only risk-policy sentinels consumed by the smoke M4 adapter |

The numeric values are deterministic test sentinels. They are not selected, calibrated, or approved scientific parameters.

## Tested variants

Exp2A:

- `EXP2A_JOINT`
- `EXP2A_MARGINAL`
- `EXP2A_COLLAPSED`

Exp2B:

- `EXP2B_COMPONENT`
- `EXP2B_CHANNEL`
- `EXP2B_SCALAR`

All six variants executed through one identity-locked downstream binding. Each produced an `exp.common.result_schema.ExperimentResult`; the M3 and M4 stages received the expected representation, M4 consumed the bound M3 envelope hashes, and every metric retained `execution_scope=TEST_ONLY_SMOKE` plus M1/M2/M3/M4 lineage.

## Production gate validation

The tests verify fail-closed behavior before any downstream callback:

- a `TEST_ONLY_SMOKE` M4 mapping is rejected by the production execution entry with `BLOCKED_UNSUPPORTED_MAPPING`;
- a missing M3 response registry identity is rejected with `BLOCKED_MISSING_ARTIFACT`;
- a missing M4 risk-policy identity/status is rejected with `BLOCKED_MISSING_ARTIFACT`.

## Verification

- `python -m compileall exp tests/experiments`: PASS
- `python -m pytest tests/experiments`: PASS, `50 passed`
- `git diff --check`: PASS
- `git status --short -- model`: empty; no model modification

## What this smoke proves

- the six frozen representation transformations can be constructed from controlled artifacts;
- the same M3/M4 binding can consume every representation variant;
- the typed protocol completes and generates `ExperimentResult` objects;
- source, representation, manifest, binding, M3, and M4 lineage is retained;
- production gates reject test-only or incomplete downstream support.

## What this smoke does not prove

- no real dataset was read;
- no model was trained, modified, calibrated, or compared;
- no scientific parameter was chosen or frozen;
- no M3 action response, M4 monetary mapping, or risk policy was scientifically validated;
- no accuracy, superiority, causal, operational, monetary, ranking, or generalization claim is supported;
- no Development, Final Test, `paper_full`, paper table, paper figure, or paper result was generated.

Scientific run: `NO`

Paper result generation: `NO`
