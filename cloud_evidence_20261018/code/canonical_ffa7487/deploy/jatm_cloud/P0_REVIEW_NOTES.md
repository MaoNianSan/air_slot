# P0 resubmission contract

Status: INDEPENDENT_REVIEW_PENDING. This change does not authorize cloud upload,
benchmarking, full Development execution, training, or Test/Final-Test access.

The independent report dated 2026-10-12 resolves the main Stage-II population as
canonical PRE/TURN chain-stage cases with full HJ recovery support, independently
of screening selection. Unsupported earliest canonical cases are not replaced.
C3 retains admissible repeated rolling epochs; it is separate from main C1 and
does not contribute extra epochs to the canonical Coverage@K denominator.

C2 is a dictionary of independent contrast descriptors keyed by year, stage, q,
contrast, reference objective and CU track. Each descriptor stores the common
screening candidates, each shortlist, their union, paired Stage-II members and
exclusions. E1 screening unions never augment E2 representation-loss cohorts.
The current runner still executes its existing nominal q=0.10, balanced E2
contrast; this P0 fix does not introduce additional q/objective experiments.

The primary recovery_loss.L_rec is sum(delta_rec)/sum(V_ref) on paired support.
Each bootstrap draw resamples complete episodes with multiplicity and recalculates
both sums. Valid zero-V cases are retained; a zero total denominator is undefined.
Node-mean ratios are explicitly named diagnostics. E3 uses the corresponding
Joint objective's V, never Marginal's own recoverable value as reference.

E2/E3 summary schema is V2. E4 requires this population/estimand contract,
full-run manifests, both CU tracks and current input/code/output receipt hashes.
Missing/failed/invalid years prevent six-year completion. The scheduler only
enters complete E4 after all six successful worker outcomes pass annual checks.
All-six computed status remains pending scientific review, never scientific PASS.

Unchanged scientific services: PRE/M1/M2, exact weighted Marginal, finite Stage-II
enumeration, nominal 41/45/0.25 and the four approved mechanism operators.
The 21 missing annual files and Linux/CUDA NOT_RUN limitations remain. F_continuity
reconciliation, full exposure Coverage@K, sensitivity/heterogeneity and stage-level
reuse are deferred issues from the independent report, not silently marked closed.

Targeted reproduction (small fixtures only):

```text
python -m pytest -q tests/contract/test_jatm_p0_acceptance.py
python -m exp.jatm_s34.p0_acceptance --source-root artifacts/experiment/jatm_s34/shared_cloud_integration_20261012/shared --output-root artifacts/experiment/jatm_s34/independent_review_p0_20261012/real_cache
python -m exp.jatm_s34.shared_golden --output-root artifacts/experiment/jatm_s34/independent_review_p0_20261012/current_tail_golden
```

The existing cached fixture retains its original legacy tail identity. Its
statistics/recovery acceptance is separate from the current-tail golden check.
Neither provides full annual scientific results.
