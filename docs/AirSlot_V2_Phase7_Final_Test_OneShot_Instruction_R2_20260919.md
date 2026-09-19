# AirSlot V2 Phase 7 Final-Test One-Shot Instruction (R2-Aligned)

## 1. Status and Purpose

- Status: `FROZEN_EXECUTION_PROTOCOL_FOR_PHASE7_GATE_A_AND_GATE_B`.
- Scientific authority: annotated local tag `v2-scientific-freeze-r2`.
- R2 tag object: `2dcca6c159dedde3803e63cb48bd8bfefff574cf`.
- R2 tag target commit: `3834eed33d4a2ea4bdba111fc29cca3529525a3a`.
- Parent freeze tag: `v2-scientific-freeze`.
- Parent tag object: `35d5fe1896dd9e17be92bec601f87ec33adb4d56`.
- Parent tag target: `d29fc769e74d6b46f86d3fdf7db18b3f9936f8b1`.
- R2 registry file SHA-256:
  `sha256:15c1e8bf5ec5fbb5ee783595a124b1255b550d7d7bc96e34b2cd3df0a4e88e6f`.
- R2 registry artifact hash:
  `sha256:4e7d3bb454e83779e6cbb592d4cf9d6ffddc0edf3435a7bc3d2822e4523417f2`.
- R2 authority reconciliation: `PASS`.
- Non-Test Stage-II corpus: `720` actionable cases, `2` typed non-actionable
  cases, `0` action disagreements, `2` tie-break cases.
- Maximum objective and recoverable-value errors in R2 reconciliation: `0.0`,
  against `M3_NUMERICAL_COMPARISON_TOLERANCE = 1e-6`.

This instruction is a new file. It does not rewrite or supersede the previous
Phase-7 instruction by modifying its bytes. The repository copy and the
Download_all copy must be byte-identical.

- Repository copy:
  `docs/AirSlot_V2_Phase7_Final_Test_OneShot_Instruction_R2_20260919.md`.
- Execution copy:
  `D:\Download_all\AirSlot_V2_Phase7_Final_Test_OneShot_Instruction_R2_20260919.md`.

## 2. Fixed Execution Chain

```text
Freeze R2
-> Gate A
-> human release
-> one Phase-7 access epoch
-> Gate B
-> atomic scientific results
-> immutable manifest
-> reporting views
-> stop
```

Gate A may be implemented and committed without Final-Test data. Gate B may
not begin until a human-created release file exists and validates against the
exact schema in Section 10.

No push is authorized. Gate B stops after its local commit. There is no
automatic transition to another phase.

## 3. Scientific Authority

### 3.1 Stage-II solver authority

```text
formal_solver = PYOMO_HIGHS
parity_oracle = EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID
objective_perturbation = NONE
long_term_deviation = false
```

Pyomo plus HiGHS is the formal Stage-II decision authority. Exact enumeration
over the same finite action grid is an independent deterministic parity oracle.
It is not the production authority.

The tie rule is:

```text
u* = min { u in U_i(theta) : J_i(u) = min_v J_i(v) }
```

The formal implementation uses a two-stage lexicographic solve:

1. Minimize `J` to obtain `J*`.
2. Minimize `u` subject to `J <= J* + tau`.

`tau = 1e-6` is only `M3_NUMERICAL_COMPARISON_TOLERANCE`. It is
`NOT_A_SCIENTIFIC_PARAMETER`. `tie_break_applied` and
`near_tie_candidate_count` are computational diagnostics and do not enter the
paper's scientific estimands.

Any action disagreement between HiGHS and enumeration is a typed blocker.
Objective and value comparisons use the declared numerical tolerance only.

### 3.2 Reference representation authority

The frozen Stage-I reference authority is History plus Joint:

```text
H_g^{C,*} = H_g^{C,History+Joint}
R_g* = H_g^{C,History+Joint} intersect StageIISupported
```

Alternative representations `r` may define their own `H_g^(r)` for the
attention comparison used by `L_att`. They do not replace `R_g*`. Every
representation-specific Stage-II information comparison uses the same fixed
`R_g*`.

### 3.3 Comparison support

- Common-support ownership belongs to M2.
- PRE owns evidence and data support only.
- Nominal threshold: `m^CS >= 0.90`.
- Below-threshold behavior: `ABSTAIN_NO_COMMON_SUPPORT`.
- Missing, unsupported, and zero are strictly distinct.
- No manuscript-predefined `m^CS` sensitivity grid exists in the current
  authority. Do not invent one.

## 4. Frozen Experimental Scope

### 4.1 Primary design

Section 5.2 uses `stage x q` as the primary design. The operating grid is:

```text
q in {0.05, 0.10, 0.20, 0.30}
```

`q` is a substantive operating condition, not a sensitivity axis.

### 4.2 Nominal base specification

The Section 5.5 nominal base is fixed:

```text
q = 0.10
lambda = 0.25
turnaround Q20 = 41
U_max = Q90 = 45
History = H16
m^CS = 0.90
```

### 4.3 OFAT sensitivities

Section 5.5 runs one-factor-at-a-time sensitivity for exactly these axes:

```text
lambda
turnaround
U_max
H8
```

For each sensitivity, only the selected factor changes and every other factor
remains at the nominal base specification. Do not form a Cartesian product
between sensitivities and the Section 5.2 `q` grid.

The specification-dependent action grid is:

```text
U_i(theta) = {0, 5, ..., U_max(theta)}
U_max(Q80) = 25
U_max(nominal) = 45
U_max(Q95) = 75
```

Every formal action must satisfy `u_i* in U_i(theta)` for the active
specification.

### 4.4 Excluded analyses

The following are not executed by Phase 7 and may not appear as formal
Final-Test claims:

```text
similar-delay 5/10/15
itinerary 30/60
service 150/210
fixed-window history
```

If these are explored later, they require a separate post-freeze exploratory
analysis with its own authority. They cannot be introduced after seeing Test
results.

## 5. Gate A: Pre-Access Implementation Gate

Gate A runs from the R2 frozen repository state and creates no Final-Test
access.

Allowed Gate A work:

- the one-shot runner;
- validation and schema checks;
- synthetic fixtures;
- Development-side support fixtures;
- deterministic dry-run;
- HiGHS/enumeration parity checks;
- release-schema validation;
- access-epoch idempotence checks.

Forbidden Gate A work:

- reading Q4 raw data;
- reading or writing the legacy `artifacts/experiment/final_test/` tree;
- invoking `allow_final_test=True`;
- opening a Phase-7 access epoch;
- creating or treating a human release as approved.

Gate A must validate:

- the R2 annotated tag object and target commit;
- the R2 registry bytes and payload hash;
- the immutable parent freeze;
- the M2 V5, supersession, turnaround, `F_continuity`, Train-support, and
  cohort identities;
- the 128-episode frozen cohort manifest;
- `final_test_cohort_reused = true`;
- `final_test_cohort_reselected = false`;
- the selected-episode hash;
- byte-identical instruction copies;
- formal HiGHS behavior and exact-enumeration parity;
- legal typed-state preservation;
- release schema;
- one-epoch-per-release idempotence.

The normalized Gate A cohort fields are authoritative for this instruction:

```text
final_test_cohort_reused = true
final_test_cohort_reselected = false
```

The older source manifest uses `selection_reused` and
`selection_reperformed`. Those source bytes are historical evidence and are
not rewritten.

The release field `cohort_manifest_sha256` binds the executed-manifest digest:

```text
sha256:3e10f0e125ed70f6487bda0f0864c9191ddde9ab2d539514a520879b0131d26f
```

The pre-access file digest is validated separately:

```text
formal/FINAL_TEST_COHORT_MANIFEST_V1.json
sha256:5024f6b0af07d7a71b3d341921925617cfe40b0b1131322c319972521cb19073
```

Do not substitute one digest for the other.

### 5.1 Frozen text-file hash normalization

Two R2 text artifacts were originally copied into the compatibility
working tree with CRLF line endings, while the annotated R2 tag stores
their canonical LF bytes. The parsed JSON payloads are identical.
Gate A therefore validates the tag-canonical LF hash and records the
legacy worktree hash only as a compatibility label:

```text
M2_F_CONTINUITY_TRAIN_SCALE_CORRECTED_V5.json
canonical LF: sha256:b335b19564c1eaf827ed0d343405dc9e9871fd0284e546be28ab987884e507c0
legacy CRLF worktree: sha256:688560356d5c7fa292b59e5a7b45cf249619c35bf6620446b1166034a5a2e061

TRAIN_TURNAROUND_HEADROOM_SUMMARY.json
canonical LF: sha256:27df8b4ea406b48ca7b494e48759edfeaf490a501ce2b6293638bbd7a2cce4c2
legacy CRLF worktree: sha256:35e570a5b9f718d44f9b60d2c0525d53c756529a590865f511a7aef1be5436bc
```

This normalization is provenance-only. It does not alter numeric payload,
sample membership, scientific statistics, or dependency semantics.

Gate A outputs only:

```text
artifacts/experiment/final_test_v2/GATE_A_PREFLIGHT.json
artifacts/experiment/final_test_v2/GATE_A_DRY_RUN.json
```

`GATE_A_PREFLIGHT.json` must report:

```text
status = READY_FOR_GATE_B
gate_b_authorized = false
q4_raw_reads = 0
old_final_test_result_tree_reads = 0
final_test_data_reads = 0
phase7_access_epoch_opened = false
```

Gate A completes with commit message:

```text
v2(phase7-gate-a): add final-test one-shot runner
```

No push is performed.

## 6. Gate B Entry Conditions

Gate B is closed until all of the following hold:

1. Gate A is committed.
2. A human-created release file exists.
3. The release validates against the exact schema in Section 10.
4. The R2 tag is unchanged.
5. The instruction copy hash is unchanged.
6. The cohort authority and executed-manifest hashes are unchanged.
7. No Phase-7 access epoch has already been opened for a different release.

A runner must not infer human approval from a plan, a commit, a timestamp, or
the presence of the instruction file. Human approval must be explicit.

## 7. DAG and Scientific Execution

The frozen Gate B DAG is:

```text
canonical nodes
-> state variants
-> M2 consequences
-> shared Stage-I decisions
-> H_g^{C,History+Joint}
-> R_g*
-> representation-specific M3/HiGHS decisions on fixed R_g*
-> M4 comparisons
-> paired bootstrap
-> Section 5 views
```

Stage-I selection is executed once per required attention environment. The
Final-Test evaluation population and 128 episodes are reused, not reselected.
Stage-II information comparisons use the fixed History+Joint reference cohort
`R_g*`.

The shared Stage-I selector covers both:

```text
P^D = delay comparator
P^C = consequence-based priority authority
```

`P^C` is the only consequence-based priority authority. `P^D` is a parallel
delay comparator and does not replace it.

The Stage-I capacity rule is:

```text
K = ceil(q * N)
tie-break = (-score, episode_id, node_id)
q0 = 0.10
q grid = {0.05, 0.10, 0.20, 0.30}
```

A00 is never a recommended action. TAXI and COMP local stages use the
singleton action set `{0}` and return `NOT_ACTIONABLE`.

## 8. Atomic Results and Reporting Views

The required order is:

```text
scientific atomic results
-> immutable manifest
-> tables and figures
```

Reporting code must not silently recompute scientific quantities while
constructing a table or figure. Every persisted atomic result must be covered
by the immutable manifest before reporting views are generated.

## 9. Acceptance Invariants

The following are legal typed scientific states. Their presence does not by
itself fail Gate B:

```text
ABSTAIN_NO_COMMON_SUPPORT
UNDEFINED_ZERO_RECOVERABLE_VALUE
NOT_ACTIONABLE
N/A_NOT_DEFINED
```

Gate B fails if such a state is required but missing, is silently coerced to
zero, is replaced by a normal numeric value, or permits an illegal action.

For a valid denominator and a non-empty reference comparison cohort:

```text
|L_att| <= tau
|L_rec| <= tau
A_0 = A_5 = 1
```

If the reference comparison cohort is empty, agreement metrics must return
`N/A_NOT_DEFINED`. If a denominator is zero, the corresponding recoverable
value must return the typed undefined state. Reference identities may not be
forced by zero filling.

Additional inequalities:

```text
V_i >= -tau
Delta J_i^(r) >= -tau
Delta A_g^(r) >= -tau  for defined valid cohorts
```

TAXI and COMP may not produce a positive action.

## 10. Gate B Human Release

The release file path is fixed:

```text
artifacts/experiment/final_test_v2/GATE_B_HUMAN_RELEASE.json
```

The release schema is exact. No extra fields are permitted:

```json
{
  "gate_a_commit": "<40-hex commit>",
  "instruction_sha256": "sha256:<64-hex>",
  "freeze_tag_object": "2dcca6c159dedde3803e63cb48bd8bfefff574cf",
  "freeze_tag_target_commit": "3834eed33d4a2ea4bdba111fc29cca3529525a3a",
  "cohort_authority_sha256": "sha256:9832b198e221042bff6f40c718f07c82169885514030308b7d50d6172d7e0088",
  "cohort_manifest_sha256": "sha256:3e10f0e125ed70f6487bda0f0864c9191ddde9ab2d539514a520879b0131d26f",
  "human_approved": true,
  "human_approval_timestamp": "<ISO-8601 timestamp with timezone>"
}
```

Required field names:

```text
gate_a_commit
instruction_sha256
freeze_tag_object
freeze_tag_target_commit
cohort_authority_sha256
cohort_manifest_sha256
human_approved
human_approval_timestamp
```

The release binds no bare `selection_*` field. The cohort-reuse meaning is
carried by `cohort_manifest_sha256` and the normalized Gate A cohort fields.

## 11. Phase-7 Access Epoch

A valid human release opens exactly one Phase-7 access epoch. The atomic audit
file is:

```text
artifacts/experiment/final_test_v2/PHASE7_ACCESS_AUDIT.json
```

Before the first Q4 raw read, the audit must contain:

```text
access_epoch_id
access_epoch_opened
raw_read_started
raw_read_completed
retry_within_same_epoch
historical_access_total = 1
phase7_increment = 1
current_total = 2
```

One release maps to one epoch. The epoch id is deterministic from the release
binding. If the same release is retried for a pure binding or I/O repair:

```text
retry_within_same_epoch = true
phase7_increment = 1
current_total = 2
```

The retry does not increment the access total again.

Any of the following closes the epoch and requires a new human review before
further Final-Test access:

- scientific definition change;
- cohort change;
- parameter-selection change;
- Test-driven reporting-choice change.

A bug-fix retry may not be used to smuggle in any of those changes.

## 12. Gate B Completion

Gate B persists atomic scientific results first, writes the immutable manifest,
then generates tables and figures. After verification it creates a local
commit with message:

```text
v2(phase7-gate-b): execute sealed final test
```

If a typed blocker occurs, the run records the typed blocker and stops. It
does not push, does not enter another phase, and does not retry with a changed
scientific definition.

The historical Final-Test access total is `1`. Gate B raises it to `2` for the
single Phase-7 epoch. Gate A leaves it at `1` and records increment `0`.
