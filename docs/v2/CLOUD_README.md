# AirSlot V2 - Cloud Reading Index

Entry point for reading the AirSlot V2 scientific state on GitHub: paper-primary
pipeline, Section 4 / Section 5 completion status, Final-Test headline results,
artifact links and paper mapping. Nothing here recomputes science - every number
is read from the persisted artifacts linked below.

## 1. Current scientific status

- Phase 7 Final Test executed once under the sealed one-shot protocol, audited
  and closed (`SCIENTIFIC_RESULT_INTEGRITY_PASS`). No re-run, no new raw read, no
  new access epoch.
- Section 4 (Development / construction) is `COMPLETE`.
- Section 5 headline results for the reference variant and the three comparators
  are `COMPLETE` and committed in the paper-facing view.
- Section 5.5 sensitivity axes are frozen and declared; sensitivity **results**
  were not produced in this single-shot run and are `BLOCKED` behind a future
  authorized access epoch.
- Fixed-window history stays `NOT_AVAILABLE_NOT_FROZEN`.

## 2. Current HEAD / branch / freeze authority

- Branch: `v2/phase7-gate-a` (cloud release branch; first publication).
- Last scientific commit before this release: `d78183f` (`v2(phase7-postrun):
  add checkpoint scientific integrity audit`).
- Release commit: tip of this branch, which introduces `docs/v2/`.
- Freeze authority: annotated tags `v2-scientific-freeze` (object
  `35d5fe1896dd9e17be92bec601f87ec33adb4d56`, target
  `d29fc769e74d6b46f86d3fdf7db18b3f9936f8b1`) and `v2-scientific-freeze-r2`
  (object `2dcca6c159dedde3803e63cb48bd8bfefff574cf`, target
  `3834eed33d4a2ea4bdba111fc29cca3529525a3a`), verified by
  `validation/v2_phase7/freeze_ancestry.py`.
- Active Stage-II authority: `EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID`;
  Pyomo+HiGHS is a parity backend only.

## 3. Scientific pipeline

`PRE -> M1 State Estimation -> M2 Consequence + Priority -> M3 Attention +
Recovery -> M4 Common-Basis Evaluation -> Experiment / Reporting Views`.
Module-by-module map and the sealed DAG:
[V2_SCIENTIFIC_PIPELINE.md](./V2_SCIENTIFIC_PIPELINE.md).

## 4. Section 4 completion status

History/Current (H16 primary, H8 capacity sensitivity), Point/Marginal/Joint
representations, consequence/CU construction, Stage-II Train support, q grid,
lambda grid, turnaround support and U_max support: all `COMPLETE`. Full matrix:
[SECTION4_SECTION5_EXPERIMENT_STATUS.md](./SECTION4_SECTION5_EXPERIMENT_STATUS.md).

## 5. Section 5 completion status

Final-Test cohort, `HISTORY_JOINT`, `CURRENT_JOINT`, `HISTORY_POINT`,
`HISTORY_MARGINAL`, Stage-I attention, Stage-II recovery, M4 `L_att` / `L_rec`,
`A0`/`A5`, bootstrap and paper views: `COMPLETE`. Sensitivity results: `BLOCKED`.
Full matrix:
[SECTION4_SECTION5_EXPERIMENT_STATUS.md](./SECTION4_SECTION5_EXPERIMENT_STATUS.md).

## 6. Final-Test headline diagnostics

Comparator results on the fixed reference cohort `R_g*` (166 support-qualified
nodes). Reference self-comparison is an identity check and is listed separately.

| comparator | L_att | L_att 95% CI | L_rec | L_rec 95% CI | A0 | A5 | exact / within-5 |
|---|---|---|---|---|---|---|---|
| CURRENT_JOINT | 0.026904 | [-0.151522, 0.223335] | 0.819601 | [0.149536, 2.126201] | 0.650602 | 0.921687 | 108 / 153 |
| HISTORY_POINT | 0.593794 | [-0.164235, 0.831861] | 0.978742 | [0.952011, 1.000000] | 0.421687 | 0.957831 | 70 / 159 |
| HISTORY_MARGINAL | 0.001005 | [-0.033606, 0.032653] | 0.038177 | [0.000000, 0.142590] | 0.969880 | 0.969880 | 161 / 161 |

Reference `HISTORY_JOINT` self-comparison: `L_att = 0`, `L_rec = 0`,
`A0 = A5 = 1`, exact actions 166/166 - identity by construction, not a
comparator outcome. Stage-II nominal (166 nodes): `HISTORY_JOINT` mean `u*`
3.7048 / sum `V` 1.936577; `CURRENT_JOINT` 4.006 / 2.212484;
`HISTORY_POINT` 0.0602 / 0.005681; `HISTORY_MARGINAL` 3.4337 / 2.166850.
Tables: [PAPER_FACING_SECTION5_VIEWS.md](../../artifacts/experiment/final_test_v2/PAPER_FACING_SECTION5_VIEWS.md).

## 7. Artifact links

- [Paper-facing Section 5 views](../../artifacts/experiment/final_test_v2/PAPER_FACING_SECTION5_VIEWS.md)
- [Checkpoint manifest (9 stages, hashes)](../../artifacts/experiment/final_test_v2/CHECKPOINT_MANIFEST.json)
- [Sealed run result](../../artifacts/experiment/final_test_v2/GATE_B_RUN_RESULT.json)
- [Access ledger](../../artifacts/experiment/final_test_v2/PHASE7_ACCESS_AUDIT.json)
- [Post-run integrity audit](../../artifacts/experiment/final_test_v2/PHASE7_POSTRUN_SCIENTIFIC_AUDIT.json)
- [Active solver authority registry](../../registries/v2_stage2_solver_authority_reconciliation.json)
- [Scientific freeze R2 registry](../../registries/v2_scientific_freeze_r2.json)
- [Freeze ancestry validation](../../artifacts/diagnostics/v2_phase7/FREEZE_ANCESTRY_VALIDATION.json)
- [Phase-5 Development diagnostics](../../artifacts/diagnostics/v2_phase5_development/PHASE5_RUN_SUMMARY.json)
- Phase reports: [Phase 0](../V2_PHASE0_AUDIT.md), [Phase 5](../V2_PHASE5_REPORT.md),
  [Phase 6 freeze](../V2_PHASE6_FREEZE_REPORT.md), [Freeze R2 correction](../V2_SCIENTIFIC_FREEZE_R2_CORRECTION_REPORT.md)
- Execution instruction: [Phase-7 one-shot R2](../AirSlot_V2_Phase7_Final_Test_OneShot_Instruction_R2_20260919.md)

## 8. Paper mapping

Scientific object -> owning module -> source artifact -> paper-facing artifact ->
manuscript destination: [SCIENTIFIC_TO_MANUSCRIPT_MAPPING.md](./SCIENTIFIC_TO_MANUSCRIPT_MAPPING.md)
(with the artifact inventory in
[SECTION4_SECTION5_ARTIFACT_MAP.md](./SECTION4_SECTION5_ARTIFACT_MAP.md)).
When the paper structure changes, only this layer is edited - never the frozen
scientific code.

## 9. Known unavailable items

- Section 5.5 sensitivity results (lambda, turnaround, U_max, H8): declared axes
  only; producing results needs a new authorized Final-Test access epoch.
- similar-delay 5/10/15, itinerary 30/60, service 150/210: `NOT_ACTIVATED_BY_PHASE6_FREEZE`.
- fixed-window history: `NOT_AVAILABLE_NOT_FROZEN` (no substitute model trained).
- Full per-node checkpoint payloads (~587 MB) stay local by design; the committed
  manifest carries their identities and hashes.
- `PHASE5_RUN_SUMMARY.json` / `GATE_B_RUN_RESULT.json` embed absolute local paths;
  they are lineage records, not portable links (see the artifact map caveats).

## 10. Next recommended work

- Select which persisted Section 5 numbers enter the manuscript using
  [SCIENTIFIC_TO_MANUSCRIPT_MAPPING.md](./SCIENTIFIC_TO_MANUSCRIPT_MAPPING.md).
- If Final-Test sensitivity results are required for Section 5.5, open a new
  human-approved access epoch first; do not recompute anything from raw Q4.
- No further framework, freeze or governance work is pending; see
  [PHASE7_FINAL_STATUS.md](./PHASE7_FINAL_STATUS.md).
