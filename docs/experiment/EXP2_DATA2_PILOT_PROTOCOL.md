# Exp2 Data2 Pilot Protocol

Status: `PREPARATION_ONLY_EXECUTION_BLOCKED`

## Purpose

The Data2 pilot is reserved for a small, frozen, predeclared subset after all required Data2, M1, M2, M3, and M4 scientific artifacts are supplied.  Its role is to exercise execution mechanics across `JOINT`, `MARGINAL`, `COLLAPSED`, `COMPONENT`, `CHANNEL`, and `SCALAR` while preserving the exact selected episode, decision-time, and scenario lineage.

`configs/experiment/exp2_data2_pilot.yaml` limits the future pilot declaration to at most five caller-frozen episode IDs.  It contains no episode IDs, no chosen scientific parameter, and no fallback.  `DATA2_VERSION_PENDING` and the missing frozen registry intentionally block execution.

## Required controls

- Use only the approved Data2 episode registry through `Data2EpisodeSelector`.
- Reject legal-record availability after the decision cutoff.
- Keep Data2 `realized_events` in their registered evaluation-outcome role; do not use post-hoc fields as decision-time inputs.
- Preserve PRE, M1, and M2 identities and scenario lineage exactly.
- Keep all six variants under the same frozen downstream artifacts.

## Not allowed

This pilot may not produce scientific conclusions, rank variants, select a best variant, generate paper tables, tune parameters, freeze new scientific artifacts, or authorize a full Exp2 run.  A pilot execution request requires an explicit later authorization after the named blockers are resolved.
