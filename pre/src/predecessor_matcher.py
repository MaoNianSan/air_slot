from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


PREDECESSOR_FEATURE_COLUMNS = [
    "has_predecessor_candidate",
    "has_supported_predecessor",
    "predecessor_flight_id",
    "predecessor_firstseen_proxy",
    "predecessor_lastseen_proxy",
    "predecessor_observed_duration",
    "predecessor_origin_inferred",
    "predecessor_destination_inferred",
    "predecessor_endpoint_quality",
    "predecessor_trajectory_coverage",
    "predecessor_registration_match",
    "predecessor_typecode_match",
    "predecessor_aircraft_group",
    "observed_ground_gap_minutes",
    "ground_gap_deviation_from_reference",
    "airport_continuity",
    "predecessor_movement_deviation_proxy",
    "predecessor_completion_state",
    "turnaround_pressure_proxy",
    "continuation_risk_proxy",
    "previous_leg_observation_quality",
    "predecessor_match_confidence",
    "predecessor_evidence_tier",
    "predecessor_support_rule",
    "predecessor_support_status",
    "predecessor_rejection_reason",
    "nearest_raw_candidate_id",
    "selected_supported_predecessor_id",
    "raw_candidate_rejection_reason",
    "search_depth",
]

M1_PREDECESSOR_MODEL_FEATURES = [
    "has_predecessor_candidate",
    "has_supported_predecessor",
    "predecessor_observed_duration",
    "predecessor_endpoint_quality",
    "predecessor_trajectory_coverage",
    "predecessor_registration_match",
    "predecessor_typecode_match",
    "predecessor_aircraft_group",
    "observed_ground_gap_minutes",
    "ground_gap_deviation_from_reference",
    "airport_continuity",
    "predecessor_movement_deviation_proxy",
    "predecessor_completion_state",
    "turnaround_pressure_proxy",
    "continuation_risk_proxy",
    "previous_leg_observation_quality",
    "predecessor_match_confidence",
    "predecessor_evidence_tier",
    "predecessor_support_rule",
    "predecessor_support_status",
    "predecessor_rejection_reason",
]

_NULL_ON_UNSUPPORTED = [
    "predecessor_firstseen_proxy",
    "predecessor_lastseen_proxy",
    "predecessor_observed_duration",
    "predecessor_origin_inferred",
    "predecessor_destination_inferred",
    "predecessor_endpoint_quality",
    "predecessor_trajectory_coverage",
    "predecessor_registration_match",
    "predecessor_typecode_match",
    "predecessor_aircraft_group",
    "observed_ground_gap_minutes",
    "ground_gap_deviation_from_reference",
    "airport_continuity",
    "predecessor_movement_deviation_proxy",
    "predecessor_completion_state",
    "turnaround_pressure_proxy",
    "continuation_risk_proxy",
    "previous_leg_observation_quality",
    "predecessor_match_confidence",
    "predecessor_evidence_tier",
    "predecessor_support_rule",
]


def _present(series: pd.Series) -> pd.Series:
    return series.notna() & series.astype("string").str.strip().ne("")


def _same_when_known(left: pd.Series, right: pd.Series) -> pd.Series:
    known = _present(left) & _present(right)
    return pd.Series(pd.NA, index=left.index, dtype="boolean").mask(
        known, left.astype("string").str.upper().eq(right.astype("string").str.upper())
    )


def _value_present(value: Any) -> bool:
    return pd.notna(value) and str(value).strip() != ""


def _structural_rejection_reason(
    candidate: pd.Series,
    current: pd.Series,
    *,
    duplicate_risk: bool,
) -> str:
    if pd.isna(candidate["firstseen_utc"]) or pd.isna(candidate["lastseen_utc"]):
        return "PREDECESSOR_TIME_MISSING"
    if not candidate["firstseen_utc"] < current["firstseen_utc"]:
        return "PREDECESSOR_NOT_BEFORE_CURRENT"
    if candidate["lastseen_utc"] > current["firstseen_utc"]:
        return "TEMPORAL_OVERLAP"
    gap = (current["firstseen_utc"] - candidate["lastseen_utc"]).total_seconds()
    if gap < 0:
        return "TEMPORAL_OVERLAP"
    if not (_value_present(candidate["origin"]) and _value_present(candidate["destination"])):
        return "ENDPOINT_QUALITY_UNSUPPORTED"
    if not _value_present(current["origin"]):
        return "ENDPOINT_QUALITY_UNSUPPORTED"
    if str(candidate["destination"]) != str(current["origin"]):
        return "AIRPORT_DISCONTINUITY"
    if (
        _value_present(candidate["registration"])
        and _value_present(current["registration"])
        and str(candidate["registration"]).upper() != str(current["registration"]).upper()
    ):
        return "REGISTRATION_CONFLICT"
    if (
        _value_present(candidate["typecode"])
        and _value_present(current["typecode"])
        and str(candidate["typecode"]).upper() != str(current["typecode"]).upper()
    ):
        return "TYPECODE_CONFLICT"
    if duplicate_risk or str(candidate["flight_id"]) == str(current["flight_id"]):
        return "POSSIBLE_SPLIT_MERGE_RISK"
    return ""


def build_predecessor_candidates(
    legs: pd.DataFrame,
    cfg: dict[str, Any],
) -> pd.DataFrame:
    """Build stable same-aircraft predecessor candidates without using successors."""
    if legs.empty:
        return pd.DataFrame(columns=["episode_id", *PREDECESSOR_FEATURE_COLUMNS])
    required = {
        "episode_id", "flight_id", "icao24", "origin", "destination",
        "firstseen_utc", "lastseen_utc", "observed_movement_time",
        "aircraft_group", "typecode",
    }
    missing = sorted(required - set(legs.columns))
    if missing:
        raise ValueError("PREDECESSOR_INPUT_MISSING:" + ",".join(missing))

    frame = legs.copy()
    if "registration" not in frame:
        frame["registration"] = pd.NA
    for column in ("firstseen_utc", "lastseen_utc"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
    if frame[["firstseen_utc", "lastseen_utc"]].isna().any().any():
        raise ValueError("PREDECESSOR_CURRENT_TIME_INVALID")
    frame = frame.sort_values(
        ["icao24", "firstseen_utc", "lastseen_utc", "flight_id"],
        kind="mergesort",
    ).reset_index(drop=True)
    source_columns = [
        "flight_id", "firstseen_utc", "lastseen_utc", "observed_movement_time",
        "origin", "destination", "registration", "typecode", "aircraft_group",
        "state_day_complete", "firstseen_month", "firstseen_time_bin",
        "distance_bin", "origin_region", "destination_region", "region_pair",
    ]
    duplicate_identity = frame.duplicated(
        ["icao24", "firstseen_utc", "lastseen_utc", "origin", "destination"],
        keep=False,
    ) | frame["flight_id"].duplicated(keep=False)
    selected_rows: list[dict[str, Any]] = []
    for _, group in frame.groupby("icao24", sort=False):
        for current_index, current in group.iterrows():
            raw = group[
                (group.index != current_index)
                & group["firstseen_utc"].lt(current["firstseen_utc"])
            ].sort_values(
                ["lastseen_utc", "firstseen_utc", "flight_id"],
                ascending=[False, False, True],
                kind="mergesort",
                na_position="last",
            )
            nearest_index = int(raw.index[0]) if not raw.empty else None
            nearest_reason = "NO_PREDECESSOR_CANDIDATE"
            selected_index: int | None = None
            depth = 0
            for candidate_index, candidate in raw.iterrows():
                depth += 1
                reason = _structural_rejection_reason(
                    candidate,
                    current,
                    duplicate_risk=bool(duplicate_identity.loc[candidate_index]),
                )
                if int(candidate_index) == nearest_index:
                    nearest_reason = reason
                if not reason:
                    selected_index = int(candidate_index)
                    break
            source_index = selected_index if selected_index is not None else nearest_index
            values = {
                f"predecessor_{column}": (
                    frame.loc[source_index, column] if source_index is not None else pd.NA
                )
                for column in source_columns
            }
            values.update(
                {
                    "has_predecessor_candidate": nearest_index is not None,
                    "nearest_raw_candidate_id": (
                        frame.loc[nearest_index, "flight_id"] if nearest_index is not None else pd.NA
                    ),
                    "selected_supported_predecessor_id": (
                        frame.loc[selected_index, "flight_id"] if selected_index is not None else pd.NA
                    ),
                    "raw_candidate_rejection_reason": nearest_reason,
                    "search_depth": depth,
                    "_selected_structural_candidate": selected_index is not None,
                    "_possible_split_merge_risk": (
                        bool(duplicate_identity.loc[source_index]) if source_index is not None else False
                    ),
                }
            )
            selected_rows.append(values)
    previous = pd.DataFrame(selected_rows, index=frame.index)
    candidates = pd.concat([frame, previous], axis=1)
    for column in ("predecessor_firstseen_utc", "predecessor_lastseen_utc"):
        candidates[column] = pd.to_datetime(candidates[column], utc=True, errors="coerce")
    candidates["observed_ground_gap_minutes"] = (
        candidates["firstseen_utc"] - candidates["predecessor_lastseen_utc"]
    ).dt.total_seconds() / 60.0
    candidates["_time_order"] = (
        candidates["predecessor_firstseen_utc"].lt(candidates["firstseen_utc"])
    )
    candidates["_no_overlap"] = (
        candidates["predecessor_lastseen_utc"].le(candidates["firstseen_utc"])
        & candidates["observed_ground_gap_minutes"].ge(0.0)
    )
    candidates["airport_continuity"] = (
        _present(candidates["predecessor_destination"])
        & _present(candidates["origin"])
        & candidates["predecessor_destination"].astype("string").eq(
            candidates["origin"].astype("string")
        )
    )
    candidates["predecessor_registration_match"] = _same_when_known(
        candidates["predecessor_registration"], candidates["registration"]
    )
    candidates["predecessor_typecode_match"] = _same_when_known(
        candidates["predecessor_typecode"], candidates["typecode"]
    )
    endpoint_complete = (
        _present(candidates["predecessor_origin"])
        & _present(candidates["predecessor_destination"])
    )
    candidates["predecessor_endpoint_quality"] = np.where(
        endpoint_complete, "COMPLETE_INFERRED_AIRPORT_PAIR", "INCOMPLETE"
    )
    candidates["predecessor_trajectory_coverage"] = np.where(
        candidates["predecessor_state_day_complete"].astype("boolean").fillna(False),
        1.0,
        np.nan,
    )
    return candidates


def apply_predecessor_support_rule(
    candidates: pd.DataFrame,
    cfg: dict[str, Any],
) -> pd.DataFrame:
    """Apply the configured provisional R3 rule and fail closed on conflicts."""
    output = candidates.copy()
    contract = cfg["predecessor_matching"]
    threshold = float(contract["gap_threshold_minutes"])
    ceiling = float(contract["administrative_hard_ceiling_minutes"])
    registration_conflict = output["predecessor_registration_match"].eq(False).fillna(False)
    typecode_conflict = output["predecessor_typecode_match"].eq(False).fillna(False)
    endpoint_ok = output["predecessor_endpoint_quality"].eq(
        "COMPLETE_INFERRED_AIRPORT_PAIR"
    )
    gap = pd.to_numeric(output["observed_ground_gap_minutes"], errors="coerce")
    selected = output["_selected_structural_candidate"].fillna(False).astype(bool)
    support_reason = np.select(
        [gap.gt(ceiling), gap.gt(threshold)],
        ["ADMINISTRATIVE_HARD_CEILING_EXCEEDED", "R3_GAP_THRESHOLD_EXCEEDED"],
        default="",
    )
    output["predecessor_rejection_reason"] = np.where(
        ~output["has_predecessor_candidate"],
        "NO_PREDECESSOR_CANDIDATE",
        np.where(selected, support_reason, output["raw_candidate_rejection_reason"]),
    )
    supported = output["predecessor_rejection_reason"].eq("")
    output["has_supported_predecessor"] = supported.astype(bool)
    strict_identity = (
        supported
        & output["predecessor_registration_match"].eq(True).fillna(False)
        & output["predecessor_typecode_match"].eq(True).fillna(False)
    )
    output["predecessor_evidence_tier"] = np.where(
        strict_identity, "R2_STRICT", np.where(supported, "R3_COVERAGE_AWARE", pd.NA)
    )
    output["predecessor_support_rule"] = np.where(
        strict_identity,
        str(contract["sensitivity_rule"]),
        np.where(supported, str(contract["primary_rule"]), pd.NA),
    )
    output["predecessor_support_status"] = np.where(
        supported, "SUPPORTED", "UNSUPPORTED"
    )
    output["selected_supported_predecessor_id"] = output[
        "predecessor_flight_id"
    ].where(supported)
    confidence = np.where(strict_identity, 1.0, 0.85)
    output["predecessor_match_confidence"] = np.where(
        supported, confidence, np.nan
    )
    return output


def build_predecessor_features(
    legs: pd.DataFrame,
    movement_reference: Any,
    turnaround_reference: Any,
    cfg: dict[str, Any],
) -> pd.DataFrame:
    """Create episode-level predecessor features from supported candidates."""
    output = apply_predecessor_support_rule(
        build_predecessor_candidates(legs, cfg), cfg
    )
    movement_deviation: list[float] = []
    turnaround_reference_minutes: list[float] = []
    for row in output.itertuples(index=False):
        if not bool(row.has_supported_predecessor):
            movement_deviation.append(np.nan)
            turnaround_reference_minutes.append(np.nan)
            continue
        predecessor = pd.Series({
            "origin": row.predecessor_origin,
            "destination": row.predecessor_destination,
            "firstseen_month": row.predecessor_firstseen_month,
            "firstseen_time_bin": row.predecessor_firstseen_time_bin,
            "aircraft_group": row.predecessor_aircraft_group,
            "distance_bin": row.predecessor_distance_bin,
            "origin_region": row.predecessor_origin_region,
            "destination_region": row.predecessor_destination_region,
            "region_pair": row.predecessor_region_pair,
        })
        try:
            reference_minutes = float(movement_reference.resolve(predecessor)[0])
            movement_deviation.append(
                float(row.predecessor_observed_movement_time) - reference_minutes
            )
        except KeyError:
            movement_deviation.append(np.nan)
        try:
            typical = turnaround_reference.resolve(
                str(row.origin),
                str(row.predecessor_aircraft_group),
                str(row.firstseen_time_bin),
            )[0]
            turnaround_reference_minutes.append(float(typical))
        except KeyError:
            turnaround_reference_minutes.append(np.nan)

    output["predecessor_movement_deviation_proxy"] = movement_deviation
    typical = pd.Series(turnaround_reference_minutes, index=output.index, dtype=float)
    output["ground_gap_deviation_from_reference"] = (
        pd.to_numeric(output["observed_ground_gap_minutes"], errors="coerce") - typical
    )
    output["turnaround_pressure_proxy"] = (
        (-output["ground_gap_deviation_from_reference"])
        .clip(lower=0.0)
        .div(typical.where(typical.gt(0.0)))
        .clip(upper=1.0)
    )
    movement_pressure = (
        pd.to_numeric(output["predecessor_movement_deviation_proxy"], errors="coerce")
        .clip(lower=0.0)
        .div(
            pd.to_numeric(output["predecessor_observed_movement_time"], errors="coerce")
            .where(lambda values: values.gt(0.0))
        )
        .clip(upper=1.0)
    )
    output["continuation_risk_proxy"] = (
        0.5 * output["turnaround_pressure_proxy"].fillna(0.0)
        + 0.5 * movement_pressure.fillna(0.0)
    ).where(output["has_supported_predecessor"])
    output["previous_leg_observation_quality"] = (
        output["predecessor_match_confidence"]
        * np.where(output["predecessor_trajectory_coverage"].notna(), 1.0, 0.8)
    )
    output["predecessor_completion_state"] = np.where(
        output["has_supported_predecessor"], "COMPLETED_BEFORE_CURRENT", pd.NA
    )
    output = output.rename(columns={
        "predecessor_firstseen_utc": "predecessor_firstseen_proxy",
        "predecessor_lastseen_utc": "predecessor_lastseen_proxy",
        "predecessor_observed_movement_time": "predecessor_observed_duration",
        "predecessor_origin": "predecessor_origin_inferred",
        "predecessor_destination": "predecessor_destination_inferred",
    })
    unsupported = ~output["has_supported_predecessor"]
    for column in _NULL_ON_UNSUPPORTED:
        if column in output:
            output.loc[unsupported, column] = pd.NA
    output["_predecessor_availability_time"] = pd.to_datetime(
        output["predecessor_lastseen_proxy"], utc=True, errors="coerce"
    )
    columns = [
        "episode_id", *PREDECESSOR_FEATURE_COLUMNS, "_predecessor_availability_time"
    ]
    return output[columns].drop_duplicates("episode_id", keep="last").reset_index(drop=True)


def attach_predecessor_features_to_snapshots(
    snapshots: pd.DataFrame,
    predecessor_features: pd.DataFrame,
) -> pd.DataFrame:
    output = snapshots.merge(
        predecessor_features, on="episode_id", how="left", validate="many_to_one"
    )
    output["has_predecessor_candidate"] = output[
        "has_predecessor_candidate"
    ].fillna(False).astype(bool)
    output["has_supported_predecessor"] = output[
        "has_supported_predecessor"
    ].fillna(False).astype(bool)
    availability = pd.to_datetime(
        output["_predecessor_availability_time"], utc=True, errors="coerce"
    )
    unavailable = output["has_supported_predecessor"] & (
        availability.isna() | availability.gt(output["decision_time_utc"])
    )
    if unavailable.any():
        output.loc[unavailable, "has_supported_predecessor"] = False
        output.loc[unavailable, "predecessor_support_status"] = "UNSUPPORTED"
        output.loc[unavailable, "predecessor_rejection_reason"] = (
            "NOT_AVAILABLE_BY_DECISION_TIME"
        )
        for column in _NULL_ON_UNSUPPORTED:
            output.loc[unavailable, column] = pd.NA
    return output
