# PRE V2 Downstream Migration Blockers

Date: 2026-08-05  
Status: `DOWNSTREAM_V2_MIGRATION_PENDING`

| Module | Retired input binding | V2 replacement input | Required Adapter work | Runnable now |
|---|---|---|---|---|
| `overall_run` | Precomputed episode/snapshot model frame, target lineage, rules, and evidence bundle | Episodes, events, source-global Observations, partitioned Membership, train-only references, registry, manifest | Build availability-safe `query_time` feature frames; define supported outcomes; freeze feature/label lineage; publish Adapter manifest | No |
| `overall_adv` | Published overall-run prediction, cohort, registry, and target identity tied to the retired input bundle | Adapter-backed overall-run publication with current PRE hashes and explicit evaluation cohort | Consume the new overall-run registry and verify cohort, prediction, cost, and recommendation lineage | No |
| `part_adv` | Retired PRE episode/snapshot inputs plus overall-run target identity | Adapter model frame and Adapter-backed overall-run publication | Define baseline/ablation input mapping without inventing unavailable outcomes | No |
| `downstream_common` | Shared historical cohort loader | Adapter-owned cohort loader | Replace the blocked function after Adapter publication exists | No |

## Current enforcement

`overall_run/main.py`, `overall_adv/main.py`, and `part_adv/main.py` all call the
same gate and return exit code 2 with:

```text
PRE_CONTRACT_MISMATCH:
AIR_CHAIN_CORE_V2 is the only available PRE contract.
The current downstream pipeline still expects the removed PRE contract.
Implement or enable the M1 Adapter before running M1-M4.
```

The gate executes before configuration resolution or data access. It does not
generate empty compatibility tables, relabel V2 data, read historical output,
or modify M1-M4 mathematics.

```text
DOWNSTREAM_MIGRATION_STATUS=PENDING
SILENT_FALLBACK_PRESENT=NO
COMPATIBILITY_BUNDLE_PRESENT=NO
M1_M4_ALGORITHM_CHANGED=NO
```
