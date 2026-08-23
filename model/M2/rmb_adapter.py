"""Canonical adapter exposing M2's seven native consequence components as C."""

from __future__ import annotations

from model.M2.contracts import ConsequenceRow
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.enums import SupportState


def consequence_component(row: ConsequenceRow) -> dict:
    """Serialize one M2 row as the monetary-independent consequence object C_k."""
    if not isinstance(row, ConsequenceRow):
        raise TypeError("M2_RMB_ADAPTER_REQUIRES_CONSEQUENCE_ROW")
    return {
        "component_id": row.component_id,
        "consequence_value": row.native_quantity,
        "native_unit": row.native_unit,
        "support_state": row.support_state.value,
        "native_artifact_id": row.native_artifact_id,
        "reference_lineage_hash": row.reference_lineage_hash,
        "reason_code": row.reason_code,
    }


def consequence_vector(rows: tuple[ConsequenceRow, ...]) -> tuple[dict, ...]:
    """Serialize an exact seven-component C vector without zero filling."""
    if tuple(row.component_id for row in rows) != CONSEQUENCE_COMPONENTS:
        raise ValueError("M2_RMB_ADAPTER_EXACT_SEVEN_COMPONENTS_REQUIRED")
    values = tuple(consequence_component(row) for row in rows)
    if any(item["support_state"] == SupportState.ABSTAIN.value and item["consequence_value"] is not None for item in values):
        raise ValueError("M2_RMB_ADAPTER_ABSTAIN_VALUE_MUST_BE_NULL")
    return values


def cu_component(row: ConsequenceRow) -> dict:
    """Serialize the intermediate constructed CU_k owned by M2."""
    if not isinstance(row, ConsequenceRow):
        raise TypeError("M2_RMB_ADAPTER_REQUIRES_CONSEQUENCE_ROW")
    return {
        "component_id": row.component_id,
        "cu_value": row.constructed_value_cu,
        "cu_status": row.cu_status.value,
        "cu_artifact_id": (getattr(row.cu_quantity, "artifact_id", None) if row.cu_quantity is not None else None),
        "consequence_value": row.native_quantity,
        "support_state": row.support_state.value,
        "native_artifact_id": row.native_artifact_id,
        "reference_lineage_hash": row.reference_lineage_hash,
        "reason_code": row.reason_code,
    }


__all__ = ["consequence_component", "consequence_vector", "cu_component"]
