# Experiment boundary

Experiment packages expose executable development interfaces, but the current runners are not yet
complete paper protocols. Evaluation variants must be derived from immutable frozen artifacts;
the shared runner rejects copied scalar metrics for non-smoke runs and guards FINAL_TEST against
tuning or frozen-contract changes. Smoke/foundation validation is not an experiment or a paper result.
