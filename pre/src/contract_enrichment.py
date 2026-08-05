from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pandas as pd

from .target_contract import FORMAL_TARGET_COLUMN
from .validate import PreBundle


def _stable_id(*values: Any) -> str:
    return hashlib.sha256("|".join(map(str, values)).encode("utf-8")).hexdigest()[:24]


def _enrich_episodes(episodes: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    output = episodes.copy()
    output["anchor_date"] = pd.to_datetime(
        output["firstseen_utc"], utc=True
    ).dt.strftime("%Y-%m-%d")
    output["departure_airport"] = output["origin"]
    output["arrival_airport"] = output["destination"]
    output["aircraft_id"] = output["icao24"]
    output["planned_departure_time"] = pd.NaT
    output["planned_arrival_time"] = pd.NaT
    output["realized_departure_time"] = output["firstseen_utc"]
    output["realized_arrival_time"] = output["lastseen_utc"]
    output["m1_outcome_label"] = output[FORMAL_TARGET_COLUMN]
    output["subset_role"] = output["split"].map(
        {"train": "model", "validation": "audit", "test": "final_test"}
    ).fillna("excluded")
    valid = output["episode_valid"].fillna(False)
    output["train_eligible"] = valid & output["split"].eq("train")
    output["evaluation_only"] = valid & ~output["split"].eq("train")
    output["formal_eligible"] = valid
    output["debug_only"] = cfg["mode"] == "fast"
    output["trigger_event_group_id"] = [
        _stable_id(date, airport)
        for date, airport in zip(output["anchor_date"], output["airport"])
    ]
    output["recovery_event_level"] = "AIRPORT_DAY"
    return output


def _enrich_snapshots(
    snapshots: pd.DataFrame, episodes: pd.DataFrame
) -> pd.DataFrame:
    episode_cols = episodes[
        [
            "episode_id",
            "flight_id",
            "aircraft_id",
            "anchor_date",
            "trigger_event_group_id",
            "formal_eligible",
            "debug_only",
        ]
    ]
    output = snapshots.copy().drop(
        columns=[
            column
            for column in episode_cols.columns
            if column != "episode_id" and column in snapshots.columns
        ]
    )
    output = output.merge(
        episode_cols, on="episode_id", how="left", validate="many_to_one"
    )
    output["snapshot_time"] = output["decision_time_utc"]
    output["airport_id"] = output["airport"]
    output["source_available"] = ~output["state_source_coverage_status"].eq(
        "SOURCE_COVERAGE_GAP"
    )
    output["state_history_available"] = output["state_record_count"].fillna(0).gt(0)
    output["aircraft_sequence_available"] = output["continuity_exposure"].notna()
    output["passenger_handling_available"] = output[
        "estimated_passenger_load"
    ].notna()
    output["state_missing"] = ~output["state_history_available"]
    output["weather_missing"] = ~output["weather_observed"].fillna(False)
    output["flow_missing"] = output["airport_flow_pressure"].isna()
    output["passenger_proxy_missing"] = output["estimated_passenger_load"].isna()
    passenger_supported = (
        output[
            [
                "estimated_passenger_load",
                "connection_pressure_proxy",
                "rebooking_scarcity_proxy",
            ]
        ]
        .notna()
        .all(axis=1)
        & pd.to_numeric(output["passenger_proxy_support"], errors="coerce").gt(0)
        & output["passenger_proxy_evidence_status"].isin(
            ["OBSERVED", "SUPPORTED_PROXY", "FALLBACK_PROXY"]
        )
    )
    output["m4_passenger_input_supported"] = passenger_supported
    output["m4_eligible"] = passenger_supported
    output["m4_ineligibility_reason"] = np.where(
        passenger_supported, "", "PASSENGER_PROXY_UNSUPPORTED"
    )
    output["reference_level"] = output["passenger_proxy_level"].fillna("MISSING")
    output["fallback_level"] = output["passenger_proxy_fallback_reason"].fillna("")
    output["exclusion_reason"] = output["snapshot_exclusion_reason"]
    return output


def _enrich_rules(rules: pd.DataFrame) -> pd.DataFrame:
    output = rules.copy()
    output["airport_resource_available"] = output["resource_available_r"]
    output["aircraft_sequence_available"] = output["resource_available_f"]
    output["passenger_handling_available"] = output["resource_available_p"]
    output["deprecated_alias_mapping_version"] = "legacy-fpr-to-afp-v1"
    return output


def _enrich_audit(audit: pd.DataFrame, episodes: pd.DataFrame) -> pd.DataFrame:
    output = audit
    output["source_name"] = output["source"]
    output["source_available"] = ~output["evidence_status"].isin(
        ["UNOBSERVED", "UNSUPPORTED"]
    )
    output["observation_age"] = (
        pd.to_datetime(output["decision_time"], utc=True)
        - pd.to_datetime(output["event_time"], utc=True)
    ).dt.total_seconds() / 60.0
    output["interpolation_used"] = ~output["imputation_status"].eq("NOT_IMPUTED")
    output["proxy_level"] = np.where(
        output["evidence_status"].isin(
            ["AGGREGATE_PROXY", "SUPPORTED_PROXY", "FALLBACK_PROXY"]
        ),
        output["fallback_level"],
        "NONE",
    )
    output["reference_level"] = output["fallback_level"]
    output = output.drop(
        columns=[
            column
            for column in ["formal_eligible", "debug_only", "exclusion_reason"]
            if column in output.columns
        ]
    )
    return output.merge(
        episodes[
            ["episode_id", "formal_eligible", "debug_only", "exclusion_reason"]
        ],
        on="episode_id",
        how="left",
        validate="many_to_one",
    )


def enrich_contract(bundle: PreBundle, cfg: dict[str, Any]) -> PreBundle:
    episodes = _enrich_episodes(bundle.episodes, cfg)
    return PreBundle(
        episodes,
        _enrich_snapshots(bundle.snapshots, episodes),
        bundle.calibration.copy(),
        _enrich_rules(bundle.rules),
        _enrich_audit(bundle.evidence_audit, episodes),
    )


_enrich_contract = enrich_contract
