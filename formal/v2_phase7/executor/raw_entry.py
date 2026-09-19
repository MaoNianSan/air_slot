"""One-shot Final-Test materialization entry (the DAG's raw boundary).

``CANONICAL_NODES`` is the only stage that may read a raw Final-Test source, and
it may do so exactly once per authorized access epoch. This module owns that
boundary:

* it validates the human release and the open access-epoch record,
* it requires an explicitly registered raw source adapter, and
* it publishes the ``CANONICAL_NODES`` payload that every later stage consumes
  as an immutable, hash-validated checkpoint.

Gate B.0 deliberately activates no adapter: the entry is bound but refuses to
read anything, so no Final-Test raw read, no epoch and no materialization can
happen before the human release. Nothing here reads Q4 raw data at import time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from .. import constants as C
from ..errors import TypedBlocker, _require
from ..materialization import _assert_not_legacy_final_test
from ..release import validate_release_schema
from .nodes import canonical_nodes_payload, nodes_from_payload

MATERIALIZATION_SCOPE = "FINAL_TEST_SEALED_MATERIALIZATION"
AUTHORIZATION_ID = "GATE_B_HUMAN_RELEASE"

RawSourceAdapter = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def validate_materialization_authorization(
    authorization: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the release + access-epoch authorization for materialization."""

    _require(
        isinstance(authorization, Mapping),
        "PHASE7_MATERIALIZATION_AUTHORIZATION_REQUIRED",
        type(authorization).__name__,
    )
    _require(
        authorization.get("authorization_id") == AUTHORIZATION_ID,
        "PHASE7_MATERIALIZATION_AUTHORIZATION_ID_INVALID",
        authorization.get("authorization_id"),
    )
    release = authorization.get("release")
    _require(
        isinstance(release, Mapping),
        "PHASE7_MATERIALIZATION_RELEASE_MISSING",
    )
    release_validation = validate_release_schema(release)
    epoch = authorization.get("access_epoch")
    _require(
        isinstance(epoch, Mapping),
        "PHASE7_MATERIALIZATION_ACCESS_EPOCH_MISSING",
    )
    _require(
        epoch.get("status") == "PHASE7_ACCESS_EPOCH_OPEN",
        "PHASE7_MATERIALIZATION_ACCESS_EPOCH_NOT_OPEN",
        epoch.get("status"),
    )
    _require(
        int(epoch.get("phase7_increment", -1)) == C.PHASE7_ACCESS_INCREMENT
        and int(epoch.get("current_total", -1)) == C.PHASE7_CURRENT_TOTAL,
        "PHASE7_MATERIALIZATION_ACCESS_ACCOUNTING_INVALID",
        {
            "phase7_increment": epoch.get("phase7_increment"),
            "current_total": epoch.get("current_total"),
        },
    )
    _require(
        epoch.get("raw_read_started") is True,
        "PHASE7_MATERIALIZATION_RAW_READ_NOT_STARTED",
    )
    _require(
        release.get("cohort_manifest_sha256")
        == C.EXECUTED_COHORT_MANIFEST_SHA256,
        "PHASE7_MATERIALIZATION_COHORT_MANIFEST_MISMATCH",
    )
    return {
        "status": "PASS",
        "authorization_id": AUTHORIZATION_ID,
        "release_validation": release_validation,
        "access_epoch_id": epoch.get("access_epoch_id"),
        "phase7_increment": int(epoch["phase7_increment"]),
        "current_total": int(epoch["current_total"]),
        "historical_access_total": C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
    }


def materialize_canonical_nodes(
    *,
    authorization: Mapping[str, Any],
    output_root: Path | None = None,
    adapter: RawSourceAdapter | None = None,
) -> dict[str, Any]:
    """Publish the authorized ``CANONICAL_NODES`` payload exactly once."""

    validated = validate_materialization_authorization(authorization)
    if adapter is None:
        raise TypedBlocker(
            "PHASE7_FINAL_TEST_RAW_ADAPTER_NOT_ACTIVATED",
            {
                "gate": "PHASE_7_GATE_B",
                "authorization": validated["authorization_id"],
                "note": (
                    "Gate B.0 binds this boundary without activating a raw "
                    "Final-Test source adapter; activation happens inside the "
                    "authorized Gate-B execution only"
                ),
            },
        )
    if output_root is not None:
        _assert_not_legacy_final_test(Path(output_root))
    produced = adapter(dict(authorization))
    _require(
        isinstance(produced, Mapping),
        "PHASE7_FINAL_TEST_ADAPTER_OUTPUT_INVALID",
        type(produced).__name__,
    )
    nodes = nodes_from_payload(produced)
    payload = canonical_nodes_payload(
        nodes,
        scope=MATERIALIZATION_SCOPE,
        provenance={
            **dict(produced.get("provenance", {})),
            "authorization_id": AUTHORIZATION_ID,
            "access_epoch_id": validated["access_epoch_id"],
            "materialization_scope": MATERIALIZATION_SCOPE,
            "final_test_data_read": True,
            "q4_raw_read": True,
        },
    )
    return payload


__all__ = [
    "AUTHORIZATION_ID",
    "MATERIALIZATION_SCOPE",
    "RawSourceAdapter",
    "materialize_canonical_nodes",
    "validate_materialization_authorization",
]
