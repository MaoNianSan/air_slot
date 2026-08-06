# M1 Leakage Code Audit

Audit date: 2026-08-02

M1_LEAKAGE_AUDIT=PASS

- The M1 feature contract is an allowlist and additionally removes `lastseen`, target/outcome, `future_`, `successor_`, action, scenario, residual, score, and rank patterns in `overall_run/config/scientific.yaml:72-83`.
- An injected `future_successor_delay` was excluded even after it was added to the allowlist.
- Current state extraction restricts event and availability time to the decision time at `pre/src/snapshot.py:116-121`.
- Predecessor features are nulled when their availability time is later than the snapshot decision time.
- Existing fast evidence contains zero supported-predecessor availability violations.

Previous-leg information available at decision time? YES, for rows marked `has_supported_predecessor=true`.
