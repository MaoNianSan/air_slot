# Cloud-compute evidence snapshot — 2026-10-18

This folder gathers the source snapshots, execution outputs, logs, manifests, and manuscript backfill material for web review. It is a read-only packaging of existing artifacts; it does not claim new experiment runs or analysis.

## Start here

- `full_snapshot/SNAPSHOT_README.md` describes the dated cloud execution snapshot and its original provenance.
- `PUBLICATION_SUMMARY.json` gives file and byte counts; `PUBLICATION_MANIFEST.jsonl` maps every logical file to its SHA-256 and stored representation.
- `EXCLUSIONS.jsonl` records omitted paths and reasons.
- `code/` contains the canonical source snapshot, cloud source changes, Q4 runtime/overlay, and relevant local code.
- `full_snapshot/` contains the archived R8 execution snapshot and associated logs, metadata, and outputs.
- `q4_results/` contains the expanded Q4 result export.
- `review_materials/` contains the backfill package, Section 5 candidates, figures, Q4 package records, and review evidence.

## How to read the file manifest

Each manifest row records the original path, byte length, SHA-256, and storage mapping. A `duplicate` row points to the first stored copy through `stored_as`. Large files are split into ordered `.parts/part_*.txt` files; concatenate the listed parts in order to recover the original bytes, then verify against the row's `sha256`.

## Scope and boundaries

- The code snapshots identify the canonical source commit as `ffa74876bf3c4dfa7031da06e59bf91a0f2899ef`. Q4 outputs and code are dated 2026-10-15; the full cloud execution snapshot is dated 2026-10-14.
- Raw input observations and materialized input copies are excluded. Their binding manifests, metadata, and source code are retained where available.
- Transport/history archives are omitted; expanded content and source identities are represented separately.
- Historical artifact trees carried inside source snapshots and Final-Test result/freeze records are excluded. Final-Test `.py` source files are retained as code.
- The cloud connection attempt on 2026-10-18 was refused according to the packaging record, so this package does not establish the server's live state after the archived snapshots.
- Snapshot summaries and validation statements are historical records included for review; they have not been independently re-run as part of packaging.
