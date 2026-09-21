# M1 history-encoder capacity selection (H8 / H16 / H32)

Development-only state-prediction experiment. No consequence, ranking,
attention, recovery or decision-value metric participates in this report,
and no Final-Test path is read.

## Run contract

- repository HEAD: `8ee66e3491d92f63d7cc5d8d8272bd148c7d0cee`
- candidates: [8, 16, 32] (parameters {'8': 4660, '16': 9620, '32': 20692})
- declared parameter counts (closure manifest, kept unchanged): {'8': 4708, '16': 9716, '32': 20884}
- frozen H16 architecture check: `FROZEN_H16_ARCHITECTURE_EQUIVALENT` (9620 parameters, signature `sha256:e4999273aace858894c7def4e6c24e2bb1900c8dd46e43926ff0c78169269c7e`),
- paired seeds: [20260813, 20260814, 20260815, 20260816, 20260817]
- training config: {'optimizer': 'Adam', 'learning_rate': 0.001, 'weight_decay': 0.0, 'epochs': 8, 'batch_size': 64}
- early stopping: `NOT_USED_BY_FROZEN_CONTRACT`
- splits: {'train': ['2019-01-01', '2019-06-30'], 'calibration': ['2019-07-01', '2019-07-31'], 'development': ['2019-08-01', '2019-09-30'], 'final_test': 'LOCKED_NOT_ACCESSED'}
- cache hash: `sha256:599be2df0cbf7f2e761709a9e86ab38ddb2672c1e6edb6b6fe2df50991ed3d41`
- feature contract hash: `sha256:56253d8ef9095588c48a31506f5bd3952ed52fbe457f5ef2c1f8d635a3cd4097`
- support contract hash: `sha256:aadc580d2015c3c6f7c30d2f5ef346e25108775552d70fb3f62200a144573d8a`
- Final-Test access count: 0
- downstream decision metrics used: false

## Primary selection metric by capacity

| H | parameters | dev joint mean | SD | SE | train joint mean | rel. gap |
|---|---|---|---|---|---|---|
| 8 | 4660 | 17.652301 | 0.18641 | 0.083365 | 29.932114 | -0.410255 |
| 16 | 9620 | 17.461718 | 0.074325 | 0.033239 | 29.570736 | -0.409493 |
| 32 | 20692 | 17.158248 | 0.062617 | 0.028003 | 29.007667 | -0.408493 |

## Selection

- rule: `ONE_SE_THEN_SMALLEST_ELIGIBLE_WITH_CALIBRATION_TAIL_CORE_TARGET_GUARDRAILS`
- best mean capacity: H32 (mean 17.158248, SE 0.028003)
- eligible (mean <= best + SE): [32]
- selected: H32
- status: `SCIENTIFIC_RECONCILIATION_REQUIRED`

## Per-target Development metrics (mean over seeds)

| H | target | MAE | median AE | P90AE | Cov50 | Cov80 | Cov90 | mean ACE |
|---|---|---|---|---|---|---|---|---|
| H8 | D_OB | 7.707911 | 1.265323 | 22.583429 | 0.153365 | 0.198435 | N/A_NOT_DEFINED | 0.4741 |
| H8 | D_TX | 4.881464 | 1.446995 | 10.547626 | 0.212738 | 0.344358 | N/A_NOT_DEFINED | 0.371452 |
| H8 | T_IB_REMAINING_HAZARD | 23.233825 | 9.771857 | 61.245736 | 0.207373 | 0.370507 | 0.445161 | 0.39232 |
| H16 | D_OB | 7.652394 | 1.108923 | 22.729771 | 0.150235 | 0.203756 | N/A_NOT_DEFINED | 0.473005 |
| H16 | D_TX | 4.809462 | 1.564384 | 10.23492 | 0.212961 | 0.321341 | N/A_NOT_DEFINED | 0.382849 |
| H16 | T_IB_REMAINING_HAZARD | 22.354081 | 11.43491 | 55.785701 | 0.201843 | 0.350231 | 0.421198 | 0.408909 |
| H32 | D_OB | 7.52453 | 0.0 | 23.0 | 0.15806 | 0.225665 | N/A_NOT_DEFINED | 0.458138 |
| H32 | D_TX | 4.840492 | 1.0 | 11.0 | 0.24581 | 0.349944 | N/A_NOT_DEFINED | 0.352123 |
| H32 | T_IB_REMAINING_HAZARD | 21.98938 | 13.444163 | 52.405845 | 0.304147 | 0.526267 | 0.614747 | 0.251613 |

## Operating-stage robustness (mean over seeds)

| H | stage | target | n | MAE | P90AE |
|---|---|---|---|---|---|
| H8 | POST_IB_PRE_OB | D_OB | 1454 | 4.636328 | 14.571344 |
| H8 | POST_IB_PRE_OB | D_TX | 1450 | 4.950452 | 10.545089 |
| H8 | POST_OB_PRE_TO | D_TX | 98 | 3.677648 | 10.531149 |
| H8 | PRE_IB | D_OB | 217 | 28.288929 | 78.300777 |
| H8 | PRE_IB | D_TX | 217 | 4.964136 | 10.140536 |
| H8 | PRE_IB | T_IB_REMAINING_HAZARD | 217 | 23.233825 | 61.245736 |
| H16 | POST_IB_PRE_OB | D_OB | 1454 | 4.572796 | 14.536987 |
| H16 | POST_IB_PRE_OB | D_TX | 1450 | 4.873841 | 10.230077 |
| H16 | POST_OB_PRE_TO | D_TX | 98 | 3.666872 | 10.328542 |
| H16 | PRE_IB | D_OB | 217 | 28.28712 | 78.476678 |
| H16 | PRE_IB | D_TX | 217 | 4.895285 | 10.051763 |
| H16 | PRE_IB | T_IB_REMAINING_HAZARD | 217 | 22.354081 | 55.785701 |
| H32 | POST_IB_PRE_OB | D_OB | 1454 | 4.357775 | 15.0 |
| H32 | POST_IB_PRE_OB | D_TX | 1450 | 4.931444 | 11.0 |
| H32 | POST_OB_PRE_TO | D_TX | 98 | 3.591837 | 11.0 |
| H32 | PRE_IB | D_OB | 217 | 28.743247 | 79.0 |
| H32 | PRE_IB | D_TX | 217 | 4.796652 | 10.492123 |
| H32 | PRE_IB | T_IB_REMAINING_HAZARD | 217 | 21.98938 | 52.405845 |

## Notes

- The frozen training contract has no early stopping; every candidate
  runs the identical 8-epoch budget with the identical optimizer,
  learning rate, batch size, cohort, seeds, support and quantile grid.
- Cov90 for D_OB / D_TX is reported as
  `NOT_DEFINED_FROZEN_QUANTILE_GRID` because the frozen grid is
  (0.1, 0.3, 0.5, 0.7, 0.9) and 90 percent coverage would need q05/q95.
- Per-lead tables use the realized-lead definitions of the frozen
  M1 horizon diagnostic; leads outside the capture window are excluded
  rather than re-binned.
- CRPS is reported only for T_IB finite support, where the frozen
  representation defines it; the hurdle targets report pinball and
  zero-mass calibration instead.
- Point metrics (MAE / median AE / P90AE) use every active label,
  hurdle zeros included; coverage, width and calibration
  diagnostics use the frozen positive-outcome population for
  D_OB / D_TX (``n_coverage`` in the target and lead tables).
- Declared candidate parameter counts from the closure manifest
  differ from the counts materialized by the current frozen
  architecture definition; materialized counts are reported, the
  declarations are preserved unchanged, and the H16 recipe is
  proven signature-equal to the frozen H16 runtime artifact.
