from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class PassengerReference:
    base: pd.DataFrame
    operations: pd.DataFrame
    regions: dict[str, str]
    group_seats: dict[str, float]
    group_support: dict[str, int]
    metadata: dict[str, Any]

    @staticmethod
    def _empty_result(
        *,
        target_period: str,
        attempted_levels: list[str],
        seat_capacity: float = np.nan,
        seat_level: str = "UNSUPPORTED",
        seat_support: int = 0,
        seat_evidence: str = "UNSUPPORTED",
        missing_reason: str = "SOURCE_HISTORY_INSUFFICIENT",
    ) -> dict[str, Any]:
        measure_filter = json.dumps(
            {
                "passenger": "M/PAS/PAS_CRD/TOT/TOTAL",
                "commercial_flights": "M/TOTAL/NR",
            },
            sort_keys=True,
        )
        return {
            "passenger_reference": np.nan,
            "commercial_flight_reference": np.nan,
            "estimated_passenger_load": np.nan,
            "seat_reference": seat_capacity,
            "seat_capacity": seat_capacity,
            "seat_capacity_level": seat_level,
            "seat_capacity_support": seat_support,
            "seat_capacity_evidence_status": seat_evidence,
            "load_factor": np.nan,
            "load_factor_support": 0,
            "load_factor_evidence_status": "UNSUPPORTED",
            "airport_month_load_factor_proxy": np.nan,
            "route_month_load_factor": np.nan,
            "connection_pressure_proxy": np.nan,
            "connection_pressure_support": 0,
            "connection_pressure_level": "UNSUPPORTED",
            "connection_pressure_evidence_status": "UNSUPPORTED",
            "connection_pressure_missing_reason": "PASSENGER_LOAD_MISSING",
            "rebooking_scarcity_proxy": np.nan,
            "rebooking_scarcity_support": 0,
            "rebooking_scarcity_level": "UNSUPPORTED",
            "rebooking_scarcity_evidence_status": "UNSUPPORTED",
            "rebooking_scarcity_missing_reason": "PASSENGER_LOAD_MISSING",
            "level": "UNSUPPORTED",
            "support": 0,
            "evidence_status": "UNSUPPORTED",
            "reference_period": "",
            "source_key": "",
            "source_record_ids": "[]",
            "raw_files": "[]",
            "raw_hashes": "[]",
            "future_data_used": False,
            "missing_reason": missing_reason,
            "fallback_reason": missing_reason,
            "attempted_levels": json.dumps(attempted_levels),
            "target_period": target_period,
            "passenger_target_period": target_period,
            "passenger_source_period": "",
            "passenger_period_end": "",
            "passenger_lag_months": pd.NA,
            "passenger_requested_level": "DESTINATION_LAGGED_MONTH",
            "passenger_used_level": "UNSUPPORTED",
            "passenger_evidence_status": "UNSUPPORTED",
            "passenger_missing_reason": missing_reason,
            "passenger_support_count": 0,
            "passenger_source_dataset": "EUROSTAT_AVIA_PAOA_AND_AVIA_TF_AIRPM",
            "passenger_measure_filter": measure_filter,
            "passenger_future_data_used": False,
        }

    def _resolve_seat(self, destination: str, target_period: str, aircraft_group: str) -> tuple[float, str, int, str]:
        seat = self.group_seats.get(str(aircraft_group))
        if str(aircraft_group) != "unknown" and seat is not None and np.isfinite(seat) and seat > 0:
            return float(seat), "AIRCRAFT_GROUP_REFERENCE", int(self.group_support.get(str(aircraft_group), 0)), "SUPPORTED_PROXY"
        ops = self.operations
        if not ops.empty:
            subset = ops[
                ops["airport"].astype(str).eq(destination)
                & ops["period"].astype(str).eq(target_period)
            ]
            values = pd.to_numeric(subset.get("seat_typical", pd.Series(dtype=float)), errors="coerce").dropna()
            if not values.empty and float(values.median()) > 0:
                return (
                    float(values.median()),
                    "DESTINATION_MONTH_TRAINING_REFERENCE",
                    int(pd.to_numeric(subset["flight_support"], errors="coerce").fillna(0).sum()),
                    "FALLBACK_PROXY",
                )
        return np.nan, "UNSUPPORTED", 0, "UNSUPPORTED"

    def resolve(
        self,
        origin: str,
        destination: str,
        period: str,
        aircraft_group: str = "unknown",
        time_bin: str | None = None,
        available_at: Any | None = None,
    ) -> dict[str, Any]:
        target = pd.Period(str(period), freq="M")
        target_period = str(target)
        attempted = [
            "OD_MONTH_AIRCRAFT_GROUP:SOURCE_UNAVAILABLE",
            "OD_MONTH:SOURCE_UNAVAILABLE",
            "DESTINATION_LAGGED_MONTH",
        ]
        seat, seat_level, seat_support, seat_evidence = self._resolve_seat(
            destination, target_period, aircraft_group
        )
        if self.base.empty:
            return self._empty_result(
                target_period=target_period,
                attempted_levels=attempted,
                seat_capacity=seat,
                seat_level=seat_level,
                seat_support=seat_support,
                seat_evidence=seat_evidence,
                missing_reason=str(self.metadata.get("empty_reason", "LOAD_FACTOR_REFERENCE_EMPTY")),
            )

        destination_history = self.base[
            self.base["destination"].astype(str).eq(destination)
        ].copy()
        candidates = destination_history.copy()
        if candidates.empty:
            return self._empty_result(
                target_period=target_period,
                attempted_levels=attempted,
                seat_capacity=seat,
                seat_level=seat_level,
                seat_support=seat_support,
                seat_evidence=seat_evidence,
                missing_reason="SOURCE_HISTORY_INSUFFICIENT",
            )
        candidates["_period"] = candidates["source_period"].map(lambda value: pd.Period(str(value), freq="M"))
        available_cutoff = (
            pd.Timestamp(available_at).tz_localize(None)
            if available_at is not None and pd.Timestamp(available_at).tzinfo is not None
            else pd.Timestamp(available_at)
            if available_at is not None
            else target.start_time
        )
        reference_cutoff = pd.Timestamp(self.metadata["reference_cutoff_date"])
        effective_cutoff = min(available_cutoff, reference_cutoff)
        candidates["_lag_months"] = candidates["_period"].map(
            lambda source: target.ordinal - source.ordinal
        )
        maximum_lag_months = int(self.metadata.get("maximum_lag_months", 3))
        candidates = candidates[
            candidates["_lag_months"].between(
                1, maximum_lag_months, inclusive="both"
            )
            & candidates["_period"].map(lambda value: value.end_time <= effective_cutoff)
        ]
        if candidates.empty:
            return self._empty_result(
                target_period=target_period,
                attempted_levels=attempted,
                seat_capacity=seat,
                seat_level=seat_level,
                seat_support=seat_support,
                seat_evidence=seat_evidence,
                missing_reason=(
                    "SOURCE_MONTH_GAP"
                    if not destination_history.empty
                    else "SOURCE_HISTORY_INSUFFICIENT"
                ),
            )
        record = candidates.sort_values("_period").iloc[-1]
        load_factor = float(record["load_factor"]) if pd.notna(record["load_factor"]) else np.nan
        if not np.isfinite(seat) or seat <= 0:
            return self._empty_result(
                target_period=target_period,
                attempted_levels=attempted,
                seat_capacity=seat,
                seat_level=seat_level,
                seat_support=seat_support,
                seat_evidence=seat_evidence,
                missing_reason="SEAT_CAPACITY_MISSING",
            )
        if not np.isfinite(load_factor) or not 0 <= load_factor <= 1:
            return self._empty_result(
                target_period=target_period,
                attempted_levels=attempted,
                seat_capacity=seat,
                seat_level=seat_level,
                seat_support=seat_support,
                seat_evidence=seat_evidence,
                missing_reason="LOAD_FACTOR_REFERENCE_EMPTY",
            )

        estimated = float(np.clip(seat * load_factor, 0.0, seat))
        op = self.operations[
            self.operations["airport"].astype(str).eq(destination)
            & self.operations["time_bin"].astype(str).eq(str(time_bin or "00_06"))
        ]
        if not op.empty:
            op_row = op.sort_values("period").iloc[-1]
            connection_raw = float(op_row.get("connection_opportunity", np.nan))
            connection = float(np.clip(load_factor * connection_raw, 0.0, 1.0)) if np.isfinite(connection_raw) else np.nan
            alternative_capacity = float(op_row.get("alternative_capacity", np.nan))
            scarcity = (
                float(np.clip(estimated / (estimated + alternative_capacity), 0.0, 1.0))
                if np.isfinite(alternative_capacity) and alternative_capacity >= 0
                else np.nan
            )
            op_support = int(op_row.get("flight_support", 0))
        else:
            connection = scarcity = np.nan
            op_support = 0

        source_period = str(record["source_period"])
        source_period_end = pd.Period(source_period, freq="M").end_time
        lag_months = int(record["_lag_months"])
        future = source_period_end > effective_cutoff
        evidence = "SUPPORTED_PROXY" if lag_months == 1 else "FALLBACK_PROXY"
        missing_reason = "" if lag_months == 1 else "MONTH_GAP_BACKOFF"
        measure_filter = json.dumps(
            {
                "passenger": "M/PAS/PAS_CRD/TOT/TOTAL",
                "commercial_flights": "M/TOTAL/NR",
            },
            sort_keys=True,
        )
        return {
            "passenger_reference": float(record["passenger_per_flight"]),
            "commercial_flight_reference": float(record["commercial_flights"]),
            "estimated_passenger_load": estimated,
            "seat_reference": seat,
            "seat_capacity": seat,
            "seat_capacity_level": seat_level,
            "seat_capacity_support": seat_support,
            "seat_capacity_evidence_status": seat_evidence,
            "load_factor": load_factor,
            "load_factor_support": int(record["support_size"]),
            "load_factor_evidence_status": evidence,
            "airport_month_load_factor_proxy": load_factor,
            "route_month_load_factor": load_factor,
            "connection_pressure_proxy": connection,
            "connection_pressure_support": op_support if np.isfinite(connection) else 0,
            "connection_pressure_level": "AIRPORT_TIME_BIN_TRAINING_PROXY" if np.isfinite(connection) else "UNSUPPORTED",
            "connection_pressure_evidence_status": evidence if np.isfinite(connection) else "UNSUPPORTED",
            "connection_pressure_missing_reason": "" if np.isfinite(connection) else "CONNECTION_REFERENCE_MISSING",
            "rebooking_scarcity_proxy": scarcity,
            "rebooking_scarcity_support": op_support if np.isfinite(scarcity) else 0,
            "rebooking_scarcity_level": "AIRPORT_TIME_BIN_TRAINING_PROXY" if np.isfinite(scarcity) else "UNSUPPORTED",
            "rebooking_scarcity_evidence_status": evidence if np.isfinite(scarcity) else "UNSUPPORTED",
            "rebooking_scarcity_missing_reason": "" if np.isfinite(scarcity) else "REBOOKING_REFERENCE_MISSING",
            "level": "DESTINATION_LAGGED_MONTH",
            "support": int(record["support_size"]),
            "evidence_status": evidence,
            "reference_period": source_period,
            "source_key": f"destination={destination}|period={source_period}",
            "source_record_ids": str(record.get("source_record_ids", "[]")),
            "raw_files": str(record.get("raw_files", "[]")),
            "raw_hashes": str(record.get("raw_hashes", "[]")),
            "future_data_used": bool(future),
            "missing_reason": missing_reason,
            "fallback_reason": missing_reason,
            "attempted_levels": json.dumps(attempted),
            "target_period": target_period,
            "passenger_target_period": target_period,
            "passenger_source_period": source_period,
            "passenger_period_end": str(source_period_end),
            "passenger_lag_months": lag_months,
            "passenger_requested_level": "DESTINATION_LAGGED_MONTH",
            "passenger_used_level": "DESTINATION_LAGGED_MONTH",
            "passenger_evidence_status": evidence,
            "passenger_missing_reason": missing_reason,
            "passenger_support_count": int(record["support_size"]),
            "passenger_source_dataset": "EUROSTAT_AVIA_PAOA_AND_AVIA_TF_AIRPM",
            "passenger_measure_filter": measure_filter,
            "passenger_future_data_used": bool(future),
        }

    def artifact_frame(self) -> pd.DataFrame:
        return self.base.copy()

    def temporal_audit_frame(self) -> pd.DataFrame:
        return pd.DataFrame([self.metadata])


