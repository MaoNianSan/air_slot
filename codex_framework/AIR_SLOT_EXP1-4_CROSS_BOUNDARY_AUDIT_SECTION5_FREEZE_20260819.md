# AirSlot Exp1–Exp4 Cross-Boundary Audit and Section 5 Freeze

## 1. Basis

This audit aligns the experiment architecture with the active Sections 1--4 manuscript center:

\[
\mathcal E_{i,\le t}\rightarrow\mathcal S_{i,t},
\qquad
(\mathcal E_{i,t},\mathcal R)\rightarrow\mathcal A_{i,t},
\qquad
(\mathcal E_{i,t},\mathcal S_{i,t},\mathcal A_{i,t})\rightarrow\mathcal D_{i,t}.
\]

The paper has two primary methodological requirements:

1. cross-stage information sharing;
2. state dependence / preservation of the same history-conditioned operating realization.

Distributional modeling is an information-preserving implementation, not a separate novelty claim. Rolling recovery itself is established prior art. Action-space extensibility is an interface property, not a third research gap.

---

## 2. Final ownership matrix

| Experiment | Owns | Must not own |
|---|---|---|
| Exp1A | Direct downstream reuse of current information | consequence granularity; refresh; benchmark adequacy |
| Exp1B | History-mediated state formation | FAST-vs-FULL architecture benchmark; joint-vs-marginal |
| Exp2A | Point/marginal/joint representation of the same frozen state | history length; direct-info permissions; state vintage |
| Exp2B | Scalar/channel/component consequence representation of the same frozen basis | information completeness; action-set changes; process timing |
| Exp3A | Refresh/aging of an initially valid recommendation | validity at issue time; rolling as novelty |
| Exp3B | State-vintage synchronization | representation granularity; action-set changes |
| Exp4A | Predictive adequacy across operational lead time | pure history-effect attribution |
| Exp4B | Recommendation admissibility at issuance | recommendation aging; action-effect truth |
| Exp4C | Portability under weaker observability/support | universal external generalization |
| Exp4D | End-to-end computational adequacy | methodological novelty |

---

## 3. Structural corrections made

### 3.1 Exp1A

Old headline:

```text
DELAY_ONLY
CONSEQUENCE_ONLY
FULL
```

Problem:
`DELAY_ONLY` simultaneously neutralized episode-specific consequence context, overlapping with Exp2B and weakening the direct mapping to the manuscript's two information paths.

Frozen headline:

```text
NO_DIRECT_REUSE
FULL
```

Interpretation:
both variants keep the full chain; only downstream direct reuse of current information is restricted after state/consequence formation.

Old delay/context-neutralization machinery may remain Appendix/legacy only.

### 3.2 Exp1B vs Exp4A

Potential duplication:
history ablation and FAST-vs-state-aware benchmark could become the same experiment under different names.

Freeze:

```text
Exp1B:
same state-aware architecture/capacity/heads
CURRENT vs ADAPTIVE history

Exp4A:
Historical vs LIGHTGBM_FAST vs RF vs STATE_AWARE_FULL
0--480 min lead-time adequacy
```

If `CURRENT` cannot be implemented under controlled architecture, Exp1B must state partial isolation rather than presenting FAST-vs-FULL as a pure history effect.

### 3.3 Exp2

All headline variants must be derived from the same FULL/ADAPTIVE frozen artifact.

Exp2 changes representation only.

`J_ref` remains internal complete-reference model-consistency diagnostic and cannot independently prove action superiority.

### 3.4 Exp3 vs Exp4B

Freeze the temporal distinction:

```text
Exp3A:
an initially valid recommendation -> does it remain executable as it ages?

Exp4B:
a recommendation at its current issue time -> is it admissible now?
```

The same word "feasibility" must not obscure the two denominators.

### 3.5 Action-family composition

Ownership:

```text
Exp2B = headline mechanism evidence
Exp3 = supplementary process description
Exp4B = descriptive cohort/system characterization
```

This avoids three experiments repeating the same stacked bar as if each were a separate result.

### 3.6 Shared-state efficiency

Not Exp1 scientific evidence.

Location:

```text
Exp4D Appendix computational mechanism diagnostic
```

It must pass output parity; otherwise the runtime comparison is invalid.

---

## 4. Final Section 5 narrative

Recommended paper structure:

### 5.1 Evaluation design and evidence hierarchy

State once:

- Data2 primary evaluation environment;
- episode-cluster inference;
- frozen Train/Calibration/Development/Test discipline;
- realized outcomes never enter decision-time inference;
- action-response replay is model-implied, not causal treatment-effect evidence;
- `J_ref` in Exp2 is internal diagnostic;
- observed predictive outcomes and hard admissibility rules are stronger evidence than LLM audit.

### 5.2 Why cross-stage information retention is needed — Exp1

#### 5.2.1 Direct downstream information reuse
`NO_DIRECT_REUSE vs FULL`

Main question:
does state/consequence mediation alone suffice?

#### 5.2.2 History-mediated state formation
`CURRENT vs ADAPTIVE`
with fixed-history baseline only if formally supported.

Main question:
does the current snapshot suffice?

Do not show the full 0--480 benchmark here.

### 5.3 Why the retained information needs the proposed representation — Exp2

#### 5.3.1 Uncertainty and dependence representation
`POINT -> MARGINAL -> JOINT`

Headline evidence:
CRPS parity + Variogram Score + decision disagreement.

#### 5.3.2 Consequence mechanism representation
`SCALAR -> 3-CHANNEL -> 7-COMPONENT`

Headline evidence:
decision disagreement + action-family composition + pre-registered matched cases.

`J_ref` is secondary/internal.

### 5.4 How the fixed chain should operate as information evolves — Exp3

#### 5.4.1 Recommendation refresh
`ONE_SHOT vs ROLLING`

Headline:
aging/executability of initially valid recommendation.

#### 5.4.2 State synchronization
`SYNC vs LAG5 vs LAG10`

Headline:
controlled model-implied replay / decision differences under identical current action sets.

Do not claim rolling recovery itself is new.

### 5.5 Is the complete chain empirically and operationally adequate? — Exp4

#### 5.5.1 Predictive adequacy
Historical / FAST / RF / FULL across 0--480 min.

#### 5.5.2 Decision-output admissibility
availability + factual/structural/execution/evidence/leakage audits.

#### 5.5.3 Cross-data portability
Data2 vs Data1 on common semantic support.

Primary inference is **within each dataset**:

```text
FULL - LIGHTGBM
```

and whether that pattern is retained across evidence environments. Raw Data1-vs-Data2 absolute error differences are descriptive, not portability effects.

#### 5.5.4 Computational adequacy
E2E p50/p95/p99 and 300-s rolling budget.
Shared-vs-recomputed only as Appendix diagnostic.

---

## 5. Evidence hierarchy to use in writing

Strongest to weakest:

1. observed outcomes for prediction;
2. hard decision-time operational/evidential validity rules;
3. controlled ablation/representation/process comparisons;
4. model-implied ex-post replay under frozen action-response assumptions;
5. internal complete-reference `J_ref` diagnostics;
6. auxiliary LLM plausibility audit.

Never reverse this hierarchy in Abstract, Results, or Discussion.

---

## 6. Claim map

### Exp1 supported claim

Allowed:
"Retaining admissible history and permitting declared current information to remain directly reusable can alter the state and recovery comparison."

Not allowed:
"All information must always be shared with every module."

### Exp2 supported claim

Allowed:
"Marginal accuracy can be preserved while dependence-sensitive state representation and selected interventions change."

Allowed if data support:
"Similar aggregate consequence can imply different interventions when mechanism composition differs."

Not allowed:
"Joint/7-component representation is causally optimal."

### Exp3 supported claim

Allowed:
"Under an already rolling recovery setting, recommendation refresh and time-aligned state propagation can matter when new information arrives."

Not allowed:
"Rolling recovery is novel" or "5-min refresh is universally optimal."

### Exp4 supported claim

Allowed:
"The frozen chain attains the reported predictive accuracy, admissibility, support portability, and runtime on the evaluated environments."

Not allowed:
"The framework proves real-world causal recovery savings" or "universal generalization."

---

## 7. TRE / JORS / Omega interpretation

### TRE
Best fit of the frozen structure:
transportation recovery problem -> interface-consistency mechanism -> controlled evidence -> operational adequacy.

### JORS
Same experiments remain usable; emphasize structured OR methodology, controlled comparisons, and operational decision-support validity.

### Omega
Do not redesign now. Only elevate broader insight if results support patterns such as:

- similar marginal accuracy but different prescriptions;
- similar aggregate consequence but different interventions;
- reduced observability contracts decision authority rather than inducing unsupported recommendations.

---

## 8. Freeze decision

The first-order experimental architecture is now frozen as:

```text
Exp1 = information-role necessity
Exp2 = representation necessity
Exp3 = temporal/process operation
Exp4 = complete-system adequacy
```

Further changes should be triggered only by:

- model-contract incompatibility;
- inability to isolate a planned ablation fairly;
- insufficient formal multi-action cohort;
- lack of semantic support in Data1;
- leakage or evaluation-circularity audit failure.

Do not re-open the top-level experiment story merely because a particular result is weak.


---

## 9. Main-text presentation budget

Recommended main experiment figures:

1. **Exp1**: one 2-panel figure;
2. **Exp2**: one 2×2 figure;
3. **Exp3**: one 2×2 figure;
4. **Exp4**: at most two figures:
   - predictive adequacy (MAE + CRPS);
   - operational adequacy (validity + portability + runtime).

Thus the main experiment section should target roughly **5 figures**, not 7–9 separate benchmark figures.

Detailed:

- calibration curves;
- all delay thresholds;
- full action-family tables outside Exp2B;
- `J_ref`;
- old sensitivity grids;
- stage-latency decomposition;
- LLM reliability details;
- shared-vs-recomputed runtime diagnostic

should default to Appendix / supplementary material.

This is preferable for TRE/JORS because the main paper should read as a sequence of answers to research questions rather than a catalogue of model diagnostics.


---

## 10. Appendix-only action-interface extensibility check

The manuscript treats action-space extensibility as an **interface property**, not a third research gap. It therefore should not become Exp5 or another headline experiment.

A low-cost Appendix contract check is nevertheless recommended.

### Protocol

Choose one already declared action contract \(a^\star\) before Final Test and perform a held-out-library replay:

```text
R_minus = R \ {a*}
construct/freeze upstream state and baseline consequence artifacts
then add a* back only through its declared action contract
```

Verify:

1. upstream admissible-information artifact unchanged;
2. M1 state/scenario hashes unchanged;
3. baseline consequence artifact unchanged;
4. only episode-specific action instantiation / action-conditioned consequence / comparison objects change;
5. support/provenance of \(a^\star\) remains exactly its declared contract;
6. no model retraining or upstream-state redefinition is required.

### Interpretation

Allowed:

> The implemented separation permits an additional declared action contract to enter the existing action branch without redefining the upstream recovery state.

Not allowed:

> Arbitrary recovery actions can always be added.

This is a software/method contract demonstration, not a performance benchmark and not a new contribution category.
