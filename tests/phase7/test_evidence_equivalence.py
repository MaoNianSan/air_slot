"""Gate-A evidence equivalence checks for the structural refactor."""

from __future__ import annotations

import json
import pytest
import re
from pathlib import Path

from formal import v2_phase7_final_test_run as runner
from formal.v2_phase7 import constants as C


def test_gate_a_refactor_evidence_equivalence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release_path = C.ROOT / "tmp" / f"NO_RELEASE_{tmp_path.name}.json"
    audit_path = C.ROOT / "tmp" / f"NO_AUDIT_{tmp_path.name}.json"
    monkeypatch.setattr(C, "GATE_B_RELEASE_PATH", release_path)
    monkeypatch.setattr(C, "PHASE7_ACCESS_AUDIT_PATH", audit_path)
    evidence_root = Path("artifacts") / "experiment" / "final_test_v2"
    committed_dry_run = evidence_root / "GATE_A_DRY_RUN.json"
    committed_preflight = evidence_root / "GATE_A_PREFLIGHT.json"

    generated_dry_run = runner.run_dry_run()
    generated_dry_run_path = tmp_path / "GATE_A_DRY_RUN.json"
    runner._write_json_atomic(generated_dry_run_path, generated_dry_run)
    assert generated_dry_run_path.read_bytes() == committed_dry_run.read_bytes()

    observed_preflight = json.loads(committed_preflight.read_text(encoding="utf-8"))
    historical = runner.historical_epoch_paths()
    current = runner.epoch_paths_for(tmp_path / "gate_a_equivalence_epoch")
    generated_preflight = runner.build_gate_a_preflight(
        epoch_paths=current,
        historical_paths=historical,
    )
    observed_commit = observed_preflight.pop("gate_a_commit")
    assert observed_commit == "RESOLVED_AFTER_GATE_A_COMMIT" or re.fullmatch(
        r"[0-9a-f]{40}", observed_commit
    )
    generated_preflight.pop("gate_a_commit")
    for key, value in observed_preflight.items():
        if key in {"access_boundary", "release_schema"}:
            for legacy_key, legacy_value in value.items():
                if key == "release_schema" and legacy_key == "path":
                    continue
                assert generated_preflight[key][legacy_key] == legacy_value
            continue
        assert generated_preflight[key] == value
