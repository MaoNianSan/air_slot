# Execution and Thread Plans

**Version**: R1.5 (thread plan freeze)
**Module**: `downstream_common.py`

## Frozen Thread Plans

Under R1.5, default thread allocations are frozen:

| Module | Default `--n-jobs` | Rationale |
|--------|-------------------|-----------|
| `pre` | **1** | PRE is I/O-bound; single-thread is the authoritative reproduction path |
| `overall_run` | **2** | M1–M4 pipeline benefits from outer parallelism on quantile grid |
| `overall_adv` | **2** | Bootstrap replicates support bounded parallelism |
| `part_adv` | **2** | M1 model ensemble supports parallel fitting |

## Thread Plan Resolution

Defined by `resolve_parallel_plan()` in `downstream_common.py`:

```python
def resolve_parallel_plan(
    requested_n_jobs: int,
    task_count: int,
    prefer_outer_parallelism: bool = True,
) -> ParallelPlan:
```

### Resolution Logic

1. `requested_n_jobs=-1` resolves to `max(1, cpu_count - 1)`
2. Requested jobs are capped at `os.cpu_count()`
3. If `prefer_outer_parallelism=True` and `task_count > 1`:
   - `outer_workers = min(task_count, resolved)`
   - `inner_model_threads = 1`
   - `parallel_backend = "thread"`
4. Otherwise:
   - `outer_workers = 1`
   - `inner_model_threads = resolved`
   - `parallel_backend = "native"`
5. Enforces: `outer_workers * inner_model_threads <= resolved`

### Thread Environment

The runtime sets these environment variables to prevent nested parallelism:

```
OMP_NUM_THREADS=1
MKL_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
NUMEXPR_NUM_THREADS=1
```

## Manifest Recording

Every run records its thread plan in `run_summary.json`:

```json
{
  "requested_n_jobs": 2,
  "resolved_n_jobs": 2,
  "outer_workers": 2,
  "inner_model_threads": 1,
  "parallel_backend": "thread"
}
```

Thread overrides via CLI (`--n-jobs`) or environment (`AIR_SLOT_N_JOBS`) are
explicitly recorded. The plan does NOT silently adapt to machine CPU count when
an explicit value is provided.

## CLI Precedence

1. CLI `--n-jobs` (highest)
2. Environment `AIR_SLOT_N_JOBS`
3. Config file `compute.workers`
4. Default: `1`

## Seed Strategy

All modules use `SHA256_BASE_SEED_MODULE_MODE_STAGE_STABLE_TASK_ID_REPLICATE_ID`.
Seeds are derived from stable task IDs, not worker IDs. This ensures:

- Cross-thread reproducibility
- Cross-machine reproducibility (with same `--n-jobs`)
- Resumability after interruption

## Invariants

- `PRE_N_JOBS=1` is the authoritative reproduction path
- `DOWNSTREAM_N_JOBS=2` is the recommended cloud/parallel path
- Thread plans are recorded in every run manifest
- Thread environment prevents nested model parallelism
- Task seeds are worker-independent
- Registry publication happens only in the parent process
