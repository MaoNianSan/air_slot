# Air Slot Exp1-Exp4 Programming Instructions

**Version:** V1  
**Date:** 2026-09-06  
**Purpose:** Convert `AIR_SLOT_EXP1_4_MASTER_PROGRAMMING_SPEC_V1_20260906.md` into executable programming instructions.  
**Scope:** Development implementation only.  
**Scientific scope:** Exp1-Exp4 as defined by the current master specification.

## 1. Authority and Boundaries

The current paper Sections 1-4 define the empirical motivation and terminology.
The master programming specification defines the Exp1-Exp4 scientific design.
This document defines the implementation contract.

The following are read-only or frozen for this work:

- `data1/` and `data2/`;
- PRE decision-time legality and publication semantics;
- M1 scientific definition, H16 primary authority, and frozen artifacts;
- M2 seven-component ontology and Train-frozen scales;
- Final Test inputs and temporal split;
- manuscript source files;
- historical paper-result artifacts.

This work must not:

- retrain or recalibrate M1;
- change M1/M2 definitions;
- access or materialize Final Test;
- implement action recommendation as an experiment outcome;
- use A00, M3, or M4 recommendation semantics as a headline result;
- select definitions, thresholds, weights, or cohorts from Development results;
- modify the manuscript;
- perform Git operations unless separately requested.

Every Development output must contain:

```text
paper_result = false
final_test_access_count = 0
model_retrained = false
calibration_refit = false
parameter_reselected = false
```

## 2. Implementation Order

The implementation order is mandatory:

```text
W0 definition ledger
W1 formal shared input package
W2 shared analytical views
W3 Exp1 and Exp2
W4 Exp3 and Exp4
W5 Development review package
```

No Exp3 or Exp4 formal runner may consume a private reconstruction of PRE,
M1, M2, support, or priority scores.

## 3. W0 Definition Ledger

Create:

```text
artifacts/experiment/EXPERIMENT_DEFINITION_LEDGER_V1.json
docs/EXPERIMENT_DEFINITION_LEDGER_V1.md
```

Each entry must have:

```text
topic
source_document
current_status
approved_definition
implementation_owner
decision_required
blocked_experiments
```

The ledger must contain these items:

1. Full-support versus conditional common-support primary estimand.
2. Exp2 component/domain population rule.
3. Exp4 budget comparison set.
4. Exp4 unsupported canonical-event handling.
5. Exp4 consensus threshold `m`.
6. Passenger 45/180 threshold sensitivity disposition.
7. Support filtering and aggregation order.
8. Canonical operating-stage labels.

Until a human-approved value exists, the implementation must use:

```text
status = UNRESOLVED
```

and the affected formal runner must fail closed with a typed block. A smoke
runner may use an explicitly labelled non-paper diagnostic configuration.

## 4. W1 Formal Shared Input Package

The shared package is the only input boundary for Exp1-Exp4. Its intended root
is:

```text
artifacts/experiment/shared/development/
```

Required files:

```text
SHARED_DEVELOPMENT_INPUTS.parquet
SHARED_SCENARIO_INPUTS.parquet
SHARED_INPUT_MANIFEST.json
SHARED_SUPPORT_AUDIT.json
```

The node table must contain at least:

```text
original_episode_id
decision_node_id
decision_time
information_cutoff
operating_stage
node_order_within_episode
split
```

The scenario table must contain:

```text
original_episode_id
decision_node_id
scenario_id
scenario_weight
R_IB
T_IB
D_OB
D_TX
D_TO
scenario_support_state
```

The consequence table or nested payload must preserve, per scenario and
component:

```text
component_id
native_value
cu_value
support_status
source_lineage
```

Required shared-input assertions:

1. All rows are Development rows.
2. No row has a Final Test date or Final Test source lineage.
3. Node identity is unique.
4. Scenario identity is unique within node.
5. Scenario weights are finite, positive, and sum to one per node.
6. `D_TO = D_OB + D_TX` within tolerance.
7. Decision-time availability is legal.
8. All seven M2 components are present as typed supported/unsupported values.
9. H16 checkpoint and calibration identities are traceable.
10. PRE, M1, M2, scale, and shared-contract hashes are recorded.

No experiment may infer missing values from filenames or historical output
names. Unsupported values remain typed unsupported values and are never
zero-filled.

## 5. W2 Shared Analytical Views

Add or complete shared modules under `exp/shared/`:

```text
support.py
records.py
lineage.py
variants.py
bootstrap_utils.py
```

The existing `contracts.py` and `recovery_priority.py` remain the scientific
single source of truth for score arithmetic.

### 5.1 Support policies

Support policy must be represented explicitly:

```text
FULL
COMMON_SUPPORT_CONDITIONAL_090
COMMON_SUPPORT_CONDITIONAL_050
```

Each analytical row must record:

```text
support_policy_id
support_mass
scenario_set_identity
support_reason_codes
```

The implementation must not silently choose the primary policy while the
definition ledger marks the choice unresolved.

### 5.2 Shared scores

For an admissible node:

```text
D = sum_s(weight_s * D_TO_s)
C_k = sum_s(weight_s * component_k_s)
Z_k = C_k / frozen_train_scale_k
S_F = mean(Z_F_continuity, Z_F_execution, Z_F_propagation)
S_P = mean(Z_P_time, Z_P_itinerary, Z_P_service)
S_R = Z_R_operating
S_C = mean(S_F, S_P, S_R)
```

The shared layer also owns:

```text
S_C_no_F_execution
S_equal_component
S_F
S_P
S_R
```

Shared code stores scores and support states. Experiment modules own cohort
selection and ranks.

### 5.3 Ranking

All experiment ranking helpers must:

1. use descending score order;
2. use average/midrank for rank statistics;
3. use stable technical `decision_node_id` only for exact Top-K boundary ties;
4. report boundary-tie counts;
5. never encode scientific meaning in the technical tie-break.

## 6. Exp1 Programming Instructions

### 6.1 Scientific role

Exp1 provides supporting evidence for the rolling-state basis. It evaluates:

```text
H16_HISTORY versus H16_CURRENT
Joint versus Marginal versus Point
```

It does not evaluate delay adequacy, stage effects, or capacity triage.

### 6.2 Required modules

Complete:

```text
exp/exp1/contracts.py
exp/exp1/inputs.py
exp/exp1/history_current.py
exp/exp1/representations.py
exp/exp1/metrics.py
exp/exp1/bootstrap.py
exp/exp1/tables.py
exp/exp1/plots.py
exp/exp1/run.py
```

Existing pure metric helpers may be reused only after their input semantics
are verified.

### 6.3 Input rules

History and Current must have:

```text
same semantic node set
same targets
same training cohort
same calibration population
same feature contract
same support contract
same scenario count
same H16 size
```

The only scientific difference may be history mode. The reader must validate
the matched audit and reject unverified alignment.

### 6.4 Estimands

Targets:

```text
predecessor availability
D_OB
D_TX
```

History/Current:

```text
MAE
CRPS
episode-balanced paired difference
```

Representation:

```text
Variogram Score, p=0.5
Joint
Marginal
Point
```

The representation implementation must preserve the following distinctions:

```text
Joint: aligned scenario vectors and weights
Marginal: per-axis distributions with dependence removed
Point: one frozen representative state
```

It must produce different representation-specific records. A common
`variogram_rows` object reused for all three representations is prohibited.

### 6.5 Exp1 outputs

Write under:

```text
artifacts/experiment/exp1/development/
```

Required:

```text
EXP1_ANALYSIS_CONTRACT.json
EXP1_INPUT_MANIFEST.json
EXP1_HISTORY_CURRENT_NODE_RECORDS.parquet
EXP1_HISTORY_CURRENT_SUMMARY.csv
EXP1_HISTORY_CURRENT_BOOTSTRAP.csv
EXP1_REPRESENTATION_RECORDS.parquet
EXP1_REPRESENTATION_SUMMARY.csv
EXP1_REPRESENTATION_CONTRASTS.csv
EXP1_SUPPORT_AUDIT.json
EXP1_OUTPUT_MANIFEST.json
```

### 6.6 Exp1 blocking conditions

Return typed `BLOCKED` for:

```text
formal PRE input missing
History/Current semantic mismatch
target or calibration mismatch
future information
unsupported observation silently converted
representation identity not distinct
Final Test access
untraceable artifact lineage
```

## 7. Exp2 Programming Instructions

### 7.1 Scientific role

Exp2 contains:

```text
Exp2A overall divergence
Exp2B component/domain informativeness
Exp2C similar-delay heterogeneity
```

It must not contain stage headline analysis or fixed-budget triage.

### 7.2 Population and metrics

Primary stages:

```text
PRE_IN_BLOCK
POST_IN_BLOCK_PRE_OFF_BLOCK
POST_OFF_BLOCK_PRE_TAKEOFF
```

Completed stages are excluded from the primary population.

Primary node metrics:

```text
Kendall tau-b(D, S_C)
median rank displacement
P90 rank displacement
Pr(rank displacement >= 0.30)
Top-10 overlap
signed displacement
```

Exp2B must build a separate finite/support-applicable sample for each component
and domain. It must not inherit Exp2A's seven-component complete-case sample.

### 7.3 Similar-delay matching

Primary:

```text
absolute delay difference <= 5 minutes
same active stage
different original episodes
```

Sensitivity:

```text
10 minutes
15 minutes
```

The implementation must aggregate qualifying pairs by
`(original_episode_i, original_episode_j)` before calculating the primary
pair-balanced estimate. It must report candidate pairs, balanced episode-pair
count, matched episodes, and coverage.

### 7.4 Bootstrap

Use:

```text
cluster = original_episode_id
replicates = 2000
seed = 20260906
```

Each replicate must resample episode clusters, rebuild the analytical cohort,
rebuild ranks, rebuild Top-K sets, rebuild similar-delay matches, and then
recompute metrics. Resampling already-computed metric rows is invalid.

### 7.5 Robustness

Implement through shared variants:

```text
NO_F_EXECUTION
support-policy sensitivity
equal-component
pre-specified alternative domain weights
Pareto reversal
```

The no-execution variant can only rule out direct mechanical dependence on
`F_execution`; it cannot establish causal independence from delay.

### 7.6 Exp2 repair list

The implementation must close these known issues:

```text
I1 component/domain-specific populations
I2 typed abstention for empty optional samples before ranking
I3 single-source no-F_execution formula
I4 complete input-lineage validation
I5 distinct smoke versus formal materialization states
```

### 7.7 Exp2 outputs

Write under:

```text
artifacts/experiment/exp2/development/
```

Required output families:

```text
analysis contract
input manifest
support audit
Exp2A node records, summary, bootstrap, tie audit
Exp2B component/domain summaries and bootstrap
Exp2C matched pairs, pair-balanced summary, bootstrap
robustness summary
representative cases
output manifest
```

## 8. Exp3 Programming Instructions

### 8.1 Scientific role

Exp3 estimates stage-specific:

```text
tau_g = Kendall tau-b(D, S_C | stage=g)
H_g = similar-delay heterogeneity at delta=5
```

It inherits all score and support definitions from `exp/shared/`.

### 8.2 Required modules

Create:

```text
exp/exp3/contracts.py
exp/exp3/inputs.py
exp/exp3/stages.py
exp/exp3/cohort.py
exp/exp3/agreement.py
exp/exp3/heterogeneity.py
exp/exp3/bootstrap.py
exp/exp3/robustness.py
exp/exp3/tables.py
exp/exp3/plots.py
exp/exp3/run.py
```

### 8.3 Stage rules

Stage labels must be canonical and inherited from the shared input package.
Exp3 may filter stages but may not redefine them from outcomes.

For every stage report:

```text
N episodes
N nodes
support coverage
Kendall tau-b and CI
H_g and CI
median rank displacement
Top-10 overlap
candidate and balanced match counts
match coverage
```

Empty or insufficient stage samples must produce typed `ABSTAIN_EMPTY_SAMPLE`
or `ABSTAIN_INSUFFICIENT_MATCHES`, never zero.

### 8.4 Common-episode robustness

Construct a secondary cohort containing only episodes with admissible nodes in
all primary active stages. Rebuild stage metrics and same-stage matching on
that cohort. Record the common-episode cohort identity and counts.

### 8.5 Exp3 outputs

Write:

```text
artifacts/experiment/exp3/development/
```

Required:

```text
EXP3_ANALYSIS_CONTRACT.json
EXP3_INPUT_MANIFEST.json
EXP3_STAGE_COHORT.csv
EXP3_STAGE_AGREEMENT.csv
EXP3_STAGE_HETEROGENEITY.csv
EXP3_MATCH_COVERAGE.csv
EXP3_BOOTSTRAP.csv
EXP3_COMMON_EPISODE_ROBUSTNESS.csv
EXP3_OUTPUT_MANIFEST.json
```

## 9. Exp4 Programming Instructions

### 9.1 Scientific role

Exp4 is a retrospective fixed-budget screening benchmark. It compares which
nodes receive limited screening attention under delay-based and
consequence-based ranking.

It is not action optimization, recommendation, intervention evaluation, or
realized cost-saving estimation.

### 9.2 Canonical event

The default canonical event is the first chronological 5-minute rolling node
for each `(original_episode_id, active_stage)`. The implementation must:

1. sort by decision time;
2. select the first valid node;
3. preserve its decision-time information state;
4. exclude completed stages;
5. never replace an unsupported first node with a later supported node.

### 9.3 Budget contract gate

Formal Exp4 implementation is blocked until the definition ledger freezes:

```text
budget comparison set
stage-stratified versus cross-stage comparison
calendar/time-window grouping
unsupported canonical-event policy
K rounding rule
consensus threshold m
```

The code may implement pure screening and capture functions before this gate,
but must not produce a formal Exp4 Development result.

### 9.4 Screening metrics

For each frozen budget cohort and `q`:

```text
K = approved rounding rule(q * N)
T_D = Top-K by delay score
T_C = Top-K by consequence score
overlap
slots_reassigned = K - overlap
reassigned_rate = slots_reassigned / K
```

Both methods must use the same candidate cohort and same budget.

### 9.5 Capture metrics

Report for both selected sets:

```text
F/P/R domain capture
all seven native-component capture values
```

Each denominator must be constructed from the same admissible candidate cohort
used for the comparison. Unsupported values do not enter a denominator unless
the frozen support policy explicitly defines that estimand.

### 9.6 Robust missed nodes and Pareto

The robust high-consequence set must be built from a pre-frozen list:

```text
BASE aggregate
F-domain
P-domain
R-domain
equal-component
alternative frozen domain weights
no-F_execution
```

The consensus threshold `m` is a contract parameter, not a result-selection
parameter. Pareto comparisons require complete supported component vectors and
must handle equal vectors and ties explicitly.

### 9.7 Exp4 outputs

Write under:

```text
artifacts/experiment/exp4/development/
```

Required:

```text
EXP4_ANALYSIS_CONTRACT.json
EXP4_INPUT_MANIFEST.json
EXP4_CANONICAL_EVENTS.parquet
EXP4_BUDGET_COHORTS.csv
EXP4_SCREENING_RESULTS.csv
EXP4_DOMAIN_CAPTURE.csv
EXP4_NATIVE_COMPONENT_CAPTURE.csv
EXP4_ROBUST_MISSED_NODES.csv
EXP4_PARETO_RESULTS.csv
EXP4_BOOTSTRAP.csv
EXP4_ROBUSTNESS_SUMMARY.csv
EXP4_OUTPUT_MANIFEST.json
```

## 10. Provenance Contract

Every experiment contract and output manifest must record:

```text
experiment_id
experiment_version
scientific_contract_id
support_policy_id
estimand_id
split
data_version
pre_version/hash
m1_checkpoint/hash
m1_calibration/hash
m2_registry/hash
train_scale_registry/hash
shared_priority_contract/hash
code_commit
input_manifest_hash
output_manifest_hash
bootstrap_seed
bootstrap_replicates
generated_at
paper_result
final_test_access_count
```

Scientific source lineage and presentation-only lineage must be separate.

## 11. Required Tests

Before any formal Development run, add focused tests for:

```text
shared score arithmetic and frozen scales
typed unsupported values and no zero-fill
node/scenario identity and weight validity
future-information rejection
History/Current semantic matching
Joint/Marginal/Point distinction
component/domain-specific Exp2 samples
midrank and deterministic Top-K ties
same-episode pair exclusion
episode-pair balancing
bootstrap rebuilding ranks and matches
canonical Exp4 event selection
same-budget screening comparison
capture denominator identity
Pareto complete-support behavior
lineage and Final Test guards
```

Tests must validate contracts and recomputation behavior, not expected
scientific result direction.

## 12. Stop Conditions

Stop and report `BLOCKED` when:

```text
an unresolved ledger item is required by the current runner
formal shared inputs are not complete
shared support policy is ambiguous
semantic node mapping is not closed
any future information is detected
Final Test access is detected
unsupported values would be zero-filled
the current HEAD changes during materialization
```

Do not convert a blocked formal run into a smoke pass by weakening the
contract. Label smoke outputs separately as non-paper diagnostics.

## 13. Completion Definition

The programming phase is complete only when:

```text
shared analytical package is verified
Exp1 formal Development runner is implemented
Exp2 I1-I5 are closed and tested
Exp3 runner is implemented and tested
Exp4 budget contract is frozen, implemented, and tested
all Development outputs have manifests
all result states distinguish PASS, ABSTAIN, BLOCKED, and NOT_RUN
no Final Test was accessed
no manuscript was edited
```

Completion of this programming phase does not authorize Protocol Freeze or
Final Test. Those require a separate explicit gate.
