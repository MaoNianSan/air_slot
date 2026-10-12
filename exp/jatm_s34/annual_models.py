"""Build versioned annual M1 runtime artifacts for Development only.

The two model roles are trained from the same annual Train/Calibration
partitions but keep their frozen roles: FULL_ADAPTIVE_CAUSAL_PREFIX is the
history primary and NO_HISTORY_CURRENT_OBSERVATION is the current comparator.
This is separate from the M5-b cohort-size battery; N=128 pilot checkpoints
are never reused here as a scientific model.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import torch

from data2.scripts.consequence_stability_battery import (
    active_rows,
    build_training_examples,
    fit_static_normalization_from_rows,
    fit_train_normalization,
    load_hash_cohort,
    normalization_rows,
    prefix_partitions,
    year_references,
)
from model.PRE.cohort import split_for_date_multiyear
from model.M1.data import FEATURE_NAMES_V2
from model.M1.lifecycle import M1Lifecycle
from model.M1.pipeline import M1Pipeline
from model.M1.history import HistoryEncoderMode
from model.M1.static_features import STATIC_FEATURE_COUNT
from model.common.config import load_config_layers
from model.common.paths import PROJECT_ROOT
from model.PRE.development import materialize_preselected_cohorts


MODEL_ROOT = PROJECT_ROOT / "artifacts" / "models" / "m1"
TRAIN_SEED = 20260813


def _hash(path: Path) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def build_annual_models(*, year: int, n: int = 4096, output_root: Path | None = None) -> dict:
    """Train both annual M1 roles on the approved hash-ranked Train prefix.

    Development rows are materialized only for input construction; no model
    parameters are selected from Development and no Test rows are loaded.
    """
    year = int(year)
    output_root = Path(output_root or (MODEL_ROOT / f"YEAR_{year}")).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    scientific = load_config_layers(PROJECT_ROOT / "configs").scientific
    selected = load_hash_cohort(year)
    partitions = prefix_partitions(selected, int(n))
    taxi, turnaround = year_references(year)
    cohorts = materialize_preselected_cohorts(
        scientific,
        root=PROJECT_ROOT,
        partitions=partitions,
        year=year,
        dataset_instance_id="data2_2017_2022",
        split_resolver=split_for_date_multiyear,
        taxi_reference=taxi,
        turnaround_reference=turnaround,
    )
    rows = {}
    for split in ("train", "calibration", "development"):
        rows[split], _ = active_rows(getattr(cohorts, split), taxi_reference=taxi)
    normalization = fit_train_normalization(
        normalization_rows([prefix for _ep, prefix, _lbl in rows["train"]]), split="train"
    )
    static_normalization = fit_static_normalization_from_rows(rows["train"])
    examples = {
        split: build_training_examples(
            rows[split], normalization, None, static_normalization=static_normalization
        )
        for split in rows
    }
    hidden_size = int(scientific.parameters["m1_hidden_size"].value)
    results = {}
    for role, mode in (
        ("M1_HISTORY_PRIMARY", HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX),
        ("M1_CURRENT_COMPARATOR", HistoryEncoderMode.NO_HISTORY_CURRENT_OBSERVATION),
    ):
        checkpoint = output_root / ("M1_HISTORY_PRIMARY.pt" if "HISTORY" in role else "M1_CURRENT_COMPARATOR.pt")
        torch.manual_seed(TRAIN_SEED)
        pipeline = M1Pipeline.from_scientific_config(
            scientific,
            input_size=len(FEATURE_NAMES_V2),
            normalization=normalization,
            hidden_size=hidden_size,
            static_input_size=STATIC_FEATURE_COUNT,
            static_normalization=static_normalization,
            history_mode=mode,
        )
        lifecycle = M1Lifecycle(pipeline, device="cpu")
        lifecycle.train(
            examples["train"], epochs=8, learning_rate=0.001, batch_size=64,
            bucketed=True, seed=TRAIN_SEED, teacher_forcing=True,
        )
        lifecycle.calibrate(examples["calibration"], batch_size=64)
        lifecycle.save(checkpoint)
        record = {
            "schema_version": "JATM_ANNUAL_M1_RUNTIME_V1",
            "year": year,
            "n": int(n),
            "role": role,
            "history_mode": mode.value,
            "checkpoint": str(checkpoint),
            "checkpoint_hash": _hash(checkpoint),
            "train_episode_count": len(partitions["train"]),
            "calibration_episode_count": len(partitions["calibration"]),
            "development_node_count": len(rows["development"]),
            "train_examples": len(examples["train"]),
            "calibration_examples": len(examples["calibration"]),
            "source": "data2.reports.cohort_size_stability.HASH_SELECTED_COHORT_RECORDS_N4096",
            "scientific_model_n": int(n),
            "m5b_n128_pilot_reused": False,
            "final_test_access_count": 0,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        manifest = checkpoint.with_name(checkpoint.stem + "_MANIFEST.json")
        manifest.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        results[role] = record | {"manifest": str(manifest), "manifest_hash": _hash(manifest)}
    return {"year": year, "n": int(n), "models": results, "final_test_access_count": 0}


__all__ = ["build_annual_models"]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--n", type=int, default=4096)
    args = parser.parse_args()
    print(json.dumps(build_annual_models(year=args.year, n=args.n), sort_keys=True, default=str))
