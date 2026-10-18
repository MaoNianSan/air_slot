# Air Slot code inventory

- Generated: 2026-10-10 (Asia/Hong_Kong)
- Source: `{root}`
- HEAD: `08712933fe05c49ec77d9fc8a6286f408e17a2f9`
- Scope: read-only inventory; no formal code or frozen artifact changed.

## File counts
- `model`: 244 Python files
- `formal`: 47 Python files
- `validation`: 99 Python files
- `exp`: 56 Python files
- `data2/scripts`: 34 Python files

## Cross-layer imports
- `data2/scripts -> exp`: 4 import references
- `data2/scripts -> model`: 99 import references
- `data2/scripts -> validation`: 3 import references
- `exp -> formal`: 1 import references
- `exp -> model`: 96 import references
- `exp -> validation`: 2 import references
- `formal -> exp`: 14 import references
- `formal -> model`: 98 import references
- `formal -> validation`: 4 import references
- `validation -> exp`: 16 import references
- `validation -> formal`: 5 import references
- `validation -> model`: 318 import references

## Current candidate patch
- `model/common/section5_contracts.py` is the proposed shared contract module.
- `exp/jatm_section5/contracts.py` remains a compatibility re-export.
- `formal/v2_phase7/execution_freeze.py` now probes `model.common.section5_contracts`.

## Authority boundaries
- `model/` is scientific implementation authority.
- `formal/v2_phase7/` is frozen execution/projection authority.
- `validation/` is audit and validation layer.
- `exp/` is experiment and compatibility layer.
- `data2/scripts/` contains operational scripts with several direct model/validation imports; these are inventory findings, not yet refactored.
