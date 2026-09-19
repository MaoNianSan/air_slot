"""Gate-A evidence equivalence checks for the structural refactor."""

from __future__ import annotations

import json
import re
from pathlib import Path

from formal import v2_phase7_final_test_run as runner


def test_gate_a_refactor_evidence_equivalence(tmp_path: Path) -> None:
    evidence_root = Path("artifacts") / "experiment" / "final_test_v2"
    committed_dry_run = evidence_root / "GATE_A_DRY_RUN.json"
    committed_preflight = evidence_root / "GATE_A_PREFLIGHT.json"

    generated_dry_run = runner.run_dry_run()
    generated_dry_run_path = tmp_path / "GATE_A_DRY_RUN.json"
    runner._write_json_atomic(generated_dry_run_path, generated_dry_run)
    assert generated_dry_run_path.read_bytes() == committed_dry_run.read_bytes()

    observed_preflight = json.loads(committed_preflight.read_text(encoding="utf-8"))
    generated_preflight = runner.build_gate_a_preflight()
    observed_commit = observed_preflight.pop("gate_a_commit")
    assert observed_commit == "RESOLVED_AFTER_GATE_A_COMMIT" or re.fullmatch(
        r"[0-9a-f]{40}", observed_commit
    )
    generated_preflight.pop("gate_a_commit")
    assert observed_preflight == generated_preflight
