# Air Slot V2 — Final Engineering Implementation Instruction

> **Revision rev2 (2026-09-18, owner-approved).** This rev2 is the single
> engineering instruction for the Phase 0-5 execution and supersedes rev1
> wherever they differ. Changes relative to rev1:
> 1. **Section 11 (Stage-II solver).** The formal Stage-II path is exact
>    enumeration over the finite action grid; Pyomo + HiGHS is a
>    development-time parity backend only. This is no longer recorded as a
>    deviation.
> 2. **Sections 5/7/8/12 (priority signals).** `P^C` is the unique
>    consequence-based priority authority; `P^D` is the parallel delay
>    comparator; both share one Stage-I selector and one candidate cohort.
> 3. **Sections 5/12 (comparison support).** The common-support requirement
>    (`m^CS >= 0.90` nominal) belongs to the M2 consequence-comparison layer;
>    PRE owns evidence/data support only. No numeric sensitivity values are
>    predefined by the current manuscript, so only the nominal 0.90 is used.
> 4. **Sections 4/5 (CU normalization).** CU normalization is five positive
>    Train-period medians plus two assumption-grounded event normalizations
>    (`P_itinerary`, `P_service`, frozen scale = one native event unit, not an
>    empirical median). The DB1B continuation-share reference stays active in
>    `P_itinerary`.
> 5. **Sections 15/26 (freeze).** Phase 5 freeze artifacts are drafts only and
>    must carry `status = DRAFT_NOT_ACTIVATED` and `freeze_commit = PENDING`.
>    Phase 6/7 gates are unchanged: no Final-Test access without a separate
>    release.
>
> Mechanical normalization: rev1 contained literal escape artifacts
> (`\b`, `\f`, `\r`, `\a`). rev2 restores the intended characters; no
> scientific text was altered by this normalization.
>
> rev1 sha256: 4b3a79a4294650e4b2b1f67526b31b9e27b7f9e647f64fd3a27242eedf482af2


**Purpose:** paper-primary implementation for the current JATM manuscript  
**Repository:** `github.com/MaoNianSan/air_slot`  
**Mode:** engineering implementation, not exploratory programming  
**Agent autonomy:** use normal senior-engineer judgment; ordinary implementation ambiguity should not stop the task.

## 0. Mission

Refactor the repository into one unified scientific implementation:

\[
\boxed{
	ext{admissible evidence}

ightarrow
	ext{operating state}

ightarrow
	ext{operational consequences}

ightarrow
	ext{attention decision}

ightarrow
	ext{local recovery decision}

ightarrow
	ext{decision evaluation}
}
\]

Conceptual ownership:

\[
\boxed{PRE
ightarrow M1
ightarrow M2
ightarrow M3
ightarrow M4}
\]

- **PRE**: rolling historical decision environment and admissible evidence.
- **M1**: unresolved operating-state reconstruction.
- **M2**: seven-component consequence representation and consequence priority.
- **M3**: Stage-I attention allocation + Stage-II local recovery optimization.
- **M4**: paired common-basis decision evaluation + optional secondary monetary interpretation.

Section 4 and Section 5 must use the same model implementation. Experiment packages may orchestrate services but must not redefine scientific logic.


# 1. Scientific authority and legacy policy

Authority order:

\[
\boxed{
	ext{latest manuscript scientific definition}
>
	ext{this instruction}
>
	ext{legacy repository}
>
	ext{legacy experimental outputs}
}
\]

Legacy files are evidence about data, existing implementations, and historical choices; they are not independent scientific authorities.

Use legacy assets primarily for:

1. real data paths/schemas;
2. field names, units, timestamp semantics and missing rules;
3. chain construction;
4. rolling-node construction;
5. evidence admissibility;
6. weather/passenger/operating-reference joins;
7. split logic;
8. compatible M1 trained/calibrated artifacts;
9. reusable Point/Marginal/Joint primitives;
10. compatible consequence formulas;
11. numerical utilities.

Classify legacy objects as **PRESERVE / REUSE / ADAPT / REWRITE / RETIRE**.

Typical treatment:

| Object | Treatment |
|---|---|
| data readers / field mapping | REUSE |
| flight-chain construction | REUSE / VERIFY |
| rolling evidence | REUSE / ADAPT |
| trained M1 estimator | REUSE if scientifically identical |
| Point/Marginal/Joint code | ADAPT into M1 |
| seven consequences | VERIFY / ADAPT |
| old A01–A23 action library | RETIRE from primary path |
| direct action→loss response coefficients | RETIRE |
| old `1 CU = 1 RMB` primary semantics | RETIRE |
| old Exp1–Exp4 scientific orchestration | RETIRE |
| bootstrap / metrics | REUSE |

Do not preserve old APIs merely for backward compatibility. Historical artifacts may remain as provenance.


# 2. Agent autonomy and escalation

Resolve ordinary implementation questions autonomously.

Do **not** stop for:

- package/file naming;
- helper placement;
- dataclass vs TypedDict;
- parquet vs CSV;
- duplicate utility choice;
- cache strategy;
- adapter design;
- internal/public aliases;
- obvious implementation bugs;
- ordinary performance optimization;
- regenerating a missing artifact when its scientific definition is already fixed.

Use three statuses:

- **AUTO-RESOLVE**: scientific meaning is clear; repair/migrate/rebuild and continue.
- **ABSTAIN**: a local row/component/metric lacks valid support.
- **BLOCK**: proceeding requires a new scientific assumption or changes the estimand, feasible set, transition, consequence, objective, or evaluation population.

Escalate only for true scientific ambiguity or data impossibility.

This is not a production AOCC platform. Do not expand into crew/fleet/gate/passenger-reaccommodation optimization, online serving, drift-monitoring infrastructure, or general airline recovery.


# 3. PRE — decision environment authority

PRE owns:

\[
	ext{historical data}
ightarrow\mathcal E_{\le t}
\]

It must expose:

- predecessor-successor chain identity;
- episode identity;
- rolling nodes;
- decision time;
- stage: PRE / TURN / TAXI / COMP;
- split;
- evidence availability;
- support metadata.

Core rule:

\[
	au_j^{avail}\le t
\]

Future outcomes may be used for retrospective evaluation but never earlier evidence.

For stage comparisons:

\[
t_i^g=\min\{t:G_{i,t}=g\}
\]

Choose the canonical node first, then evaluate support. Never replace an unsupported canonical node with a later supported node.

PRE should expose a stable logical `DecisionEvidence` object containing identity, decision time, stage, split, scheduled/observed milestones, admissible context, static references, availability flags, and support flags. Downstream code should not depend on raw BTS/NOAA/DB1B column names.


# 4. M1 — unresolved-state authority

M1 owns:

\[
\mathcal E_{\le t}
ightarrow\widehat{\mathcal S}_{i,t}
\]

Only unresolved state dimensions are estimated. Realized milestones replace uncertainty.

Core state primitives:

\[
T^{IB},\qquad D^{OB},\qquad D^{TX}
\]

and per scenario:

\[
\boxed{D^{TO}=D^{OB}+D^{TX}}
\]

Keep internal training-target names separate from public scientific names. Explicitly map targets such as `T_IB_REMAINING_HAZARD` to public objects such as `T_IB_A00`; do not use public aliases to query internal labels.

## Temporal dimension
- `CURRENT`
- `HISTORY`

Primary History = **H16**.  
Sensitivity/lower-capacity comparator = **H8**.  
H32 = legacy benchmark/provenance only unless a later manuscript explicitly restores it.

## Uncertainty dimension
- `POINT`
- `MARGINAL`
- `JOINT`

All three uncertainty representations must derive from the same frozen `HISTORY_H16_PRIMARY` source.

- **Joint**: aligned scenarios + weights.
- **Marginal**: preserve weighted marginals; deterministically destroy common scenario identity via coordinate-wise permutation. Do not call this physical independence.
- **Point**: coherent frozen weighted joint medoid; do not combine independent coordinate means/medians.

Expose a stable logical `StateScenarioSet` with node identity, temporal/uncertainty representation, scenario id/weight, \(T^{IB},D^{OB},D^{TX},D^{TO}\), observed/predicted status where useful, and support state.


# 5. M2 — consequence authority

M2 owns:

\[
State
ightarrow Operational\ Consequences
\]

Seven components:

- \(F_{continuity}\)
- \(F_{execution}\)
- \(F_{propagation}\)
- \(P_{time}\)
- \(P_{itinerary}\)
- \(P_{service}\)
- \(R_{operating}\)

Use the exact current-manuscript formulas. Experiments must not reimplement them.

M2 owns:

- native consequence quantities;
- provenance/support;
- CU mapping;
- F/P/R aggregation;
- overall consequence representation;
- consequence-based attention signal:

\[
\boxed{P^C=\Phi_C(\mathbf C^0)}
\]

Preserve `missing`, `unsupported`, `zero`, and `false` as distinct states.

CU is a common constructed comparison scale:

\[
\boxed{CU
eq RMB,\ EUR,\ accounting\ cost,\ welfare}
\]

The old `1 CU = 1 RMB` semantics must be inactive on the paper-primary path.

M2 ends at native consequences / CU / priority.


# 6. Secondary monetary interpretation

If retained, monetary interpretation belongs to **M4 as a secondary evaluation/interpretation branch**, not the primary M2/M3 decision chain.

It must be literature/reference grounded, component-specific, and preserve monetary abstention for unsupported components such as `P_itinerary` / `P_service` when applicable.

Never:
- map unsupported monetary components to zero;
- redefine CU as currency;
- insert secondary monetary mapping into the primary Stage-I or Stage-II objective unless the current manuscript explicitly requires it.


# 7. Delay comparator \(P^D\)

Delay is not a state representation.

\[
\boxed{Delay\ vs.\ Consequence=Stage\!-\!I\ priority\ signal\ comparison}
\]

The delay-signal adapter belongs to M3 Stage I.

Do **not** invent a formula for \(P^D\).

During Phase 0/1:

1. inspect the latest manuscript;
2. inspect the frozen specification / compatible legacy implementation;
3. recover the exact intended delay-signal definition;
4. implement it consistently on common support.

If one unambiguous frozen definition exists, use it. Escalate only if multiple scientifically reasonable definitions remain and would materially alter the Stage-I estimand.


# 8. M3 — sole decision authority

M3 owns both Stage I and Stage II.

Any legacy document assigning Stage-I selection to M4 is superseded.

## Stage I

Input:
- common candidate cohort;
- `PrioritySignal`;
- \(q\) or \(K\).

\[
K=\lceil qN
ceil
\]

Solve:

\[
\max_z \sum_iP_i z_i
\]

subject to:

\[
\sum_i z_i\le K,\qquad z_i\in\{0,1\}
\]

Deterministic Top-K is the exact implementation. Do not use Pyomo just for appearance.

Tie-breaking must be deterministic and independent of future outcome/representation, e.g. `(-priority_score, episode_id, node_id)`.

Expose an `AttentionDecision`-equivalent output with score, rank, q, K, selected flag, signal type and stable identity.

Delay and Consequence use the same selector.

Nominal attention capacity:

\[
q_0=0.10
\]

Substantive grid:

\[
q\in\{0.05,0.10,0.20,0.30\}
\]

Do not choose q from Development performance.


# 9. M3 Stage II — local recovery

Only PRE and TURN are actionable under the local off-block recovery model.

For TAXI / COMP:

\[
\boxed{\mathcal U=\{0\}}
\]

and return typed metadata such as `NOT_ACTIONABLE`.

## Train-derived support

Primary turnaround reference:

\[
T^{turn,lb}=Q_{0.20}
\]

Sensitivity: Q10 / Q30.

For eligible factual Train rotations:

\[
LB_{OB}^{fact}=\max(SOBT,T_{IB}^{obs}+T^{turn,lb})
\]

\[
H^{fact}=\max(AOBT^{obs}-LB_{OB}^{fact},0)
\]

Primary action cap:

\[
\boxed{
U_{\max}
=
	ext{floor-to-5min}\left(Q_{0.90}(H^{fact}\mid H^{fact}>0)
ight)
}
\]

Sensitivity: Q80 / Q95.

Action support must be representation-independent.

Primary action grid:

\[
\boxed{u\in\{0,5,10,\ldots,U_{\max}\}}
\]

No A01–A23 template IDs are allowed in the paper-primary optimization contract.


# 10. Stage-II transition and objective

For scenario \(s\):

\[
AOBT_s^0=SOBT+D_{OB,s}^0
\]

\[
LB_{OB,s}=\max(SOBT,T_{IB,s}+T^{turn,lb})
\]

\[
H_s=\max(AOBT_s^0-LB_{OB,s},0)
\]

\[
r_s(u)=\min(u,H_s)
\]

Post-action:

\[
AOBT_s(u)=AOBT_s^0-r_s(u)
\]

\[
D_{OB,s}(u)=\max(AOBT_s(u)-SOBT,0)
\]

while:

\[
T_{IB,s}(u)=T_{IB,s}(0),\qquad
D_{TX,s}(u)=D_{TX,s}(0)
\]

and:

\[
\boxed{D_{TO,s}(u)=D_{OB,s}(u)+D_{TX,s}(u)}
\]

The post-action state must be accepted by the same M2 service as baseline.

Mandatory chain:

\[
\boxed{u
ightarrow S(u)
ightarrow M2
ightarrow C(u)
ightarrow J(u)}
\]

Never implement direct action→percentage-loss reduction.

Primary objective:

\[
J_i(u;\lambda)
=
\sum_s w_s\Phi_C(C^{CU}_{i,s}(u))
+
\lambda\frac{u}{U_{\max}}
\]

Use the current manuscript’s exact scalar consequence mapping if notation differs.

Nominal:

\[
\lambda_0=0.25
\]

Sensitivity:

\[
\lambda\in\{0.10,0.25,0.50,1.00\}
\]

Lambda is a policy scenario, not a fitted airline preference.

\[
u_i^*=\arg\min_uJ_i(u)
\]

On ties choose the smaller intervention.

\[
\boxed{V_i=J_i(0)-J_i(u_i^*)}
\]

\(V\) belongs to M3.


# 11. Stage-II solver

Formal path:

\[
\boxed{\text{exact enumeration over the finite action grid}}
\]

Exact enumeration over the finite one-dimensional action grid is the formal
Stage-II implementation. It is deterministic, exact, and independent of
solver behavior.

Pyomo + HiGHS is retained only as a development-time parity backend. On
representative PRE/TURN cases, verify

\[
u^*_{HiGHS}=u^*_{enum}
\]

and objective parity within numerical tolerance.

After parity is established, do not run the solver for every Final-Test row.
Do not add SCIP benchmarking unless diagnosing a genuine solver defect.

# 12. M4 — common-basis evaluation

M4 answers:

\[
\boxed{	ext{How much decision value is lost under the comparator?}}
\]

M4 does not reconstruct state, define the seven consequences, choose the shortlist, or optimize recovery.

## Stage I

Reference shortlist \(H^*\), comparator \(H^{(r)}\):

\[
\Delta A^{(r)}=A^*(H^*)-A^*(H^{(r)})
\]

\[
\boxed{
L^{att,(r)}
=
\frac{\Delta A^{(r)}}{A^*(H^*)}
}
\]

Also support:
- overlap;
- entered/displaced;
- consequence-domain coverage;
- Kendall/Spearman;
- rank displacement.

These are diagnostics, not substitutes for \(L^{att}\).

## Fixed Stage-II cohort

\[
\boxed{
R_g^*=H_g^{C,*}\cap StageIISupported
}
\]

Only PRE/TURN. No backfill.

All information representations must solve Stage II on the same \(R_g^*\).

## Stage II

For comparator \(r\):

\[
\Delta J_i^{(r)}
=
J_i^*(u_i^{*(r)})-J_i^*(u_i^*)
\]

\[
V_g^*=\sum_{i\in R_g^*}V_i^*
\]

\[
\boxed{
L_g^{rec,(r)}
=
\frac{\sum_{i\in R_g^*}\Delta J_i^{(r)}}{V_g^*}
}
\]

If \(V_g^*=0\), return `UNDEFINED_ZERO_RECOVERABLE_VALUE`.

Also output:

\[
A_0=Pr(u^{*(r)}=u^*)
\]

\[
A_5=Pr(|u^{*(r)}-u^*|\le5)
\]

and:
- `MISSED_ACTIVATION`
- `FALSE_ACTIVATION`
- `UNDER_RECOVERY`
- `OVER_RECOVERY`

Never compare each representation under its own objective.

Never construct \(L^{total}=L^{att}+L^{rec}\) or weighted variants.


# 13. Data lifecycle

## Train
May produce:
- M1 estimated parameters;
- operating references;
- CU references;
- turnaround reference;
- factual headroom distribution;
- \(U_{\max}\).

## Calibration
Only probability/distribution calibration.

Do not use Calibration to choose q, lambda, consequence weights, or action support.

## Development
Used for:
- implementation/configuration selection where predefined;
- state-interface validation;
- Current/History evidence;
- Point/Marginal/Joint evidence;
- freeze preparation.

Do not use downstream \(L^{att}\) or \(L^{rec}\) to choose the primary information representation or policy parameters.

## Final Test
Used only for substantive held-out evaluation.

No retraining, reselection, representation redesign, support-rule redesign, or after-the-fact metric selection.


# 14. Section 4 workflow

Section 4 is:

\[
\boxed{define+instantiate+validate+freeze}
\]

Only two substantive Development evidence families are required.

## A. Current vs History

Primary:
- Current comparator on the common state/output contract;
- `HISTORY_H16_PRIMARY`;
- `HISTORY_H8` lower-capacity sensitivity.

Do not restore H32 into the primary comparison.

Use:
- state reconstruction metrics;
- distribution/calibration metrics;
- consequence-level transmission/distortion.

Do not use \(L^{att}\) or \(L^{rec}\) to select H16.

## B. Point / Marginal / Joint

Use the same frozen `HISTORY_H16_PRIMARY` Joint source.

Use where valid:
- marginal CRPS;
- Energy Score;
- Variogram Score \(p=0.5\);
- consequence distortion vs Joint.

Do not require Joint to dominate Marginal.

Tests should verify representation-specific inputs, not expected result ordering.

The historical bug that reused one shared `variogram_rows` object across Point/Marginal/Joint must not recur.

## Non-experimental materialization

Before Final Test also materialize:
- turnaround nominal/sensitivity;
- factual Train headroom summary;
- \(U_{\max}\) nominal/sensitivity;
- action grid;
- q nominal/grid;
- lambda nominal/grid;
- consequence/CU registry;
- evaluation definitions.


# 15. Scientific freeze

After Section 4 Development and Train-support materialization, create:

- one compact machine-readable freeze specification;
- one short human-readable summary.

Record at least:
- split definitions;
- canonical-node rule;
- common-support rule;
- primary M1 model/config;
- calibration id;
- History primary = H16;
- reference representation = History+Joint;
- scenario count;
- seven consequence definitions/version;
- CU references;
- exact frozen \(P^C\);
- exact recovered \(P^D\);
- q nominal/grid;
- turnaround reference;
- \(U_{\max}\);
- action step;
- lambda nominal/grid;
- transition;
- objective;
- solver;
- \(L^{att}\);
- \(L^{rec}\);
- bootstrap specification;
- predefined sensitivity list;
- freeze commit.

Do not build a separate governance subsystem.

Only after freeze may the new paper-primary Final Test run.


# 16. Final-Test shared DAG

Do not implement Section 5 as five independent scientific pipelines.

Use:

\[
\boxed{
FinalTest

ightarrow
CanonicalNodes

ightarrow
StateVariants

ightarrow
ConsequenceVariants

ightarrow
AttentionDecisions

ightarrow
ReferenceRecoveryCohort

ightarrow
RecoveryDecisions

ightarrow
M4Comparisons

ightarrow
Bootstrap

ightarrow
PaperViews
}
\]

Materialize one canonical Final-Test node index with episode, chain, node, stage, decision time, canonical-stage status, and support.

Primary state variants:
- `HISTORY_JOINT`
- `CURRENT_JOINT`
- `HISTORY_POINT`
- `HISTORY_MARGINAL`

H8 / fixed-window belong to sensitivity.

Run every state variant through the same M2.


# 17. Section 5.1 — Delay compression

Under:
- `HISTORY_JOINT`;
- common canonical nodes;
- common support;
- same K;
- same M3 selector;
- same M4 evaluator;

compare:

\[
P^D\quad vs.\quad P^C
\]

Primary:

\[
\boxed{L^{att,D}}
\]

Supporting:
- Kendall;
- Spearman;
- overlap;
- missed-by-delay;
- extra-by-delay;
- rank displacement.

Persist atomic rows with episode/node, stage, \(P^D\), \(P^C\), ranks, selections, and q.


# 18. Section 5.2 — Operating conditions

This is a conditional expansion of 5.1, not a new model.

Run:

\[
\{PRE,TURN,TAXI\}
	imes
\{0.05,0.10,0.20,0.30\}
\]

Per cell report:

\[
\Delta A_{s,q},\qquad
\boxed{L^{att}_{s,q}}
\]

Also compute:
- F/P/R decomposition;
- `MISSED_BY_DELAY`;
- `EXTRA_BY_DELAY`;
- consequence coverage;
- similar-delay mechanism.

Primary similar-delay caliper:

\[
|D_i-D_j|\le5
\]

Sensitivity: 10 / 15 minutes.

Optional secondary boundary diagnostic:

\[
m_i=P_i^C-P_{(K)}^C
\]

Use it only to analyze amplification near the shortlist cutoff; do not alter the selector.


# 19. Section 5.3 — Reference recovery

Use:

\[
\boxed{History+Joint,\quad q=0.10}
\]

Construct \(H^*\), then:

\[
R^*=H^*\cap StageIISupported
\]

Run M3 Stage II.

Persist:
- \(P_i^C\);
- selected flag;
- headroom summary;
- \(J_i(0)\);
- \(u_i^*\);
- \(J_i(u_i^*)\);
- \(V_i\);
- actionability.

Primary statistics:

\[
Pr(u^*>0)
\]

\[
Median(u^*\mid u^*>0)
\]

\[
Median(V)
\]

\[
\sum_iV_i
\]

Keep opportunity distinct from activation:
- headroom \(>0\) = recovery opportunity;
- \(u^*>0\) = model-implied activation.

For severity–recoverability analysis use:

\[
P_i^C\quad vs.\quad V_i
\]

and mark \(u_i^*\)/activation.

Do not encode the expected relation as a test.


# 20. Section 5.4 — Information value

Reference:

\[
\boxed{History+Joint}
\]

## Temporal comparison

\[
Current+Joint\quad vs.\quad History+Joint
\]

Only temporal information changes.

## Uncertainty comparison

\[
History+Point,\ History+Marginal
\]

vs.

\[
History+Joint
\]

Only retained uncertainty/dependence changes.

## Stage I

Each representation creates its own:

\[
P^{C,(r)}
ightarrow H^{(r)}
\]

M4 computes:

\[
\Delta A^{(r)},\quad L^{att,(r)}
\]

on the reference consequence basis.

## Stage II

Every representation uses fixed \(R^*\).

Each solves \(u_i^{*(r)}\) on that cohort.

M4 evaluates comparator actions under the reference objective and produces:

\[
\Delta J^{(r)},\quad L^{rec,(r)},\quad A_0,\quad A_5
\]

plus activation/intensity error classes.

Retain atomic outputs sufficient to inspect:

\[
state
ightarrow consequence
ightarrow attention
ightarrow recovery
\]

Optional derived views:

\[
\eta^{att}=1-L^{att},\qquad
\eta^{rec}=1-L^{rec}
\]

These are interpretive transformations, not new primary estimands.


# 21. Section 5.5 — Sensitivity

Use one-factor-at-a-time changes around nominal:

| Parameter | Nominal | Sensitivity |
|---|---:|---|
| turnaround | Q20 | Q10 / Q30 |
| \(U_{\max}\) | Q90 | Q80 / Q95 |
| \(\lambda\) | 0.25 | 0.10 / 0.50 / 1.00 |
| itinerary threshold | 45 | 30 / 60 |
| service threshold | 180 | 150 / 210 |
| History capacity | H16 | H8 |
| History scope | full causal prefix | fixed window |

Do not run a full Cartesian product unless a scientific interaction is explicitly required.

Use dependency-aware reruns:
- lambda → from M3 Stage II;
- q → from M3 Stage I;
- consequence threshold → from M2;
- History capacity/window → from M1;
- figure formatting → no scientific rerun.

Sensitivity need not preserve conclusion direction; report actual stability.


# 22. Bootstrap

Use:

\[
\boxed{B=2000}
\]

with:
- resampling unit = `episode_id`;
- paired bootstrap;
- percentile 95% CI;
- one shared bootstrap plan/seed across related comparator metrics.

Reuse a correct legacy implementation if available.


# 23. Scientific atomic artifacts

Persist scientific interfaces, not every computational intermediate.

At minimum retain reusable outputs equivalent to:

## State
node, representation, scenario, weight, \(T^{IB},D^{OB},D^{TX},D^{TO}\).

## Consequence
node, representation, seven native components, seven CU components where supported, F/P/R, \(P^C\), support.

## Attention
node, representation, signal type, q, score, rank, selected.

## Recovery
node, representation, headroom, actionability, \(u^*\), necessary objective fields, reference \(V\).

## Evaluation
reference/comparator id, \(\Delta A\), \(L^{att}\), \(\Delta J\), \(L^{rec}\), \(A_0\), \(A_5\), action error class.

Storage format and directory layout are engineering choices.

Paper tables/figures must be derived from atomic outputs. Changing presentation must not require rerunning M1–M4.


# 24. Scientific tests

Do test:

## PRE
- no future evidence;
- stable identity;
- canonical stage rule;
- split isolation.

## M1
- Current/History common contract;
- realized-state substitution;
- \(D^{TO}=D^{OB}+D^{TX}\);
- Point/Marginal/Joint semantics.

## M2
- seven manuscript formulas;
- CU/support semantics;
- missing vs unsupported vs zero;
- single \(P^C\) authority.

## M3
- deterministic Top-K;
- action feasibility;
- transition invariants;
- TAXI/COMP `{0}`;
- HiGHS/enumeration parity.

## M4
- common-basis Stage-I evaluation;
- reference-objective Stage-II evaluation;
- denominator handling;
- fixed \(R^*\);
- no total loss.

Do **not** assert empirical result direction.

Forbidden:
- History must outperform Current;
- Joint must outperform Marginal;
- \(L^{att}\) must exceed a threshold;
- delay must be inadequate;
- severity must differ from recoverability.

These are empirical questions.


# 25. Unsupported / failure policy

Use typed statuses such as:
- `ABSTAIN_NO_COMMON_SUPPORT`
- `UNDEFINED_ZERO_RECOVERABLE_VALUE`
- `NOT_ACTIONABLE`
- `N/A_NOT_DEFINED`

Never:
- zero-fill unsupported science;
- borrow Development values into Final Test;
- replace canonical nodes with later nodes;
- default a solver failure to \(u=0\) without diagnosis.

A local unsupported component should not invalidate unrelated valid components.

For solver failure:
1. diagnose and repair ordinary implementation/numerical problems autonomously;
2. return typed closed/unsupported status when scientifically appropriate;
3. block only if fixing requires changing action space, constraints, transition, or objective.


# 26. Execution phases

## Phase 0 — Legacy/data audit
Audit priority:

\[
data\ semantics > preprocessing > scientific\ primitives > legacy\ orchestration
\]

Produce concise:
- `LEGACY_TO_V2_MIGRATION_MAP`
- `DATA_FIELD_MAP`
- `REUSABLE_ARTIFACT_MAP`
- `SUPERSEDED_OBJECTS`

Do not perform a full repository walkthrough.

## Phase 1 — Contracts + PRE
Build stable decision-environment interfaces.

## Phase 2 — M1/M2 consolidation
Prefer compatible artifact reuse over unnecessary retraining. Move representation ownership into M1. Reconcile M2 to current manuscript.

## Phase 3 — M3 decision layer
Implement Stage I and Stage II. This is the main scientific rewrite.

## Phase 4 — M4 evaluator
Implement paired common-basis decision evaluation and optional secondary monetary interpretation.

## Phase 5 — Section 4 Development + Train support
Run only the two Development evidence families and materialize support/policy artifacts. No substantive Final-Test access.

## Phase 6 — Scientific freeze
Freeze all scientific choices and record freeze commit.

## Phase 7 — Section 5 Final Test
Build shared atomic results first, then 5.1–5.5 views, bootstrap, sensitivity, and final paper outputs.


# 27. Reuse vs recompute

Reuse a legacy artifact only if:

\[
\boxed{same\ scientific\ object+same\ split+same\ definition}
\]

If implementation semantics remain valid but downstream science changed, reuse code/artifact input and recompute downstream outputs.

If the estimand changed, retire the old result.

Explicitly superseded:
- old A01–A23 Stage-II recommendations;
- old direct action-response results;
- old RMB-primary Stage-II outputs.

Old Stage-I outputs are reusable only if cohort, support, M1, M2, \(P^D/P^C\), selector and evaluator identities are truly unchanged.

Do not spend more effort proving legacy numerical reconciliation than recomputing the new pipeline when recomputation is straightforward.


# 28. Ordinary engineering quality

Use normal engineering judgment for tests, logging, error handling, reproducibility, and performance.

Not required as primary scientific completion criteria:
- all legacy tests passing;
- repository-wide lint cleanup;
- coverage targets;
- exhaustive hash registries;
- fixed physical directory layout;
- complex schema/type frameworks;
- persistence of every intermediate object.

Preserve enough provenance to identify:
- split;
- frozen scientific spec;
- model/reference version;
- source artifact identity.

Do not build a separate governance subsystem.


# 29. Completion criteria

## Model complete
The paper-primary chain runs:

\[
PRE
ightarrow M1
ightarrow M2
ightarrow M3
ightarrow M4
\]

with all scientific invariants satisfied.

## Section 4 complete
- canonical historical decision environment works;
- M1 representations share one contract;
- both Development evidence families are generated;
- M2 consequence/CU/priority matches manuscript;
- Stage II computes \(u^*,V\);
- Train support artifacts are materialized;
- no substantive Final-Test access was required.

## Freeze valid
- all scientific choices fixed;
- freeze commit recorded;
- no downstream model/parameter selection remains.

## Section 5 complete
- 5.1 \(L^{att}\);
- 5.2 stage×q \(L^{att}\) + mechanisms;
- 5.3 \(u^*,V\) + severity–recoverability;
- 5.4 Current/History and Point/Marginal/Joint \(L^{att},L^{rec}\);
- predefined sensitivity;
- final paper views derived from atomic Final-Test outputs.


# 30. Reporting format

At the end of each major phase report only:

1. Completed scope
2. Core files changed/added
3. Scientific interfaces now available
4. Legacy assets reused
5. Scientific blockers/new assumptions, if any
6. Artifacts created
7. Next dependency unlocked

Final report:

1. final branch / commit;
2. paper-primary architecture;
3. legacy assets reused;
4. Section 4 Development outputs;
5. scientific freeze location/version;
6. Section 5 Final-Test atomic outputs;
7. final paper tables/figures;
8. remaining abstain/unsupported items;
9. any scientific assumptions that had to be escalated or changed.

Do not return long operational logs.


# 31. Final anti-drift rules

Do not:
- redesign the research question;
- invent new consequence components;
- invent a new delay comparator;
- revive A01–A23 as primary action space;
- convert CU back into money;
- optimize q or lambda on Final Test;
- make prediction accuracy the paper’s final research endpoint;
- turn Section 4 into a second Section 5;
- allow each representation to use its own Stage-II evaluation cohort;
- compare representation-specific objectives directly;
- construct total loss;
- encode expected conclusions into tests;
- expand into a full airline-recovery platform.

The intended empirical questions remain:

\[
\boxed{
	ext{ranking agreement}
\stackrel{?}{=}
	ext{attention allocation agreement}
}
\]

\[
\boxed{
	ext{information richness}
\stackrel{?}{=}
	ext{decision value}
}
\]

\[
\boxed{
	ext{consequence severity}
\stackrel{?}{=}
	ext{recoverability}
}
\]

The implementation must make these questions measurable without presupposing their answers.




# 32. Recommended code framework

The following framework is the **preferred implementation shape**, not a rigid filesystem mandate.

If the existing repository has a cleaner compatible layout, adapt it.  
However, preserve the ownership boundaries and dependency direction below.

A recommended target structure is:

```text
air_slot/
    common/
        contracts.py
        enums.py
        errors.py
        ids.py

    pre/
        data_adapter.py
        chain_builder.py
        rolling_nodes.py
        stage.py
        admissibility.py
        support.py
        service.py

    state/                     # M1
        contracts.py
        estimator.py
        current.py
        history.py
        representations.py
        calibration.py
        service.py

    consequence/               # M2
        contracts.py
        native.py
        cu.py
        aggregation.py
        priority.py
        support.py
        service.py

    decision/                  # M3
        contracts.py

        attention/
            signal.py
            selector.py
            service.py

        recovery/
            support.py
            feasibility.py
            action_space.py
            transition.py
            objective.py
            solver.py
            enumeration_oracle.py
            service.py

    evaluation/                # M4
        contracts.py
        attention_value.py
        recovery_value.py
        diagnostics.py
        monetary.py
        bootstrap.py
        service.py

    pipeline/
        section4.py
        final_test.py
        materialize.py

    config/
        scientific_defaults.py
        policy_scenarios.py

experiments/
    section4/
        history_vs_current.py
        uncertainty_representation.py
        tables.py
        figures.py
        run.py

    section5/
        attention_value.py
        attention_conditions.py
        reference_recovery.py
        information_value.py
        sensitivity.py
        tables.py
        figures.py
        run.py

validation/
    scientific_invariants.py
    solver_parity.py
    split_isolation.py

tests/
    ...
```

Do not mechanically create every file above if the same responsibility can be implemented more cleanly in fewer files.

The important requirement is that model definitions live in the model/service layers, while experiment packages only orchestrate frozen services and create paper views.

---

# 33. Required dependency direction

Keep the primary dependency direction conceptually as:

```text
common
  |
  v
PRE
  |
  v
M1/state
  |
  v
M2/consequence
  |
  v
M3/decision
  |
  v
M4/evaluation
  |
  v
pipeline / experiments
```

With one deliberate service call:

```text
M3 recovery transition
    -> post-action StateScenarioSet
    -> M2 consequence service
```

This does **not** mean M2 imports M3.

Preferred dependency rule:

```text
M2 must never depend on M3.
M3 may invoke the public M2 consequence service.
M4 may consume M2/M3 outputs but must not own their scientific definitions.
experiments may consume public services but must not redefine them.
```

Avoid circular imports by placing shared contracts, IDs, enums, and small value objects in `common/` or another neutral package.

---

# 34. Core public contracts

The implementation should expose stable logical contracts equivalent to the following.

Exact Python syntax is flexible.

## 35.1 DecisionEvidence

```python
DecisionEvidence(
    episode_id,
    chain_id,
    node_id,
    decision_time,
    stage,
    split,
    scheduled_milestones,
    observed_milestones,
    dynamic_evidence,
    static_references,
    availability,
    support,
)
```

## 35.2 StateRepresentationSpec

```python
StateRepresentationSpec(
    temporal="CURRENT" | "HISTORY",
    uncertainty="POINT" | "MARGINAL" | "JOINT",
    history_capacity=None | 8 | 16,
    history_scope="FULL_PREFIX" | "FIXED_WINDOW" | None,
)
```

Do not encode Delay as a state representation.

## 35.3 StateScenarioSet

```python
StateScenarioSet(
    episode_id,
    chain_id,
    node_id,
    stage,
    representation,
    scenario_id,
    scenario_weight,
    T_IB,
    D_OB,
    D_TX,
    D_TO,
    support,
)
```

Invariant:

```python
D_TO == D_OB + D_TX
```

scenario by scenario.

## 35.4 ConsequenceProfile / ConsequenceScenarioSet

```python
ConsequenceScenarioSet(
    episode_id,
    chain_id,
    node_id,
    representation,
    scenario_id,
    scenario_weight,
    native_components,
    cu_components,
    domain_scores,
    consequence_priority,
    support,
)
```

## 35.5 PrioritySignal

```python
PrioritySignal(
    episode_id,
    chain_id,
    node_id,
    signal_type="DELAY" | "CONSEQUENCE",
    score,
    support,
)
```

The Stage-I selector must not care how the signal was constructed.

## 35.6 AttentionDecision

```python
AttentionDecision(
    episode_id,
    chain_id,
    node_id,
    signal_type,
    score,
    rank,
    q,
    K,
    selected,
)
```

## 35.7 RecoveryDecision

```python
RecoveryDecision(
    episode_id,
    chain_id,
    node_id,
    representation,
    actionable_status,
    headroom_summary,
    u_star,
    J_zero,
    J_star,
    recoverable_value,
    solver_status,
)
```

`recoverable_value` is required for the reference representation and may be omitted/null for comparator representations when only comparator action is needed.

## 35.8 DecisionEvaluation

```python
DecisionEvaluation(
    reference_id,
    comparator_id,
    delta_attention_value,
    L_att,
    delta_recovery_objective,
    L_rec,
    A0,
    A5,
    diagnostics,
    support_status,
)
```

---

# 35. Preferred service APIs

Prefer a small number of public service entry points instead of experiments importing internal helpers.

Illustrative APIs:

```python
build_decision_evidence(...)
```

```python
reconstruct_state(
    evidence,
    representation_spec,
) -> StateScenarioSet
```

```python
evaluate_consequences(
    state: StateScenarioSet,
) -> ConsequenceScenarioSet
```

```python
build_priority_signal(
    source,
    signal_type,
) -> PrioritySignal
```

```python
select_attention(
    signals,
    q,
) -> AttentionDecision
```

```python
solve_recovery(
    state,
    recovery_policy,
    consequence_service,
) -> RecoveryDecision
```

```python
evaluate_attention(
    reference_attention,
    comparator_attention,
    reference_consequence_basis,
)
```

```python
evaluate_recovery(
    reference_recovery,
    comparator_recovery,
    reference_objective,
)
```

Names may differ, but Section 4/5 orchestration should operate at roughly this level.

Experiments should not import:

- neural-network internal heads;
- raw CU scaling internals;
- raw transition helpers;
- private solver state;
- legacy action-response coefficients.

---

# 36. Recommended orchestration layer

Use a thin pipeline layer to coordinate the scientific services.

For example:

```python
state = state_service.reconstruct(evidence, representation)
consequence = consequence_service.evaluate(state)

signal = priority_service.build(consequence, signal_type)
attention = attention_service.select(signal, q)

recovery = recovery_service.solve(
    state=state,
    attention=attention,
    policy=policy,
)

evaluation = evaluation_service.compare(
    reference=...,
    comparator=...,
)
```

The pipeline layer owns sequencing, not scientific formulas.

Section 4 and Section 5 should call the same services.

---

# 37. Configuration framework

Separate **scientific configuration** from ordinary runtime configuration.

Recommended logical groups:

```text
ScientificConfig
    state definition
    consequence registry
    reference representation
    scenario count
    q nominal/grid
    turnaround reference
    U_max rule
    lambda nominal/grid
    action step
    evaluation formulas
    sensitivity definitions
```

```text
RuntimeConfig
    paths
    cache settings
    parallel workers
    logging
    output format
```

Do not allow runtime flags to silently change scientific definitions.

After scientific freeze, the Final-Test runner should load the frozen scientific configuration rather than reconstructing it from scattered constants.

---

# 38. Legacy coexistence strategy

Do not immediately delete legacy packages.

Preferred migration pattern:

```text
legacy implementation
        |
        | extract reusable primitives
        v
paper-primary V2 services
```

During migration:

- old action-template code may remain in place;
- old experiment scripts may remain runnable;
- new Section 4/5 must not call superseded primary logic.

Where feasible, explicitly label legacy primary paths as:

```text
LEGACY
PROVENANCE_ONLY
SUPERSEDED_FOR_PAPER
```

Do not spend substantial effort making old and new scientific APIs mutually compatible.

---

# 39. Suggested implementation order inside the framework

Within the previously defined Phase 0–7 plan, use this concrete construction order:

```text
1. common scientific contracts / IDs
2. PRE adapters + admissibility
3. M1 state service
4. M1 representation service
5. M2 consequence service
6. M3 Stage-I signal + selector
7. Train Stage-II support materializer
8. M3 Stage-II transition/objective/solver
9. M4 attention evaluator
10. M4 recovery evaluator
11. Section 4 orchestration
12. scientific freeze loader/writer
13. Final-Test materialization pipeline
14. Section 5 paper views
15. sensitivity / bootstrap views
```

This order is preferred because each later layer consumes stable public contracts from the previous layer.



# 40. Environment and dependency reproducibility

Reuse the repository’s existing environment mechanism when adequate. Do not create multiple competing environment specifications.

The paper-primary path must record enough information to recreate the computational environment:

- Python version;
- main package/environment specification (`pyproject.toml`, lock file, or existing equivalent);
- Pyomo version;
- HiGHS / `highspy` version;
- major numerical-library versions when they materially affect serialized models or numerical output.

Before Stage-II execution, perform one explicit solver preflight equivalent to:

```python
solver = pyo.SolverFactory("highs")
assert solver.available()
```

Do not silently switch to another solver when HiGHS is unavailable.

A missing/invalid environment is an engineering failure to repair, not a reason to change the scientific model.

---

# 41. Determinism and random-seed policy

All stochastic or pseudo-random scientific operations must be reproducible and independent of execution order.

This includes at least:

- scenario sampling when sampling is required;
- deterministic Marginal permutations;
- any randomized Point/representation helper if one remains;
- bootstrap resampling;
- stochastic model inference if applicable.

Use one frozen root seed plus deterministic child seeds derived from stable scientific keys, for example:

```text
root_seed
+ split
+ episode_id
+ node_id
+ representation
+ operation
```

Do not derive scientific randomness from:

- process ID;
- worker index;
- wall-clock time;
- unordered dataframe iteration;
- parallel completion order.

The same frozen inputs/configuration must produce the same scientific atomic outputs regardless of worker count.

Where an operation is designed to be deterministic by construction, keep it deterministic rather than merely setting a random seed.

---

# 42. Lightweight artifact identity and stale-cache protection

Artifact reuse must be safe.

Each reusable scientific artifact should carry lightweight metadata sufficient to determine whether it is compatible with the current run.

Recommended logical metadata:

```text
artifact_type
schema_version
scientific_spec_version
split_id
representation
source_artifact_ids
model/calibration/reference ids as applicable
root_seed / bootstrap_seed where applicable
code_commit
created_at
```

A cached artifact may be reused only when its scientific identity matches the requested computation.

Do not reuse an artifact merely because the filename exists.

If a scientific upstream dependency changes, invalidate downstream artifacts according to ownership:

```text
PRE/data semantics change -> invalidate M1 and everything downstream
M1/config change          -> invalidate M1-derived outputs and downstream
M2/formula/CU change      -> invalidate M2 and downstream
q change                  -> invalidate Stage-I and dependent recovery/evaluation
lambda/Umax change        -> invalidate Stage-II and recovery evaluation
M4 metric change          -> invalidate evaluation/paper views only
figure layout change      -> invalidate paper views only
```

This is a lightweight compatibility check, not a separate provenance database or hash-governance system.

---

# 43. Idempotency, atomic writes, and overwrite policy

Phase runners and materializers should be safe to re-run.

Requirements:

1. completed compatible artifacts may be reused;
2. incomplete or incompatible outputs must not be mistaken for completed results;
3. scientific outputs should be written atomically where practical:
   - write temporary file;
   - validate;
   - rename/move to final path;
4. do not overwrite historical or frozen artifacts silently;
5. overwriting a paper-primary artifact should require either:
   - exact compatible recomputation, or
   - explicit invalidation/new artifact namespace.

A failed run must not leave a final-looking partial CSV/Parquet/JSON that downstream phases can consume as valid.

---

# 44. Resumable and dependency-aware execution

Long phases should be resumable from validated scientific artifacts.

Do not require a full raw-data-to-paper rerun after an unrelated downstream failure.

The orchestration layer should support the equivalent of:

```text
resume from canonical evidence
resume from state variants
resume from consequence variants
resume from attention decisions
resume from reference recovery cohort
resume from recovery decisions
rebuild evaluation only
rebuild paper views only
```

Use the dependency graph already defined in this instruction to determine the minimum necessary rerun.

Do not implement a complex workflow engine unless the repository already uses one.

A simple validated artifact-exists/compatibility mechanism is sufficient.

---

# 45. Data/schema contracts and fail-fast validation

At the boundary of each scientific layer, validate the data contract before expensive computation.

At minimum validate:

## Canonical/PRE
- required identity fields present;
- identity keys non-null where required;
- no unintended duplicate scientific keys;
- timestamps parse correctly;
- milestone chronology is internally coherent where deterministically checkable;
- units match the canonical contract;
- split identity is present;
- decision-time admissibility fields exist.

## M1
- scenario weights finite and non-negative;
- weights normalize according to the frozen convention;
- required state primitives present;
- scenario identities unique within node where required;
- \(D^{TO}=D^{OB}+D^{TX}\).

## M2
- required state inputs supported;
- native units known;
- unsupported components remain explicitly unsupported;
- CU references exist before CU conversion.

## M3/M4
- cohorts contain unique canonical node keys;
- same-cohort comparisons truly use the same keys;
- q/K are internally consistent;
- reference cohort \(R^*\) is frozen before comparator Stage-II evaluation;
- objective inputs are finite on supported rows.

Fail fast on structural/schema corruption.

Use typed abstention only for scientifically legitimate lack of support, not for malformed files.

---

# 46. Parallelism and resource-control policy

Parallelize only where scientific independence is clear, such as independent episodes/nodes or bootstrap replicates.

Preserve deterministic ordering when materializing outputs.

Avoid CPU oversubscription caused by simultaneously using:

- Python multiprocessing;
- BLAS/OpenMP threads;
- LightGBM/other model threads;
- HiGHS threads.

Expose ordinary runtime controls such as:

```text
workers
solver_threads
model_threads
batch_size
```

with conservative defaults.

Runtime parallelism must not change scientific results.

Prefer vectorization/batching for M1/M2 scenario computation where already supported.

Do not parallelize by mutating shared scientific state.

---

# 47. Reproducible run entry points and smoke/integration checks

Provide a small set of top-level reproducible entry points for the paper-primary workflow.

Exact command names are flexible, but the repository should support the equivalent of:

```text
phase0 / audit
section4-development
freeze
final-test-primary
final-test-sensitivity
paper-views
validate
```

A Makefile/task runner/CLI is optional; reuse the repository’s existing command pattern if cleaner.

Avoid requiring users to manually execute many internal scripts in a fragile order.

Before expensive full runs, maintain a small deterministic smoke/integration fixture that exercises:

```text
PRE
-> M1
-> M2
-> M3 Stage I
-> M3 Stage II
-> M4
```

The fixture should include at least:

- one PRE actionable row;
- one TURN actionable row;
- one TAXI/COMP non-actionable row;
- one zero-headroom row;
- one positive-headroom row;
- multiple candidates for Top-K;
- at least two information representations.

The smoke fixture verifies wiring and contracts only. It must not be used as scientific evidence.

Also provide one final validation entry point that checks, at minimum:

- environment/solver availability;
- split isolation;
- frozen config loaded;
- required artifacts compatible;
- core scientific invariants;
- no unexpected legacy primary path invoked.

# 48. Start now

Begin with **Phase 0**.

Inspect the latest repository and current manuscript inputs, recover the real data/schema/legacy implementation facts, and produce the migration map.

Do not begin broad refactoring until the Phase-0 mapping is internally coherent.

Do not stop for ordinary engineering ambiguity. Use judgment, continue, and record the decision.

Escalate only when proceeding would require a new scientific assumption or would materially alter the scientific estimand.
