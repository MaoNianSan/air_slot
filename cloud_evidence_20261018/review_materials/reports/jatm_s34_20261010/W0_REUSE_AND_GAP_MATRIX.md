# W0 Reuse and Gap Matrix — 2026-10-11

## Authority baseline

- Repository: `D:\research\air_slot\code\explore`
- Branch: `v2/paper-primary`
- HEAD: `5e0f6cb`
- Remote: `origin/v2/paper-primary` (previously verified synchronized)
- Worktree: only pre-existing untracked `figures/`; no tracked dirty files.
- Concurrent work: no other Codex agents; no active Python experiment process observed.
- Frozen data policy: `data1/`, `data2/` read-only; no frozen artifact modified.

## Reuse and gap matrix

| Requirement | Existing implementation / evidence | Status | Direct dependency | Proposed action |
|---|---|---|---|---|
| W0 authority and branch | `REPOSITORY_AUTHORITY.md`; Git baseline above | REUSABLE | none | reuse |
| Stage-I PRE/TURN Top-K | `model/M3/stage1.py`; `formal/v2_phase7/stage_q_screening_sensitivity.py` | REUSABLE | current frozen selector | reuse; no pooled ranking |
| Stage-II finite-grid exact enumeration | `model/M3/stage2.py::enumerate_recovery_decision` | REUSABLE | current M3/M4 | reuse |
| E1 Delay expected vs consequence | `formal/v2_phase7/stage_q_screening_sensitivity.py`; `exp/jatm_section5/attention_value.py` | PARTIAL | Delay Exposure definition blocked | implement only existing DELAY_EXPECTED path; keep DELAY_EXPOSURE blocked |
| E2 representation / recoverability | `exp/jatm_section5/information_value.py`, `recovery_value.py`, `exp/jatm_section4/h_capacity.py` | PARTIAL | C1/C2/C3 orchestration absent; HM interpretation depends on G0-2 | reuse C0 and build bounded orchestration only after support contract |
| E3 objective × distribution | `formal/v2_phase7/consequence_domain_emphasis_robustness.py` | PARTIAL | strict HM coupling / mechanism operators unresolved | reuse C0 domain profiles; no pure-dependence result until decision |
| E4 six-year Test | `model/PRE`, `model/M1/pipeline.py`, `artifacts/models/pre/PRE_MULTIYEAR_V1/{2017..2022}` | BLOCKED | existing artifacts are Development; Test access/annual protocol runner not present | prepare year-isolated runner contract; do not substitute Development for Test |
| Stage×q supplement | `formal/v2_phase7/stage_q_screening_sensitivity.py` | REUSABLE | sealed epoch permission | reuse; no rerun in W0/G0 |
| Domain emphasis supplement | `formal/v2_phase7/consequence_domain_emphasis_robustness.py` | REUSABLE | sealed epoch permission | reuse; no rerun in W0/G0 |
| H8/H16/H32 | `exp/jatm_section4/h_capacity.py`, `model/M1/tuning_stage1.py` | REUSABLE/PARTIAL | output authority varies by split | reconcile existing artifacts before new run |
| G0 evidence | local `reports/refactor_20261010/G0_*.{json,md}` | REUSABLE_WITH_UPDATED_HEAD | current scientific files unchanged by two commits | carry forward with current HEAD wrapper |

## Freeze exclusions

No Class-alpha artifact, registry, raw data, Final-Test checkpoint, or paper number was modified. No Final-Test access was opened.

