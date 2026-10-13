import json
from pathlib import Path

import pytest

from exp.jatm_s34.shared_run import (
    _run_evaluation_stages,
    evaluation_is_current,
)
from exp.jatm_s34.shared_store import atomic_json


def _write_stage(folder: Path, filename: str, value: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / filename).write_text(
        json.dumps({"value": value, "final_test_access_count": 0}), encoding="utf-8"
    )
    (folder / "detail.json").write_text(json.dumps({"detail": value}), encoding="utf-8")


def _setup_shared(root: Path) -> Path:
    shared = root / "shared"
    fixed = shared / "fixed_common"
    for folder in (shared, fixed):
        folder.mkdir(parents=True)
        atomic_json(folder / "CACHE_MANIFEST.json", {"identity": folder.name})
        atomic_json(folder / "SHARED_ANNUAL_MANIFEST.json", {"identity": folder.name})
    return shared


def test_stage_receipts_resume_after_later_stage_failure(tmp_path):
    shared = _setup_shared(tmp_path)
    calls = {"local": 0, "prepare": 0, "fixed": 0, "e2e3": 0}

    def local(_source, out):
        calls["local"] += 1
        _write_stage(out, "E1_PAIRED_SUMMARY.json", "local")

    def prepare():
        calls["prepare"] += 1

    def fixed(_source, out):
        calls["fixed"] += 1
        _write_stage(out, "E1_PAIRED_SUMMARY.json", "fixed")

    def e2e3(_source, out):
        calls["e2e3"] += 1
        if calls["e2e3"] == 1:
            raise RuntimeError("simulated interruption before E2/E3 receipt")
        _write_stage(out, "E2_E3_SUMMARY.json", "e2e3")

    identity = {"cache": "cache-hash", "algorithm": "algorithm-hash"}
    with pytest.raises(RuntimeError, match="simulated interruption"):
        _run_evaluation_stages(
            tmp_path,
            shared,
            identity,
            e1_runner=local,
            fixed_prepare=prepare,
            fixed_runner=fixed,
            e2e3_runner=e2e3,
        )

    _run_evaluation_stages(
        tmp_path,
        shared,
        identity,
        e1_runner=local,
        fixed_prepare=prepare,
        fixed_runner=fixed,
        e2e3_runner=e2e3,
    )

    assert calls == {"local": 1, "prepare": 1, "fixed": 1, "e2e3": 2}
    assert evaluation_is_current(tmp_path, identity)


def test_receipt_invalidates_only_corrupt_stage_outputs(tmp_path):
    shared = _setup_shared(tmp_path)
    calls = {"local": 0, "prepare": 0, "fixed": 0, "e2e3": 0}

    def local(_source, out):
        calls["local"] += 1
        _write_stage(out, "E1_PAIRED_SUMMARY.json", f"local-{calls['local']}")

    def prepare():
        calls["prepare"] += 1

    def fixed(_source, out):
        calls["fixed"] += 1
        _write_stage(out, "E1_PAIRED_SUMMARY.json", "fixed")

    def e2e3(_source, out):
        calls["e2e3"] += 1
        _write_stage(out, "E2_E3_SUMMARY.json", "e2e3")

    identity = {"cache": "cache-hash", "algorithm": "algorithm-hash"}
    kwargs = dict(e1_runner=local, fixed_prepare=prepare, fixed_runner=fixed, e2e3_runner=e2e3)
    _run_evaluation_stages(tmp_path, shared, identity, **kwargs)
    (tmp_path / "E1" / "detail.json").write_text("corrupted", encoding="utf-8")
    _run_evaluation_stages(tmp_path, shared, identity, **kwargs)

    assert calls == {"local": 2, "prepare": 1, "fixed": 1, "e2e3": 1}
    assert evaluation_is_current(tmp_path, identity)


def test_cloud_scheduler_records_linux_uss_and_cpu_time():
    from types import SimpleNamespace

    from exp.jatm_s34.cloud_schedule import process_usage

    class Process:
        def memory_info(self):
            return SimpleNamespace(rss=900, private=None)

        def memory_full_info(self):
            return SimpleNamespace(uss=500)

        def cpu_times(self):
            return SimpleNamespace(user=12.5, system=3.25)

    assert process_usage(Process()) == {
        "rss_bytes": 900,
        "private_bytes": 500,
        "cpu_seconds": 15.75,
    }


def test_missing_annual_m1_training_requires_explicit_year_authorization():
    from exp.jatm_s34.cloud_train_models import validate_authorization

    approved = {
        "schema": "JATM_ANNUAL_M1_TRAINING_AUTHORIZATION_V1",
        "status": "USER_APPROVED",
        "years": [2020],
        "n": 4096,
        "roles": ["M1_HISTORY_PRIMARY", "M1_CURRENT_COMPARATOR"],
        "train_months": [1, 2, 3, 4, 5, 6],
        "calibration_months": [7],
        "development_used_for_fit": False,
        "final_test_access_count": 0,
    }
    validate_authorization(approved, 2020)
    with pytest.raises(ValueError, match="YEAR_NOT_AUTHORIZED"):
        validate_authorization(approved, 2021)
    approved["status"] = "NOT_APPROVED"
    with pytest.raises(ValueError, match="AUTHORIZATION_INVALID:status"):
        validate_authorization(approved, 2020)


def test_source_only_archive_can_bind_commit_without_git_metadata(tmp_path):
    from deploy.jatm_cloud.prepare_source_snapshot import prepare

    head = "7ed39edc2f4de5853983a6f8e2be926fceec501f"
    archive_hash = "sha256:" + "a" * 64
    expected = prepare(tmp_path, head, archive_hash)
    assert prepare(tmp_path, head, archive_hash) == expected
    with pytest.raises(FileExistsError, match="IDENTITY_CONFLICT"):
        prepare(tmp_path, "8ed39edc2f4de5853983a6f8e2be926fceec501f", archive_hash)
