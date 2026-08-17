# Air Slot EXPERIMENT_PROTOCOL_V5 Implementation Audit

Audit date: 2026-08-16
Repository: `D:\research\air_slot\code\explore`
Branch: `main`
Repository authority: the user request in the pasted task text, constrained by the attached
`EXPERIMENT_PROTOCOL_V5.md`, `DATA1_DATA_USAGE_SPEC.md`, and `DATA2_DATA_USAGE_SPEC.md`.

## 0. Instruction Boundary

The pasted task is the implementation request. The three attached Markdown files are not
additional conversational requests; they are the scientific/data contracts that constrain the
implementation. The current repository is the target checkout. No second project is created and
the attached files are treated as read-only source specifications.

The precedence used in this audit is:

1. Latest scientific definitions in the supplied V5 protocol and data-usage specifications.
2. Typed model contracts and frozen registries/configuration in this checkout.
3. Current experiment runners, tests, and validation reports.
4. Historical reports and old experiment artifacts.

## 1. Repository State

`git rev-parse --show-toplevel` resolves to `D:/research/air_slot/code/explore`.
`git status --short --branch` was clean on `main` and aligned with `origin/main` at audit time.

The repository already contains `model/PRE`, `model/M1`, `model/M2`, `model/M3`, `model/M4`,
`exp/common`, `exp/exp1` through `exp/exp4`, `exp/reporting`, `configs`, `registries`, and a
substantial contract/integration test suite. This is a partial V5 implementation rather than a
legacy-only tree.

## 2. Current Formal Inference Path

### 2.1 PRE

- Module: `model/PRE/pipeline.py::publish_production_pre`.
- Public input: `ProductionPRERequest`, containing episode/node identity, UTC decision time and
  information cutoff, canonical source records, dataset identity, config hash, registry hash,
  stage, and roll interval.
- Output: `PREBuildResult` containing typed `PREState`, evidence ledger, variable lineage, and
  frozen reference entries.
- Configuration/registry: `configs/scientific/foundation.yaml` through
  `model.common.config.load_config_layers`; `registries/` through
  `model.PRE.feature_registry.loader.load_registry_bundle`.
- RNG: none in PRE publication; node identity and mappings are deterministic.
- Artifacts: typed PRE state/lineage objects; no V5 formal namespace writer yet.
- Coverage: adapter, PRE foundation, production PRE, lineage, temporal, and smoke tests.

### 2.2 M1

- Modules: `model/M1/pipeline.py`, `model/M1/service.py`, `model/M1/data.py`,
  `model/M1/scenarios.py`, `model/M1/target_builder.py`.
- Public interfaces: `M1Pipeline`, `M1Service.predict_now`, `M1Service.generate_scenarios`,
  `AlignedScenario`, and typed target/forecast contracts.
- Inputs: typed PRE state plus normalized historical feature sequences and model artifacts.
- Outputs: ordered `R_IB`, `DELTA_OB`, `T_TX` distributions and aligned scenario bundles; `R_OB` is derived compatibility output.
- Configuration: scientific foundation YAML; formal horizons are `(0, 15, 60)`, delay thresholds
  are `(15, 30, 60)`, hidden-size candidates are `[16, 32]`, and the signed-target Development
  freeze selects `H=32` with fixed history `W=30`.
- RNG: deterministic hash-based scenario keys in `model/M1/scenarios.py`; no shared global RNG.
- Artifacts: M1 normalization/model/scenario objects exist as typed pieces, but no single immutable
  formal artifact writer captures the V5 hash set.
- Coverage: M1 contract, lifecycle, pipeline, loss, coverage, and integration tests.

### 2.3 M2

- Modules: `model/M2/mapper.py`, `model/M2/drivers.py`, `model/M2/contracts.py`,
  `model/M2/valuation.py`.
- Public interface: `M2Mapper.map_scenarios`.
- Inputs: aligned M1 scenarios and typed `M2ScientificContext`/`ConsequenceScope`.
- Outputs: seven-component `ScenarioConsequence` values, diagnostics, and formal-estimand status.
- Configuration: valuation registry and consequence scope supplied by callers; the current smoke
  valuation path is not a paper-frozen registry.
- RNG: none in M2 mapping.
- Artifacts: typed consequence rows; no V5 formal namespace writer.
- Coverage: M2 contract/mapping and integration tests; no complete formal cohort artifact.

### 2.4 M3

- Modules: `model/M3/registry.py`, `model/M3/instantiate.py`, `model/M3/contracts.py`.
- Public interface: `instantiate_candidates(pre_state, registry)`.
- Inputs: typed PRE state or a normalized dictionary plus frozen action registry.
- Outputs: typed `CandidateAction` records with preconditions, mitigation/induced effects,
  provenance, coverage, and response parameter status.
- Configuration: action registry under `registries/`; response parameters are mostly not frozen.
- RNG: no sampling in M3 instantiation.
- Artifacts: registry and candidate objects; no V5 hash manifest writer.
- Coverage: registry/candidate and closure tests.

### 2.5 M4

- Modules: `model/M4/decision.py`, `post_action.py`, `coverage.py`, `lanes.py`, `ranking.py`,
  `response.py`, and `risk.py`.
- Public interface: `evaluate_request(M4DecisionRequest)` and `evaluate_decision(...)`.
- Inputs: PRE + aligned M1 scenarios + M2 consequences + M3 candidates + material coverage
  contract + risk policy.
- Outputs: typed `EpisodeDecision`, action evaluations, lanes, residual risk, and authoritative
  ranking.
- Configuration: caller-supplied lambda/alpha; principal V5 values are 0.25/0.90.
- RNG: `model/M4/response.py::stable_uniform` is hash-keyed by seed, episode, scenario, action,
  and response component; it correctly excludes decision time but is not yet exposed as a named
  V5 stream object.
- Artifacts: typed decision objects; no single immutable formal writer.
- Coverage: M4 decision, response, lane, and closure tests.

### 2.6 End-to-end status

The typed chain is present as PRE -> M1 -> M2 -> M3 -> M4. A reusable frozen formal pipeline
entrypoint and V5 formal artifact namespace are missing. Existing bounded smoke scripts stop before
formal M2-M4 publication and are explicitly non-paper evidence.

## 3. Experiment Entrances

Current executable entrances are:

- `exp/cli.py` (`smoke-all`, `run`, and `report`).
- `exp/exp1/runner.py`, `exp/exp2/runner.py`, `exp/exp3/runner.py`, `exp/exp4/runner.py`.
- `exp/common/runner.py` and supporting bootstrap/split/metrics/reporting modules.
- Validation-only bounded runners under `validation/`.

No active `overall_run`, `overall_adv`, or `part_adv` Python entrypoints were found in this
checkout. Historical references appear in reports and validation notes only. The migration map is:

| Historical name | V5 disposition |
| --- | --- |
| `overall_run` | `LEGACY_COMPAT` conceptually maps to formal pipeline plus compact reporting; no active wrapper exists yet. |
| `overall_adv` | `DEPRECATE`; it must not define the scientific hierarchy. |
| `part_adv` | `DEPRECATE`; component sensitivity belongs to Exp2/Exp4. |
| current `exp/exp1..4` | `REFACTOR`; retain package boundaries and replace placeholder variants/contracts. |

## 4. Scientific-Contract Findings

### 4.1 M1 event-time and delay semantics

The D3 signed target contract derives total takeoff delay from `DELTA_OB`, `T_TX`, and the train-frozen taxi reference. It
requires the event-time identity `T_TO = T_OB + T_TX` while defining total takeoff delay from
its own schedule/reference terms; therefore `D_TO` must not be treated as a generally additive
`D_OB + D_TX` identity. The canonical helper accepts the signed offset and train-frozen reference.

### 4.2 M1 capacity

The current foundation config exposes candidates `[16, 32]` and freezes the signed-target winner
at `H=32` with `W=30` under `D3_SIGNED_M1_H_W_REFREEZE`. Existing historical reports mention an
older 8/16 contract; no active 8-size formal value may be reintroduced.

### 4.3 M2 formal scope

`M2Mapper` can return formal status for a supplied `ConsequenceScope`, but the repository has no
single V5 `FULL_FIXED_FORMAL_SCOPE` object or formal multi-action cohort gate. Dynamic per-episode
available-component sums are diagnostics only and must not become the principal estimand.

### 4.4 M3/M4 support lanes

Lane assignment already distinguishes `FORMAL`, `CONDITIONAL`, `SCENARIO`, and `EXCLUDED`, and
response provenance prevents unfrozen scenario responses from entering formal ranking. However,
the experiment layer does not yet expose the V5 feasibility audit or a frozen registry hash in every
evaluation artifact.

### 4.5 Formal/evaluation separation

`exp/common/runner.py` has a copy-only artifact guard, but the non-smoke runners still rely on
synthetic `variant_metrics` rows rather than a shared frozen formal pipeline. Exp1/2/3 transforms
are evaluation copies, yet variant names and transformations do not fully match the V5 ownership
contract. Publication/reporting is separate, but no immutable formal namespace is enforced by the
CLI.

## 5. RNG Findings

The M1 and M4 primitives are deterministic, but the repository lacks a named cross-experiment RNG
stream contract. `exp/common/bootstrap.py` uses a local NumPy generator, while Exp2 lineage
corruption uses `random.Random(seed + offset)` and does not yet include episode/node/q/replicate in
its key. These must be unified under explicit streams:
`m1_scenario`, `m3_m4_response`, `exp2_lineage_corruption`, `bootstrap`,
`llm_case_selection`, and `llm_repetition`.

## 6. Current Test and Runtime Evidence

The repository contains broad contract/integration coverage and bounded fixture smoke validation.
Current README/report evidence states that compile, unit/integration validation, and a 64-scenario
bounded M1 smoke have passed, while no paper-ready Exp1-Exp4 formal run, Final Test promotion,
DeepSeek audit, or 10,000-scenario full cohort has run. This audit does not promote historical
reports to current scientific readiness.

## 7. Required V5 Closure Work

The implementation work after this audit must, at minimum:

1. Add one `ExperimentCrossContract` source of truth for DATA2 split, units, bootstrap, lead times,
   thresholds, risk policy, scenario counts, and runtime modes.
2. Add explicit `smoke`, `development`, `paper_full`, and `numerical_stress` mode validation;
   keep `FAST` as an M1 computational path only.
3. Add a reusable frozen formal pipeline and immutable artifact writer with all V5 hash fields.
4. Correct M1 total-delay semantics and add contract tests for non-additive delay references.
5. Rename/repair Exp1-Exp4 variants and implement the required copy-only evaluation guards,
   formal multi-action and feasibility gates, and portability/status manifests.
6. Add deterministic named RNG streams and order-invariance tests.
7. Add `EXPERIMENT_CROSS_CONTRACT_STATUS.json`,
   `EXPERIMENT_V5_IMPLEMENTATION_STATUS.json`, and the final implementation report.
8. Keep `paper_full` gated and do not execute a paper/full run in this implementation turn.

## 8. Audit Decision

The repository is structurally ready for a scoped V5 implementation closure, but is not currently
`READY_FOR_PAPER_FULL_REVIEW`. It is `PAPER_FULL_BLOCKED` until the cross-contract, formal artifact,
semantic, RNG, and gate manifests below are implemented and validated.
