"""Second extraction pass: derived populations, headroom, cross-checks, E4 ladder.

Derived quantities are explicitly labelled; everything else is copied from the
audited cloud artifacts.
"""

from __future__ import annotations

import glob
import json
import math
import statistics
from pathlib import Path

SNAP = Path(
    "D:/research/air_slot/airslot_full_execution_snapshot_20261014/artifacts/experiment/jatm_s34/full_20261013"
)
REPO = Path("D:/research/air_slot/code/explore")
OUT = Path("D:/Local_Projects/airslot/backfill_20261014/extracted")
YEARS = (2017, 2018, 2019, 2020, 2021, 2022)


def load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_stage_nodes(year: int):
    """Canonical PRE/TURN nodes from the E1 chunk artifacts (one per episode x stage)."""
    best = {}
    for path in sorted(glob.glob(str(SNAP / "e1" / str(year) / "chunks" / "chunk_*.json"))):
        for node in load(path)["nodes"]:
            key = (node["episode_id"], node["stage"])
            current = best.get(key)
            stamp = (node["decision_time"], node["node_id"])
            if current is None or stamp < current[0]:
                best[key] = (stamp, node)
    return [value[1] for value in best.values()]


def derived_populations(year: int) -> dict:
    nodes = canonical_stage_nodes(year)
    per_stage = {}
    for stage in ("PRE_IB", "POST_IB_PRE_OB"):
        rows = [node for node in nodes if node["stage"] == stage]
        full = [node for node in rows if node["support"]["included"] and abs(float(node["support"]["supported_mass"]) - 1.0) <= 1e-9]
        per_stage["PRE" if stage == "PRE_IB" else "TURN"] = {
            "canonical_candidates": len(rows),
            "full_support_candidates": len(full),
            "support_mass_histogram": {
                str(value): sum(1 for node in rows if round(float(node["support"]["supported_mass"]), 3) == value)
                for value in sorted({round(float(node["support"]["supported_mass"]), 3) for node in rows})
            },
        }
    return {
        "derivation": "counted from E1 bounded chunk artifacts: canonical PRE/TURN nodes; "
                      "full support = support.included and supported_mass == 1.0 "
                      "(same criterion as reference_recovery_cohort / support_full)",
        "per_stage": per_stage,
        "derived_full_stage2_eligible_total": sum(v["full_support_candidates"] for v in per_stage.values()),
    }


def headroom(year: int) -> dict:
    payload = load(REPO / "data2" / "reports" / "paper_formal" / str(year) / str(year) / "M2_TRAIN_HEADROOM_SUMMARY.json")
    summary = payload["factual_headroom"]["headroom_summary"]
    return {
        "year": year,
        "turnaround_lower_bound_q": summary.get("turnaround_lower_bound_q"),
        "u_max": summary.get("u_max"),
        "floor_to_minutes": summary.get("floor_to_minutes"),
        "train_partition": payload.get("train_partition", {}).get("fit_period"),
        "source": str(REPO / "data2" / "reports" / "paper_formal" / str(year) / str(year) / "M2_TRAIN_HEADROOM_SUMMARY.json"),
    }


def e4_ladder(year: int) -> dict:
    payload = load(SNAP / "e4" / str(year) / "EVAL_SUMMARY.json")
    block = payload["years"][str(year)]
    keys = sorted({key for level in block["eval"].values() if isinstance(level, dict) for key in level})
    ladder = {}
    for name, level in sorted(block["eval"].items(), key=lambda item: int(item[0])):
        ladder[name] = level if isinstance(level, str) else {key: level.get(key) for key in keys}
    return {
        "year": year,
        "protocol_hash": payload["protocol_hash"],
        "evaluation_E": block["evaluation_E"],
        "bootstrap": payload["bootstrap"],
        "eval_keys": keys,
        "eval_ladder": ladder,
        "fit_ladder": {name: level for name, level in sorted(block["fit"].items(), key=lambda item: int(item[0]))},
        "decision": payload["decision"],
    }


def main() -> int:
    report = {"derived_populations": {}, "headroom": {}, "e4_ladder": {}, "crosschecks": {}}
    for year in YEARS:
        report["derived_populations"][year] = derived_populations(year)
        report["headroom"][year] = headroom(year)
        report["e4_ladder"][year] = e4_ladder(year)

        # cross-check: E2 reference_V (Balanced HJ) vs sum of E3 per-node recoverable values
        e2 = load(SNAP / "e2e3" / str(year) / "E2_E3_SUMMARY.json")
        rows = load(SNAP / "e2e3" / str(year) / "E3_OBJECTIVE_ROWS.json")
        balanced = [row for row in rows if row["profile"] == "BALANCED" and row["representation"] == "HISTORY_JOINT"]
        total = sum(row["recoverable_value"] for row in balanced)
        reference = [row for row in e2["e2"]["recovery_rows"] if row["representation"] == "CURRENT_JOINT"][0]["reference_recoverable_value"]
        cohorts = e2["e2"]["reference_cohort_size"]
        stage1 = e2["e2"]["stage1_rows"]
        report["crosschecks"][year] = {
            "e3_balanced_HJ_node_count": len(balanced),
            "e3_sum_recoverable_value": round(total, 9),
            "e2_reference_recoverable_value": round(float(reference), 9),
            "abs_diff": abs(total - float(reference)),
            "e2_reference_cohort_size": cohorts,
            "stage1_K_sum": sum(row["K"] for row in stage1),
            "e3_mechanism_rows": len(load(SNAP / "e2e3" / str(year) / "E3_MECHANISM_DIAGNOSTICS.json")),
        }
        print(f"{year}: full-support PRE/TURN = "
              f"{report['derived_populations'][year]['per_stage']['PRE']['full_support_candidates']}+"
              f"{report['derived_populations'][year]['per_stage']['TURN']['full_support_candidates']} ; "
              f"U_max={report['headroom'][year]['u_max']} T_lb={report['headroom'][year]['turnaround_lower_bound_q']} ; "
              f"V cross-check |diff|={report['crosschecks'][year]['abs_diff']:.2e} ; "
              f"cohort={cohorts} == K_sum={report['crosschecks'][year]['stage1_K_sum']}")
    path = OUT / "derived_and_checks.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
