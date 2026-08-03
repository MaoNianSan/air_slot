# Run Profiles

**Version**: R1.5 (profile specification freeze)
**Module**: `run_profiles.py`

## Frozen Profiles

Three formal run profiles are frozen under R1.5:

| Profile | Purpose | Compute Profile | Data Selection |
|---------|---------|-----------------|----------------|
| `fast` | **Engineering gate** — validates full M1–M4 chain on a fixed anchor-day subset | `fast` | Fixed 5 anchor days |
| `middle` | 72-day design — the original scientific evaluation scale | `full` | 72-day trailing window |
| `full` | Continuous complete calendar months or all qualified data | `full` | `full_data_readiness()` gate |

## Special-Purpose Profiles

| Profile | Purpose | Compute |
|---------|---------|---------|
| `diagnostic` | Debug and development diagnostics | `diagnostic` |
| `precision` | Convergence and precision evaluation | `precision` |

## Legacy Compatibility

| Token | Resolves To | Status |
|-------|------------|--------|
| `adapt_full` | `acceptance_23d` (alias) | Legacy only; NOT a fourth profile size |
| `acceptance_23d` | Self | Legacy compatibility; uses `full` compute |

## Profile Contract

Defined by `ProfileContract` dataclass in `run_profiles.py`:

```python
@dataclass(frozen=True)
class ProfileContract:
    requested_token: str      # Raw CLI token (e.g. "adapt_full")
    profile_id: str           # Resolved canonical ID (e.g. "acceptance_23d")
    run_profile: str | None   # Actual run profile; None for acceptance-only
    acceptance_profile: str | None  # Acceptance profile; None for run profiles
    compute_profile: str      # Compute tier: "fast", "diagnostic", "full"
    legacy_token: str | None  # Legacy alias if applicable
    smoke_subset: bool        # Whether smoke subset is active
    output_id: str            # Output directory name
```

## Resolution Rules

1. `adapt_full` is aliased to `acceptance_23d` via `PROFILE_ALIASES`
2. `acceptance_23d` sets `run_profile=None`, `acceptance_profile="acceptance_23d"`, `compute_profile="full"`
3. `middle` and `full` use `compute_profile="full"`
4. `fast` and `diagnostic` use their own compute profiles
5. `--smoke-subset` is only valid for `middle` profile
6. `output_id` is `{profile_id}_smoke` when smoke_subset=True

## Profile Selection Guide

| Scenario | Recommended Profile |
|----------|-------------------|
| Engineering gate / CI | `fast` |
| Scientific evaluation (72-day) | `middle` |
| Full data readiness | `full` |
| Development / debugging | `diagnostic` |
| Precision evaluation | `precision` |
| Cloud acceptance | `acceptance_23d` (via `adapt_full`) |

## Invariants

- `fast` is the only engineering gate profile
- `fast` data selection is frozen (5 anchor days)
- `full` is gated by `full_data_readiness()` — at least one continuous complete calendar month
- `acceptance_23d` / `adapt_full` are NOT a fourth profile size
- Profile resolution is deterministic and idempotent
- `smoke_subset` only applies to `middle`
