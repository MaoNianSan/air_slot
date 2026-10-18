# G0 Scientific Audit — 2026-10-11

Status: `G0_CLOSED_OR_TYPED_BLOCKED`

| Check | Status | Evidence | Blocks |
|---|---|---|---|
| G0-1 decision time / screening budget | `PASS` | Existing read-only audit and `model/M3/stage1.py` | None for retrospective Stage-I |
| G0-2 weighted Marginal | `PASS_MARGINAL_PRESERVATION` | Existing audit, 238 paired nodes | E3 pure-dependence interpretation still needs a coupling decision |
| G0-3 native units / time / CU | `UNKNOWN_BLOCKED_UNIT_CONTRACT` | Existing trace, 45,934 formula rows | Raw-to-primitive closure and TAXI trace |
| G0-4 headroom / 7×u response | `PASS_SOURCE_CONTRACT_AUDIT_PENDING_CASE_TRACE` | Existing formula checks and `model/M3/transition.py` | New corrected response claims until case trace closes |
| G0-5 lineage / yearly partitions | `FROZEN_BUT_LINEAGE_PARTIAL` | Existing lineage audit and PRE manifests | E4 Test and paper release |
| G0-6 reference / wording boundaries | `PASS_WORDING_BOUNDARIES_DOCUMENTED` | Existing G0 report and authority file | None |

## Scientific decisions requiring confirmation

- D1 Marginal coupling: exact weighted-marginal coupling, constrained approximate coupling, or diagnostic dependence ablation.
- D2 `F_continuity` time base: retain current `r_ib` semantics or version a corrected `T_IB` implementation.
- D3 `DELAY_EXPOSURE`: defer and run `DELAY_EXPECTED` only, or approve a pre-specified exposure score.
- D4 `FIXED_COMMON`: approve an audited pre-test reference source or keep the cross-year track blocked and run `YEAR_LOCAL` only.

No decision item was silently selected. Existing non-dependent engineering preparation may continue.
