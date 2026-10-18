"""DataFrame adapter to the existing shared priority authority."""

import numpy as np
import pandas as pd

from exp.shared.contracts import SupportedScore
from exp.shared.recovery_priority import (
    compute_domain_scores, compute_aggregate_priority,
    compute_no_f_execution_priority, compute_equal_component_priority,
)
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS as COMPONENTS

ACTIVE_STAGES = ("PRE_IB", "POST_IB_PRE_OB", "POST_OB_PRE_TO")


def scores(frame):
    out = frame.copy()
    if "original_episode_id" not in out:
        out["original_episode_id"] = out.episode_id
    out["D"] = out["delay_to_mean_cs"]
    columns = ["S_F", "S_P", "S_R", "S_C", "NO_F_EXECUTION", "EQUAL_COMPONENT"]
    values = []
    for row in out.to_dict("records"):
        components = {}
        for c in COMPONENTS:
            v = row[f"Z_{c}_cs"]
            ok = v is not None and np.isfinite(v) and v >= 0
            components[c] = SupportedScore(
                value=float(v) if ok else None, support="SUPPORTED" if ok else "UNSUPPORTED",
                reason_codes=() if ok else ("INPUT_UNSUPPORTED",),
            )
        domains = compute_domain_scores(components)
        values.append([
            *[domains[f"score_{d}"].value for d in ("F", "P", "R")],
            compute_aggregate_priority(domains).value,
            compute_no_f_execution_priority(components, domains).value,
            compute_equal_component_priority(components).value,
        ])
    out[columns] = pd.DataFrame(values, index=out.index, columns=columns, dtype=float)
    return out


def primary_mask(data):
    mask = (
        data.operational_stage.isin(ACTIVE_STAGES)
        & data.support_primary.eq(True)
        & data.conditional_aggregate_complete.eq(True)
        & np.isfinite(data[["D", "S_C"]].to_numpy(float)).all(axis=1)
    )
    if "common_support_mass" in data:
        mask &= data.common_support_mass.ge(.9)
    return mask


def validate_development(frame):
    for field in ("decision_time", "information_cutoff"):
        times = pd.to_datetime(frame[field], utc=True, errors="raise")
        if times.isna().any() or not times.between(
            pd.Timestamp("2019-08-01", tz="UTC"),
            pd.Timestamp("2019-10-01", tz="UTC"), inclusive="left",
        ).all():
            raise ValueError("FINAL_TEST_OR_NON_DEVELOPMENT_DATE_REJECTED")
    if (pd.to_datetime(frame.information_cutoff, utc=True) >
            pd.to_datetime(frame.decision_time, utc=True)).any():
        raise ValueError("FUTURE_INFORMATION_REJECTED")
    if "final_test_access_count" not in frame or not frame.final_test_access_count.eq(0).all():
        raise ValueError("FINAL_TEST_ACCESS_GUARD_FAILED")
    if frame.duplicated(["episode_id", "decision_node_id"]).any():
        raise ValueError("DUPLICATE_INPUT_NODE")
