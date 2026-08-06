# M1 Matcher Code Audit

Audit date: 2026-08-02

M1_CODE_AUDIT=FAIL

## Correctly implemented

- `icao24` is normalized before matching in `pre/src/episode.py:92-96` using `pre/src/input.py:41-43`.
- Legs are stably sorted by `icao24`, `firstseen_utc`, `lastseen_utc`, and `flight_id` at `pre/src/predecessor_matcher.py:117-120`.
- Temporal order, overlap, gap, airport continuity, registration, typecode, endpoint quality, and split/merge risk produce explicit rejection reasons at `pre/src/predecessor_matcher.py:134-240`.
- Snapshot times are generated from `firstseen_utc + ratio * reference_movement_time` at `pre/src/snapshot.py:21-43`; `lastseen_utc` is used only to determine whether the snapshot still lies inside the current flight.
- Availability gating at `pre/src/predecessor_matcher.py:339-365` passed the required counterexample: t1 unavailable, t2/t3 available.
- The existing fast output has 142,659 snapshots, zero supported-predecessor availability violations, and predecessor features in the published schema.

## Blocking matcher defect

The candidate builder uses exactly one `groupby("icao24").shift(1)` at `pre/src/predecessor_matcher.py:127-129`. It rejects an overlapping immediate row but does not search earlier rows for the latest valid non-overlapping predecessor.

Active counterexample:

- `valid_old` ends before the current flight and has airport continuity.
- `overlap` is the immediately preceding sorted row but overlaps the current flight.
- Expected selection: `valid_old`.
- Actual selection: `overlap`, then rejection `TEMPORAL_OVERLAP`.

This is a false-negative predecessor match and directly matches the workflow's warned `shift(1)` failure mode.

## Data characteristics, not parameter approval

- Candidate rate: 89.62%.
- Supported rate: 9.05%.
- The largest rejection class is `AIRPORT_DISCONTINUITY` (91,251 snapshot rows).
- Train/validation/test supported rates are close (9.09%, 9.00%, 9.00%), but no R3 parameter approval is made because code correctness failed first.
