from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


TYPED_GATE_COLUMNS = (
    "aircraft_swap_available", "rotation_reassignment_available",
    "standby_aircraft_available", "aircraft_group_compatible",
    "crew_swap_available", "standby_crew_available",
    "crew_reposition_available", "crew_qualification_compatible",
    "gate_reassignment_available", "ground_support_available",
    "tow_support_available", "cancellation_authority_available",
    "network_reset_authority_available",
    "passenger_reaccommodation_available",
    "capacity_coordination_available",
)


def build_rules(snapshots: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    action_ids = list(cfg["actions"]["action_ids"])
    profile_id = cfg["rules"]["authority_profile_id"]
    profile = cfg["actions"].get("authority_profiles", {}).get(profile_id)
    authority_source = "DECLARED_RULE"
    if profile is None:
        profile = {action: action == "A00" for action in action_ids}
        authority_source = "DEFAULT_NULL_ONLY"
    valid = snapshots[snapshots["snapshot_valid"].fillna(False)].reset_index(drop=True)
    if valid.empty:
        return pd.DataFrame()
    count = len(action_ids)
    source_columns = [
        "episode_id", "snapshot_id", "_capacity_threshold", "_capacity_p05", "_capacity_p95",
        "_capacity_fallback_level", "window_margin_complete", "execution_window_margin", "lead_time_margin",
        "aircraft_group", "has_supported_predecessor", "estimated_passenger_load",
        "passenger_proxy_support", "passenger_proxy_evidence_status",
    ]
    rules = valid[source_columns].iloc[np.repeat(np.arange(len(valid)), count)].reset_index(drop=True)
    rules["action_id"] = pd.Categorical(np.tile(action_ids, len(valid)), categories=action_ids)
    specs = cfg["actions"].get("action_specs", {})
    window_map = {action: str(specs.get(action, {}).get("window_type", "flight_timing")) for action in action_ids}
    capacity_map = {action: bool(specs.get(action, {}).get("capacity_required", False)) for action in action_ids}
    rules["window_type"] = rules["action_id"].astype(str).map(window_map).astype("category")
    rules["capacity_required"] = rules["action_id"].astype(str).map(capacity_map).astype(bool)
    window_applicable = rules["window_type"].astype(str).isin(["flight_timing", "combined"])
    window_complete = rules["window_margin_complete"].fillna(False).astype(bool) & rules["execution_window_margin"].notna()
    rules["action_window_open"] = (~window_applicable) | (window_complete & rules["execution_window_margin"].gt(0))
    rules["action_window_margin"] = rules["execution_window_margin"].where(window_applicable, 0.0)
    rules["window_rule_id"] = pd.Categorical(np.where(window_applicable, "ACTION_SPECIFIC_WINDOW_V2", "NOT_APPLICABLE"))
    rules["authority_allowed"] = rules["action_id"].astype(str).map(profile).fillna(False).astype(bool)

    derived_values = {
        "has_supported_predecessor": rules["has_supported_predecessor"].fillna(False).astype(bool),
        "aircraft_group_known": rules["aircraft_group"].astype("string").notna()
        & ~rules["aircraft_group"].astype("string").isin(["", "unknown"]),
        "passenger_handling_available": rules["estimated_passenger_load"].notna()
        & pd.to_numeric(rules["passenger_proxy_support"], errors="coerce").gt(0)
        & rules["passenger_proxy_evidence_status"].astype("string").isin(
            ["OBSERVED", "SUPPORTED_PROXY", "FALLBACK_PROXY"]
        ),
        "capacity_reference_available": rules[
            ["_capacity_threshold", "_capacity_p05", "_capacity_p95"]
        ].notna().all(axis=1),
    }
    typed_defaults = cfg["actions"].get("typed_gate_defaults", {})
    for gate in TYPED_GATE_COLUMNS:
        gate_cfg = typed_defaults.get(gate, {})
        source = gate_cfg.get("value_from")
        if source:
            value = derived_values.get(source, pd.Series(False, index=rules.index))
        else:
            value = pd.Series(bool(gate_cfg.get("value", False)), index=rules.index)
        rules[gate] = value.fillna(False).astype(bool)
        evidence = str(gate_cfg.get("evidence_status", "UNSUPPORTED"))
        evidence_values = pd.Series(evidence, index=rules.index, dtype="string")
        if evidence == "OBSERVED":
            evidence_values = evidence_values.mask(~rules[gate], "UNSUPPORTED")
        rules[f"{gate}_evidence_status"] = evidence_values.astype("category")

    typed_map = {
        action: tuple(specs.get(action, {}).get("typed_gates", ()))
        for action in action_ids
    }
    rules["typed_gate_required"] = rules["action_id"].astype(str).map(
        lambda action: "|".join(typed_map.get(action, ()))
    )
    typed_pass = pd.Series(True, index=rules.index)
    for gate in TYPED_GATE_COLUMNS:
        required = rules["typed_gate_required"].str.split("|", regex=False).map(
            lambda values: gate in values
        )
        typed_pass &= ~required | rules[gate]
    rules["typed_gate_pass"] = typed_pass.astype(bool)
    rules["typed_gate_status"] = np.where(
        rules["typed_gate_required"].eq(""),
        "NOT_APPLICABLE",
        np.where(rules["typed_gate_pass"], "PASS", "FAIL_CLOSED"),
    )

    missing = pd.Series("", index=rules.index, dtype="string")
    for column, label in [
        ("_capacity_threshold", "capacity_threshold"),
        ("_capacity_p05", "capacity_reference_p05"),
        ("_capacity_p95", "capacity_reference_p95"),
    ]:
        condition = rules["capacity_required"] & rules[column].isna()
        missing = missing.mask(condition & missing.eq(""), label)
        missing = missing.mask(condition & missing.ne("") & ~missing.str.endswith(label), missing + "," + label)
    condition = window_applicable & ~window_complete
    missing = missing.mask(condition & missing.eq(""), "action_window_margin")
    missing = missing.mask(condition & missing.ne("") & ~missing.str.endswith("action_window_margin"), missing + ",action_window_margin")
    condition = rules["lead_time_margin"].isna()
    missing = missing.mask(condition & missing.eq(""), "lead_time_margin")
    missing = missing.mask(condition & missing.ne("") & ~missing.str.endswith("lead_time_margin"), missing + ",lead_time_margin")
    rules["rule_missing_reason"] = ("RECORD_EXPECTED_BUT_MISSING:" + missing).where(missing.ne(""), "").astype("category")

    resource = str(cfg["rules"]["resource_profile_id"])
    old_f = {"scarce": .35, "normal": .80, "ample": .95}.get(resource, np.nan)
    old_p = {"scarce": .35, "normal": .70, "ample": .95}.get(resource, np.nan)
    old_r = {"scarce": .45, "normal": .85, "ample": .95}.get(resource, np.nan)
    rules = rules.rename(columns={
        "_capacity_threshold": "capacity_threshold",
        "_capacity_p05": "capacity_reference_p05",
        "_capacity_p95": "capacity_reference_p95",
        "_capacity_fallback_level": "capacity_fallback_level",
    })
    constants = {
        "lead_rule_id": "TREF_REMAINING_TIME_V1", "authority_rule_id": profile_id,
        "authority_profile_id": profile_id, "authority_source": authority_source,
        "resource_profile_id": resource, "airport_resource_available": old_r,
        "aircraft_sequence_available": old_f, "passenger_handling_available": old_p,
        "resource_available_f": old_f, "resource_available_p": old_p, "resource_available_r": old_r,
        "deprecated_alias_mapping_version": "legacy-fpr-to-afp-v1", "rule_evidence_status": "RULE_GENERATED",
        "rule_generation_version": cfg["rules"]["rule_generation_version"],
    }
    for column, value in constants.items():
        rules[column] = value
        if isinstance(value, str):
            rules[column] = rules[column].astype("category")
    rules = rules.drop(columns=[
        "window_margin_complete", "execution_window_margin", "aircraft_group",
        "has_supported_predecessor", "estimated_passenger_load",
        "passenger_proxy_support", "passenger_proxy_evidence_status",
    ])
    for column in rules.select_dtypes(include=["object", "string"]).columns:
        rules[column] = rules[column].astype("category")
    return rules
