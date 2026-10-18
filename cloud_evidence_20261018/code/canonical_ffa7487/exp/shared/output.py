"""Development output provenance and explicitly completed uncertainty counts."""

import json
from hashlib import sha256
from pathlib import Path
import numpy as np
import pandas as pd
from exp.shared.resampling import interval

ROOT = Path(__file__).resolve().parents[2]
GUARDS = {"final_test_access_count": 0, "paper_result": False,
          "model_retrained": False, "calibration_refit": False, "parameter_reselected": False}


def digest(path):
    return "sha256:" + sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, payload):
    def clean(x):
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [clean(v) for v in x]
        if isinstance(x, (np.integer, np.floating)):
            x = x.item()
        if isinstance(x, float) and not np.isfinite(x):
            return None
        return x
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+".tmp")
    temp.write_text(json.dumps(clean(payload), indent=2, allow_nan=False, default=str)+"\n", encoding="utf-8")
    temp.replace(path)


def with_intervals(estimates, replicates, keys, metrics=None):
    out = estimates.copy()
    if metrics is None:
        metrics = [c for c in estimates.select_dtypes(include="number")
                   if c not in keys and c not in ("replicate", "n", "k", "n_nodes", "n_episodes")]
    for idx, row in estimates.iterrows():
        sample = replicates
        for key in keys:
            sample = sample[sample[key].eq(row[key])]
        for metric in metrics:
            if metric not in sample:
                continue
            low, high = interval(sample[metric])
            out.loc[idx, f"{metric}_ci_low"] = low
            out.loc[idx, f"{metric}_ci_high"] = high
    return out


def manifest(output, experiment, mode, input_path, required, completed, **extra):
    files = {p.name: digest(p) for p in output.iterdir() if p.is_file() and "MANIFEST" not in p.name}
    payload = {"experiment_id": experiment, "mode": mode,
               "status": "DEVELOPMENT_COMPLETE" if completed == required and mode == "development" else "NON_PAPER_FAST_DIAGNOSTIC",
               "bootstrap_replicates_required": required, "bootstrap_replicates_completed": completed,
               "bootstrap_seed": 20260906, "cluster": "original_episode_id",
               "input_path": str(input_path), "input_hash": digest(input_path),
               "outputs": files, **GUARDS, **extra}
    write_json(output / f"{experiment}_OUTPUT_MANIFEST.json", payload)
    return payload
