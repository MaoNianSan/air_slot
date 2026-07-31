from __future__ import annotations

import numpy as np
import pandas as pd

from .validate import PreBundle


def _table_columns(cfg: dict[str, Any], table: str) -> list[str]:
    return list(cfg["schema"]["tables"][table]["required"])


def _formal_frame(frame: pd.DataFrame, cfg: dict[str, Any], table: str) -> pd.DataFrame:
    columns = _table_columns(cfg, table) + list(
        cfg["schema"]["tables"][table].get("optional", [])
    )
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame.loc[:, columns].copy(deep=False)


def _missingness_report(bundle: PreBundle) -> pd.DataFrame:
    rows = []
    for table_name, frame in bundle.tables().items():
        for column in frame.columns:
            count = int(frame[column].isna().sum())
            rows.append({
                "table": table_name,
                "column": column,
                "row_count": len(frame),
                "missing_count": count,
                "missing_rate": float(count / len(frame)) if len(frame) else np.nan,
            })
    return pd.DataFrame(rows)


def _reference_fallback_report(calibration: pd.DataFrame) -> pd.DataFrame:
    columns = [column for column in calibration.columns if column.endswith("fallback_level")]
    rows = []
    for column in columns:
        counts = calibration[column].fillna("MISSING").astype(str).value_counts(dropna=False)
        rows.extend({"field": column, "fallback_level": level, "count": int(count)} for level, count in counts.items())
    return pd.DataFrame(rows)


def _passenger_fallback_audit(snapshots: pd.DataFrame) -> pd.DataFrame:
    mapping = {
        "snapshot_id": "snapshot_id",
        "flight_id": "flight_id",
        "split": "split",
        "airport": "airport",
        "origin": "origin",
        "destination": "destination",
        "period": "period",
        "aircraft_group": "aircraft_group",
        "selected_level": "passenger_proxy_level",
        "attempted_levels": "passenger_proxy_attempted_levels",
        "seat_capacity_level": "seat_capacity_level",
        "passenger_proxy_support": "passenger_proxy_support",
        "passenger_proxy_evidence_status": "passenger_proxy_evidence_status",
        "missing_reason": "passenger_proxy_missing_reason",
        "future_data_used": "passenger_proxy_future_data_used",
        "reference_period": "passenger_proxy_reference_period",
        "source_key": "passenger_proxy_source_key",
        "passenger_target_period": "passenger_target_period",
        "passenger_source_period": "passenger_source_period",
        "passenger_period_end": "passenger_period_end",
        "passenger_lag_months": "passenger_lag_months",
        "passenger_requested_level": "passenger_requested_level",
        "passenger_used_level": "passenger_used_level",
        "passenger_evidence_status": "passenger_evidence_status",
        "passenger_support_count": "passenger_support_count",
        "passenger_source_dataset": "passenger_source_dataset",
        "passenger_measure_filter": "passenger_measure_filter",
        "m4_eligible": "m4_eligible",
        "m4_ineligibility_reason": "m4_ineligibility_reason",
    }
    result = pd.DataFrame(index=snapshots.index)
    for target, source in mapping.items():
        result[target] = snapshots[source] if source in snapshots else pd.NA
    return result.reset_index(drop=True)


def _passenger_supported(frame: pd.DataFrame) -> pd.Series:
    required = [
        "estimated_passenger_load",
        "connection_pressure_proxy",
        "rebooking_scarcity_proxy",
    ]
    return (
        frame[required].notna().all(axis=1)
        & pd.to_numeric(frame["passenger_support_count"], errors="coerce").gt(0)
        & frame["passenger_evidence_status"].isin(
            ["OBSERVED", "SUPPORTED_PROXY", "FALLBACK_PROXY"]
        )
    )


