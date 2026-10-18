# Round 2 Framework Figure Alignment

## Current status

`MISSING_EXPLANATION`.

The inspected PDF contains no Figure 1 and no occurrence of `Figure` or `Fig.`. Section 3 has equations and tables but no visual framework. Therefore the current manuscript cannot be audited as having a framework figure; it only has a prose-level chain.

## Required conceptual dependency for a future figure

The figure should express one directed workflow:

```text
Information layer (PRE)
E_<=t -> admissible history | r_fast | c_static
                    |
                    v
State layer (M1)
chi_t -> weighted scenarios z_t,s
                    |
                    v
Consequence layer (M2)
native q_k(s) -> baseline C_k^{0,CU}(s)
                    |
                    v
Action layer (M3)
eligibility I(a) + response P(a) -> C_k^{a,CU}(s)
                    |
                    v
Risk layer (M4)
monetary system f^m -> L^{a,m}(s) -> weighted residual risk J^m(a)
```

## Dependencies the figure must show

- PRE cutoff/provenance controls every downstream input.
- `chi` contains history, current fast information, and static context.
- Scenario identity and weight continue through M2, M3, and M4.
- Native quantity, CU, and money are distinct transitions.
- M3 receives the baseline consequence and produces action-conditioned consequence; it does not rank actions.
- M4 consumes the post-response distribution; it does not create an action response.
- A00 is an identity branch from `C^{0,CU}` to `C^{A00,CU}`.
- Missing response or valuation support leads to `ABSTAIN`, not a hidden fallback.

## Visual claims to avoid

- Five disconnected boxes with no typed arrows.
- A direct arrow from raw information to recommendation.
- A direct arrow from delay to RMB.
- A loop suggesting M4 rewrites M1 state or M3 response.
- Equal visual status for `SUPPORTED`, `SCENARIO_ASSUMPTION`, and `ABSTAIN` actions.
- A “causal” arrow that could be read as an identified treatment effect.

Figure status for this tranche: `MISSING`; no bitmap, vector, TeX, or manuscript figure was created.
