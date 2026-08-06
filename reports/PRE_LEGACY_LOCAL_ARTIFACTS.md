# PRE Retired Local Artifacts

Inventory date: 2026-08-05  
Repository HEAD: `6627a705bf331c3d1a79aa201d598eee543d4d8d`

| Path | Audit state | Final action |
|---|---|---|
| `pre/output/` | 174 files, 1,394,306,785 bytes; retired PRE output and intermediates | Deleted |
| Confirmed predecessor Core staging under `pre/output_core/fast/` | Incomplete observation staging; not a V2 bundle | Deleted |
| `pre/output_core/` | Mixed local Core root before cleanup | Preserved; zero files remain after targeted deletion |
| `pre/cache/` | 5,379 files, 1,457,804,201 bytes; reusable source extraction cache | Preserved unchanged |
| Separate PRE staging root | Absent | No action |
| `data/` | Raw/source data | Preserved unchanged |
| `pre/reports/published/core_v2/` | Curated V2 implementation evidence | Preserved and refreshed |

## Enforcement

- Current code does not read `pre/output/` as a PRE fallback.
- The cache implementation no longer consults retired PRE output to decide
  reuse; it validates the current V2 cache directly.
- Unidentified cache data was not deleted.
- No Fast build, commit, branch, or push was started.

```text
RETIRED_PRE_OUTPUT_PRESENT=NO
CONFIRMED_PREDECESSOR_STAGING_PRESENT=NO
V2_CACHE_PRESERVED=YES
RAW_DATA_PRESERVED=YES
```
