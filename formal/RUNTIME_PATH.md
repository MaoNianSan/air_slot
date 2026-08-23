# Formal Runtime Path

Use the typed protocol runners under `exp/exp1`, `exp/exp2`, `exp/exp3`, and
`exp/exp4`. They bind shared identities through `exp/common/context.py` and
`exp/common/frozen_artifact_loader.py`.

The archived V1/Exp234 and direct CU/RMB workflows under `archive/` are
provenance-only. Compatibility shims exist only to keep historical tests and
readers importable; they must not be used for formal experiment execution.
