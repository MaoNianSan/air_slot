"""Materialize the Train-only empirical positive-tail continuation.

This script reads the frozen Development FAST cache only.  It never opens
Calibration, Development, Final Test, or raw Data1/Data2 inputs and never
changes the M1 checkpoint.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from model.common.identity import content_id
from model.common.paths import PROJECT_ROOT
from model.M1.tail import EmpiricalTailContinuation


CACHE = PROJECT_ROOT / "artifacts/models/m1/M1_FROZEN_H8/DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3.npz"
CACHE_MANIFEST = PROJECT_ROOT / "artifacts/models/m1/M1_FROZEN_H8/DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3_MANIFEST.json"
OUTPUT = PROJECT_ROOT / "artifacts/diagnostics/m1_positive_tail_continuation_v1"


def _hash_file(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def materialize(output: Path = OUTPUT) -> dict:
    source_hashes = {
        "cache": _hash_file(CACHE),
        "cache_manifest": _hash_file(CACHE_MANIFEST),
    }
    cache = np.load(CACHE, allow_pickle=False)
    splits = cache["sample_splits"]
    output.mkdir(parents=True, exist_ok=True)
    continuations = {}
    target_paths = {}
    for target in ("D_OB", "D_TX"):
        mask = (
            (splits == "train")
            & cache[f"active_{target}"]
            & (cache[f"labels_{target}"] > 0)
        )
        positive = cache[f"labels_{target}"][mask].astype(float)
        continuation = EmpiricalTailContinuation.from_exceedances(
            target=target,
            positive_values=positive,
            fit_start="2019-01-01",
            fit_end="2019-06-30",
            source_hashes=source_hashes,
        )
        continuations[target] = continuation
        target_path = output / f"M1_{target}_TRAIN_EMPIRICAL_TAIL.json"
        _write(target_path, continuation.to_payload())
        target_paths[target] = str(target_path.relative_to(PROJECT_ROOT))

    manifest_base = {
        "schema_version": "M1_EMPIRICAL_POSITIVE_TAIL_CONTINUATION_MANIFEST_V1",
        "artifact_id": "M1_POSITIVE_TAIL_CONTINUATION_V1",
        "method": "TRAIN_EMPIRICAL_EXCEEDANCE_CONTINUATION",
        "evidence_class": "EMPIRICAL_TRAIN_REFERENCE",
        "fit_partition": "train",
        "fit_start": "2019-01-01",
        "fit_end": "2019-06-30",
        "targets": {name: item.to_payload() for name, item in continuations.items()},
        "target_paths": target_paths,
        "source_hashes": source_hashes,
        "minimum_tail_observations": 30,
        "parametric_tail": False,
        "continuous_parametric_extrapolation": False,
        "final_test_access_count": 0,
        "model_retrained": False,
        "parameter_reselected": False,
        "experiment_created": False,
        "data1_modified": False,
        "data2_modified": False,
    }
    manifest = dict(manifest_base)
    manifest["artifact_hash"] = content_id(manifest_base)
    manifest_path = output / "M1_POSITIVE_TAIL_CONTINUATION_V1.json"
    _write(manifest_path, manifest)
    return {
        "manifest": str(manifest_path),
        "artifact_hash": manifest["artifact_hash"],
        "targets": {
            name: item.to_payload() for name, item in continuations.items()
        },
        "final_test_access_count": 0,
        "model_retrained": False,
        "parameter_reselected": False,
        "experiment_created": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(materialize(args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
