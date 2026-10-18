#!/usr/bin/env python3
"""Minimal real Development-only smoke (round 4, bounded annual Development).

Parameters mirror the 2026-10/11-12 smoke precedents (node_limit small,
chunk_size small, few bootstrap replicates). Development chain only; no Test/
Final-Test path; output tree under artifacts/experiment/jatm_s34/.
"""
import json
import sys
from pathlib import Path

REPO = Path("/data/airslot/worktree")
sys.path.insert(0, str(REPO))
from exp.jatm_s34.annual_development import run_year_bounded  # noqa: E402

out = REPO / "artifacts/experiment/jatm_s34/development_smoke_20261013_2019"
result = run_year_bounded(year=2019, output_root=out, n=4096, chunk_size=4,
                          node_limit=8, bootstrap_replicates=5)
print(json.dumps({k: result.get(k) for k in
                  ("schema_version", "status", "scientific_status",
                   "final_test_access_count", "bounded_memory", "chunk_size")},
                 indent=2, default=str))
print("SMOKE_RESULT:", "PASS" if result.get("status") == "DEVELOPMENT_COMPLETE" else "FAIL")
sys.exit(0 if result.get("status") == "DEVELOPMENT_COMPLETE" else 1)
