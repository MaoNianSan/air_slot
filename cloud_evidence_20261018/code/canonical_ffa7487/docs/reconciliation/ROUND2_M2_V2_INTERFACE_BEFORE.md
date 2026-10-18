# Round 2 M2 V2 Interface Before Audit

Audit HEAD: `cbc4b137eb5de51a54095d77a177154e14873d2b`  
Starting worktree: clean  
Focused baseline: `67 passed, 1 skipped`

## Scope

This tranche closes the already-designed M2 V2 interface. It does not redesign native mechanisms, freeze pending scientific parameters, implement action logic, alter M4 ranking, or run experiments.

## Output-contract audit

| Required output | Before state | Closure required |
|---|---|---|
| `scenario_id` | present on scenario, native quantity, and component row | validate identity across all layers |
| `scenario_weight` | present only on scenario output | carry explicitly on each native/CU row and validate equality |
| `component_id` | exact ordered seven-component vector | retain exact order and uniqueness |
| native quantity | scalar plus native unit in `NativeQuantity`/`ConsequenceRow` | give native layer a stable artifact identity |
| CU quantity | scalar `constructed_value_cu` plus partial rule lineage | add a distinct typed CU object and frozen-registry artifact identity |
| `support_state` | present and abstention-safe | retain; unsupported must remain null/`ABSTAIN` |
| `reference_source` | present on scientific context only | propagate an explicit source to native and CU output rows |
| `reference_lineage` | present at scenario level and embedded in provenance text | carry a typed per-component lineage tuple and stable lineage hash |
| `confidence` | present only for node exposure | propagate component confidence; pure M1 quantities use explicit high confidence in scenario identity, unsupported inputs use none |

## CU/reference audit

The normalization code preserves registry ID, rule ID, and parameter version, but a frozen CU row does not currently expose registry digest, rule freeze ID, reference period, or normalization parameter. Therefore two otherwise similar registries can be distinguished only indirectly. Closure must make a scale-version/reference change produce a different CU artifact identity without invoking any monetary mapping.

## Exposure-lineage audit

The accepted hierarchy is already implemented and is not changed:

`same-aircraft successor > same-route reference > airport reference > global reference`.

Before closure, exposure records contain `support_level`, `reference_source`, `confidence`, freeze/provenance information, but no explicit `reference_id`, `reference_version`, or computed lineage hash. These fields must become reproducible and version-sensitive.

## Scenario-distribution audit

`M2Mapper.map_m1_scenarios` preserves every supplied scenario and validates weights per node. `summarize_formal_consequence` computes weighted mean, variance, CVaR, and tail probability. A typed distribution object is still missing, so the contract does not yet package identities and weights as one immutable M2-to-downstream interface.

## M3 namespace constraint

The requested path `model/M3/contracts/m2_action_interface.py` cannot coexist on Windows with the tracked file `model/M3/contracts.py`. Converting the module into a package would force broad import migration and exceeds the contract-only boundary. The compatible location is `model/M3/m2_action_interface.py`; it will contain contracts only and will not modify action behavior.

## Scientific gates retained

- V2 CU-scale registry freeze: pending human decision.
- `P_itinerary` evidence: pending; remains `ABSTAIN`.
- `P_service` evidence/rule: pending; remains `ABSTAIN`.
- same-route exposure reference: pending; no invented reference.
