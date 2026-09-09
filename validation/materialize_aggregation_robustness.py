"""Materialize Final Test consequence-aggregation robustness diagnostics.

This is a reporting-only lane. It reads the frozen Exp2A node records, checks
the existing Exp4 view definitions, and recomputes ranks and pair gaps for
each aggregation view under the frozen episode bootstrap plan.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

try:
    from numba import njit
except ImportError:  # pragma: no cover - fallback is covered by the Python path
    njit = None

# Allow both ``python -m validation...`` and direct script execution.
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from exp.exp2.metrics import midrank_percentiles, priority_metrics
from exp.exp2.protocol import (
    ACTIVE_STAGES,
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_SEED,
    COMPONENTS,
    MATERIAL_RANK_GAP,
    SIMILAR_DELAY_PRIMARY,
    TOP_FRACTION_PRIMARY,
)
from exp.shared.resampling import bootstrap_plan, episode_ids, expand_draw
from exp.exp4.triage import _views as canonical_views


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "artifacts" / "experiment" / "final_test" / "exp2" / "data" / "EXP2A_NODE_RECORDS.parquet"
DEFAULT_CANONICAL = ROOT / "artifacts" / "experiment" / "final_test" / "exp4" / "EXP4_CANONICAL_EVENTS.parquet"
DEFAULT_OUTPUT = ROOT / "artifacts" / "paper_results_v2_final_test" / "aggregation_robustness"
EXPECTED_QUALIFYING_NODE_PAIRS = 726455
EXPECTED_UNIQUE_EPISODE_PAIRS = 7045

VIEW_ORDER = (
    "BASE_EQUAL_DOMAIN",
    "EQUAL_COMPONENT",
    "NO_F_EXEC",
    "FLIGHT_EMPHASIS",
    "PASSENGER_EMPHASIS",
    "OPERATING_EMPHASIS",
)

OVERALL_METRICS = (
    "kendall_tau_b",
    "spearman_rho",
    "top_decile_overlap",
    "median_abs_rank_displacement",
    "p90_abs_rank_displacement",
    "share_abs_rank_displacement_ge_030",
)
SIMILAR_METRICS = (
    "median_abs_priority_separation",
    "share_priority_separation_ge_030",
)
STAGE_METRICS = (
    "kendall_tau_b",
    "median_abs_rank_displacement",
    "top_decile_overlap",
)

BASELINE_EXPECTED = {
    "kendall_tau_b": 0.736488790649004,
    "top_decile_overlap": 0.7289156626506024,
    "median_abs_rank_displacement": 0.06974637681159424,
}
BASELINE_SIMILAR_EXPECTED = {
    "median_abs_priority_separation": 0.20410628019323673,
    "share_priority_separation_ge_030": 0.33782824698367636,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise RuntimeError(reason)


def _finite_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "episode_id",
        "original_episode_id",
        "decision_node_id",
        "technical_node_id",
        "operational_stage",
        "delay_to_mean",
        "score_C",
        "score_F",
        "score_P",
        "score_R",
        "final_test_access_count",
        "support_primary",
        "conditional_aggregate_complete",
        *(f"Z_{component}" for component in COMPONENTS),
    }
    _require(required <= set(frame.columns), "AGGREGATION_SOURCE_COLUMNS_MISSING")
    active = frame[frame.operational_stage.isin(ACTIVE_STAGES)].copy()
    _require(len(active) == 1656, "AGGREGATION_FINAL_TEST_NODE_COUNT_MISMATCH")
    _require(active.original_episode_id.nunique() == 128, "AGGREGATION_FINAL_TEST_EPISODE_COUNT_MISMATCH")
    _require(active.final_test_access_count.astype(int).eq(1).all(), "AGGREGATION_FINAL_TEST_ACCESS_COUNT_MISMATCH")
    _require(active.support_primary.eq(True).all(), "AGGREGATION_PRIMARY_SUPPORT_MISMATCH")
    _require(active.conditional_aggregate_complete.eq(True).all(), "AGGREGATION_COMPLETE_SUPPORT_MISMATCH")
    _require(active.technical_node_id.astype(str).is_unique, "AGGREGATION_TECHNICAL_NODE_ID_COLLISION")
    numeric = ["delay_to_mean", "score_C", "score_F", "score_P", "score_R", *(f"Z_{c}" for c in COMPONENTS)]
    _require(np.isfinite(active[numeric].to_numpy(float)).all(), "AGGREGATION_NONFINITE_FROZEN_INPUT")
    _require(np.isclose(active.score_C, (active.score_F + active.score_P + active.score_R) / 3.0, atol=1e-12).all(), "AGGREGATION_BASE_SCORE_MISMATCH")
    return active.reset_index(drop=True)


def compute_view_scores(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    components = frame[[f"Z_{component}" for component in COMPONENTS]].to_numpy(float)
    flight = components[:, :3].mean(axis=1)
    passenger = components[:, 3:6].mean(axis=1)
    operating = components[:, 6]
    equal_component = components.mean(axis=1)
    no_f_exec = (components[:, [0, 2]].mean(axis=1) + passenger + operating) / 3.0
    return {
        "BASE_EQUAL_DOMAIN": (flight + passenger + operating) / 3.0,
        "EQUAL_COMPONENT": equal_component,
        "NO_F_EXEC": no_f_exec,
        "FLIGHT_EMPHASIS": 0.50 * flight + 0.25 * passenger + 0.25 * operating,
        "PASSENGER_EMPHASIS": 0.25 * flight + 0.50 * passenger + 0.25 * operating,
        "OPERATING_EMPHASIS": 0.25 * flight + 0.25 * passenger + 0.50 * operating,
    }


def _definition_payload() -> dict[str, object]:
    return {
        "schema_version": "AIR_SLOT_AGGREGATION_ROBUSTNESS_VIEW_DEFINITIONS_V1",
        "view_order": list(VIEW_ORDER),
        "component_order": list(COMPONENTS),
        "base_view": {
            "id": "BASE_EQUAL_DOMAIN",
            "formula": "(mean(F_continuity,F_execution,F_propagation) + mean(P_time,P_itinerary,P_service) + R_operating) / 3",
            "domain_weights": {"Flight": 1 / 3, "Passenger": 1 / 3, "Operating": 1 / 3},
            "source": "exp.shared.recovery_priority.compute_domain_scores + compute_aggregate_priority",
        },
        "alternative_views": {
            "EQUAL_COMPONENT": {
                "formula": "mean(all seven normalized consequence components)",
                "domain_weights": None,
                "source": "exp.shared.recovery_priority.compute_equal_component_priority",
            },
            "NO_F_EXEC": {
                "formula": "(mean(F_continuity,F_propagation) + mean(P_time,P_itinerary,P_service) + R_operating) / 3",
                "domain_weights": {"Flight": 1 / 3, "Passenger": 1 / 3, "Operating": 1 / 3},
                "source": "exp.shared.recovery_priority.compute_no_f_execution_priority",
            },
            "FLIGHT_EMPHASIS": {
                "formula": "0.50*Flight + 0.25*Passenger + 0.25*Operating",
                "domain_weights": {"Flight": 0.50, "Passenger": 0.25, "Operating": 0.25},
                "source": "exp.exp4.triage._views",
            },
            "PASSENGER_EMPHASIS": {
                "formula": "0.25*Flight + 0.50*Passenger + 0.25*Operating",
                "domain_weights": {"Flight": 0.25, "Passenger": 0.50, "Operating": 0.25},
                "source": "exp.exp4.triage._views",
            },
            "OPERATING_EMPHASIS": {
                "formula": "0.25*Flight + 0.25*Passenger + 0.50*Operating",
                "domain_weights": {"Flight": 0.25, "Passenger": 0.25, "Operating": 0.50},
                "source": "exp.exp4.triage._views",
            },
        },
        "diagnostic_only_views": ["S_F", "S_P", "S_R"],
        "thresholds": {"similar_delay_caliper_minutes": SIMILAR_DELAY_PRIMARY, "material_rank_gap": MATERIAL_RANK_GAP, "top_fraction": TOP_FRACTION_PRIMARY},
        "normalization": "training-frozen normalized consequence component columns Z_*",
    }


def verify_view_definitions(frame: pd.DataFrame, scores: dict[str, np.ndarray], canonical_path: Path) -> dict[str, object]:
    _require(canonical_path.is_file(), "AGGREGATION_CANONICAL_EVENT_ARTIFACT_MISSING")
    canonical = pd.read_parquet(canonical_path)
    required = {"S_F", "S_P", "S_R", "S_C", "NO_F_EXECUTION", "EQUAL_COMPONENT", "decision_node_id", *(f"Z_{c}" for c in COMPONENTS)}
    _require(required <= set(canonical.columns), "AGGREGATION_CANONICAL_VIEW_COLUMNS_MISSING")
    calc = compute_view_scores(canonical)
    triage = canonical_views(canonical)
    expected_names = ("S_F", "S_P", "S_R", "EQUAL_COMPONENT", "NO_F_EXECUTION", "FLIGHT_EMPHASIS", "PASSENGER_EMPHASIS", "OPERATING_EMPHASIS")
    triage_checks = {}
    for index, name in enumerate(expected_names):
        expected = canonical[name].to_numpy(float) if name in canonical else triage[:, index]
        triage_checks[name] = bool(np.isclose(triage[:, index], expected, atol=1e-12, rtol=0).all())
        _require(triage_checks[name], f"AGGREGATION_EXP4_VIEW_MISMATCH:{name}")
    stored_columns = {
        "BASE_EQUAL_DOMAIN": "S_C",
        "EQUAL_COMPONENT": "EQUAL_COMPONENT",
        "NO_F_EXEC": "NO_F_EXECUTION",
    }
    for name, canonical_name in stored_columns.items():
        _require(
            np.isclose(
                calc[name], canonical[canonical_name].to_numpy(float), atol=1e-12, rtol=0
            ).all(),
            f"AGGREGATION_CANONICAL_FORMULA_MISMATCH:{name}",
        )
    triage_emphasis = {
        "FLIGHT_EMPHASIS": triage[:, 5],
        "PASSENGER_EMPHASIS": triage[:, 6],
        "OPERATING_EMPHASIS": triage[:, 7],
    }
    for name, values in triage_emphasis.items():
        _require(
            np.isclose(values, calc[name], atol=1e-12, rtol=0).all(),
            f"AGGREGATION_CANONICAL_FORMULA_MISMATCH:{name}",
        )
    canonical_ids = set(canonical.decision_node_id.astype(str))
    source_ids = set(frame.decision_node_id.astype(str))
    _require(canonical_ids <= source_ids, "AGGREGATION_CANONICAL_SOURCE_NODE_MISMATCH")
    return {"status": "PASS", "canonical_event_count": int(len(canonical)), "supported_canonical_event_count": int(len(canonical)), "view_checks": triage_checks}


def _point_overall(frame: pd.DataFrame, view_scores: dict[str, np.ndarray]) -> dict[str, dict[str, float | int | None]]:
    ids = frame.technical_node_id.astype(str).tolist()
    delay = frame.delay_to_mean.to_numpy(float)
    output = {}
    for view in VIEW_ORDER:
        metrics = priority_metrics(delay.tolist(), view_scores[view].tolist(), ids, top_fraction=TOP_FRACTION_PRIMARY, material_gap=MATERIAL_RANK_GAP)
        output[view] = {
            "kendall_tau_b": metrics["kendall_tau_b"],
            "spearman_rho": metrics["spearman_rho"],
            "top_decile_overlap": metrics["top_overlap"],
            "median_abs_rank_displacement": metrics["median_rank_displacement"],
            "p90_abs_rank_displacement": metrics["p90_rank_displacement"],
            "share_abs_rank_displacement_ge_030": metrics["share_rank_displacement_ge_030"],
            "n_node": int(len(frame)),
            "n_episode": int(frame.original_episode_id.nunique()),
            "support_status": "SUPPORTED",
        }
    return output


def _pair_table(frame: pd.DataFrame, view_scores: dict[str, np.ndarray]) -> pd.DataFrame:
    """Build the fixed eligibility universe once for all views and replicates."""
    node_ids = frame.decision_node_id.astype(str).to_numpy()
    episodes = frame.original_episode_id.astype(str).to_numpy()
    stages = frame.operational_stage.astype(str).to_numpy()
    delays = frame.delay_to_mean.to_numpy(float)
    left_parts: list[np.ndarray] = []
    right_parts: list[np.ndarray] = []
    stage_parts: list[np.ndarray] = []
    for stage in ACTIVE_STAGES:
        stage_indices = np.flatnonzero(stages == stage)
        order = stage_indices[np.lexsort((node_ids[stage_indices], delays[stage_indices]))]
        ordered_delays = delays[order]
        right_limits = np.searchsorted(
            ordered_delays,
            ordered_delays + SIMILAR_DELAY_PRIMARY,
            side="right",
        )
        for position, left in enumerate(order):
            right_positions = np.arange(position + 1, right_limits[position], dtype=int)
            if not len(right_positions):
                continue
            right = order[right_positions]
            right = right[episodes[right] != episodes[left]]
            if not len(right):
                continue
            swap = (episodes[right] < episodes[left]) | (
                (episodes[right] == episodes[left]) & (node_ids[right] < node_ids[left])
            )
            left_values = np.where(swap, right, left)
            right_values = np.where(swap, left, right)
            left_parts.append(left_values.astype(int, copy=False))
            right_parts.append(right_values.astype(int, copy=False))
            stage_parts.append(np.full(len(right_values), stage, dtype=object))
    left_index = np.concatenate(left_parts) if left_parts else np.empty(0, dtype=int)
    right_index = np.concatenate(right_parts) if right_parts else np.empty(0, dtype=int)
    pair_table = pd.DataFrame({
        "pair_id": np.arange(len(left_index), dtype=int),
        "node_index_a": left_index,
        "node_index_b": right_index,
        "node_a": node_ids[left_index],
        "node_b": node_ids[right_index],
        "episode_a": episodes[left_index],
        "episode_b": episodes[right_index],
        "original_episode_a": episodes[left_index],
        "original_episode_b": episodes[right_index],
        "operational_stage": np.concatenate(stage_parts) if stage_parts else np.empty(0, dtype=object),
        "abs_delay_gap": np.abs(delays[left_index] - delays[right_index]),
    })
    for view in VIEW_ORDER:
        ranks = midrank_percentiles(view_scores[view])
        pair_table[f"{view}_gap"] = np.abs(ranks[left_index] - ranks[right_index])
    _require(len(pair_table) == EXPECTED_QUALIFYING_NODE_PAIRS, "AGGREGATION_PAIR_COUNT_MISMATCH")
    return pair_table


def _pair_summary_from_groups(pair_groups, ranks: np.ndarray) -> dict[str, object]:
    episode_pair_medians = [
        float(np.median(np.abs(ranks[left] - ranks[right])))
        for left, right in pair_groups.values()
    ]
    if not episode_pair_medians:
        return {
            "support_status": "ABSTAIN_NO_SIMILAR_DELAY_EPISODE_PAIRS",
            "unique_episode_pairs": 0,
        }
    values = np.asarray(episode_pair_medians, dtype=float)
    return {
        "support_status": "SUPPORTED",
        "unique_episode_pairs": int(len(values)),
        "median_priority_separation": float(np.median(values)),
        "share_priority_separation_ge_030": float(np.mean(values >= MATERIAL_RANK_GAP)),
    }


def _point_similar(frame: pd.DataFrame, view_scores: dict[str, np.ndarray], pair_table: pd.DataFrame, pair_groups) -> dict[str, dict[str, object]]:
    output = {}
    for view in VIEW_ORDER:
        pair_summary = _pair_summary_from_groups(pair_groups, midrank_percentiles(view_scores[view]))
        output[view] = {
            "median_abs_priority_separation": pair_summary.get("median_priority_separation"),
            "share_priority_separation_ge_030": pair_summary.get("share_priority_separation_ge_030"),
            "n_node": int(len(frame)),
            "n_episode": int(frame.original_episode_id.nunique()),
            "n_pair": int(pair_summary.get("unique_episode_pairs", 0)),
            "support_status": pair_summary["support_status"],
        }
    return output


def _point_stage(frame: pd.DataFrame, view_scores: dict[str, np.ndarray]) -> dict[tuple[str, str], dict[str, object]]:
    output = {}
    for view in VIEW_ORDER:
        for stage in ACTIVE_STAGES:
            mask = frame.operational_stage.eq(stage).to_numpy()
            group = frame.loc[mask]
            metrics = priority_metrics(group.delay_to_mean.tolist(), view_scores[view][mask].tolist(), group.technical_node_id.astype(str).tolist(), top_fraction=TOP_FRACTION_PRIMARY, material_gap=MATERIAL_RANK_GAP)
            output[(view, stage)] = {
                "kendall_tau_b": metrics["kendall_tau_b"],
                "median_abs_rank_displacement": metrics["median_rank_displacement"],
                "top_decile_overlap": metrics["top_overlap"],
                "n_node": int(len(group)),
                "n_episode": int(group.original_episode_id.nunique()),
                "support_status": "SUPPORTED" if len(group) >= 2 else "ABSTAIN_INSUFFICIENT_SAMPLE",
            }
    return output


def _expanded_index(frame: pd.DataFrame, draw: Iterable[str]) -> tuple[np.ndarray, np.ndarray]:
    groups = {str(episode): group.index.to_numpy(dtype=int) for episode, group in frame.groupby("original_episode_id", sort=False)}
    indices, occurrences = [], []
    for occurrence, episode in enumerate(draw):
        group = groups.get(str(episode))
        if group is not None:
            indices.append(group)
            occurrences.append(np.full(len(group), occurrence, dtype=int))
    return np.concatenate(indices), np.concatenate(occurrences)


def _pair_groups(pair_frame: pd.DataFrame) -> dict[tuple[str, str], tuple[np.ndarray, np.ndarray]]:
    grouped = {}
    for key, group in pair_frame.groupby(["original_episode_a", "original_episode_b"], sort=True):
        left = group.node_index_a.to_numpy(dtype=int)
        right = group.node_index_b.to_numpy(dtype=int)
        grouped[(str(key[0]), str(key[1]))] = (left, right)
    return grouped


def _pair_kernel(pair_groups, episodes: tuple[str, ...]):
    episode_index = {episode: index for index, episode in enumerate(episodes)}
    starts, ends, episode_a, episode_b = [], [], [], []
    left_parts, right_parts = [], []
    offset = 0
    for (left_episode, right_episode), (left, right) in pair_groups.items():
        starts.append(offset)
        ends.append(offset + len(left))
        episode_a.append(episode_index[left_episode])
        episode_b.append(episode_index[right_episode])
        left_parts.append(left)
        right_parts.append(right)
        offset += len(left)
    return (
        np.concatenate(left_parts).astype(np.int64, copy=False),
        np.concatenate(right_parts).astype(np.int64, copy=False),
        np.asarray(starts, dtype=np.int64),
        np.asarray(ends, dtype=np.int64),
        np.asarray(episode_a, dtype=np.int64),
        np.asarray(episode_b, dtype=np.int64),
        episode_index,
    )


if njit is not None:

    @njit(cache=True)
    def _similar_delay_numba(left, right, starts, ends, episode_a, episode_b, occurrence_ids, occurrence_counts, ranks):
        total = 0
        for group in range(len(starts)):
            total += occurrence_counts[episode_a[group]] * occurrence_counts[episode_b[group]]
        output = np.empty(total, dtype=np.float64)
        cursor = 0
        for group in range(len(starts)):
            start = starts[group]
            end = ends[group]
            length = end - start
            scratch = np.empty(length, dtype=np.float64)
            for index_a in range(occurrence_counts[episode_a[group]]):
                occurrence_a = occurrence_ids[episode_a[group], index_a]
                for index_b in range(occurrence_counts[episode_b[group]]):
                    occurrence_b = occurrence_ids[episode_b[group], index_b]
                    for position in range(length):
                        pair_position = start + position
                        scratch[position] = abs(
                            ranks[occurrence_a, left[pair_position]]
                            - ranks[occurrence_b, right[pair_position]]
                        )
                    output[cursor] = np.median(scratch)
                    cursor += 1
        return output
else:
    _similar_delay_numba = None


def _bootstrap_similar(pair_groups, occurrences_by_episode, rank_by_occurrence) -> dict[str, float | int | None]:
    values = []
    for (episode_a, episode_b), (left, right) in pair_groups.items():
        for occurrence_a in occurrences_by_episode.get(episode_a, ()):
            for occurrence_b in occurrences_by_episode.get(episode_b, ()):
                values.append(float(np.median(np.abs(rank_by_occurrence[occurrence_a, left] - rank_by_occurrence[occurrence_b, right]))))
    if not values:
        return {"median_abs_priority_separation": None, "share_priority_separation_ge_030": None, "n_pair": 0, "support_status": "ABSTAIN_NO_SIMILAR_DELAY_EPISODE_PAIRS"}
    array = np.asarray(values, dtype=float)
    return {"median_abs_priority_separation": float(np.median(array)), "share_priority_separation_ge_030": float(np.mean(array >= MATERIAL_RANK_GAP)), "n_pair": int(len(array)), "support_status": "SUPPORTED"}


def _bootstrap_similar_fast(pair_kernel, draw_indices, rank_by_occurrence) -> dict[str, float | int | None]:
    left, right, starts, ends, episode_a, episode_b, _ = pair_kernel
    occurrence_ids = np.full((int(max(episode_a.max(), episode_b.max()) + 1), len(draw_indices)), -1, dtype=np.int64)
    occurrence_counts = np.zeros(occurrence_ids.shape[0], dtype=np.int64)
    for occurrence, episode in enumerate(draw_indices):
        index = int(episode)
        count = occurrence_counts[index]
        occurrence_ids[index, count] = occurrence
        occurrence_counts[index] = count + 1
    values = _similar_delay_numba(
        left, right, starts, ends, episode_a, episode_b,
        occurrence_ids, occurrence_counts, rank_by_occurrence,
    )
    if not len(values):
        return {
            "median_abs_priority_separation": None,
            "share_priority_separation_ge_030": None,
            "n_pair": 0,
            "support_status": "ABSTAIN_NO_SIMILAR_DELAY_EPISODE_PAIRS",
        }
    return {
        "median_abs_priority_separation": float(np.median(values)),
        "share_priority_separation_ge_030": float(np.mean(values >= MATERIAL_RANK_GAP)),
        "n_pair": int(len(values)),
        "support_status": "SUPPORTED",
    }


def _bootstrap_once(frame: pd.DataFrame, view_scores: dict[str, np.ndarray], draw, pair_kernel, pair_groups, episode_groups, episode_index) -> tuple[dict[str, dict[str, float | None]], dict[str, dict[str, float | int | None]], dict[tuple[str, str], dict[str, float | None]]]:
    row_index, occurrence = _expanded_index(frame, draw)
    _require(len(row_index) > 0, "AGGREGATION_EMPTY_BOOTSTRAP_SAMPLE")
    original_nodes = frame.decision_node_id.astype(str).to_numpy()[row_index]
    technical_ids = [f"{node}#bootstrap-{position:04d}" for node, position in zip(original_nodes, occurrence)]
    delay = frame.delay_to_mean.to_numpy(float)[row_index]
    overall = {}
    similar = {}
    stages = {}
    draw_indices = np.asarray([episode_index[str(episode)] for episode in draw], dtype=np.int64)
    for view in VIEW_ORDER:
        consequence = view_scores[view][row_index]
        metrics = priority_metrics(delay.tolist(), consequence.tolist(), technical_ids, top_fraction=TOP_FRACTION_PRIMARY, material_gap=MATERIAL_RANK_GAP)
        overall[view] = {
            "kendall_tau_b": metrics["kendall_tau_b"],
            "spearman_rho": metrics["spearman_rho"],
            "top_decile_overlap": metrics["top_overlap"],
            "median_abs_rank_displacement": metrics["median_rank_displacement"],
            "p90_abs_rank_displacement": metrics["p90_rank_displacement"],
            "share_abs_rank_displacement_ge_030": metrics["share_rank_displacement_ge_030"],
        }
        ranks = midrank_percentiles(consequence)
        rank_matrix = np.full((len(draw), len(frame)), np.nan, dtype=float)
        offset = 0
        for position, episode in enumerate(draw):
            group = episode_groups[str(episode)]
            rank_matrix[position, group] = ranks[offset:offset + len(group)]
            offset += len(group)
        if _similar_delay_numba is not None:
            similar[view] = _bootstrap_similar_fast(pair_kernel, draw_indices, rank_matrix)
        else:  # pragma: no cover - exercised only without the bundled numba runtime
            occurrences_by_episode = defaultdict(list)
            for position, episode in enumerate(draw):
                occurrences_by_episode[str(episode)].append(position)
            similar[view] = _bootstrap_similar(pair_groups, occurrences_by_episode, rank_matrix)
        for stage in ACTIVE_STAGES:
            stage_mask = frame.operational_stage.to_numpy()[row_index] == stage
            stage_metrics = priority_metrics(delay[stage_mask].tolist(), consequence[stage_mask].tolist(), [technical_ids[i] for i in np.flatnonzero(stage_mask)], top_fraction=TOP_FRACTION_PRIMARY, material_gap=MATERIAL_RANK_GAP)
            stages[(view, stage)] = {
                "kendall_tau_b": stage_metrics["kendall_tau_b"],
                "median_abs_rank_displacement": stage_metrics["median_rank_displacement"],
                "top_decile_overlap": stage_metrics["top_overlap"],
            }
    return overall, similar, stages


def _interval(values: list[object]) -> tuple[float | None, float | None]:
    numeric = np.asarray([value for value in values if value is not None], dtype=float)
    if not len(numeric):
        return None, None
    return float(np.quantile(numeric, 0.025)), float(np.quantile(numeric, 0.975))


def _rows_with_ci(point, bootstrap_values, metrics, *, extra=None):
    rows = []
    extra = extra or {}
    for view in VIEW_ORDER:
        for metric in metrics:
            low, high = _interval([result.get(metric) for result in bootstrap_values[view]])
            rows.append({"aggregation_view": view, "metric": metric, "estimate": point[view].get(metric), "ci_low": low, "ci_high": high, **extra.get(view, {}), "support_status": point[view].get("support_status", "SUPPORTED")})
    return rows


def run(source_path: Path = DEFAULT_SOURCE, canonical_path: Path = DEFAULT_CANONICAL, output_path: Path = DEFAULT_OUTPUT, *, replicates: int = BOOTSTRAP_REPLICATES, seed: int = BOOTSTRAP_SEED) -> dict[str, object]:
    source_hash = _sha256(source_path)
    frame = _finite_frame(pd.read_parquet(source_path))
    view_scores = compute_view_scores(frame)
    definition_check = verify_view_definitions(frame, view_scores, canonical_path)
    _require(np.isclose(view_scores["BASE_EQUAL_DOMAIN"], frame.score_C.to_numpy(float), atol=1e-12, rtol=0).all(), "AGGREGATION_BASE_VIEW_NOT_FROZEN_SCORE_C")
    point_overall = _point_overall(frame, view_scores)
    t0 = time.perf_counter()
    pair_table = _pair_table(frame, view_scores)
    pair_groups = _pair_groups(pair_table)
    _require(len(pair_groups) == EXPECTED_UNIQUE_EPISODE_PAIRS, "AGGREGATION_UNIQUE_EPISODE_PAIR_COUNT_MISMATCH")
    print(f"AGGREGATION timing pair_universe={time.perf_counter() - t0:.3f}s pairs={len(pair_table)} episode_pairs={len(pair_groups)}", flush=True)
    point_similar = _point_similar(frame, view_scores, pair_table, pair_groups)
    point_stage = _point_stage(frame, view_scores)
    baseline_checks = {
        key: bool(np.isclose(point_overall["BASE_EQUAL_DOMAIN"][key], value, atol=1e-12, rtol=0))
        for key, value in BASELINE_EXPECTED.items()
    }
    baseline_checks.update({key: bool(np.isclose(point_similar["BASE_EQUAL_DOMAIN"][key], value, atol=1e-12, rtol=0)) for key, value in BASELINE_SIMILAR_EXPECTED.items()})
    _require(all(baseline_checks.values()), "AGGREGATION_BASELINE_REPRODUCTION_FAILED")
    plan = bootstrap_plan(episode_ids(frame), replicates, seed)
    episode_groups = {
        str(episode): group.index.to_numpy(dtype=int)
        for episode, group in frame.groupby("original_episode_id", sort=False)
    }
    episodes = tuple(sorted(episode_ids(frame)))
    episode_index = {episode: index for index, episode in enumerate(episodes)}
    pair_kernel = _pair_kernel(pair_groups, episodes)
    bootstrap_overall = defaultdict(list)
    bootstrap_similar = defaultdict(list)
    bootstrap_stage = defaultdict(list)
    for replicate, draw in enumerate(plan):
        overall, similar, stages = _bootstrap_once(
            frame,
            view_scores,
            draw,
            pair_kernel,
            pair_groups,
            episode_groups,
            episode_index,
        )
        for view in VIEW_ORDER:
            bootstrap_overall[view].append(overall[view])
            bootstrap_similar[view].append(similar[view])
        for key, value in stages.items():
            bootstrap_stage[key].append(value)
        if (replicate + 1) % 100 == 0 or replicate + 1 == replicates:
            print(f"AGGREGATION bootstrap {replicate + 1}/{replicates}", flush=True)
    overall_rows = _rows_with_ci(point_overall, bootstrap_overall, OVERALL_METRICS)
    similar_rows = _rows_with_ci(point_similar, bootstrap_similar, SIMILAR_METRICS, extra={view: {"n_pair": point_similar[view]["n_pair"], "n_node": point_similar[view]["n_node"], "n_episode": point_similar[view]["n_episode"]} for view in VIEW_ORDER})
    stage_rows = []
    for view in VIEW_ORDER:
        for stage in ACTIVE_STAGES:
            point = point_stage[(view, stage)]
            for metric in STAGE_METRICS:
                low, high = _interval([result[metric] for result in bootstrap_stage[(view, stage)]])
                stage_rows.append({"aggregation_view": view, "stage": stage, "metric": metric, "estimate": point[metric], "ci_low": low, "ci_high": high, "n_node": point["n_node"], "n_episode": point["n_episode"], "support_status": point["support_status"]})
    manifest = {
        "schema_version": "AIR_SLOT_AGGREGATION_ROBUSTNESS_FINAL_TEST_MANIFEST_V1",
        "status": "FINAL_TEST_COMPLETE",
        "artifact_scope": "FINAL_TEST_ONLY",
        "head": _head(),
        "source_path": str(source_path),
        "source_sha256": source_hash,
        "canonical_event_path": str(canonical_path),
        "canonical_event_sha256": _sha256(canonical_path),
        "final_test_access_count": 1,
        "n_episode": int(frame.original_episode_id.nunique()),
        "n_node": int(len(frame)),
        "date_min": str(pd.to_datetime(frame.decision_time, utc=True).min()),
        "date_max": str(pd.to_datetime(frame.decision_time, utc=True).max()),
        "stages": list(ACTIVE_STAGES),
        "views": list(VIEW_ORDER),
        "bootstrap": {"unit": "EPISODE", "replicates": replicates, "seed": seed, "ci": "percentile_95", "ranks_rebuilt_per_view_and_replicate": True, "similar_delay_eligibility_universe_precomputed_once": True, "similar_delay_rank_gaps_recomputed_per_view_and_replicate": True},
        "scientific_guards": {"model_retrained": False, "calibration_refit": False, "parameter_reselected": False, "cohort_modified": False, "new_data_accessed": False, "consequence_definitions_modified": False, "screening_rerun": False, "domain_only_scores_included_as_aggregate_views": False},
        "view_definition_check": definition_check,
        "baseline_reproduction": {"status": "PASS", "checks": baseline_checks, "point_overall": point_overall["BASE_EQUAL_DOMAIN"], "point_similar": point_similar["BASE_EQUAL_DOMAIN"]},
        "similar_delay": {"caliper_minutes": SIMILAR_DELAY_PRIMARY, "base_qualifying_node_pairs": int(len(pair_table)), "base_unique_episode_pairs": int(point_similar["BASE_EQUAL_DOMAIN"]["n_pair"])},
        "interpretation": "Values and percentile ranges are reported without an automatic robustness conclusion.",
    }
    report = _render_report(pd.DataFrame(overall_rows), pd.DataFrame(similar_rows), pd.DataFrame(stage_rows), manifest)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "AGGREGATION_VIEW_DEFINITIONS.json").write_text(json.dumps(_definition_payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pd.DataFrame(overall_rows).to_csv(output_path / "AGGREGATION_ROBUSTNESS_OVERALL.csv", index=False)
    pd.DataFrame(similar_rows).to_csv(output_path / "AGGREGATION_ROBUSTNESS_SIMILAR_DELAY.csv", index=False)
    pd.DataFrame(stage_rows).to_csv(output_path / "AGGREGATION_ROBUSTNESS_STAGE.csv", index=False)
    (output_path / "AGGREGATION_ROBUSTNESS_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_path / "AGGREGATION_ROBUSTNESS_REPORT.md").write_text(report, encoding="utf-8")
    manifest["outputs"] = {
        path.name: _sha256(path)
        for path in output_path.iterdir()
        if path.is_file() and path.name != "AGGREGATION_ROBUSTNESS_MANIFEST.json"
    }
    (output_path / "AGGREGATION_ROBUSTNESS_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _render_report(overall: pd.DataFrame, similar: pd.DataFrame, stage: pd.DataFrame, manifest: dict[str, object]) -> str:
    def table(frame: pd.DataFrame) -> str:
        return frame.to_markdown(index=False, floatfmt=".6f")
    lines = [
        "# Aggregation Robustness Report",
        "",
        "Reporting-only Final Test computation using the frozen Exp2A node population.",
        "",
        f"- HEAD: `{manifest['head']}`",
        f"- Population: `{manifest['n_node']}` nodes, `{manifest['n_episode']}` episodes",
        f"- Bootstrap: `{manifest['bootstrap']['replicates']}` episode clusters, seed `{manifest['bootstrap']['seed']}`, percentile 95% CI",
        "- Interpretation: numerical estimates and ranges are shown; no automatic robustness conclusion is assigned.",
        "",
        "## Overall",
        "",
        table(overall),
        "",
        "## Similar Delay",
        "",
        table(similar),
        "",
        "## Stage",
        "",
        table(stage),
        "",
        "## Gates",
        "",
        f"- BASE reproduction: `{manifest['baseline_reproduction']['status']}`",
        f"- Exp4 view-definition consistency: `{manifest['view_definition_check']['status']}`",
        "- Model retraining: `false`; calibration refit: `false`; parameter reselection: `false`.",
        "- BLOCKED / ABSTAIN: none in the materialized six-view tables.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--replicates", type=int, default=BOOTSTRAP_REPLICATES)
    parser.add_argument("--seed", type=int, default=BOOTSTRAP_SEED)
    args = parser.parse_args()
    run(args.source, args.canonical, args.output, replicates=args.replicates, seed=args.seed)


if __name__ == "__main__":
    main()
