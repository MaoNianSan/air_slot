"""Epoch-scoped pre-open access-boundary tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

from formal.v2_phase7 import constants as C
from formal.v2_phase7 import gate_b0


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _epoch_fixture(tmp_path: Path) -> tuple[C.EpochPaths, C.EpochPaths]:
    historical_root = tmp_path / "historical_epoch"
    current_root = tmp_path / "current_epoch"
    historical = C.epoch_paths_for(historical_root)
    current = C.epoch_paths_for(current_root)
    _write(historical.gate_b_release_path, "historical release\n")
    _write(historical.access_audit_path, "historical audit\n")
    return current, historical


def _boundary(
    current: C.EpochPaths,
    historical: C.EpochPaths,
) -> dict[str, object]:
    return gate_b0._access_boundary(
        epoch_paths=current,
        historical_paths=historical,
    )


def test_historical_epoch_does_not_block_new_epoch_pre_open(
    tmp_path: Path,
) -> None:
    current, historical = _epoch_fixture(tmp_path)
    result = _boundary(current, historical)

    assert result["status"] == "PASS"
    assert result["current_epoch_release_present"] is False
    assert result["current_epoch_access_audit_present"] is False
    assert result["current_epoch_access_count"] == 0
    assert result["historical_epoch_present"] is True
    assert result["historical_epoch_release_present"] is True
    assert result["historical_epoch_access_audit_present"] is True
    assert result["historical_epoch_used_for_scientific_computation"] is False
    assert result["historical_epoch_used_for_selection"] is False


def test_new_epoch_release_fails_pre_open(tmp_path: Path) -> None:
    current, historical = _epoch_fixture(tmp_path)
    _write(current.gate_b_release_path, "current release\n")

    result = _boundary(current, historical)

    assert result["status"] == "FAIL"
    assert result["current_epoch_release_present"] is True
    assert result["current_epoch_access_audit_present"] is False


def test_new_epoch_access_audit_fails_pre_open(tmp_path: Path) -> None:
    current, historical = _epoch_fixture(tmp_path)
    _write(current.access_audit_path, "current audit\n")

    result = _boundary(current, historical)

    assert result["status"] == "FAIL"
    assert result["current_epoch_release_present"] is False
    assert result["current_epoch_access_audit_present"] is True
    assert result["current_epoch_access_count"] == 0


def test_historical_release_and_audit_remain_unchanged(tmp_path: Path) -> None:
    current, historical = _epoch_fixture(tmp_path)
    before = {
        "release": _sha256(historical.gate_b_release_path),
        "audit": _sha256(historical.access_audit_path),
    }

    result = _boundary(current, historical)

    assert result["status"] == "PASS"
    assert _sha256(historical.gate_b_release_path) == before["release"]
    assert _sha256(historical.access_audit_path) == before["audit"]


def test_current_and_historical_epoch_roots_are_distinct(tmp_path: Path) -> None:
    current, historical = _epoch_fixture(tmp_path)
    result = _boundary(current, historical)

    assert Path(result["current_epoch_root"]).resolve() != Path(
        result["historical_epoch_root"]
    ).resolve()
    assert (
        current.gate_b_release_path.resolve()
        != historical.gate_b_release_path.resolve()
    )
    assert current.access_audit_path.resolve() != historical.access_audit_path.resolve()


def test_stage_matched_epoch_path_bundle_is_complete() -> None:
    paths = C.stage_matched_epoch_paths()
    assert paths.root != C.FINAL_TEST_V2_ROOT
    assert paths.gate_a_preflight_path == paths.root / "GATE_A_PREFLIGHT.json"
    assert paths.gate_a_dry_run_path == paths.root / "GATE_A_DRY_RUN.json"
    assert paths.gate_b_release_path == paths.root / "GATE_B_HUMAN_RELEASE.json"
    assert paths.access_audit_path == paths.root / "PHASE7_ACCESS_AUDIT.json"
    assert paths.scientific_output_root == paths.root / "checkpoints"
    assert paths.checkpoint_root == paths.scientific_output_root


def test_gate_b0_ignores_historical_release_and_audit_for_new_epoch(
    tmp_path: Path,
) -> None:
    current, historical = _epoch_fixture(tmp_path)
    report = gate_b0.run_gate_b0_binding_audit(
        output_root=tmp_path / "gate_b0_report.json",
        fixture_root=tmp_path / "fixture",
        node_limit=16,
        write=False,
        epoch_paths=current,
        historical_paths=historical,
    )
    assert report["status"] == "PASS"
    access = report["access_boundary"]
    assert access["current_epoch_release_present"] is False
    assert access["current_epoch_access_audit_present"] is False
    assert access["current_epoch_access_count"] == 0
    assert access["historical_epoch_release_present"] is True
    assert access["historical_epoch_access_audit_present"] is True
