# Validation Gates

**Version**: R1.5
**Principle**: Engineering and scientific validation are independent.

## Gate Hierarchy

### Fast Engineering Gate (Primary)

The `fast` engineering gate is the **only** primary engineering gate. It validates:

| Gate | Method | Validator |
|------|--------|-----------|
| Schema | Contract version check | `overall_run validate fast` |
| Manifest | Run manifest + implementation manifest | `overall_run validate fast` |
| Core Registry | 24 required semantic artifact IDs + per-file hashes | `overall_run validate fast` |
| Publication Registry | Publication manifest + 5 figure triplets | `overall_run validate fast` |
| Leakage | `label_identity_mismatch_count=0` | Formal validator |
| Split Safety | Training/validation/test label hashes | Formal validator |
| Fixed Seed | `task_seed_hash` + `task_seed_strategy` | Formal validator |
| Parallel Determinism | Worker count + ordering + seed strategy | Formal validator |
| Clean/Cache | `stale_artifacts=0` | Formal validator |
| Publication Completeness | 5 core figure triplets (png+pdf+svg) | Formal validator |
| overall_run→overall_adv | upstream_run_id + cohort hash | `overall_adv validate --mode fast` |
| overall_run→part_adv | upstream_run_id + cohort hash | `part_adv validate --mode fast` |

### Middle/Full Gates (Secondary)

`middle` and `full` profiles use the same validator but with extended data.
They are **not** primary engineering gates. Their smoke/readiness results
are preserved but not used for gate decisions.

## Command Semantics

### `validate` — Read-Only Contract Check

```powershell
# overall_run
python overall_run/main.py validate fast --progress detail --n-jobs 2

# overall_adv / part_adv
python overall_adv/main.py validate --mode fast
python part_adv/main.py validate --mode fast
```

`validate` checks:
- PRE data contract (file existence, schema, rows)
- Formal target consistency
- Registry hashes and artifact integrity
- Publication manifest and figure triplets
- Label identity and split safety
- Config/implementation hash matching

`validate` does NOT:
- Re-run any computation
- Re-train any model
- Modify data or artifacts
- Change scientific parameters

### `report` — Frozen Publication Generation

```powershell
python overall_run/main.py report fast --progress detail --n-jobs 2
```

`report` reads FROZEN published artifacts and generates tables, figures, audits.
It never re-trains models or re-runs M1–M4.

## Engineering vs. Scientific Status

| Status | Meaning | Gate |
|--------|---------|------|
| `engineering_status=PASS` | All formal validators pass | Automated |
| `scientific_status=PASS` | All required scientific gates pass (incl. D6 distributional metrics; thresholds frozen 2026-08-03) | Automated |
| `scientific_status=STOP_AND_REVIEW` | At least one required acceptance gate failed; needs human review (e.g. `PASSENGER_PROXY_SUPPORT_FAIL` on middle) | Manual review |

Fast engineering PASS does NOT imply scientific validity. Scientific
acceptance follows a separate review gate with D6 numeric thresholds.

## P1 Integration Gate

P1 integration requires:
1. `FORMAL_P1_INTEGRATION_ALLOWED=YES`
2. All fast engineering gates PASS
3. Scientific review complete

P1 is **not yet formally integrated** as of R1.5.

## Stop Conditions

The following conditions halt execution immediately:

```
PRE_REGISTRY_INVALID
DUPLICATE_ACTIVE_RUN
HALF_WRITTEN_OUTPUT
UNDECLARED_SCIENTIFIC_DELTA
CORE_REGISTRY_FAIL
PUBLICATION_REGISTRY_FAIL
D6_CURRENT_OUTPUT_FAIL
OVERALL_ADV_LINEAGE_STALE
PART_ADV_LINEAGE_STALE
SCHEMA_BREAK
NUMERICAL_NONDETERMINISM
```
