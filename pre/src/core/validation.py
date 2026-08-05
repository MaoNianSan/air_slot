from __future__ import annotations

from typing import Any

import pandas as pd

from .chain_validation import validate_chains
from .column_registry import validate_column_registry
from .event_validation import validate_events
from .observation_membership import validate_observation_membership


def core_statistics(
    tables: dict[str, pd.DataFrame],
    observation_validation: dict[str, Any],
    membership_validation: dict[str, Any],
    registry: list[dict[str, Any]],
) -> dict[str, Any]:
    episodes = tables.get("episodes", pd.DataFrame())
    events = tables.get("events", pd.DataFrame())
    calibration = tables.get("calibration", pd.DataFrame())
    evidence = tables.get("evidence_audit", pd.DataFrame())
    match_counts = (
        episodes.get("chain_match_status", pd.Series(dtype="string"))
        .value_counts(dropna=False)
        .to_dict()
    )
    eligibility_counts = {
        column: int(episodes.get(column, pd.Series(False, index=episodes.index)).fillna(False).astype(bool).sum())
        for column in (
            "core_eligible", "engineering_eligible",
            "scientific_chain_eligible", "formal_eligible",
        )
    }
    unsupported_labels = int(
        episodes.get("label_missing_reason", pd.Series("", index=episodes.index))
        .fillna("")
        .ne("")
        .sum()
    )
    future_information = int(
        evidence.get(
            "future_information_used", pd.Series(False, index=evidence.index)
        )
        .fillna(False)
        .astype(bool)
        .sum()
    )
    observation_partitions = observation_validation.get("partition_counts", {})
    if isinstance(observation_partitions, dict) and observation_partitions:
        observation_partition_count = sum(int(value) for value in observation_partitions.values())
    else:
        observation_partition_count = int(
            observation_validation.get("partition_count", 0)
        )
    observation_pass_empty = int(observation_validation.get("pass_empty_count", 0))
    membership_pass_empty = int(membership_validation.get("pass_empty", 0))
    return {
        "episodes_rows": len(episodes),
        "events_rows": len(events),
        "observation_rows": int(observation_validation.get("observation_rows", 0)),
        "membership_rows": int(membership_validation.get("membership_rows", 0)),
        "observation_partition_count": observation_partition_count,
        "membership_partition_count": int(membership_validation.get("partition_count", 0)),
        "observation_pass_empty_count": observation_pass_empty,
        "membership_pass_empty_count": membership_pass_empty,
        "pass_empty_count": observation_pass_empty + membership_pass_empty,
        "duplicate_key_counts": {
            "episodes": int(episodes.get("chain_episode_id", pd.Series(dtype="string")).duplicated().sum()),
            "events": int(events.get("event_id", pd.Series(dtype="string")).duplicated().sum()),
            "observations": int(observation_validation.get("duplicate_observation_ids", 0)),
            "membership_ids": int(membership_validation.get("duplicate_membership_ids", 0)),
            "membership_relations": int(membership_validation.get("duplicate_relations", 0)),
        },
        "chain_matched_count": int(match_counts.get("MATCHED", 0)),
        "chain_ambiguous_count": int(match_counts.get("AMBIGUOUS", 0)),
        "chain_unmatched_count": int(match_counts.get("UNMATCHED", 0)),
        "eligibility_counts": eligibility_counts,
        "unsupported_label_count": unsupported_labels,
        "future_information_count": future_information,
        "reference_row_count": len(calibration),
        "registry_column_count": len(registry),
    }


def _table_contracts(
    tables: dict[str, pd.DataFrame], cfg: dict[str, Any]
) -> dict[str, Any]:
    failures: dict[str, Any] = {}
    for name, spec in cfg["core_schema"]["tables"].items():
        if name in {"observations", "observation_membership"}:
            continue
        frame = tables.get(name)
        if frame is None:
            failures[name] = {"missing_table": True}
            continue
        missing = sorted(set(spec["required"]) - set(frame.columns))
        duplicate = int(frame.duplicated(spec["key"]).sum()) if not missing else -1
        if missing or duplicate:
            failures[name] = {"missing_columns": missing, "duplicate_keys": duplicate}
    return {"status": "PASS" if not failures else "FAIL", "failures": failures}


def _reference_contract(calibration: pd.DataFrame, cfg: dict[str, Any]) -> dict[str, Any]:
    train_end = pd.Timestamp(cfg["splits"]["train"][1], tz="UTC")
    fit_split_errors = int(calibration["fit_split"].ne("train").sum())
    future_fit = int(pd.to_datetime(calibration["fit_end_time"], utc=True).gt(train_end).sum())
    missing_hash = int(calibration["source_hash"].fillna("").astype(str).str.len().eq(0).sum())
    return {
        "status": "PASS" if not any([fit_split_errors, future_fit, missing_hash]) else "FAIL",
        "fit_split_errors": fit_split_errors,
        "future_fit_periods": future_fit,
        "missing_source_hash": missing_hash,
    }


def _leakage_contract(
    events: pd.DataFrame, episodes: pd.DataFrame, evidence: pd.DataFrame
) -> dict[str, Any]:
    future_evidence = int(evidence["future_information_used"].fillna(False).astype(bool).sum())
    unsupported_event_nonnull = int(
        (events["support_level"].eq("UNSUPPORTED") & events["event_time"].notna()).sum()
    )
    unsupported_labels = episodes["label_missing_reason"].ne("")
    zero_labels = int(
        episodes.loc[unsupported_labels, ["y_ob", "y_tx", "y_to"]]
        .eq(0)
        .any(axis=1)
        .sum()
    )
    supported_labels = episodes[["y_ob", "y_tx", "y_to"]].notna().all(axis=1)
    identity_errors = int(
        (~episodes.loc[supported_labels, "y_to"].eq(
            episodes.loc[supported_labels, "y_ob"] + episodes.loc[supported_labels, "y_tx"]
        )).sum()
    )
    evidence_missing_hash = int(
        evidence["source_hash"].fillna("").astype(str).str.len().eq(0).sum()
    )
    return {
        "status": "PASS" if not any([future_evidence, unsupported_event_nonnull, zero_labels, identity_errors, evidence_missing_hash]) else "FAIL",
        "future_information_used": future_evidence,
        "unsupported_event_nonnull": unsupported_event_nonnull,
        "missing_zero_confusion": zero_labels,
        "target_identity_status": "PASS" if supported_labels.any() and not identity_errors else "NOT_APPLICABLE" if not supported_labels.any() else "FAIL",
        "target_identity_errors": identity_errors,
        "evidence_missing_source_hash": evidence_missing_hash,
    }


def validate_core(
    tables: dict[str, pd.DataFrame],
    observation_validation: dict[str, Any],
    registry: list[dict[str, Any]],
    cfg: dict[str, Any],
    *,
    membership_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = validate_events(tables["events"])
    chain = validate_chains(tables["episodes"])
    table = _table_contracts(tables, cfg)
    reference = _reference_contract(tables["calibration"], cfg)
    leakage = _leakage_contract(
        tables["events"], tables["episodes"], tables["evidence_audit"]
    )
    column_registry = validate_column_registry(registry, cfg)
    membership = membership_validation or validate_observation_membership(
        tables.get("observation_membership", pd.DataFrame())
    )
    components = {
        "tables": table,
        "events": event,
        "chains": chain,
        "observations": observation_validation,
        "references": reference,
        "leakage": leakage,
        "column_registry": column_registry,
        "membership": membership,
    }
    status = "PASS" if all(value.get("status") == "PASS" for value in components.values()) else "FAIL"
    return {
        "status": status,
        **components,
        "statistics": core_statistics(
            tables, observation_validation, membership, registry
        ),
    }


def build_readiness(validation: dict[str, Any], episodes: pd.DataFrame) -> dict[str, Any]:
    engineering_rows = int(
        episodes["engineering_eligible"].fillna(False).astype(bool).sum()
    )
    scientific_rows = int(
        episodes.get(
            "scientific_chain_eligible", pd.Series(False, index=episodes.index)
        )
        .fillna(False)
        .astype(bool)
        .sum()
    )
    engineering_ready = validation["status"] == "PASS" and engineering_rows > 0
    labels_supported = episodes[["y_ob", "y_tx", "y_to"]].notna().all(axis=1).any()
    return {
        "status": "ENGINEERING_READY_FOR_ADAPTER" if engineering_ready else "NOT_READY",
        "engineering_ready": engineering_ready,
        "engineering_adapter_ready": bool(engineering_ready),
        "scientific_chain_ready": bool(validation["status"] == "PASS" and scientific_rows > 0),
        "scientific_status": "PASS" if labels_supported else "STOP_AND_REVIEW",
        "formal_chain_rows": engineering_rows,
        "engineering_chain_rows": engineering_rows,
        "scientific_chain_rows": scientific_rows,
        "supported_chain_labels": bool(labels_supported),
        "m1_migration_ready": bool(engineering_ready and labels_supported),
        "blockers": [] if labels_supported else ["AOBT_PLUS_AND_SOBT_UNSUPPORTED_FOR_CHAIN_LABELS"],
    }
