"""R2-aware freeze ancestry validation.

The Phase-6 activation validator remains the historical validator for its own
checkout.  Current R2 checkouts use this module instead: it verifies that the
R2 freeze descends from the Phase-6 tag and that the frozen registry payloads
have not been rewritten.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from model.common.identity import content_id
from validation.v2_phase6_r2.common import PROJECT_ROOT, assert_not_final_test


SCHEMA_VERSION = "V2_PHASE7_FREEZE_ANCESTRY_VALIDATION_V1"
VALIDATOR_ID = "V2_PHASE7_FREEZE_ANCESTRY"
REPORT_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "v2_phase7"
    / "FREEZE_ANCESTRY_VALIDATION.json"
)

PHASE6_TAG = "v2-scientific-freeze"
PHASE6_TAG_OBJECT = "35d5fe1896dd9e17be92bec601f87ec33adb4d56"
PHASE6_TAG_TARGET = "d29fc769e74d6b46f86d3fdf7db18b3f9936f8b1"
R2_TAG = "v2-scientific-freeze-r2"
R2_TAG_OBJECT = "2dcca6c159dedde3803e63cb48bd8bfefff574cf"
R2_TAG_TARGET = "3834eed33d4a2ea4bdba111fc29cca3529525a3a"

PARENT_REGISTRY = "registries/v2_scientific_freeze.json"
PARENT_REGISTRY_FILE_SHA256 = (
    "sha256:2b89976da5158f0fee87222daef33a8b3b617d61ece94ade00a001869134afdd"
)
PARENT_REGISTRY_ARTIFACT_HASH = (
    "sha256:3828b17ac93cbaf81579e865faf32ed9547a1d540a65d3679ab4248a2bf17e2d"
)
PARENT_REGISTRY_BLOB_OID = "a8c43beffbdefaf2ca9c573ec7730ae9a2f55ce3"
R2_REGISTRY = "registries/v2_scientific_freeze_r2.json"
R2_REGISTRY_FILE_SHA256 = (
    "sha256:15c1e8bf5ec5fbb5ee783595a124b1255b550d7d7bc96e34b2cd3df0a4e88e6f"
)
R2_REGISTRY_ARTIFACT_HASH = (
    "sha256:4e7d3bb454e83779e6cbb592d4cf9d6ffddc0edf3435a7bc3d2822e4523417f2"
)
ADOPTED_REGISTRIES = (
    "registries/m2_data2_formal_cu_v5.json",
    "registries/passenger_reference_supersession_v3.json",
)
FINAL_TEST_ROOT = PROJECT_ROOT / "artifacts" / "experiment" / "final_test"


class FreezeAncestryError(RuntimeError):
    """Raised for an invalid checker invocation or inaccessible Git object."""


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "artifact_hash"}
    return content_id(body)


def _git_bytes(*args: str) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
    )
    return result.stdout


def _git_text(*args: str) -> str:
    return _git_bytes(*args).decode("utf-8").strip()


def _is_ancestor(ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
    )
    if result.returncode not in (0, 1):
        raise FreezeAncestryError(
            f"GIT_ANCESTRY_CHECK_FAILED:{ancestor}:{descendant}"
        )
    return result.returncode == 0


def _object_type(object_id: str) -> str:
    return _git_text("cat-file", "-t", object_id)


def _commit_bytes(commit: str, path: str) -> bytes:
    guarded = Path(PROJECT_ROOT / path).resolve()
    assert_not_final_test(guarded)
    return _git_bytes("show", f"{commit}:{path}")


def _read_commit_json(commit: str, path: str) -> dict[str, Any]:
    return json.loads(_commit_bytes(commit, path).decode("utf-8"))


def _check_registry_snapshot(
    *,
    path: str,
    commit: str,
    file_sha256: str,
    artifact_hash: str,
    failures: list[str],
    label: str,
) -> dict[str, Any]:
    try:
        raw = _commit_bytes(commit, path)
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        failures.append(f"{label}_READ_FAILED:{error}")
        return {"path": path, "commit": commit, "status": "FAIL"}
    actual_file_sha256 = _sha256_bytes(raw)
    actual_artifact_hash = payload.get("artifact_hash")
    computed_artifact_hash = _payload_sha256(payload)
    if actual_file_sha256 != file_sha256:
        failures.append(f"{label}_FILE_HASH_MISMATCH")
    if actual_artifact_hash != artifact_hash:
        failures.append(f"{label}_ARTIFACT_HASH_MISMATCH")
    if computed_artifact_hash != artifact_hash:
        failures.append(f"{label}_PAYLOAD_HASH_MISMATCH")
    return {
        "path": path,
        "commit": commit,
        "file_sha256": actual_file_sha256,
        "expected_file_sha256": file_sha256,
        "artifact_hash": actual_artifact_hash,
        "expected_artifact_hash": artifact_hash,
        "payload_hash": computed_artifact_hash,
        "status": (
            "PASS"
            if actual_file_sha256 == file_sha256
            and actual_artifact_hash == artifact_hash
            and computed_artifact_hash == artifact_hash
            else "FAIL"
        ),
    }


def _registry_payload_at_head(path: str) -> dict[str, Any]:
    guarded = Path(PROJECT_ROOT / path).resolve()
    assert_not_final_test(guarded)
    return json.loads(guarded.read_text(encoding="utf-8"))


def _current_head() -> str:
    return _git_text("rev-parse", "HEAD")


def _registry_immutability(
    *,
    parent_commit: str,
    r2_commit: str,
    failures: list[str],
) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for path, expected_hash, label, exists_at_parent in (
        (PARENT_REGISTRY, PARENT_REGISTRY_FILE_SHA256, "PARENT_REGISTRY", True),
        (R2_REGISTRY, R2_REGISTRY_FILE_SHA256, "R2_REGISTRY", False),
    ):
        r2_raw = _commit_bytes(r2_commit, path)
        head_raw = assert_not_final_test(Path(PROJECT_ROOT / path)).read_bytes()
        parent_raw = (
            _commit_bytes(parent_commit, path) if exists_at_parent else None
        )
        immutable = (
            r2_raw == head_raw
            if parent_raw is None
            else parent_raw == r2_raw == head_raw
        )
        if not immutable:
            failures.append(f"{label}_CHANGED_AFTER_ACTIVATION")
        head_hash = _sha256_bytes(head_raw)
        if head_hash != expected_hash:
            failures.append(f"{label}_CURRENT_FILE_HASH_MISMATCH")
        checks[path] = {
            "parent_bytes_sha256": (
                _sha256_bytes(parent_raw) if parent_raw is not None else None
            ),
            "r2_bytes_sha256": _sha256_bytes(r2_raw),
            "head_bytes_sha256": head_hash,
            "declared_file_sha256": expected_hash,
            "immutable": immutable,
        }
    for path in ADOPTED_REGISTRIES:
        parent_raw = _commit_bytes(parent_commit, path)
        r2_raw = _commit_bytes(r2_commit, path)
        head_raw = assert_not_final_test(Path(PROJECT_ROOT / path)).read_bytes()
        immutable = parent_raw == r2_raw == head_raw
        if not immutable:
            failures.append(f"ADOPTED_REGISTRY_CHANGED:{path}")
        checks[path] = {
            "parent_bytes_sha256": _sha256_bytes(parent_raw),
            "r2_bytes_sha256": _sha256_bytes(r2_raw),
            "head_bytes_sha256": _sha256_bytes(head_raw),
            "immutable": immutable,
        }
    return checks


def _parent_linkage(
    *,
    parent_registry: Mapping[str, Any],
    r2_registry: Mapping[str, Any],
    failures: list[str],
) -> dict[str, Any]:
    activation = r2_registry.get("activation_state", {})
    parent = r2_registry.get("parent_freeze", {})
    checks = {
        "parent_tag": parent.get("tag") == PHASE6_TAG,
        "parent_tag_object": activation.get("parent_tag_object")
        == PHASE6_TAG_OBJECT
        and parent.get("tag_object") == PHASE6_TAG_OBJECT,
        "parent_tag_target": activation.get("parent_tag_target_commit")
        == PHASE6_TAG_TARGET
        and parent.get("tag_target_commit") == PHASE6_TAG_TARGET,
        "parent_registry_file_sha256": parent.get("registry_file_sha256")
        == PARENT_REGISTRY_FILE_SHA256,
        "parent_registry_artifact_hash": parent.get("registry_artifact_hash")
        == PARENT_REGISTRY_ARTIFACT_HASH,
        "parent_registry_blob_sha256": parent.get("registry_blob_sha256")
        == f"sha256:{PARENT_REGISTRY_BLOB_OID}",
        "parent_bytes_rewritten_false": activation.get(
            "parent_registry_bytes_rewritten"
        )
        is False,
        "parent_status": parent_registry.get("status")
        == "SCIENTIFIC_FREEZE_ACTIVE",
        "r2_status": r2_registry.get("status")
        == "SCIENTIFIC_FREEZE_R2_ACTIVE",
    }
    for name, passed in checks.items():
        if not passed:
            failures.append(f"R2_PARENT_LINKAGE_FAILED:{name}")
    return checks


def check_freeze_ancestry(*, head: str | None = None) -> dict[str, Any]:
    """Validate the R2 freeze ancestry without touching Final-Test data."""

    failures: list[str] = []
    current_head = head or _current_head()
    try:
        parent_tag_object = _git_text("rev-parse", f"{PHASE6_TAG}^{{tag}}")
        parent_tag_target = _git_text("rev-parse", f"{PHASE6_TAG}^{{commit}}")
        r2_tag_object = _git_text("rev-parse", f"{R2_TAG}^{{tag}}")
        r2_tag_target = _git_text("rev-parse", f"{R2_TAG}^{{commit}}")
        object_types = {
            "phase6_tag": _object_type(parent_tag_object),
            "r2_tag": _object_type(r2_tag_object),
        }
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        return {
            "schema_version": SCHEMA_VERSION,
            "validator_id": VALIDATOR_ID,
            "status": "FAIL",
            "failures": [f"GIT_TAG_RESOLUTION_FAILED:{error}"],
            "final_test_boundary": {
                "legacy_final_test_tree_read": False,
                "final_test_absolute_path": str(FINAL_TEST_ROOT),
            },
        }

    expected = {
        "phase6_tag_object": PHASE6_TAG_OBJECT,
        "phase6_tag_target": PHASE6_TAG_TARGET,
        "r2_tag_object": R2_TAG_OBJECT,
        "r2_tag_target": R2_TAG_TARGET,
    }
    actual = {
        "phase6_tag_object": parent_tag_object,
        "phase6_tag_target": parent_tag_target,
        "r2_tag_object": r2_tag_object,
        "r2_tag_target": r2_tag_target,
    }
    for name, expected_value in expected.items():
        if actual[name] != expected_value:
            failures.append(f"{name.upper()}_MISMATCH")
    for name, expected_value in {
        "phase6_tag": "tag",
        "r2_tag": "tag",
    }.items():
        if object_types[name] != expected_value:
            failures.append(f"{name.upper()}_OBJECT_TYPE_MISMATCH")

    ancestry = {
        "phase6_is_ancestor_of_r2": _is_ancestor(
            parent_tag_target, r2_tag_target
        ),
        "r2_is_ancestor_of_head": _is_ancestor(r2_tag_target, current_head),
    }
    for name, passed in ancestry.items():
        if not passed:
            failures.append(f"ANCESTRY_FAILED:{name}")

    parent_registry = _read_commit_json(parent_tag_target, PARENT_REGISTRY)
    r2_registry = _read_commit_json(r2_tag_target, R2_REGISTRY)
    linkage = _parent_linkage(
        parent_registry=parent_registry,
        r2_registry=r2_registry,
        failures=failures,
    )
    immutability = _registry_immutability(
        parent_commit=parent_tag_target,
        r2_commit=r2_tag_target,
        failures=failures,
    )
    parent_snapshot = _check_registry_snapshot(
        path=PARENT_REGISTRY,
        commit=parent_tag_target,
        file_sha256=PARENT_REGISTRY_FILE_SHA256,
        artifact_hash=PARENT_REGISTRY_ARTIFACT_HASH,
        failures=failures,
        label="PARENT_REGISTRY",
    )
    r2_snapshot = _check_registry_snapshot(
        path=R2_REGISTRY,
        commit=r2_tag_target,
        file_sha256=R2_REGISTRY_FILE_SHA256,
        artifact_hash=R2_REGISTRY_ARTIFACT_HASH,
        failures=failures,
        label="R2_REGISTRY",
    )

    registry = {
        "phase6": {
            "tag": PHASE6_TAG,
            "tag_object": parent_tag_object,
            "tag_target_commit": parent_tag_target,
            "object_type": object_types["phase6_tag"],
            "snapshot": parent_snapshot,
        },
        "r2": {
            "tag": R2_TAG,
            "tag_object": r2_tag_object,
            "tag_target_commit": r2_tag_target,
            "object_type": object_types["r2_tag"],
            "snapshot": r2_snapshot,
        },
        "current_head": current_head,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "validator_id": VALIDATOR_ID,
        "status": "PASS" if not failures else "FAIL",
        "registry": registry,
        "ancestry": ancestry,
        "parent_linkage": linkage,
        "registry_immutability": immutability,
        "final_test_boundary": {
            "legacy_final_test_tree_read": False,
            "final_test_absolute_path": str(FINAL_TEST_ROOT),
        },
        "failures": failures,
    }


def _write_report(report: Mapping[str, Any]) -> Path:
    target = assert_not_final_test(REPORT_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def _read_report() -> dict[str, Any]:
    target = assert_not_final_test(REPORT_PATH)
    return json.loads(target.read_text(encoding="utf-8"))


def _report_comparison_failures(
    observed: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    ancestor_check: Any = _is_ancestor,
) -> list[str]:
    """Compare a stored report while allowing only a lagging HEAD field."""

    if not isinstance(observed, Mapping) or not isinstance(expected, Mapping):
        return ["PHASE7_FREEZE_ANCESTRY_REPORT_MISMATCH"]
    if expected.get("status") != "PASS":
        return ["PHASE7_FREEZE_ANCESTRY_RECOMPUTED_FAILURE"]
    expected_ancestry = expected.get("ancestry")
    if not isinstance(expected_ancestry, Mapping) or expected_ancestry != {
        "phase6_is_ancestor_of_r2": True,
        "r2_is_ancestor_of_head": True,
    }:
        return ["PHASE7_FREEZE_ANCESTRY_RECOMPUTED_FAILURE"]

    observed_registry = observed.get("registry")
    expected_registry = expected.get("registry")
    if not isinstance(observed_registry, Mapping) or not isinstance(
        expected_registry, Mapping
    ):
        return ["PHASE7_FREEZE_ANCESTRY_REPORT_MISMATCH"]

    observed_head = observed_registry.get("current_head")
    expected_head = expected_registry.get("current_head")
    if not isinstance(observed_head, str) or not isinstance(expected_head, str):
        return ["PHASE7_FREEZE_ANCESTRY_REPORT_HEAD_MISSING"]
    if len(observed_head) != 40 or len(expected_head) != 40:
        return ["PHASE7_FREEZE_ANCESTRY_REPORT_HEAD_INVALID"]
    try:
        int(observed_head, 16)
        int(expected_head, 16)
    except ValueError:
        return ["PHASE7_FREEZE_ANCESTRY_REPORT_HEAD_INVALID"]

    comparison = copy.deepcopy(dict(observed))
    comparison_registry = comparison.get("registry")
    if not isinstance(comparison_registry, Mapping):
        return ["PHASE7_FREEZE_ANCESTRY_REPORT_MISMATCH"]
    if observed_head != expected_head:
        try:
            is_ancestor = bool(ancestor_check(observed_head, expected_head))
        except Exception:
            is_ancestor = False
        if not is_ancestor:
            return ["PHASE7_FREEZE_ANCESTRY_REPORT_HEAD_NOT_ANCESTOR"]
        comparison_registry["current_head"] = expected_head

    if comparison != expected:
        return ["PHASE7_FREEZE_ANCESTRY_REPORT_MISMATCH"]
    return []


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    report = check_freeze_ancestry()
    if args.write:
        _write_report(report)
    else:
        try:
            observed = _read_report()
        except (OSError, ValueError) as error:
            print(
                json.dumps(
                    {
                        "status": "FAIL",
                        "reason": "PHASE7_FREEZE_ANCESTRY_REPORT_MISSING_OR_INVALID",
                        "detail": str(error),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        comparison_failures = _report_comparison_failures(observed, report)
        if comparison_failures:
            print(
                json.dumps(
                    {
                        "status": "FAIL",
                        "reason": "PHASE7_FREEZE_ANCESTRY_REPORT_MISMATCH",
                        "report_path": str(REPORT_PATH),
                        "failures": comparison_failures,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "mode": "WRITE" if args.write else "CHECK",
                "report_path": str(REPORT_PATH),
                "failures": report.get("failures", []),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "PASS" else 1


__all__ = ["check_freeze_ancestry", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
