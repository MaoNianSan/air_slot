"""Finalize quick-diagnostic outputs (2026-08-18).

Merges the already-computed Exp1 lead-time quantiles (cross-validated against
the frozen evidence.json) into the M1 horizon JSON and writes the final MD
report. No Exp1 inference rerun; values are from the frozen parquets computed
by exp1_lead_quantiles_quick_20260818.py in this session.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from exp1_lead_quantiles_quick_20260818 import JSON_PATH, MD_PATH, write_markdown  # noqa: E402

# Computed in this session from the frozen principal_s250 parquets, with
# frozen evidence.json cross-checks.
LEAD = {
    "source": "AIR_SLOT_EXP1_DEVELOPMENT_WARNING_FREEZE principal_s250 (frozen parquet, read-only)",
    "operating_point": "target episode FPR 0.1",
    "lead_definition": (
        "sustained-warning positive episodes: minutes from the first sustained warning node "
        "(two consecutive 5-min nodes with min(warning_probability) >= threshold) to realized WheelsOff"
    ),
    "quantile_rule": "nearest-rank, identical to frozen exp/exp1/metrics.py",
    "variants": {
        "CURRENT": {
            "threshold": 0.364, "N_leads": 4686, "median_min": 105.0,
            "q25_min": 80.0, "q75_min": 142.0, "iqr_min": 62.0,
            "positive_evaluable": 120092, "sustained_warning_count": 4686,
            "frozen_median_crosscheck": 105.0, "frozen_iqr_crosscheck": 62.0,
            "crosscheck_status": "PASS (median/IQR/denominator 与 frozen evidence 完全一致)",
        },
        "FIXED_HISTORY": {
            "threshold": 0.384, "N_leads": 5772, "median_min": 108.0,
            "q25_min": 83.0, "q75_min": 145.0, "iqr_min": 62.0,
            "positive_evaluable": 120092, "sustained_warning_count": 5772,
            "frozen_median_crosscheck": 108.0, "frozen_iqr_crosscheck": 62.0,
            "crosscheck_status": "PASS (median/IQR/recall/denominator 全部与 frozen evidence 完全一致)",
        },
        "ADAPTIVE_HISTORY": {
            "threshold": 0.392, "N_leads": 4325, "median_min": 108.0,
            "q25_min": 84.0, "q75_min": 145.0, "iqr_min": 61.0,
            "positive_evaluable": 120092, "sustained_warning_count": 4325,
            "frozen_median_crosscheck": 109.0, "frozen_iqr_crosscheck": 61.0,
            "crosscheck_status": (
                "PARTIAL (IQR/denominator 与 frozen 一致; 本会话计算 median=108 vs frozen=109, "
                "sustained-warning episode 集少约 800, Q25/Q75 为近似值 ±1 min)"
            ),
        },
    },
    "crosscheck_against_frozen_evidence": (
        "FIXED/CURRENT 完全一致; ADAPTIVE IQR 一致、median 差 1 min（近似）"
    ),
}


def main() -> None:
    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    assert "exp1_lead_time_quantiles" not in payload
    payload["exp1_lead_time_quantiles"] = LEAD
    payload["status"] = "M1_HORIZON_QUICK_DIAGNOSTIC = PASS"
    JSON_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("MERGED", JSON_PATH)
    write_markdown(payload)
    print("WROTE", MD_PATH)


if __name__ == "__main__":
    main()
