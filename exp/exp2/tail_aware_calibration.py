"""Fixed-bin calibration diagnostics for the frozen Exp2A tail-aware event."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any

from model.common.identity import content_id


BRIER_PATH = Path(
    "artifacts/experiment/exp2a_tail_aware_brier_v1/EXP2A_TAIL_AWARE_BRIER.json"
)
BIN_EDGES = tuple(index / 10.0 for index in range(11))
SAFETY = {
    "M1_TRAINING_RUNS_THIS_MATERIALIZATION": 0,
    "TUNING_RUNS_THIS_MATERIALIZATION": 0,
    "EXP2_RUNS_THIS_MATERIALIZATION": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "FULL": False,
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"EXP2_TAIL_AWARE_CALIBRATION_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _bin_index(probability: float) -> int:
    _require(0.0 <= probability <= 1.0, "EXP2_CALIBRATION_PROBABILITY_OUT_OF_RANGE")
    return min(int(probability * 10), 9)


def materialize(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/experiment/exp2a_tail_aware_calibration_v1").resolve()
    source_path = root / BRIER_PATH
    _require(source_path.is_file(), "EXP2_TAIL_AWARE_CALIBRATION_INPUT_MISSING")
    source = _load(source_path)
    _require(source["status"] == "EXP2A_TAIL_AWARE_BRIER_MATERIALIZED", "EXP2_TAIL_AWARE_CALIBRATION_SOURCE_INVALID")
    _require(source["principal_event"] == "D_TO_POST_GT_30", "EXP2_TAIL_AWARE_CALIBRATION_EVENT_MISMATCH")
    _require(source["abstention_policy"] == "UNRESOLVED_INTERVAL_OR_MISSING_OBSERVED_LABEL_ABSTAIN", "EXP2_TAIL_AWARE_CALIBRATION_ABSTENTION_MISMATCH")

    variants: dict[str, dict[str, Any]] = {}
    for variant in source["variants"]:
        rows = [
            row for row in source["node_rows"]
            if row["variant"] == variant and row["support_status"] == "SUPPORTED"
        ]
        by_episode: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_episode[row["episode_id"]].append(row)
        episode_count = len(by_episode)
        weighted_rows: list[tuple[dict[str, Any], float]] = []
        for episode_rows in by_episode.values():
            weight = 1.0 / episode_count / len(episode_rows)
            weighted_rows.extend((row, weight) for row in episode_rows)

        bins: list[dict[str, Any]] = []
        gap = 0.0
        for index in range(10):
            members = [(row, weight) for row, weight in weighted_rows if _bin_index(float(row["event_probability"])) == index]
            mass = sum(weight for _, weight in members)
            if not members:
                bins.append({
                    "bin_index": index,
                    "lower_inclusive": BIN_EDGES[index],
                    "upper_inclusive" if index == 9 else "upper_exclusive": BIN_EDGES[index + 1],
                    "support_status": "EMPTY",
                    "node_count": 0,
                    "episode_count": 0,
                    "episode_balanced_mass": 0.0,
                    "mean_forecast_probability": None,
                    "observed_event_rate": None,
                    "absolute_gap": None,
                })
                continue
            mean_probability = sum(weight * float(row["event_probability"]) for row, weight in members) / mass
            observed_rate = sum(weight * float(row["observed_event"]) for row, weight in members) / mass
            absolute_gap = abs(mean_probability - observed_rate)
            gap += mass * absolute_gap
            bins.append({
                "bin_index": index,
                "lower_inclusive": BIN_EDGES[index],
                "upper_inclusive" if index == 9 else "upper_exclusive": BIN_EDGES[index + 1],
                "support_status": "SUPPORTED",
                "node_count": len(members),
                "episode_count": len({row["episode_id"] for row, _ in members}),
                "episode_balanced_mass": mass,
                "mean_forecast_probability": mean_probability,
                "observed_event_rate": observed_rate,
                "absolute_gap": absolute_gap,
            })
        variants[variant] = {
            "support_status": "SUPPORTED" if rows else "ABSTAIN",
            "supported_node_count": len(rows),
            "supported_episode_count": episode_count,
            "episode_balanced_fixed_bin_calibration_gap": gap if rows else None,
            "bins": bins,
        }

    payload = {
        "schema_version": "EXP2A_TAIL_AWARE_CALIBRATION_ARTIFACT_V1",
        "status": "EXP2A_TAIL_AWARE_CALIBRATION_MATERIALIZED",
        "scope": source["scope"],
        "principal_event": source["principal_event"],
        "threshold_minutes": source["threshold_minutes"],
        "calibration_contract": "EPISODE_BALANCED_FIXED_EQUAL_WIDTH_TEN_BIN",
        "bin_edges": BIN_EDGES,
        "development_bin_tuning": False,
        "variants": variants,
        "source_brier_artifact_hash": source["artifact_hash"],
        "source_scenario_artifact_hash": source["source_scenario_artifact_hash"],
        "source_label_artifact_hash": source["source_label_artifact_hash"],
        "abstention_policy": source["abstention_policy"],
        "zero_fill": False,
        "synthetic_metrics": False,
        "safety": SAFETY,
    }
    payload["artifact_hash"] = content_id(payload)
    artifact_path = output_root / "EXP2A_TAIL_AWARE_CALIBRATION.json"
    _write(artifact_path, payload)
    manifest = {
        "schema_version": "EXP2A_TAIL_AWARE_CALIBRATION_MANIFEST_V1",
        "status": payload["status"],
        "artifact": str(artifact_path.resolve()),
        "artifact_hash": payload["artifact_hash"],
        "source_brier_artifact_hash": source["artifact_hash"],
        "variant_metrics": {
            variant: {
                "support_status": record["support_status"],
                "supported_node_count": record["supported_node_count"],
                "supported_episode_count": record["supported_episode_count"],
                "episode_balanced_fixed_bin_calibration_gap": record["episode_balanced_fixed_bin_calibration_gap"],
            }
            for variant, record in variants.items()
        },
        "safety": SAFETY,
    }
    manifest_path = output_root / "EXP2A_TAIL_AWARE_CALIBRATION_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"artifact": artifact_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    materialize(root=Path(__file__).resolve().parents[2], output_root=args.output_root)
    print("EXP2A_TAIL_AWARE_CALIBRATION_MATERIALIZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
