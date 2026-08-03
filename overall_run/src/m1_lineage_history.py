from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .m1_lineage_contract import (
    DEPRECATION_DATE,
    EXPECTED_CONFIG_HASH,
    EXPECTED_RUN_ID,
    EXPECTED_SCIENTIFIC_IMPLEMENTATION_HASH,
    FAST_ROOT,
    HISTORICAL_FIXTURE_ROOT,
    LOG_ROOT,
    MODULE_ROOT,
    PROJECT_ROOT,
    sha256_file,
)


def build_historical_deprecation_registry() -> pd.DataFrame:
    claims = [
        ("coverage_approx_0_895", 0.895, "coverage", "M1_INTERVAL_COVERAGE_90_V1"),
        ("coverage_approx_0_942", 0.942, "coverage", "M1_INTERVAL_COVERAGE_90_V1"),
        ("crps_approx_7_17", 7.17, "CRPS", "M1_CRPS_V1"),
        ("crps_approx_20_48", 20.48, "CRPS", "M1_CRPS_V1"),
        ("twcrps_approx_14_90", 14.90, "twCRPS", "M1_TWCRPS_V1"),
        ("twcrps_approx_46_20", 46.20, "twCRPS", "M1_TWCRPS_V1"),
        ("tail_approx_0_818", 0.818, "tail metric", "M1_OUTCOME_SELECTED_TAIL_COVERAGE_V1"),
        ("tail_approx_0_795", 0.795, "tail metric", "M1_OUTCOME_SELECTED_TAIL_COVERAGE_V1"),
        ("d6_b_q95_calibration_claim", np.nan, "q95 calibration conclusion", "M1_Q95_CALIBRATION_ABS_V2"),
        ("d6_b_q99_calibration_pass_claim", np.nan, "q99 calibration conclusion", "M1_Q99_CALIBRATION_ABS_V2"),
        ("d6_b_twcrps_comparative_claim", np.nan, "twCRPS comparative conclusion", "M1_TWCRPS_PROP_MINUS_HIST_V1"),
        ("d6_b_q95_pinball_claim", np.nan, "q95 pinball conclusion", "M1_PINBALL_Q95_PROP_MINUS_HIST_V1"),
        ("d6_b_q99_pinball_claim", np.nan, "q99 pinball conclusion", "M1_PINBALL_Q99_PROP_MINUS_HIST_V1"),
        ("d6_b_upper_shortfall_claim", np.nan, "upper shortfall conclusion", "M1_UPPER_SHORTFALL_Q99_REPORT_ONLY_V1"),
    ]
    return pd.DataFrame(
        [
            {
                "historical_value_label": label,
                "approximate_value": value,
                "claimed_metric": metric,
                "source_artifact_status": "HISTORICAL_NUMBER_SOURCE_NOT_RECOVERED",
                "prediction_artifact_status": "MISSING",
                "cohort_status": "UNKNOWN_NOT_RECOVERED",
                "metric_version_status": "UNKNOWN_NOT_RECOVERED",
                "calibration_layer_status": "UNKNOWN_NOT_RECOVERED",
                "bootstrap_lineage_status": "UNKNOWN_NOT_RECOVERED",
                "reconstructability": "NOT_RECONSTRUCTABLE",
                "authority_status": "NON_AUTHORITATIVE",
                "manuscript_use_status": "PROHIBITED",
                "current_replacement_metric_id": replacement,
                "replacement_implies_historical_equivalence": False,
                "researcher_disposition": "DEPRECATED_UNRECOVERABLE",
                "disposition_date": DEPRECATION_DATE,
            }
            for label, value, metric, replacement in claims
        ]
    )


def build_historical_tables(deprecation: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    lineage_path = HISTORICAL_FIXTURE_ROOT / "audit" / "historical_d6_label_lineage.json"
    inventory = pd.DataFrame(
        [
            {
                "path": str(lineage_path),
                "filename": lineage_path.name,
                "created_time": datetime.fromtimestamp(lineage_path.stat().st_ctime).isoformat(),
                "modified_time": datetime.fromtimestamp(lineage_path.stat().st_mtime).isoformat(),
                "run_id": EXPECTED_RUN_ID,
                "mode": "fast",
                "config_hash": EXPECTED_CONFIG_HASH,
                "implementation_hash": EXPECTED_SCIENTIFIC_IMPLEMENTATION_HASH,
                "source_artifact_hash": sha256_file(lineage_path),
                "metric_version": "UNKNOWN_NOT_RECOVERED",
                "cohort_description": "UNKNOWN_NOT_RECOVERED",
                "support": None,
                "reconstructability": "SUMMARY_ONLY_NOT_FULLY_RECONSTRUCTABLE",
                "authoritative": False,
                "superseded": True,
                "disposition": "DEPRECATED_UNRECOVERABLE",
            }
        ]
    )
    identity = deprecation[
        ["historical_value_label", "approximate_value", "claimed_metric", "current_replacement_metric_id"]
    ].copy()
    identity["independently_reconstructed_value"] = np.nan
    identity["identity_status"] = "NOT_RECONSTRUCTABLE_DEPRECATED"
    identity["authority_status"] = "NON_AUTHORITATIVE"
    comparison = identity.copy()
    comparison["current_value"] = np.nan
    comparison["difference"] = np.nan
    comparison["difference_classification"] = "HISTORICAL_ARTIFACT_INCOMPLETE"
    comparison["direct_comparison_prohibited"] = True
    comparison["unexplained_difference"] = False
    comparison["lineage_collision"] = False
    comparison["note"] = (
        "Deprecation is evidence governance, not reconstruction or scientific reconciliation."
    )
    return inventory, identity, comparison


def scan_formal_materials_for_deprecated_claims() -> list[str]:
    patterns = [
        re.compile(r"coverage\s+(?:approximately|approx\.?|about)\s+0\.895", re.I),
        re.compile(r"coverage\s+(?:approximately|approx\.?|about)\s+0\.942", re.I),
        re.compile(r"CRPS\s+(?:approximately|approx\.?|about)\s+(?:7\.17|20\.48)", re.I),
        re.compile(r"twCRPS\s+(?:approximately|approx\.?|about)\s+(?:14\.90|46\.20)", re.I),
        re.compile(r"tail\s+(?:approximately|approx\.?|about)\s+(?:0\.818|0\.795)", re.I),
    ]
    candidates = [
        PROJECT_ROOT / "README.md", PROJECT_ROOT / "CLOUD_RUNBOOK.md",
        PROJECT_ROOT / "FINAL_STAGE_STATUS.md", PROJECT_ROOT / "FINAL_CODE_FREEZE_SUMMARY.json",
        MODULE_ROOT / "README.md", FAST_ROOT / "run_summary.json", FAST_ROOT / "scientific_gate.json",
    ]
    candidates.extend((FAST_ROOT / "tables").rglob("*.csv"))
    hits = []
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in patterns):
            hits.append(str(path.relative_to(PROJECT_ROOT)))
    return sorted(set(hits))


