# H/W Artifact Lineage After Ownership Migration

- migration date: `2026-08-17`
- repository HEAD during migration: `88ad2843c8f2713cd4ae6c704b7d9247442ea51e`
- migration worktree status: `UNCOMMITTED_BY_INSTRUCTION`
- architecture tree hash: `sha256:4146d94aa3b69fc22769c558ce554e64447d519aba0eb2372d4665559a63b112`
- Final Test access count: `0`

The architecture tree hash is `content_id({relative_path: sha256(file_bytes)})`.
It covers the new M1 history/preparation modules, PRE cohort/development/support/
profiling/reference/streaming modules, PRE raw-schema and publisher changes,
exp-owned H/W runners, and ownership gate implementation. It is the reproducible
identity for the uncommitted architecture state; it is not represented as a Git
commit.

## Historical evidence identity

| Evidence | Original code SHA | Embedded evidence hash | File byte hash before migration | File byte hash after migration |
| --- | --- | --- | --- | --- |
| H selection | `4fcdd050ff3cec4760437909bacf55cf3fda016e` | `sha256:a56a7254e5e08c959d8e9d8be58456469b2f37a293f33495dfaf58cdf452b3a5` | `sha256:438b34a68243c97ae68aa3f32dd4f9e115aca335f3a5da11703fc94ebd588496` | `sha256:438b34a68243c97ae68aa3f32dd4f9e115aca335f3a5da11703fc94ebd588496` |
| W selection | `4fcdd050ff3cec4760437909bacf55cf3fda016e` | `sha256:35fed8273d737762a8c48321a1ce8bbd0aee76ff7c27537a57266430d3038fa1` | `sha256:4c6984effbf8c7d01be935565e0abd5370c74cd52446e2d3e22d3c0cdc32458b` | `sha256:4c6984effbf8c7d01be935565e0abd5370c74cd52446e2d3e22d3c0cdc32458b` |

The H/W JSON files were not opened for writing. Their byte identities are
unchanged.

## Frozen decisions

- `H_STAR = 32`
- `W_STAR = 30 minutes`
- status: `DEVELOPMENT_FROZEN`
- H rerun: `FALSE`
- W rerun: `FALSE`
- architecture migration creates a new model-selection result: `FALSE`

## Migration equivalence

The fixed-fixture and frozen-evidence suite verifies:

- episode identity and rolling-node identity;
- latest-admissible weather assignment;
- PRE target/family support and evidence/lineage state;
- M1 feature tensors within `rtol=1e-6`, `atol=1e-7`;
- M1 labels exactly;
- CURRENT, FIXED(30), and ADAPTIVE history exactly;
- H evidence aggregation exactly;
- W aggregation, 0.5 percent equivalence rule, and recommendation exactly;
- aggregate PRE streaming counts against full PRE publication on a typed fixture.
- the first 64 completed August 2019 Data2 rows through both the historical typed
  canonicalization path and the PRE lightweight streaming path, including episode
  identity.

Result at closure: `MIGRATION_EQUIVALENCE = PASS`.

Historical H/W evidence remains evidence about the code and artifacts recorded
at original SHA `4fcdd05`. The ownership migration is linked by exact regression
tests; it does not rewrite historical provenance to the current worktree.
