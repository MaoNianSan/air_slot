# Air Slot — Section 5 Paper-Facing Results (sealed canonical-v2 projection)

Read-only manuscript-facing projection of the sealed canonical stage-matched 
Final-Test epoch. No scientific computation was performed, no epoch was 
re-opened, and no value was taken from any legacy or Development source.

## Provenance

- paper-primary: `v2/paper-primary` @ `b753db8251812faec2eb2dbdabf34c325eb76f9b`
- final-test authority: `v2/phase7-gate-a` @ `8360dd7d88958ae139322d0ea5c66f1c5fe6455c` (tag `jatm-final-test-freeze-20260920`)
- epoch: `artifacts/experiment/final_test_v2_stage_matched_canonical_v2`
- EPOCH_SEAL: `artifacts/experiment/final_test_v2_stage_matched_canonical_v2/EPOCH_SEAL.json` — `sha256:eb4a22a2079183f1eca3511c5002334eeccb9f19b282f9781189475ce9c21614` — status `SEALED_AUDIT_PASS`
- PAPER_VIEWS checkpoint: `artifacts/experiment/final_test_v2_stage_matched_canonical_v2/checkpoints/PAPER_VIEWS.json` — file `sha256:cfedca4f4f99d5fcdb7f745c23603b884f9df19ff3efc9a4c97af807fc5424a3`
- PAPER_VIEWS payload hash: `sha256:88b470adbf6b54634fc196c8f4be94d1ec99caa82ce3af74faf2b4840a595466`
- POST_EXECUTION_AUDIT: `artifacts/experiment/final_test_v2_stage_matched_canonical_v2/POST_EXECUTION_AUDIT.json` — `sha256:efb3c26ad85d3cdc780df26513e3896f9d52c421298a7c2b1e776463bb9be693` — status `PASS` (audited `2026-09-20T03:28:24.830132+00:00`)
- freeze artifact hash: `sha256:05b6327ae842dc23b5449e61d541337a18da4aa388063f9ab6862ae2a1808ecc`
- projection_only = true; scientific_recomputation_performed = false; scientific_definition_changed = false

## 5.1 Stage-I attention

- reference representation: `HISTORY_H16:JOINT` (`HISTORY_JOINT`)
- capacity rule: `K_STAGE = ceil(q * N_STAGE); K_OVERALL = sum_g K_g`; q grid `[0.05, 0.1, 0.2, 0.3]`, nominal q = `0.1`
- overall aggregation: `OBJECTIVES_THEN_NORMALIZE` (confirmed `OBJECTIVES_THEN_NORMALIZE`); pooled PRE+TURN ranking constructed: `False`

### Capacity design (stage × q)

| stage | q | N_g | K_g | selected | eligible | abstaining |
|---|---|---|---|---|---|---|
| PRE_IB | 0.05 | 29 | 2 | 2 | 29 | 0 |
| POST_IB_PRE_OB | 0.05 | 127 | 7 | 7 | 127 | 0 |
| OVERALL | 0.05 | 156 | 9 | 9 | 156 | 0 |
| PRE_IB | 0.1 | 29 | 3 | 3 | 29 | 0 |
| POST_IB_PRE_OB | 0.1 | 127 | 13 | 13 | 127 | 0 |
| OVERALL | 0.1 | 156 | 16 | 16 | 156 | 0 |
| PRE_IB | 0.2 | 29 | 6 | 6 | 29 | 0 |
| POST_IB_PRE_OB | 0.2 | 127 | 26 | 26 | 127 | 0 |
| OVERALL | 0.2 | 156 | 32 | 32 | 156 | 0 |
| PRE_IB | 0.3 | 29 | 9 | 9 | 29 | 0 |
| POST_IB_PRE_OB | 0.3 | 127 | 39 | 39 | 127 | 0 |
| OVERALL | 0.3 | 156 | 48 | 48 | 156 | 0 |

- Reference/comparator attention objectives and displacement diagnostics are sealed at the nominal q = 0.10 operating point only; rows at other q carry typed nulls and are never recomputed

### Attention comparison at nominal q = 0.1 (per stage × comparator)

**PRE_IB** (PRE, N_g = 29, K_g = 3)

| comparator | reference value | comparator value | Δ | L_att | retained | overlap | entered | displaced | reassigned share |
|---|---|---|---|---|---|---|---|---|---|
| CURRENT_JOINT | 3.2615917421940086 | 3.2615917421940086 | 0.0 | 0.0 | 1.0 | 3 | 0 | 0 | 0.0 |
| HISTORY_POINT | 3.2615917421940086 | 1.155484971805712 | 2.1061067703882967 | 0.6457297347005055 | 0.35427026529949446 | 0 | 3 | 3 | 1.0 |
| HISTORY_MARGINAL | 3.2615917421940086 | 3.2615917421940086 | 0.0 | 0.0 | 1.0 | 3 | 0 | 0 | 0.0 |

**POST_IB_PRE_OB** (TURN, N_g = 127, K_g = 13)

| comparator | reference value | comparator value | Δ | L_att | retained | overlap | entered | displaced | reassigned share |
|---|---|---|---|---|---|---|---|---|---|
| CURRENT_JOINT | 13.501981165915817 | 13.190533044579169 | 0.3114481213366478 | 0.023066846080548712 | 0.9769331539194512 | 10 | 3 | 3 | 0.23076923076923078 |
| HISTORY_POINT | 13.501981165915817 | 6.262398752597847 | 7.23958241331797 | 0.5361866769295646 | 0.46381332307043543 | 2 | 11 | 11 | 0.8461538461538461 |
| HISTORY_MARGINAL | 13.501981165915817 | 13.501981165915817 | 0.0 | 0.0 | 1.0 | 13 | 0 | 0 | 0.0 |

### Overall attention (OBJECTIVES_THEN_NORMALIZE)

- aggregation = `STAGE_OBJECTIVES_THEN_NORMALIZE` (confirmed `OBJECTIVES_THEN_NORMALIZE`); pooled ranking constructed: `False`
- aggregated reference objective: `16.763572908109825`

| comparator | aggregated comparator objective | overall Δ | overall L_att | retained | overlap | entered | displaced | reassigned share |
|---|---|---|---|---|---|---|---|---|
| CURRENT_JOINT | 16.452124786773176 | 0.31144812133664956 | 0.01857886281426188 | 0.9814211371857381 | 13 | 3 | 3 | 0.1875 |
| HISTORY_POINT | 7.417883724403559 | 9.345689183706266 | 0.557499838186944 | 0.44250016181305596 | 2 | 14 | 14 | 0.875 |
| HISTORY_MARGINAL | 16.763572908109825 | 0.0 | 0.0 | 1.0 | 16 | 0 | 0 | 0.0 |

- stage-specific L_att values are never averaged; overall Δ = aggregated reference − aggregated comparator, overall L_att is sealed.

## 5.2 Stage-II recovery

- R* = R_PRE* ∪ R_TURN* — count `16` (PRE `3`, TURN `13`), support exclusions `0` (`ACTIONABLE_STAGE_AND_REFERENCE_STATE_FULLY_SUPPORTED`)
- reference representation: `HISTORY_H16:JOINT` (`HISTORY_JOINT`)

| stage | N | median V | IQR V | P90 V | positive-V share | activations | activation share | median u*>0 | IQR u*>0 | P90 u*>0 |
|---|---|---|---|---|---|---|---|---|---|---|
| PRE | 3 | 0.009455829633296498 | 0.005218809669331526 | 0.01724734230757332 | 1.0 | 3 | 1.0 | 5.0 | 7.5 | 17.0 |
| TURN | 13 | 0.005264776332794874 | 0.014066944325716979 | 0.022399033494506695 | 0.7692307692307693 | 10 | 0.7692307692307693 | 5.0 | 0.0 | 6.999999999999993 |
| OVERALL | 16 | 0.00718095387547435 | 0.013991119043307243 | 0.021869067974855994 | 0.8125 | 13 | 0.8125 | 5.0 | 0.0 | 17.00000000000001 |

- descriptive deterministic summaries over the sealed RECOVERY_DECISIONS reference rows; per-stage values equal the sealed ROBUSTNESS nominal rows; cross-check `{'PRE': 'MATCH', 'TURN': 'MATCH'}`

## 5.3 Information value

### Stage-I (attention) comparator summary

| comparator | L_att | 95% CI | overlap | entered | displaced | reassigned share |
|---|---|---|---|---|---|---|
| CURRENT_JOINT | 0.01857886281426188 | [0.0035120821938504675, 0.07365221875141258] | 13 | 3 | 3 | 0.1875 |
| HISTORY_POINT | 0.557499838186944 | [0.3911116321026571, 0.6538808011069845] | 2 | 14 | 14 | 0.875 |
| HISTORY_MARGINAL | 0.0 | [0.0, 0.0042318127317281075] | 16 | 0 | 0 | 0.0 |

### Stage-II (recovery) comparator summary

| comparator | L_rec | 95% CI | A0 | A5 | exact (count) | exact (share) | within-5 (count) | within-5 (share) | activation events |
|---|---|---|---|---|---|---|---|---|---|
| CURRENT_JOINT | 0.9070157057407199 | [0.3123238158393114, 1.7847903093105455] | 0.375 | 0.8125 | 6 | 0.375 | 13 | 0.8125 | {'FALSE_ACTIVATION': 1, 'MISSED_ACTIVATION': 6, 'OVER_RECOVERY': 1, 'UNDER_RECOVERY': 2} |
| HISTORY_POINT | 0.9536416660613012 | [0.7034794553395216, 1.0] | 0.25 | 0.875 | 4 | 0.25 | 14 | 0.875 | {'FALSE_ACTIVATION': 0, 'MISSED_ACTIVATION': 12, 'OVER_RECOVERY': 0, 'UNDER_RECOVERY': 0} |
| HISTORY_MARGINAL | 0.016464660023900957 | [0.0, 0.18174804051303176] | 0.9375 | 0.9375 | 15 | 0.9375 | 15 | 0.9375 | {'FALSE_ACTIVATION': 0, 'MISSED_ACTIVATION': 0, 'OVER_RECOVERY': 0, 'UNDER_RECOVERY': 1} |

### Marginal uncertainty increment

- definition: `L_HISTORY_POINT - L_HISTORY_MARGINAL` (sealed label `HISTORY_POINT_MINUS_HISTORY_MARGINAL`)
- Stage-I: estimate `0.557499838186944`, paired 95% CI `[0.38933634567710973, 0.6538432281498671]`
- Stage-II: estimate `0.9371770060374003`, paired 95% CI `[0.6440497115191729, 1.0]`
- paired-bootstrap intervals are copied from the sealed BOOTSTRAP checkpoint; they are never derived by subtracting comparator intervals

### Cross-state dependence

- definition: `L_HISTORY_MARGINAL - L_HISTORY_JOINT` (comparator `HISTORY_MARGINAL` vs `HISTORY_JOINT`)
- L_att `0.0`; L_rec `0.016464660023900957`
- paired 95% CI (copied from sealed bootstrap): Stage-I `[0.0, 0.0042318127317281075]`, Stage-II `[0.0, 0.18174804051303176]`

## 5.4 Robustness (fixed R*, one-factor-at-a-time)

- design `ONE_FACTOR_AT_A_TIME`; fixed R* `True` (size `16`); Stage-I rerun `False`
- nominal base: `{'q': 0.1, 'lambda': 0.25, 'turnaround_lower_bound': 41.0, 'u_max': 45.0, 'history_capacity': 16, 'm_cs': 0.9}`

| axis | level | stage | nominal | median V | IQR V | P90 V | positive-V share | activation share | median u*>0 | IQR u*>0 | P90 u*>0 | L_rec | A5 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lambda | 0.1 | PRE | false | 0.05869139135935386 | 0.025349114247908533 | 0.07263627531184129 | 1.0 | 1.0 | 20.0 | 15.0 | 32.0 | -0.14247233532184608 | 0.6666666666666666 |
| lambda | 0.1 | TURN | false | 0.021931442999461592 | 0.019629758008378073 | 0.06450336312855487 | 0.9230769230769231 | 0.9230769230769231 | 30.0 | 30.0 | 35.0 | -0.13486401145715088 | 0.46153846153846156 |
| lambda | 0.25 | PRE | true | 0.009455829633296498 | 0.005218809669331526 | 0.01724734230757332 | 1.0 | 1.0 | 5.0 | 7.5 | 17.0 | 0.0 | 1.0 |
| lambda | 0.25 | TURN | true | 0.005264776332794874 | 0.014066944325716979 | 0.022399033494506695 | 0.7692307692307693 | 0.7692307692307693 | 5.0 | 0.0 | 6.999999999999993 | 0.0 | 1.0 |
| lambda | 0.5 | PRE | false | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | n/a | n/a | n/a | n/a | 0.6666666666666666 |
| lambda | 0.5 | TURN | false | 0.0 | 0.0 | 0.0 | 0.07692307692307693 | 0.07692307692307693 | 25.0 | 0.0 | 25.0 | -1.0817669764688704 | 1.0 |
| lambda | 1 | PRE | false | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | n/a | n/a | n/a | n/a | 0.6666666666666666 |
| lambda | 1 | TURN | false | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | n/a | n/a | n/a | n/a | 0.9230769230769231 |
| turnaround_lower_bound | Q10 | PRE | false | 0.009455829633296498 | 0.005218809669331526 | 0.01724734230757332 | 1.0 | 1.0 | 5.0 | 7.5 | 17.0 | 0.0 | 1.0 |
| turnaround_lower_bound | Q10 | TURN | false | 0.005264776332794874 | 0.01298891090636256 | 0.022399033494506695 | 0.8461538461538461 | 0.8461538461538461 | 5.0 | 0.0 | 5.0 | -0.008736678949460366 | 1.0 |
| turnaround_lower_bound | Q20 | PRE | true | 0.009455829633296498 | 0.005218809669331526 | 0.01724734230757332 | 1.0 | 1.0 | 5.0 | 7.5 | 17.0 | 0.0 | 1.0 |
| turnaround_lower_bound | Q20 | TURN | true | 0.005264776332794874 | 0.014066944325716979 | 0.022399033494506695 | 0.7692307692307693 | 0.7692307692307693 | 5.0 | 0.0 | 6.999999999999993 | 0.0 | 1.0 |
| turnaround_lower_bound | Q30 | PRE | false | 0.008757601137479476 | 0.0062851047167175045 | 0.01710769660840992 | 1.0 | 1.0 | 5.0 | 7.5 | 17.0 | 0.0 | 1.0 |
| turnaround_lower_bound | Q30 | TURN | false | 0.0032755104413556557 | 0.006374076632635672 | 0.020041517956560843 | 0.6153846153846154 | 0.6153846153846154 | 5.0 | 0.0 | 10.999999999999996 | -0.04378686401384931 | 1.0 |
| u_max | Q80 | PRE | false | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | n/a | n/a | n/a | n/a | 0.6666666666666666 |
| u_max | Q80 | TURN | false | 0.0 | 0.0 | 0.0004240972949745018 | 0.15384615384615385 | 0.15384615384615385 | 25.0 | 10.0 | 23.0 | -0.63167825932297 | 1.0 |
| u_max | Q90 | PRE | true | 0.009455829633296498 | 0.005218809669331526 | 0.01724734230757332 | 1.0 | 1.0 | 5.0 | 7.5 | 17.0 | 0.0 | 1.0 |
| u_max | Q90 | TURN | true | 0.005264776332794874 | 0.014066944325716979 | 0.022399033494506695 | 0.7692307692307693 | 0.7692307692307693 | 5.0 | 0.0 | 6.999999999999993 | 0.0 | 1.0 |
| u_max | Q95 | PRE | false | 0.0303063315872536 | 0.015958053358561486 | 0.049181485579643525 | 1.0 | 1.0 | 20.0 | 27.5 | 52.0 | -0.01992127048097908 | 0.6666666666666666 |
| u_max | Q95 | TURN | false | 0.027375532458829288 | 0.10651832497843317 | 0.34815330349367934 | 0.9230769230769231 | 0.9230769230769231 | 10.0 | 61.25 | 70.0 | -0.6328520887592225 | 0.6923076923076923 |

## Validation

- seal flags: `{"final_test_complete": true, "paper_results_frozen": true, "ready_for_freeze": true, "execution_status": "PASS", "audit_status": "PASS", "epoch_seal_status": "SEALED_AUDIT_PASS", "scientific_definition_changed": false, "second_epoch_opened": false}`
- checkpoint hashes: 10 checked — file hashes `True`, payload hashes `True`
- PAPER_VIEWS payload hash recomputed: `sha256:88b470adbf6b54634fc196c8f4be94d1ec99caa82ce3af74faf2b4840a595466` — match `True`
- POST_EXECUTION_AUDIT mirror checks (all match):
  - `R_STAR_COUNT`: audit `16` = artifact `16`
  - `R_STAR_STAGE_COUNTS`: audit `{'POST_IB_PRE_OB': 13, 'PRE_IB': 3}` = artifact `{'PRE_IB': 3, 'POST_IB_PRE_OB': 13}`
  - `MARGINAL_UNCERTAINTY_INCREMENT_L_ATT`: audit `0.557499838186944` = artifact `0.557499838186944`
  - `MARGINAL_UNCERTAINTY_INCREMENT_L_REC`: audit `0.9371770060374003` = artifact `0.9371770060374003`
  - `cross_state_dependence_L_att`: audit `0.0` = artifact `0.0`
  - `cross_state_dependence_L_rec`: audit `0.016464660023900957` = artifact `0.016464660023900957`
  - `marginal_uncertainty_increment_L_att_ci`: audit `[0.38933634567710973, 0.6538432281498671]` = artifact `[0.38933634567710973, 0.6538432281498671]`
  - `marginal_uncertainty_increment_L_rec_ci`: audit `[0.6440497115191729, 1.0]` = artifact `[0.6440497115191729, 1.0]`
- robustness nominal cross-check: `{'PRE': 'MATCH', 'TURN': 'MATCH'}` (tolerance 1e-12)
- no recomputation: {'final_test_raw_data_read': False, 'final_test_rerun': False, 'new_access_epoch_opened': False, 'legacy_epochs_read': False, 'development_results_used': False, 'model_or_solver_code_executed': False}

