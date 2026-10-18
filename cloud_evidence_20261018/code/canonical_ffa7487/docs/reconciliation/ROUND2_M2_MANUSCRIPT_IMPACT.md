# Round 2 M2 Manuscript Impact

This is a paper-team handoff only. No manuscript or TeX source is modified in this tranche.

## Section 3: consequence definition

The methods section needs to define the M2 role as a scenario-conditioned operational-consequence representation:

\[
q_k(s)=g_k(T_{IB,A00}(s),R_{IB}(s),D_{OB}(s),D_{TX}(s),D_{TO}(s),x_{ref}),
\qquad
C_k^{0,CU}(s)=q_k(s)/c_k^{CU}.
\]

It must enumerate the exact seven-component ordered set and define the native unit/mechanism for each component. It must state that `P_time` is a route-level passenger-exposure proxy, while `P_itinerary` and `P_service` currently abstain. The text must not imply observed itinerary recovery, compensation, crew cost, gate cost, or internal airline cost.

The section also needs to distinguish baseline `C^{0,CU}` from later action-adjusted `C^{a,CU}`. The action response belongs after the native baseline mapping; it is not part of `q_k(s)`.

## Section 4: implementation

The current draft at `docs/manuscript/EXPERIMENTAL_EVALUATION_V5_DRAFT_20260818.md:72-74` is stale in two ways:

- it uses the pre-closure `D_TO = max(0, DELTA_OB + T_TX - taxi_ref)` identity rather than consuming M1's `D_TO = D_OB + D_TX`;
- it describes the historical five-component `M2_DATA2_FORMAL_CU_V1`, whereas M2 V2 freezes a seven-component ontology whose all-seven formal aggregate is not yet available.

Implementation text should state that M2 consumes typed M1 scenario envelopes with PRE/reference lineage, rejects future schedule information, and resolves `E_down(node)` through the explicit same-aircraft, same-route, airport, and global hierarchy. It should also state that scenarios remain separate through M2; weighted mean, variance, CVaR, and tail analysis are downstream summaries, not inputs to the native mapper.

Any existing Development result produced with `M2_DATA2_FORMAL_CU_V1` must remain labelled as historical V1 evidence. It cannot be relabelled as an M2 V2 seven-component result without a new frozen V2 normalization registry and a newly authorized run.

## Appendix: valuation and reference assumptions

The appendix needs:

- the train/reference-only rule for `c_k^CU`, including reference period, freeze ID, and component-specific normalization rule;
- the statement that CU is cross-component normalization, not money;
- a separate M4 monetary equation `L_k^m=f_k^m(C_k^{CU})` and monetary-registry lineage;
- the exposure fallback hierarchy with support level, reference source, confidence, cutoff, and 360-minute horizon;
- the exact passenger reference scope and explicit abstentions;
- any future literature proxy's citation/reference ID and applicability scope.

## Missing equations and definitions

1. Seven native mappings `q_k(s)` and their units.
2. `C_k^{CU}=q_k/c_k^{CU}` with frozen-parameter constraints.
3. Baseline/action separation: `C^{0,CU}` versus `C^{a,CU}`.
4. Node-specific `E_down(node)` and its ordered fallback operator.
5. Weighted scenario mean, variance, CVaR level `alpha`, and tail threshold/probability.
6. The support rule: an unsupported included component yields an unavailable formal aggregate, never zero-fill/drop/renormalize.

## Symbol conflicts to resolve

- Avoid using valuation or monetary-loss notation for CU; reserve `L^m` for M4.
- Avoid using `E_down` without a node argument or fallback-level qualifier.
- Keep `D_OB`, `D_TX`, and `D_TO` aligned with the M1 V2 public identities; do not reintroduce `DELTA_OB` or `T_TX` as downstream formal variables.
- Distinguish passenger volume/exposure (a reference proxy) from itinerary-disruption event counts.
- State whether `LF`/`LP` are channel-level groupings or scalar losses; they must not replace the seven component identifiers without a mapping table.

Paper editing remains gated on the human decisions recorded in `ROUND2_M2_V2_DESIGN.md`.
