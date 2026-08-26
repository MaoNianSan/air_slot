"""Exp2 Development evidence closure — Exp2A variogram records (DEVELOPMENT_ONLY).

Implements the Exp2A item of the Development closure execution order
(``docs/experiment/DEVELOPMENT_CLOSURE_EXECUTION_20260825.md`` §2): the Point
variogram records are materialized from the same frozen Joint scenario
artifact.  The Point rule follows freeze F1 (2026-08-25): the weighted joint
scenario medoid uses only the manuscript primitive coordinates
(R_IB, D_OB, D_TX); R_IB is read from the frozen scenario target T_IB_A00;
D_TO is a derived identity check only and never enters the distance.  Nodes
whose medoid does not form a finite paired term ABSTAIN for the Point
contrast and are reported separately as Point coverage.

Freeze F2 (2026-08-25): the partial-q dependency-disruption series is NOT
implemented (the manuscript defines no partial-q); there is no q entry point
in this module.  See ``docs/HUMAN_DECISION_LOG.md`` and
``codex_framework/AIR_SLOT_EXP23_G2_FREEZE_DECISIONS_20260825.md``.

All outputs carry DEVELOPMENT_ONLY / paper_result=false /
FINAL_TEST_ACCESS_COUNT=0.  No model training, no Final Test access, no
modification of frozen artifacts, registries, configs, or the baseline audit
document.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from exp.common.official_execution import file_sha256, load_json, write_json
from exp.exp2.global_development import _scenario_rows
from exp.exp2.tail_scores import Q_MAX_MINUTES

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path("artifacts/experiment/exp2/exp2a_point_variogram_closure_20260825")
SCENARIOS = Path(
    "artifacts/experiments/exp2/full_development_scenarios_v1/"
    "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIOS.parquet"
)
SCENARIO_MANIFEST = Path(
    "artifacts/experiments/exp2/full_development_scenarios_v1/"
    "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIO_MANIFEST.json"
)
LABELS = Path(
    "artifacts/experiment/full_development_inputs_v1/"
    "M1_V2_FULL_DEVELOPMENT_LABELS.json"
)
GLOBAL_SEED = 20260825
BOOTSTRAP_REPLICATES = 2000
PRIMITIVE_FIELDS = ("R_IB", "D_OB", "D_TX")
REPRESENTATION_ORDER = ("POINT", "MARGINAL", "JOINT")
REPRESENTATION_LABELS = {
    "POINT": "Point",
    "MARGINAL": "Marginal",
    "JOINT": "Joint",
}
SAFETY = {
    "M1_TRAINING_RUNS": 0,
    "TUNING_RUNS": 0,
    "EXP2_RUNS": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "FULL": False,
    "paper_result": False,
}
SCHEMA_VERSION = "AIR_SLOT_EXP2_DEVELOPMENT_CLOSURE_V1"


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _envelope_scalar(row: Mapping[str, Any], target: str) -> float | None:
    env = next(item for item in row["target_envelopes"] if item["target_name"] == target)
    return None if env.get("scalar_minutes") is None else float(env["scalar_minutes"])


def _episode_bootstrap(
    values: Iterable[float], *, replicates: int = BOOTSTRAP_REPLICATES, seed: int = GLOBAL_SEED,
) -> dict[str, float | int]:
    """Episode-cluster estimate and percentile 95% CI (unified statistical layer)."""
    array = np.asarray(list(values), dtype=float)
    array = array[np.isfinite(array)]
    if not len(array):
        raise ValueError("EXP2_CLOSURE_NO_FINITE_EPISODE_VALUES")
    generator = np.random.default_rng(seed)
    indices = generator.integers(0, len(array), size=(replicates, len(array)))
    bootstrap_means = array[indices].mean(axis=1)
    return {
        "estimate": float(array.mean()),
        "ci_lower": float(np.quantile(bootstrap_means, 0.025)),
        "ci_upper": float(np.quantile(bootstrap_means, 0.975)),
        "n_episodes": int(len(array)),
    }


# --------------------------------------------------------------------------
# Shared variogram helpers (single source of truth for Figure 6A; the
# reporting module re-exports these names).
# --------------------------------------------------------------------------


def _variogram_score(
    draws: np.ndarray, observation: tuple[float, float], *, p: float = 0.5
) -> float | None:
    if not len(draws):
        return None
    observed_distance = abs(observation[0] - observation[1]) ** p
    expected_distance = np.mean(np.abs(draws[:, 0] - draws[:, 1]) ** p)
    return float((expected_distance - observed_distance) ** 2)


def _point_medoid_index(frame: pd.DataFrame) -> int:
    """Closed-form weighted-L2 medoid over (R_IB, D_OB, D_TX); matches the
    freeze-F1 ``exp/exp2/representation.ScenarioRepresentationAdapter`` rule
    (argmin of the weighted squared primitive distance over candidate rows,
    ties broken by row order).  D_TO never enters the distance."""
    ordered = frame.sort_values("scenario_id", kind="stable").reset_index(drop=True)
    weights = ordered["scenario_weight"].to_numpy(dtype=float)
    values = ordered[list(PRIMITIVE_FIELDS)].to_numpy(dtype=float)
    usable_columns = np.isfinite(values).any(axis=0)
    if not usable_columns.any():
        raise RuntimeError("EXP2_POINT_NO_COMPLETE_PRIMITIVE_CANDIDATE")
    complete = np.isfinite(values[:, usable_columns]).all(axis=1)
    distances = np.zeros(len(ordered), dtype=float)
    for column in np.where(usable_columns)[0]:
        source = values[:, column]
        available = np.isfinite(source)
        source_values = source[available]
        source_weights = weights[available]
        weight_sum = source_weights.sum()
        first_moment = np.dot(source_weights, source_values)
        second_moment = np.dot(source_weights, source_values * source_values)
        distances[complete] += (
            second_moment
            - 2.0 * source[complete] * first_moment
            + (source[complete] ** 2) * weight_sum
        )
    distances[~complete] = np.inf
    if not complete.any():
        raise RuntimeError("EXP2_POINT_NO_COMPLETE_PRIMITIVE_CANDIDATE")
    return int(np.argmin(distances))


def _representation_draws(frame: pd.DataFrame, representation: str) -> np.ndarray:
    ordered = frame.sort_values("scenario_id", kind="stable").reset_index(drop=True)
    if "R_IB" not in ordered.columns:
        ordered = ordered.rename(columns={"T_IB_A00": "R_IB"})
    values = ordered[list(PRIMITIVE_FIELDS)].to_numpy(dtype=float)
    if representation == "JOINT":
        output = values
    elif representation == "MARGINAL":
        # Freeze F1: independent deterministic permutation of the three
        # primitives with field-name offsets (D_OB shift 0, D_TX shift 1,
        # R_IB shift 2; matches exp/exp2/representation.py); equal weights
        # only.  The variogram itself is scored on (D_OB, D_TX) pairs, the
        # same pair convention as the materialized POINT records.
        output = values.copy()
        offsets = {"R_IB": 2, "D_OB": 0, "D_TX": 1}
        for column, field in enumerate(PRIMITIVE_FIELDS):
            output[:, column] = np.roll(values[:, column], -offsets[field])
    elif representation == "POINT":
        output = values[[_point_medoid_index(ordered)]]
    else:
        raise ValueError(f"Unknown representation: {representation}")
    return output[:, 1:3][np.isfinite(output[:, 1:3]).all(axis=1)]


def exp2_variogram_episode_values(root: Path) -> pd.DataFrame:
    """Recompute Exp2 variograms separately for Point, Marginal, and Joint.

    Each representation is formed from the frozen scenario rows before its
    node-level score is calculated; the Point representation uses the
    freeze-F1 weighted medoid over (R_IB, D_OB, D_TX).  The authoritative
    Point record set is written by :func:`materialize_point_records`; this
    helper is the in-memory recompute used by the reporting module and is
    kept identical to it.
    """
    labels_payload = load_json(root / LABELS)
    label_frame = pd.DataFrame(labels_payload["labels"])
    labels = label_frame[
        label_frame["target_name"].isin(("D_OB", "D_TX"))
        & label_frame["active"].astype(bool)
        & label_frame["exact_minutes"].notna()
    ]
    label_pivot = labels.pivot_table(
        index=["episode_id", "decision_node_id"],
        columns="target_name",
        values="exact_minutes",
        aggfunc="first",
    )
    scenario_frame = pd.read_parquet(
        root / SCENARIOS,
        columns=[
            "episode_id", "decision_node_id", "scenario_id", "scenario_weight",
            "T_IB_A00", "D_OB", "D_TX",
        ],
    )
    rows: list[dict[str, object]] = []
    for (episode_id, node_id), node_frame in scenario_frame.groupby(
        ["episode_id", "decision_node_id"], sort=False
    ):
        try:
            observed = label_pivot.loc[(episode_id, node_id)]
        except KeyError:
            continue
        if "D_OB" not in observed or "D_TX" not in observed:
            continue
        observation = (float(observed["D_OB"]), float(observed["D_TX"]))
        if observation[0] >= Q_MAX_MINUTES["D_OB"] or observation[1] >= Q_MAX_MINUTES["D_TX"]:
            continue
        for representation in REPRESENTATION_ORDER:
            score = _variogram_score(_representation_draws(node_frame, representation), observation)
            if score is not None:
                rows.append(
                    {
                        "episode_id": episode_id,
                        "decision_node_id": node_id,
                        "representation": REPRESENTATION_LABELS[representation],
                        "variogram_score": score,
                    }
                )
    node_values = pd.DataFrame(rows)
    if node_values.empty:
        raise ValueError("EXP2_CLOSURE_NO_FINITE_VARIOGRAM_SCORES")
    return (
        node_values.groupby(["episode_id", "representation"], as_index=False)["variogram_score"]
        .mean()
        .sort_values(["representation", "episode_id"], kind="stable")
    )


def exp2_variogram_summaries(episode_values: pd.DataFrame, replicates: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows: list[dict[str, object]] = []
    by_representation = {
        name: group.set_index("episode_id")["variogram_score"]
        for name, group in episode_values.groupby("representation", sort=False)
    }
    available_order = [
        REPRESENTATION_LABELS[item]
        for item in REPRESENTATION_ORDER
        if REPRESENTATION_LABELS[item] in by_representation
    ]
    if "Joint" not in by_representation:
        raise ValueError("EXP2_CLOSURE_JOINT_VARIOGRAM_MISSING")
    for representation in available_order:
        estimate = _episode_bootstrap(by_representation[representation].to_numpy(), replicates=replicates)
        summary_rows.append(
            {
                "representation": representation,
                "variogram_score": estimate["estimate"],
                "ci_lower": estimate["ci_lower"],
                "ci_upper": estimate["ci_upper"],
                "episodes": estimate["n_episodes"],
            }
        )
    contrast_rows: list[dict[str, object]] = []
    reference = by_representation["Joint"]
    for representation in available_order:
        if representation == "Joint":
            continue
        paired = pd.concat([by_representation[representation], reference], axis=1, join="inner")
        paired.columns = ["comparison", "joint"]
        difference = paired["comparison"] - paired["joint"]
        estimate = _episode_bootstrap(difference.to_numpy(), replicates=replicates)
        contrast_rows.append(
            {
                "contrast": f"{representation} minus Joint",
                "difference_in_variogram_score": estimate["estimate"],
                "ci_lower": estimate["ci_lower"],
                "ci_upper": estimate["ci_upper"],
                "paired_episodes": estimate["n_episodes"],
            }
        )
    return pd.DataFrame(summary_rows), pd.DataFrame(contrast_rows)


def materialize_point_records(*, root: Path, output_root: Path) -> pd.DataFrame:
    """Materialize Exp2A Point variogram records (freeze-F1 medoid rule)."""
    scenario_manifest = load_json(root / SCENARIO_MANIFEST)
    labels_payload = load_json(root / LABELS)
    _require(
        file_sha256(root / SCENARIOS) == scenario_manifest["artifact_hash"],
        "EXP2_CLOSURE_SCENARIO_HASH_MISMATCH",
    )
    label_frame = pd.DataFrame(labels_payload["labels"])
    observed_rows = label_frame[
        label_frame["target_name"].isin(("D_OB", "D_TX"))
        & label_frame["active"].astype(bool)
    ]
    observed_pivot = observed_rows.pivot_table(
        index=["episode_id", "decision_node_id"],
        columns="target_name",
        values="exact_minutes",
        aggfunc="first",
    )
    parquet = pq.ParquetFile(root / SCENARIOS)
    _require(
        parquet.num_row_groups == scenario_manifest["node_count"],
        "EXP2_CLOSURE_ROW_GROUP_CARDINALITY_INVALID",
    )
    records: list[dict[str, Any]] = []
    for node_index in range(parquet.num_row_groups):
        source_rows = _scenario_rows(parquet.read_row_group(node_index))
        episode_id = source_rows[0]["episode_id"]
        node_id = source_rows[0]["decision_node_id"]
        if (episode_id, node_id) in observed_pivot.index:
            observed = observed_pivot.loc[(episode_id, node_id)]
            ob_value = observed["D_OB"] if "D_OB" in observed else None
            tx_value = observed["D_TX"] if "D_TX" in observed else None
        else:
            ob_value = None
            tx_value = None
        point_ob = None
        point_tx = None
        medoid_index = None
        score = None
        if (
            ob_value is None or tx_value is None
            or pd.isna(ob_value) or pd.isna(tx_value)
        ):
            status = "ABSTAIN_NO_FINITE_OBSERVED_PAIR"
        elif float(ob_value) >= Q_MAX_MINUTES["D_OB"] or float(tx_value) >= Q_MAX_MINUTES["D_TX"]:
            status = "EXCLUDED_OBSERVED_BEYOND_Q_MAX"
        else:
            frame = pd.DataFrame([
                {
                    "scenario_id": int(row["scenario_id"]),
                    "scenario_weight": float(row["scenario_weight"]),
                    "R_IB": row["T_IB_A00"],
                    "D_OB": row["D_OB"],
                    "D_TX": row["D_TX"],
                }
                for row in source_rows
            ])
            medoid_index = _point_medoid_index(frame)
            medoid = source_rows[medoid_index]
            point_ob = _envelope_scalar(medoid, "D_OB")
            point_tx = _envelope_scalar(medoid, "D_TX")
            if point_ob is None or point_tx is None:
                status = "ABSTAIN_MEDOID_NONFINITE_PAIR"
            else:
                status = "SUPPORTED"
                score = _variogram_score(
                    np.asarray([[point_ob, point_tx]], dtype=float),
                    (float(ob_value), float(tx_value)),
                )
        records.append(
            {
                "episode_id": episode_id,
                "decision_node_id": node_id,
                "operational_stage": source_rows[0]["operational_stage"],
                "representation": "Point",
                "medoid_scenario_id": None if medoid_index is None else int(source_rows[medoid_index]["scenario_id"]),
                "point_ob_minutes": point_ob,
                "point_tx_minutes": point_tx,
                "observed_ob_minutes": None if ob_value is None else float(ob_value),
                "observed_tx_minutes": None if tx_value is None else float(tx_value),
                "variogram_score": score,
                "support_status": status,
            }
        )
    frame = pd.DataFrame(records)
    _require(len(frame) == scenario_manifest["node_count"], "EXP2_CLOSURE_POINT_RECORD_CARDINALITY_INVALID")
    output_root.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_root / "EXP2A_POINT_VARIOGRAM_RECORDS_DEVELOPMENT_ONLY.csv", index=False)
    frame.to_parquet(output_root / "EXP2A_POINT_VARIOGRAM_RECORDS_DEVELOPMENT_ONLY.parquet", index=False)
    return frame


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exp2A Point variogram closure (DEVELOPMENT_ONLY)")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = ROOT
    output_root = (args.output_root or ROOT / DEFAULT_OUTPUT).resolve()
    records = materialize_point_records(root=root, output_root=output_root)
    episode_values = exp2_variogram_episode_values(root)
    summary, contrast = exp2_variogram_summaries(episode_values, replicates=BOOTSTRAP_REPLICATES)
    summary.to_csv(output_root / "EXP2A_VARIOGRAM_SUMMARIES_DEVELOPMENT_ONLY.csv", index=False)
    contrast.to_csv(output_root / "EXP2A_VARIOGRAM_CONTRASTS_DEVELOPMENT_ONLY.csv", index=False)
    supported = records[records["support_status"] == "SUPPORTED"]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "scope": "DATA2_FULL_DEVELOPMENT_NO_FINAL_TEST",
        "freeze_refs": {
            "F1": "PRIMITIVE_MEDOID_COORDINATES_R_IB_D_OB_D_TX_D_TO_IDENTITY_ONLY",
            "F2": "PARTIAL_Q_SERIES_NOT_IMPLEMENTED",
        },
        "source_artifact": str(SCENARIOS).replace("\\", "/"),
        "source_artifact_hash": file_sha256(root / SCENARIOS),
        "scenario_manifest_hash": load_json(root / SCENARIO_MANIFEST)["manifest_hash"],
        "node_count": len(records),
        "point_supported_nodes": int(len(supported)),
        "point_abstain_nodes": int(len(records) - len(supported)),
        "episode_bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_seed": GLOBAL_SEED,
        "summary_rows": summary.to_dict(orient="records"),
        "contrast_rows": contrast.to_dict(orient="records"),
        "outputs": [
            "EXP2A_POINT_VARIOGRAM_RECORDS_DEVELOPMENT_ONLY.csv",
            "EXP2A_POINT_VARIOGRAM_RECORDS_DEVELOPMENT_ONLY.parquet",
            "EXP2A_VARIOGRAM_SUMMARIES_DEVELOPMENT_ONLY.csv",
            "EXP2A_VARIOGRAM_CONTRASTS_DEVELOPMENT_ONLY.csv",
        ],
        "safety": SAFETY,
    }
    write_json(output_root / "EXP2A_POINT_VARIOGRAM_MANIFEST.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
