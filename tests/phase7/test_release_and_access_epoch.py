"""Gate-B release schema and one-epoch access-ledger tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from formal import v2_phase7_final_test_run as runner


RELEASE_KEYS = {
    "gate_a_commit",
    "instruction_sha256",
    "freeze_tag_object",
    "freeze_tag_target_commit",
    "cohort_authority_sha256",
    "cohort_manifest_sha256",
    "human_approved",
    "human_approval_timestamp",
}


def _write_release(path: Path, release: dict[str, object]) -> Path:
    path.write_text(
        json.dumps(release, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def test_release_schema_is_exact_and_has_no_bare_selection_fields() -> None:
    release = runner.make_release()
    assert set(release) == RELEASE_KEYS
    assert "selection_reused" not in release
    assert "selection_reperformed" not in release
    assert runner.validate_release_schema(release)["status"] == "PASS"

    with pytest.raises(runner.TypedBlocker) as error:
        runner.validate_release_schema({**release, "selection_reused": True})
    assert error.value.code == "GATE_B_RELEASE_SCHEMA_MISMATCH"

    with pytest.raises(runner.TypedBlocker) as approval_error:
        runner.validate_release_schema({**release, "human_approved": False})
    assert approval_error.value.code == "GATE_B_RELEASE_HUMAN_APPROVAL_REQUIRED"


def test_access_epoch_is_idempotent_for_the_same_release(
    tmp_path: Path,
) -> None:
    release = runner.make_release()
    audit_path = tmp_path / "PHASE7_ACCESS_AUDIT.json"
    first = runner.open_access_epoch(
        audit_path,
        release,
        timestamp="2026-09-19T00:00:00+00:00",
    )
    second = runner.open_access_epoch(
        audit_path,
        release,
        timestamp="2026-09-19T00:00:01+00:00",
    )
    assert first["phase7_increment"] == 1
    assert first["historical_access_total"] == 1
    assert first["current_total"] == 2
    assert first["raw_read_started"] is False
    assert first["raw_read_completed"] is False
    assert second["access_epoch_id"] == first["access_epoch_id"]
    assert second["retry_within_same_epoch"] is True
    assert second["retry_count"] == 1
    assert second["phase7_increment"] == 1
    assert second["current_total"] == 2


def test_different_release_cannot_reuse_an_open_epoch(tmp_path: Path) -> None:
    audit_path = tmp_path / "PHASE7_ACCESS_AUDIT.json"
    first = runner.make_release(
        human_approval_timestamp="2026-09-19T00:00:00+00:00"
    )
    second = runner.make_release(
        human_approval_timestamp="2026-09-19T00:00:01+00:00"
    )
    runner.open_access_epoch(audit_path, first)
    with pytest.raises(runner.TypedBlocker) as error:
        runner.open_access_epoch(audit_path, second)
    assert error.value.code == "PHASE7_ACCESS_EPOCH_ID_MISMATCH"


def test_unbound_gate_b_validates_release_but_does_not_open_epoch(
    tmp_path: Path,
) -> None:
    release_path = _write_release(tmp_path / "release.json", runner.make_release())
    audit_path = tmp_path / "PHASE7_ACCESS_AUDIT.json"
    with pytest.raises(runner.TypedBlocker) as error:
        runner.execute_gate_b(release_path=release_path, audit_path=audit_path)
    assert error.value.code == "GATE_B_SCIENTIFIC_EXECUTOR_NOT_BOUND"
    assert not audit_path.exists()


def test_bound_executor_uses_one_completed_epoch(tmp_path: Path) -> None:
    release_path = _write_release(tmp_path / "release.json", runner.make_release())
    audit_path = tmp_path / "PHASE7_ACCESS_AUDIT.json"
    calls: list[dict[str, object]] = []

    def pipeline(context: dict[str, object]) -> dict[str, object]:
        calls.append(context)
        return {"status": "PASS", "synthetic": True}

    result = runner.execute_gate_b(
        release_path=release_path,
        audit_path=audit_path,
        pipeline=pipeline,
    )
    assert result["status"] == "PASS"
    assert len(calls) == 1
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["status"] == "PHASE7_ACCESS_EPOCH_COMPLETE"
    assert audit["raw_read_started"] is True
    assert audit["raw_read_completed"] is True
    assert audit["historical_access_total"] == 1
    assert audit["phase7_increment"] == 1
    assert audit["current_total"] == 2
