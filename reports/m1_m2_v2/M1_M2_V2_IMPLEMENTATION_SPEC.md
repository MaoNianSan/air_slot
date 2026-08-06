# M1-M2 V2 Implementation Specification

Date: 2026-08-06

## Scope

The implemented boundary is:

    Published PRE bundle
    -> M1 five-minute snapshots and calibrated marginals
    -> structurally coupled M1ScenarioBundle
    -> M2InputBundle with PRE context
    -> DIRECT_STRUCTURAL_COMPACT subitems
    -> subitem constructed units
    -> channel RMB loss

M3 action response, action cost, feasibility, and M4 ranking are outside this
implementation. The global pipeline stops with M3_CONTRACT_MISMATCH.

## M1 Model Boundary

The M1 architecture remains one unidirectional, one-layer GRU with hidden size
8 and sensitivity size 16. It retains three heads: R_IB, R_OB, and T_TX. No
fourth takeoff head, attention, Transformer, LightGBM, copula, online training,
or M2 backpropagation was added.

The model API distinguishes forward_sequence for a full episode and step for
exactly one incremental snapshot node.

## M1 Scenario Contract

M1ScenarioBundle groups metadata, operational references, marginal
distributions, sampling metadata, joint samples, and PRE context. Each sample
exposes r_ib_minutes, r_ob_minutes, earliest_offblock_time, predecessor
in-block, successor off-block, successor takeoff, taxi time, derived delays,
overflow flags, evidence, and fallback status.

The dependence claim is limited to
CONDITIONAL_INDEPENDENCE_WITH_STRUCTURAL_COUPLING. It is not described as a
fitted full multivariate joint distribution.

## Sampling

Finite bins use FIXED_WITHIN_BIN_UNIFORM. Bin selection and within-bin
position use distinct stable random streams. Overflow uses a training-only
EmpiricalTailArtifact containing target, lower bound, training tail values,
count, version, source split, and minimum support.

Non-TRAIN tail sources are rejected. When overflow has no resolved empirical
tail, the value is unresolved rather than replaced with the overflow lower
bound. M2 then blocks formal tail publication.

## M2 Input and Validation

M2InputBundle combines M1 samples, PRE-derived operational/flight/passenger/
resource context, subitem activation, valuation and rule parameters, and
evidence/proxy/tail audit status.

The adapter sorts sample IDs, derives equal weights 1/S, and checks episode,
snapshot, cutoff, sample count, reference provenance, R_IB identity, R_OB
identity, and taxi identity.

## Events, Subitems, and Rules

M2 constructs TURN_DEFICIT or proxy semantics, EXTRA_OFFBLOCK_WAIT equal to
R_OB, extra taxi time, and total takeoff delay.

Candidate subitems:

    F: TURN, WAIT, PROPAGATION
    P: DELAY, CONNECTION, CARE
    R: GROUND, TAXI, SCARCITY

Activation states are ACTIVE, PROXY_ACTIVE, UNSUPPORTED, and
DISABLED_BY_CONFIG. Unsupported is preserved as unavailable and is not
relabelled as zero loss.

The compact rule family includes continuous accumulation, excess
accumulation, piecewise marginal with at most two nonzero breakpoints,
threshold events, and one bounded context multiplier. High-order
interactions and neural reconstruction are disabled.

Production value and rule parameters remain NOT_CONFIGURED until a
development freeze. Tests inject explicitly labelled fixture parameters.

## Constructed Units and RMB

Each active subitem is converted before aggregation:

    C[g,j] = v[g,j] * Q[g,j]
    C[g] = sum_j C[g,j]
    L[g,RMB] = kappa[g] * C[g]

The current currency layer is 1 CU = 1 RMB with separate channel rates.
Changing currency rates does not change quantities or constructed units.

## Tail Publication

If unresolved overflow is present, M2 status is ABSTAIN, formal total loss is
unavailable, and formal q95/CVaR90 are unavailable. Overflow probability and
tail status remain visible.

## Current Status

    M1_CORE_ARCHITECTURE=UNCHANGED
    M1_M2_V2_CODE_STATUS=VALIDATED_BY_TARGETED_TESTS
    M1_FORMAL_TRAINING_STATUS=NOT_RUN
    M1_FORMAL_CALIBRATION_STATUS=NOT_RUN
    M1_FORMAL_EVALUATION_STATUS=NOT_RUN
    M3_STATUS=M3_CONTRACT_MISMATCH
    M4_STATUS=MIGRATION_REQUIRED
    GLOBAL_FORMAL_RERUN=NOT_RUN
