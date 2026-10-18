# Runtime Contracts

- All run/artifact paths are resolved and checked against an approved project output root before writing.
- `run_id = sha256(canonical(run_kind, config_hash, inputs, stage contract versions))`.
- Resume is exact-match only; mismatch raises `RESUME_MANIFEST_MISMATCH`.
- Progress event order is monotonic within a run.
- Worker completion timing cannot change output order or artifact identity.
- Smoke/fixture manifests always carry `paper_result=false`.
- A PRE-to-M4 run cannot enter M4 formal ranking when a critical M2 component is abstained.
- Real-smoke reads are bounded by both file and row limits and never write beneath raw roots.

