# Research Decisions

- Use content-addressed run identities; exclude wall-clock timestamps from the identity payload.
- Use `ThreadPoolExecutor` for bounded I/O-oriented parallel tasks, returning results in submitted order.
- Resume only when run identity, configuration hash, input hashes, and stage statuses match exactly.
- Treat progress JSONL as operational telemetry, not scientific evidence.
- Keep cleanup dry-run by default and constrain executable deletion to approved derived roots.
- A small real-data smoke verifies readers/contracts only; it does not imply complete real PRE publication or scientific validation.
- The synthetic end-to-end smoke is a wiring validation and is permanently non-paper.

