from __future__ import annotations

from typing import Any

import pandas as pd

from ..chain_validation import validate_chains
from ..event_validation import validate_events


def eligibility_checks(episodes: pd.DataFrame) -> dict[str, Any]:
    required = {"core_eligible", "engineering_eligible", "scientific_chain_eligible"}
    missing = sorted(required - set(episodes.columns))
    if missing:
        return {"status": "FAIL", "missing": missing}
    proxy = episodes["chain_support_level"].eq("OBSERVED_CHAIN_PROXY")
    errors = int(
        (~episodes["core_eligible"].astype(bool).ge(episodes["engineering_eligible"].astype(bool))).sum()
        + (proxy & episodes["scientific_chain_eligible"].astype(bool)).sum()
    )
    return {"status": "PASS" if errors == 0 else "FAIL", "errors": errors, "observed_proxy_rows": int(proxy.sum())}


def leakage_checks(tables: dict[str, pd.DataFrame]) -> dict[str, Any]:
    events = tables.get("events", pd.DataFrame())
    episodes = tables.get("episodes", pd.DataFrame())
    evidence = tables.get("evidence_audit", pd.DataFrame())
    unsupported_event_nonnull = int((events.get("support_level", pd.Series(dtype="string")).eq("UNSUPPORTED") & events.get("event_time", pd.Series(dtype="datetime64[ns]")).notna()).sum()) if not events.empty else 0
    unsupported_label_nonnull = target_identity_errors = 0
    if not episodes.empty:
        unsupported = episodes.get("label_missing_reason", pd.Series("", index=episodes.index)).ne("")
        unsupported_label_nonnull = int(episodes.loc[unsupported, ["y_ob", "y_tx", "y_to"]].notna().any(axis=1).sum())
        supported = episodes[["y_ob", "y_tx", "y_to"]].notna().all(axis=1)
        if supported.any():
            target_identity_errors = int((~episodes.loc[supported, "y_to"].eq(episodes.loc[supported, "y_ob"] + episodes.loc[supported, "y_tx"])).sum())
    future_evidence = int(evidence.get("future_information_used", pd.Series(dtype="boolean")).fillna(False).astype(bool).sum()) if not evidence.empty else 0
    missing_hash = int(evidence.get("source_hash", pd.Series(dtype="string")).fillna("").astype(str).str.len().eq(0).sum()) if not evidence.empty else 0
    errors = unsupported_event_nonnull + unsupported_label_nonnull + target_identity_errors + future_evidence + missing_hash
    return {"status": "PASS" if errors == 0 else "FAIL", "unsupported_event_nonnull": unsupported_event_nonnull, "unsupported_label_nonnull": unsupported_label_nonnull, "target_identity_errors": target_identity_errors, "future_information_used": future_evidence, "evidence_missing_source_hash": missing_hash}


def reference_checks(calibration: pd.DataFrame, cfg: dict[str, Any]) -> dict[str, Any]:
    train_end = pd.Timestamp(cfg["splits"]["train"][1], tz="UTC")
    passed = calibration["fit_split"].eq("train").all() and not pd.to_datetime(calibration["fit_end_time"], utc=True).gt(train_end).any()
    return {"status": "PASS" if passed else "FAIL"}


def run_scientific_checks(tables: dict[str, pd.DataFrame], cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checks: dict[str, dict[str, Any]] = {}
    if "events" in tables:
        checks["event_contract"] = validate_events(tables["events"])
    if "episodes" in tables:
        checks["chain_contract"] = validate_chains(tables["episodes"])
        checks["eligibility_semantics"] = eligibility_checks(tables["episodes"])
    if "calibration" in tables:
        checks["reference_train_only"] = reference_checks(tables["calibration"], cfg)
    checks["leakage"] = leakage_checks(tables)
    return checks
