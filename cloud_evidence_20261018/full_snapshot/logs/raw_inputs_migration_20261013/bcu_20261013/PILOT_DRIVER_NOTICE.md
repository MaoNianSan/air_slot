# PILOT DRIVER NOTICE (round 6)

**Single-driver rule**: exactly ONE operator (ZCode round-6 agent session) must own the pilot task dirs under
tasks/pilot_* and tasks/tail_* etc. Parallel launches of the same pilot corrupt wall/RSS measurement records.

Incident on 2026-10-13: pilot_e2e3 was launched 4x (10:31:47, 11:05:02, 11:23:21 by a parallel session on the
same network; 11:30:26 by the round-6 driver). Actions taken by the round-6 driver:
- kept the EARLIEST instance (10:31:47, most advanced; first pass complete, second pass running);
- terminated the later duplicate (11:30:26) and its children;
- all measurements in PILOT_RESULTS.json will be attributed to the surviving instance, with this incident noted.

Planned sequence (do not launch duplicates):
1. E1 pilot 2019 (node_limit=128, chunk=4) - DONE 10:27:37, wall 38:34, PASS.
2. E2E3 pilot 2019 (node_limit=128, chunk=4, replicates=2000) - RUNNING since 10:31:47 (survivor instance).
3. E4 pilot 2019 (n_grid=(128), headroom->fit->ladder->eval) - to be launched by the round-6 driver after E2E3.
