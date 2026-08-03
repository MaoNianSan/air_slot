# Clean, Cache, and Resume

**Version**: R1.5
**Modules**: `clean_common.py`, per-module `clean.py`

## Clean Contract

Clean is always an **explicit, independent command**. `main.py` never calls `clean.py`.

### Command

```powershell
python <module>/clean.py --mode <mode> [--dry-run] [--stop-owned-processes]
python <module>/clean.py --all-output [--dry-run]
```

### Supported Modes (per module)

| Module | Supported Modes |
|--------|----------------|
| `pre` | `fast`, `diagnostic`, `acceptance_23d`, `middle`, `middle_smoke`, `full`, `precision` |
| `overall_run` | `fast`, `diagnostic`, `acceptance_23d`, `middle`, `middle_smoke`, `full`, `precision` |
| `overall_adv` | `fast`, `diagnostic`, `acceptance_23d`, `middle`, `middle_smoke`, `full` |
| `part_adv` | `fast`, `diagnostic`, `acceptance_23d`, `middle`, `middle_smoke`, `full`, `precision` |

### Safety Guarantees

1. **Never deletes `data/`** — read-only data is never touched
2. **Never deletes `pre/cache/`** — PRE cache is preserved across cleans
3. **Refuses active runs** — checks `run_state.json` for active owned processes
4. **`--dry-run` reports without deleting** — safe preview mode
5. **`--stop-owned-processes` requires ownership match** — module, mode, run_id, PID must all match
6. **Frozen baselines are NOT deleted by default** — only runtime output for specified mode

### What Gets Cleaned

| Scope | Effect |
|-------|--------|
| `--mode fast` | Removes `output/fast/` for that module only |
| `--all-output` | Removes all `output/*/` for that module only |
| Staging | Removes `.staging/` residuals within the target |

### What Is Preserved

| Path | Protected By |
|------|-------------|
| `data/` | Hard boundary check |
| `pre/cache/` | Explicit exclusion |
| Other modules' output | Module-scoped clean |
| Active run output | `run_state.json` ownership check |

## Cache Isolation

- PRE maintains `pre/cache/` for reusable state/flow computation
- `--rebuild-cache` flag forces cache regeneration
- Cache keys are derived from input hashes + config hashes
- Cache is NOT invalidated by `--n-jobs` changes (thread count doesn't affect output)

## Resume Contract

### overall_run

Resume is only from an EXPLICIT isolated staging path:

```powershell
python overall_run/main.py fast --resume PATH --progress normal --n-jobs 1
```

The staging path must be under `output/.staging/`. Required checkpoint files:
`m1.joblib`, `m2.joblib`, `m4.joblib`.

### overall_adv / part_adv

`--resume` flag resumes a hash-valid incomplete mode output:

```powershell
python overall_adv/main.py fast --resume
python part_adv/main.py fast --resume
```

Hash validation checks: input, scientific config, task partition, target contract,
and task output hashes. Changing only `--n-jobs` does not change task identity.

## Invariants

- Clean is always explicit, never automatic
- Clean does NOT delete frozen baselines by default
- Clean is module-scoped (each module cleans only its own output)
- Cache keys are deterministic and input-hash-based
- Resume requires full hash validation, not just file existence
