# Phase 2 Report — M1 representation ownership + M2 comparison support and CU V5

Branch `v2/paper-primary`; instruction `docs/AirSlot_V2_Instruction_rev2_20260918.md`.
Phase 1 checkpoint: `a70c871 v2(phase1): decision contracts and PRE decision environment`.

## 1. Completed scope

- Moved state-representation ownership into M1 (`model/M1/state_representation.py`):
  - **Joint**: the aligned frozen joint scenario set is returned unchanged;
  - **Point**: the frozen weighted joint medoid — one coherent real scenario
    `(T_IB, D_OB, D_TX)` with `D_TO = D_OB + D_TX`; coordinate-wise means/medians
    are never combined;
  - **Marginal**: deterministic ascending-value coordinate permutation. The
    coordinate value multiset and the slot weight vector are preserved exactly
    (hence the weighted marginal is exact under equal scenario weights); the
    joint alignment is destroyed and the representation is machine-labelled
    `DETERMINISTIC_COORDINATE_PERMUTATION_NOT_PHYSICAL_INDEPENDENCE`, never
    physical independence.
  - Realized milestones stay a shared-contract rule: a realized scenario
    collapses to a single weight-1.0 POINT scenario.
- Implemented M2 comparison support (`model/M2/comparison_support.py`):
  `Omega^CS` (delay and every required CU quantity jointly supported),
  `m^CS = sum_{s in Omega^CS} w_s`, nominal `m^CS >= 0.90`, typed
  `ABSTAIN_NO_COMMON_SUPPORT` for below-threshold nodes, with no
  renormalisation, drop or zero-proxy filling. Missing, unsupported and
  supported zero stay distinct states.
- Implemented the unique consequence-based priority authority
  `P^C = Phi_C(C^CU)` with the manuscript's fixed **primary domain-balanced**
  mapping, and the parallel delay comparator
  `P^D = (1/m^CS) sum_{s in Omega^CS} w_s D^{+,TO}_s` (manuscript section 4,
  `eq:empirical_delay_score`). Both signals are produced on one shared
  `Omega^CS` attestation for the shared Stage-I selector.
- Built the CU V5 registry and design (five principal components keep the V4
  recomputed positive Train medians; `P_itinerary` and `P_service` use
  `ASSUMPTION_EVENT_NORMALIZATION` with scale 1.0 and
  `empirical_train_positive_median = false`), plus the V4-to-V5 supersession
  record marked `DRAFT_NOT_ACTIVATED`.

## 2. Core files changed/added

- `model/M1/state_representation.py`
- `model/M2/comparison_support.py`
- `model/M2/cu/registry.py` (V5 validation branch and constants; V4 path unchanged)
- `model/M2/scientific_registry.py` (V5 loaders; legacy V4 loaders unchanged)
- `registries/m2_data2_formal_cu_v5.json`
- `registries/m2_v5_passenger_consequence_design.json`
- `registries/passenger_reference_supersession_v3.json`
- `tests/m1/test_state_representation_v2.py`
- `tests/m2/test_comparison_support_v2.py`
- `tests/m2/test_cu_registry_v5.py`

## 3. Scientific interfaces now available

- `build_joint_representation` / `build_point_representation` /
  `build_marginal_representation` / `canonical_slot_order`.
- `ComparisonSupportRule(rule_id, threshold=0.90, predefined_sensitivity=(),
  sensitivity_status="NO_MANUSCRIPT_PREDEFINED_SENSITIVITY_VALUES")`.
- `build_comparison_support(state, consequence, rule)` ->
  `ComparisonSupport(Omega^CS, m^CS, threshold, included, status, reason_codes)`.
- `delay_priority_signal` -> `PrioritySignal(DELAY)`;
  `consequence_priority_signal` -> `PrioritySignal(CONSEQUENCE)`;
  `priority_signals` -> both on one shared attestation.
- `expected_cu_vector` (common-support expected CU per component) and
  `phi_c(cu, view="PRIMARY_DOMAIN_BALANCED")`.
- `load_active_v2_cu_registry` / `load_active_v2_passenger_consequence_design`.

## 4. Legacy assets reused

- V4 reference artifacts and their hashes are carried over unchanged
  (`DB1B_CONNECTION_SHARE_REFERENCE`, `T100_EXPECTED_PAX_PER_FLIGHT_REFERENCE`,
  `DATA2_*_REFERENCE_TRAIN_FROZEN_V1`, `M2_SEVEN_COMPONENT_TRAIN_SCALES`).
- The five principal medians are the V4 recomputed 2019-H1 values
  (`F_continuity 43.0`, `F_execution 17.0`, `F_propagation 10.0`,
  `P_time 990.3555555555556`, `R_operating 5.0`); the stale V2 medians are not
  adopted and the V2 seven-median partition is not restored.
- `p_itinerary_native` already carries `s_conn`, so `P_itinerary = N_pax · s_conn ·
  1(D_TO > 45)` needs no code change (ruling R1).
- V4 registry file retained unchanged:
  `registries/m2_data2_formal_cu_v4.json` sha256
  `e28ba89ef73fd5ba13ee67bd3aa16de8e097a64c133812c7ded341a9294c6e95`; the legacy
  loaders keep pointing at it for the frozen Final-Test-era pipelines.

## 5. Scientific blockers / new assumptions

- **No new assumption was introduced.** One interaction was resolved from the
  existing authority and is recorded here for audit: the manuscript body
  (`eq:empirical_aggregation_mapping`) states that the primary `Phi_C` weights
  are "fixed by the primary domain-balanced aggregation specification reported
  in Appendix", and that appendix entry defines equal weight within the
  flight-chain and passenger domains and equal weight across the three domains.
  V2 therefore implements
  `Phi_C = (1/3)[mean(F) + mean(P) + R_operating]` as primary and records the
  legacy unit-weight sum-over-seven (`SUM_OVER_SEVEN_ONLY_IF_ALL_SUPPORTED`) and
  the appendix `EQUAL_COMPONENT` view as non-primary comparators.
- `m^CS` keeps the nominal 0.90 only. The latest manuscript body predefines no
  sensitivity values, so no grid is activated; this is recorded in the rule, in
  `passenger_reference_supersession_v3.json`, and will be carried into the
  Phase-5 freeze draft.
- `P^D` authority stays the manuscript `eq:empirical_delay_score`
  (common-support conditional mean). The legacy
  `exp/shared/recovery_priority.py::summarize_delay_score` remains classified as
  a deviating implementation and is not used on the paper-primary path.
- `registries/ACTIVE_MODEL_ARTIFACTS_V1.json` was deliberately **not** rewritten:
  its digest is recorded inside a frozen Final-Test-era manifest, so the V2
  chain records the V5 supersession in
  `passenger_reference_supersession_v3.json` and in this report instead. No
  Final-Test artifact was read, written or re-interpreted.
- Pre-existing legacy failures outside Phase 2 scope (verified at HEAD `a70c871`
  in a clean worktree): `tests/m1/test_feature_gate_b2.py`,
  `tests/m1/test_feature_gate_b2r.py` (`M1_B2_B2R_NOT_READY`) and
  `tests/m1/test_model_baseline_fingerprint.py` (live-hash check against the
  frozen V1R1 runtime manifest, which is stale relative to committed code).
  Phase 2 also changes the hashes of `model/M2/cu/registry.py` and
  `model/M2/scientific_registry.py`, which that frozen live-hash test compares;
  per instruction section 28, repository-wide legacy test pass is not a V2
  completion criterion. The V1R1 manifest is not rewritten.

## 6. Artifacts created

- `registries/m2_data2_formal_cu_v5.json`
  (`registry_id = M2_DATA2_FORMAL_CU_V5`,
  `scientific_status = HUMAN_APPROVED_PENDING_FREEZE`,
  `registry_hash = sha256:219c6d37a47080df1b6687cae682ca57bdd0233eb83f3bb746cdacd25cea1bef`,
  `final_test_access_count = 0`, `paper_full_run = false`).
- `registries/m2_v5_passenger_consequence_design.json` (5.0.0,
  `activation_status = DRAFT_NOT_ACTIVATED`).
- `registries/passenger_reference_supersession_v3.json` (V4 superseded for the V2
  chain only; legacy V4 retained unchanged; no predefined `m^CS` sensitivity; no
  new Final Test).

## 7. Verification and next dependency unlocked

- `python -m pytest tests/m1/test_state_representation_v2.py
  tests/m2/test_comparison_support_v2.py tests/m2/test_cu_registry_v5.py -q` ->
  22 + 6 passed.
- `python -m pytest tests/decision tests/pre tests/m1 tests/m2 -q` ->
  337 passed, 5 pre-existing legacy failures (listed in section 5).
- `python validation/split_isolation.py` -> PASS (6 cases,
  `final_test_access_count = 0`).
- `python -m compileall -q model/common model/PRE model/M1/state_representation.py
  model/M2/comparison_support.py model/M2/cu/registry.py
  model/M2/scientific_registry.py` -> clean.
- `FINAL_TEST_ACCESS_COUNT` unchanged (= 1, no new access);
  `artifacts/experiment/final_test/` was not read or written.
- Phase 3 is unlocked: M3 Stage I (shared selector over `P^D`/`P^C`) and Stage II
  (PRE/TURN only, exact-enumeration formal path, HiGHS parity backend).
