# AirSlot V2 - Scientific Freeze Summary (DRAFT)

- status: `DRAFT_NOT_ACTIVATED`
- freeze_commit: `PENDING`
- draft artifact hash: `sha256:286c27fc858ec06721e84e13f311ce4c4e3b0e38b93d351807276b32c45b94d3`
- activation owner: `PHASE_6_SCIENTIFIC_FREEZE` (not executed)
- new Final Test executed this round: `NO` (`FINAL_TEST_ACCESS_COUNT=1` unchanged)

This document is a **draft only**. It does not activate the scientific
freeze, does not authorise Final Test, and must not be cited as a formal
freeze.

## 1. Split definitions

- `train`: window=2019-01-01..2019-06-30 (parameter fitting and Train-derived support only)
- `calibration`: window=2019-07-01..2019-07-31 (M1 calibration only)
- `development`: window=2019-08-01..2019-09-30, episodes=128, decision_nodes=1769 (Section-4 Development comparisons)
- `final_test`: window=2019-10-01 onward, new_access_requested=False, final_test_access_count_this_round=1 (sealed; Phase 7 only)

## 2. Canonical node rule

Rolling decision nodes are rebuilt from the rolling PRE environment; the published PRE state at the frozen M1 cache position is the cross-artifact identity authority, and the node's information cutoff may never exceed its decision time.

## 3. Common support rule

- owner: `M2_COMPARISON_SUPPORT`; PRE: `EVIDENCE_AND_DATA_SUPPORT_ONLY`
- rule id: `M2_COMMON_SUPPORT_NOMINAL_0P90`
- nominal threshold: `0.9`
- predefined sensitivity: `[]` (NO_MANUSCRIPT_PREDEFINED_SENSITIVITY_VALUES)
- missing / unsupported / zero: `STRICTLY_DISTINCT`
- below threshold: `TYPED_ABSTAIN_NO_ZERO_FILL`

## 4. Primary M1 model and calibration

- model: `HISTORY_H16_PRIMARY` (`M1_STATE_ESTIMATOR_V2_H16`)
- hidden size: `16`; history mode: `FULL_ADAPTIVE_CAUSAL_PREFIX`
- seed `20260813`, epochs `8`, optimizer `Adam`, lr `0.001`, weight decay `0.0`, batch `64`
- checkpoint hash: `sha256:061c3540c38ad8272982590de437d27064d50b1e023b55b672e77392d2c4ac3b`
- History primary is H16: `True`
- lower-capacity sensitivity: `HISTORY_H8_SENSITIVITY` (hidden `8`, matched contract `PASS`)
- calibration id: `sha256:f8747ac873c8bc930b50985b254912425a05e3384e50fabf91047ac4c26772e3`

## 5. Reference representation and scenario count

- representation: `HISTORY_H16:JOINT` (temporal `HISTORY`, uncertainty `JOINT`)
- Point rule: `FROZEN_WEIGHTED_JOINT_MEDOID`
- Marginal rule: `DETERMINISTIC_COORDINATE_PERMUTATION` (`NOT_A_CLAIM_OF_PHYSICAL_INDEPENDENCE`)
- realized milestones: `COLLAPSE_TO_WEIGHT_ONE_POINT`
- scenario count: `64`

## 6. Seven consequence definitions (V5)

- `F_continuity = max(0, T_IB - turnaround_reference)`
- `F_execution = D_OB`
- `F_propagation = D_TO * expected_downstream_exposure`
- `P_time = N_pax * D_TO`
- `P_itinerary = N_pax * s_conn * I[D_TO > 45]`
- `P_service = N_pax * I[D_TO >= 180]`
- `R_operating = D_TX`

CU registry: `M2_DATA2_FORMAL_CU_V5` `sha256:fd3ccfa0c56ba64d840ab163b5a133a5b0d6a662249d89af38c7377f6f24b030` (scientific `HUMAN_APPROVED_PENDING_FREEZE`, implementation `MATCH`).

Scale adoption: `FIVE_PRINCIPAL_MEDIANS_PLUS_TWO_EVENT_NORMALIZATIONS`; principal scale source `M2_DATA2_FORMAL_CU_V4_PLUS_CORRECTED_F_CONTINUITY`; event scale source `ASSUMPTION_EVENT_NORMALIZATION`.

## 7. Priority signals

- `P^C` (UNIQUE_CONSEQUENCE_BASED_PRIORITY_AUTHORITY): `P^C = Phi_C(C^CU)`
- `P^D` (PARALLEL_DELAY_COMPARATOR): `P^D = E[D^{+,TO} | Omega^CS]` -> `(1 / m^CS) * sum_{s in Omega^CS} w_s * D^{+,TO}_s`
- `P^D` authority: manuscript section 4 eq:empirical_delay_score (lines 336-344)
- legacy deviation recorded: exp/shared/recovery_priority.py::summarize_delay_score (weight sum without m^CS renormalisation, all-or-nothing scenario support) - recorded deviation, not paper-primary
- shared Stage-I selector: `True`; A00 recommendation forbidden: `True`

## 8. Stage I attention allocation

- `K = ceil(q * N)` with `q0=0.1` and grid `[0.05, 0.1, 0.2, 0.3]`
- tie break: `(-score, episode_id, node_id)`
- operates on `COMMON_SUPPORT_NODES_ONLY`
- A00 never recommended: `True`

## 9. Stage II recovery and solver

- actionable stages: `['PRE', 'TURN']`; non-actionable: `['COMP', 'TAXI']` -> `NOT_ACTIONABLE`
- transition: A proposed recovery action shifts the node's successor departure time by u minutes inside PRE/TURN stages only; the post-action state is mapped through the same M2 consequence service. TAXI/COMP stages admit the singleton action set {0} and return NOT_ACTIONABLE; no action-specific percentage reduction is ever applied.
- turnaround lower bound: `T^{turn,lb} = Q20(T^{turn} | Train)` (sensitivity `[0.1, 0.3]`)
- headroom: `U_max = floor5(Q90(H^{+,fact} | Train))` nominal `45.0` minutes, sensitivity `[0.8, 0.95]`
- action step: `5.0` minutes
- objective: J(u) = sum_s w_s * Phi_C(C^CU(s, u)) + lambda * u / U_max, with ties broken towards the smaller u; the recoverable value is V = J(0) - J(u*).
- lambda nominal `0.25`, grid `[0.1, 0.25, 0.5, 1.0]`, tie break `SMALLER_U`

Solver: formal path `EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID`; `PYOMO_HIGHS` is a `REPRESENTATIVE_PRE_TURN_CASES_ONLY` parity backend; recorded as a long-term deviation: `False`.

## 10. M4 common-basis evaluation

- `L_att = [A*(H*) - A*(H^(r))] / A*(H*), reported with overlap, entered/displaced nodes, coverage and Kendall/Spearman statistics`
- `L_rec = sum_i [J_i(u_i^*(r)) - J_i(u_i^*)] / sum_i V_i^* on the fixed cohort R_g* = H_g^{C,*} intersect StageIISupported; a zero denominator returns UNDEFINED_ZERO_RECOVERABLE_VALUE, and no L_total is ever constructed`
- fixed Stage-II cohort: `R_g* = H_g^{C,*} intersect StageIISupported`
- zero denominator: `UNDEFINED_ZERO_RECOVERABLE_VALUE`
- `L_total` constructed: `False`
- monetary branch: `SECONDARY_INTERPRETATION_ONLY`

## 11. Bootstrap

- B = `2000`, unit `episode_id`, paired `True`, interval `percentile_95`, shared plan `True`

## 12. Predefined sensitivity list

- `m^CS`: nominal `0.9`, grid `[]` (NO_MANUSCRIPT_PREDEFINED_SENSITIVITY_VALUES)
- `q`: nominal `0.1`, grid `[0.05, 0.1, 0.2, 0.3]`
- `lambda`: nominal `0.25`, grid `[0.1, 0.25, 0.5, 1.0]`
- turnaround quantile: nominal `0.2`, grid `[0.1, 0.3]`
- headroom quantile: nominal `0.9`, grid `[0.8, 0.95]`

## 13. V4 -> V5 CU supersession

- superseded: `M2_DATA2_FORMAL_CU_V4`; adopted: `M2_DATA2_FORMAL_CU_V5`
- principal components: `FIVE_TRAIN_POSITIVE_MEDIANS_RETAINED_FROM_V4`
- `P_itinerary` scale `1.0` (`ASSUMPTION_EVENT_NORMALIZATION`, empirical median `False`)
- `P_service` scale `1.0` (`ASSUMPTION_EVENT_NORMALIZATION`, empirical median `False`)
- passenger formula: P_itinerary = N_pax * s_conn * I[D_TO > 45] (DB1B continuation share retained)
- legacy references retained: `['T-100 expected pax', 'DB1B connection share']`

## 14. Phase 5 Train support and Development families

- Train rotations: `2668531` (population gates `True` / median match `True`)
- turnaround quantiles (minutes): `{'q10': 34.0, 'q20': 41.0, 'q30': 47.0}`
- `U_max`: `45.0` minutes; action grid size `10`
- Family A artifact hash: `sha256:92dd3769c4e7516a8203f2a174868a61ad2d1a33d2e16fcea1e0816de56c1e52`
- Family B artifact hash: `sha256:e7706447a308d3c7b3c3338f23e752a85b31fb907a879e206f052c395e654467`

## 15. Rulings recorded this round

- `R1`: P_itinerary = N_pax * s_conn * I[D_TO > 45]; the DB1B historical continuation share stays in the formula. (authority: manuscript body (corrected in the review copy))
- `R2`: CU normalization = five principal positive Train medians plus two assumption-grounded event components with scale 1.0. (authority: owner decision; registry M2_DATA2_FORMAL_CU_V5)
- `R3`: Stage-II formal path is exact enumeration; Pyomo+HiGHS is a parity backend only. (authority: instruction rev2 section 11)
- `R4`: P^C is the unique consequence-based priority authority; P^D is the parallel delay comparator; both share one Stage-I selector. (authority: instruction rev2 sections 5/7/8)
- `R5`: common support m^CS >= 0.90 nominal belongs to M2; PRE owns evidence/data support only. (authority: instruction rev2 sections 5/12)
- `R6`: m^CS sensitivity stays empty because the current manuscript body predefines no numeric sensitivity values. (authority: manuscript body; appendix grid is not authoritative)
- `R7`: The superseded turnaround reference sha256:7c6ac016 was an active M2 node-reference input, not stale metadata. The V2 chain binds the corrected Data Gate A2 reference (sha256:aa241b90) and keeps the superseded artifact as provenance only. (authority: freeze-precheck audit 2026-09-19; registry M2_DATA2_FORMAL_CU_V5)
- `R8`: The M2 node reference stays the airport-conditioned empirical Train median with global fallback; T^{turn,lb} = Q20 = 41 minutes stays a separate Stage-II lower-tail support. Substituting the scalar Q20 bound into the node reference was rejected because it would redefine F_continuity. (authority: DATA2_TURNAROUND_REFERENCE@1.0.0 statistic MEDIAN; instruction rev2 sections 7/11)

## 16. Open items

- `O1` [HUMAN_DECISION_REQUIRED]: manuscript appendix CU section is not yet synchronised
- `O2` [OPEN_MANUSCRIPT_ITEM]: m^CS predefined sensitivity values absent from the manuscript body
- `O3` [OPEN_DOCUMENTATION_ITEM]: instruction rev2 contains 14 mechanically truncated '\rightarrow' escapes ('ightarrow') inherited from the source attachment; text is unambiguously recoverable but the authority document was left byte-identical in Phase 0-5
- `O4` [RECORDED_NOT_ZERO_FILLED]: four PGV->CLT Development nodes have no admissible reference binding and stay typed UNSUPPORTED_REFERENCE

## 17. Freeze commit

`freeze_commit = PENDING`. Phase 5 records the pending
value only; resolving it is a Phase 6 action and requires explicit human
release.

## 18. Turnaround reference freeze-precheck (2026-09-19)

- audit finding: `SUPERSEDED_REFERENCE_WAS_ACTIVE_NOT_STALE_METADATA` (owner `M2_NODE_REFERENCE_BUNDLE`)
- active node reference: `sha256:aa241b902536c500c21e6a9563ba3c9ac563d1167d4220c77a1e89771677ad57` (`BTS_SIGNED_DELAY_SEMANTIC_CORRECTION`, global median 57.0 minutes, 349 cells)
- superseded node reference: `sha256:7c6ac01673f200260fc925eb4c0b57f143fcc34532832375124945252b69707c` -> `SUPERSEDED_PROVENANCE_ONLY` (global median 51.0 minutes)
- reference delta over 349 shared cells: 332 changed, max 41.5 minutes, mean 4.16 minutes
- node reference quantity: AIRPORT_LEVEL_POSITIVE_TRAIN_MEDIAN_TURNAROUND_REFERENCE (DATA2_TURNAROUND_REFERENCE@1.0.0, statistic MEDIAN, global fallback)
- Stage-II quantity: `T^{turn,lb} = Q20(T^{turn} | Train)` nominal 41.0 minutes; same quantity: `False`
- scalar substitution rejected: `True`
- `F_continuity` Train scale corrected: 43.0 -> 44.0 minutes (positive n 186742, population 2668531), scale rule `Median_Train(q_k | q_k > 0)`
- M1 retrained this round: `False`; new Final-Test access: `False`
- this precheck leaves the draft `DRAFT_NOT_ACTIVATED` with `freeze_commit = PENDING`
