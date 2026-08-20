# Round 2 M2 Manuscript Alignment Audit

No TeX or manuscript source was edited.

## Section 3: consequence definition

Required model statement:

\[
q_k(s) \longrightarrow C_k^{0,CU}(s)=q_k(s)/c_k^{CU},
\qquad k\in\{1,\ldots,7\}.
\]

The manuscript must define the seven native quantities and units, state that the output is a scenario-indexed vector rather than a scalar monetary loss, and distinguish `C^{0,CU}` from the future M3-owned `C^{a,CU}`. It must not describe action response as part of M2 native consequence.

## Section 4: implementation and reference assumptions

The implementation description should include:

- the strict M1 scenario envelope and `D_TO = D_OB + D_TX` identity;
- one output row per component per scenario, with scenario weight preserved;
- distinct native and CU objects;
- CU registry hash, scale freeze ID, reference period, and version-sensitive artifact identity;
- the named `E_down` fallback hierarchy and confidence levels;
- the fact that no scenario is top-k filtered or collapsed before M2 output;
- `P_time` as an aggregate reference proxy and `P_itinerary`/`P_service` as abstentions.

## Current draft conflicts

`docs/manuscript/EXPERIMENTAL_EVALUATION_V5_DRAFT_20260818.md` around lines 70-75 remains stale:

1. it uses the old `R_IB -> DELTA_OB -> T_TX` chain and reconstructs `D_TO` from legacy variables;
2. it presents historical `M2_DATA2_FORMAL_CU_V1` and five principal components as the current formal chain;
3. it does not define the seven-component scenario vector or baseline/action separation;
4. it does not expose native-to-CU normalization metadata or exposure fallback lineage.

Historical V1 Development results may remain in the evaluation section only when explicitly labelled V1 and `NOT_FINAL_PAPER_RESULT`. They cannot be presented as V2 seven-component evidence.

## Missing definitions

- `q_k(s)` for all seven components and each native unit;
- `C_k^{0,CU}(s)` and the freeze constraint on `c_k^{CU}`;
- the immutable scenario distribution and weight convention;
- weighted mean, variance, CVaR level, and tail threshold;
- `E_down(node)` resolver level/source/reference/confidence;
- support semantics for `SUPPORTED`, `REFERENCE_BASED`, `PROXY`, and `ABSTAIN`;
- the future M3 interface from baseline `C^{0,CU}` to action-conditioned `C^{a,CU}`.

## Symbol conflicts and overclaims

- Do not use CU and monetary loss interchangeably; monetary mapping remains M4-only.
- Do not use unqualified `E_down` as though it were always an airport median.
- Do not call a passenger exposure proxy an observed itinerary or service outcome.
- Do not claim an all-seven formal scalar aggregate while two components and V2 scales remain unfrozen.
- Do not describe scenario response parameters as empirical causal effects unless separately supported.
