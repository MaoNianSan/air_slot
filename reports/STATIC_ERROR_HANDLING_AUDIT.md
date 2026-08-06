# Static Error Handling Audit

Audit date: 2026-08-02

STATIC_ERROR_HANDLING_AUDIT=FAIL

## Confirmed protections

- Missing required PRE predecessor keys raise at `pre/src/pipeline_config.py:126-143`.
- Missing/unsupported typed gates fail closed at `overall_run/src/m4_screening.py:242-260`.
- Ranking padding with a non-null action is rejected at `ranking_contract.py:125-132`.
- Missing upstream artifacts are rejected by overall_adv and part_adv loaders.

## Defects

- PRE configuration uses an unrestricted recursive merge (`pre/src/pipeline_config.py:26-33`) and its validator does not reject unknown fields. The active injection `unknown PRE override field added` was silently accepted.
- overall_adv and part_adv apply shallow `cfg.update(...)` overrides (`overall_adv/src/pipeline_analysis.py:26-30`, `part_adv/src/pipeline_inputs.py:22-26`) without a schema or unknown-field rejection.
- `build_predecessor_features` catches broad `Exception` and silently substitutes `NaN` for movement and turnaround reference failures (`pre/src/predecessor_matcher.py:271-286`), which can conceal programming and schema errors.
- M3 boolean fields are not type-validated: injected string `"false"` remains a truthy string in `Action.capacity_required`.
- The ranking builder returns an empty frame for empty input (`ranking_contract.py:34-36`), so a known zero-candidate episode cannot receive the required fixed-width padding.
- The Global/Local ranking comparator treats a candidate-set contract violation as a normal `DIFFERENT_SET` result instead of rejecting it.

## Validator depth

Existing validators inspect schemas, row counts, lineage, padding, and artifact hashes. They are stronger than file-existence checks, but the defects above remain outside their rejection surface.
