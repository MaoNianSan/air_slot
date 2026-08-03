# Legacy Profile Migration

**Version**: R1.5

## Legacy Profiles

Two tokens exist for backward compatibility:

| Legacy Token | Resolves To | Status |
|-------------|------------|--------|
| `adapt_full` | `acceptance_23d` | Legacy alias; frozen under R1.5 |
| `acceptance_23d` | Self | Legacy compatibility; use `full` compute |

## Migration Path

### `adapt_full` → `acceptance_23d`

`adapt_full` is an alias defined in `PROFILE_ALIASES = {"adapt_full": "acceptance_23d"}`.
It resolves to:

```python
ProfileContract(
    requested_token="adapt_full",
    profile_id="acceptance_23d",
    run_profile=None,           # No run profile (acceptance-only)
    acceptance_profile="acceptance_23d",
    compute_profile="full",
    legacy_token="adapt_full",
    smoke_subset=False,
    output_id="acceptance_23d",
)
```

### Why `adapt_full` Is NOT a Fourth Profile

The three frozen profiles are `fast`, `middle`, `full`. `acceptance_23d` (and
its alias `adapt_full`) is an acceptance evaluation mode that uses `full`
compute but with a 23-day acceptance window. It is a **different evaluation
dimension**, not a fourth data scale.

## When to Use Each

| Need | Use |
|------|-----|
| Engineering gate | `fast` |
| Scientific evaluation | `middle` or `full` |
| Cloud acceptance | `acceptance_23d` (via `adapt_full`) |
| Legacy script compatibility | `adapt_full` (alias, unchanged behavior) |

## CLI Compatibility

Legacy tokens are accepted everywhere profiles are resolved:

```powershell
# These are equivalent:
python overall_run/main.py adapt_full
python overall_run/main.py acceptance_23d
```

The `legacy_token` field is recorded in the profile contract for audit purposes.

## Future Deprecation

No deprecation timeline is set as of R1.5. `adapt_full` and `acceptance_23d`
remain fully supported for backward compatibility. Future rounds may
consolidate acceptance into the `full` profile directly.

## Invariants

- `adapt_full` ≡ `acceptance_23d` (deterministic alias)
- `acceptance_23d` is NOT a fourth profile size
- Legacy tokens produce identical `compute_profile` and `output_id` as their canonical forms
- Profile resolution is idempotent: resolving the same token always yields the same contract
