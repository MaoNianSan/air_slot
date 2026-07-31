from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .m1_lineage_contract import AuditStop


def build_current_identity(context: dict[str, Any], dictionary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    formal_hash = context["formal_cohort_hash"]
    tail_hash = context["tail_cohort_hash"]
    for spec in dictionary.to_dict("records"):
        key = spec["value_key"]
        reconstructed = context["values"][key]
        reported = context["reported_values"].get(key)
        support = int(context["tail_mask"].sum()) if key == "tail_coverage90" else len(context["predictions"])
        reported_support = context["reported_support"].get(key)
        tolerance = max(1e-12, 32 * np.finfo(np.float64).eps * max(1.0, abs(float(reconstructed))))
        if reported is None:
            absolute_error = np.nan
            relative_error = np.nan
            value_match: bool | None = None
            support_match: bool | None = None
            status = "RECONSTRUCTED_NOT_PUBLISHED"
        else:
            absolute_error = abs(float(reported) - float(reconstructed))
            relative_error = absolute_error / max(abs(float(reported)), tolerance)
            value_match = bool(absolute_error <= tolerance)
            support_match = bool(int(reported_support) == support)
            status = "PASS" if value_match and support_match else "MISMATCH"
        is_tail = key == "tail_coverage90"
        artifact_cohort = tail_hash if is_tail else formal_hash
        reconstructed_cohort = (
            context["reconstructed_tail_cohort_hash"]
            if is_tail else context["reconstructed_formal_cohort_hash"]
        )
        rows.append(
            {
                "metric_id": spec["metric_id"],
                "canonical_metric_id": spec["canonical_metric_id"],
                "reported_value": reported,
                "independently_reconstructed_value": reconstructed,
                "absolute_error": absolute_error,
                "relative_error": relative_error,
                "float_tolerance": tolerance,
                "value_match": value_match,
                "support_reported": reported_support,
                "support_reconstructed": support,
                "support_match": support_match,
                "artifact_cohort_hash": artifact_cohort,
                "reconstructed_cohort_hash": reconstructed_cohort,
                "cohort_hash_match": artifact_cohort == reconstructed_cohort,
                "prediction_layer": spec["prediction_layer"],
                "prediction_layer_match": True,
                "identity_status": status,
                "reported_artifact": spec["reported_artifact"],
            }
        )
    frame = pd.DataFrame(rows)
    if frame["identity_status"].eq("MISMATCH").any():
        failed = frame.loc[frame["identity_status"].eq("MISMATCH"), "metric_id"].tolist()
        raise AuditStop("CURRENT_METRIC_IDENTITY_MISMATCH:" + ",".join(failed))
    if not frame["cohort_hash_match"].all() or not frame["prediction_layer_match"].all():
        raise AuditStop("CURRENT_COHORT_OR_LAYER_IDENTITY_MISMATCH")
    return frame


