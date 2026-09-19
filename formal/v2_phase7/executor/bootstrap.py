"""``BOOTSTRAP``: paired episode-cluster bootstrap over the M4 comparisons.

The frozen inference plan is the one locked in
``formal/FINAL_TEST_LOCK_20260907.md`` and implemented by
``exp.shared.resampling``: cluster = episode, ``B = 2000``, percentile 95% CI,
seed ``20260906``. The executor never re-implements the resampling; it calls
``bootstrap_plan`` and ``interval`` directly.

The plan is drawn once per run over the union of participating episodes, so the
attention and recovery estimators of a comparator share exactly the same
replicate draws (paired design). A replicate whose denominator is zero is
skipped and counted; it is never coerced to a zero loss. The point estimate is
recomputed from the same per-node rows and must reproduce the M4 record, which
fails closed on any mismatch.

``bootstrap_seed_provenance`` proves the seed is pre-lock and not result-driven:
the seed already existed in ``exp/shared/resampling.py`` before the lock
document that froze ``B``, the seed and the interval was committed. The
provenance record states the remaining caveat explicitly: this is single-author
local history with no third-party attestation.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping, Sequence

import numpy as np

from exp.shared.resampling import bootstrap_plan, interval

from .. import constants as C
from ..errors import TypedBlocker, _require
from ..materialization import _git
from . import stages as S
from .m4_comparisons import N_A_NOT_DEFINED

ZERO_DENOMINATOR_STATE = "UNDEFINED_ZERO_RECOVERABLE_VALUE"
POINT_ESTIMATE_TOLERANCE = 1e-9


@lru_cache(maxsize=1)
def bootstrap_seed_provenance() -> dict[str, Any]:
    """Prove ``seed = 20260906`` predates the lock that froze the plan."""

    lock_path = C.BOOTSTRAP_SEED_LOCK_PATH
    source_path = C.BOOTSTRAP_SEED_SOURCE_PATH
    for path in (lock_path, source_path):
        _require(path.is_file(), "PHASE7_BOOTSTRAP_SEED_EVIDENCE_MISSING", str(path))
    lock_text = lock_path.read_text(encoding="utf-8")
    source_text = source_path.read_text(encoding="utf-8")
    seed_text = str(C.BOOTSTRAP_SEED)
    _require(
        seed_text in lock_text and str(C.BOOTSTRAP_REPLICATES) in lock_text,
        "PHASE7_BOOTSTRAP_LOCK_DOES_NOT_DECLARE_PLAN",
        str(lock_path),
    )
    _require(
        seed_text in source_text,
        "PHASE7_BOOTSTRAP_SOURCE_DOES_NOT_DECLARE_SEED",
        str(source_path),
    )
    lock_relative = str(lock_path.relative_to(C.ROOT)).replace("\\", "/")
    source_relative = str(source_path.relative_to(C.ROOT)).replace("\\", "/")
    source_commits = _git(
        "log",
        "--format=%H|%cI",
        "-S",
        seed_text,
        "--reverse",
        "--",
        source_relative,
    ).splitlines()
    lock_commits = _git(
        "log", "--format=%H|%cI", "--reverse", "--", lock_relative
    ).splitlines()
    _require(
        bool(source_commits),
        "PHASE7_BOOTSTRAP_SEED_SOURCE_HISTORY_MISSING",
        source_relative,
    )
    _require(
        bool(lock_commits),
        "PHASE7_BOOTSTRAP_LOCK_HISTORY_MISSING",
        lock_relative,
    )
    seed_commit, seed_time = source_commits[0].split("|", 1)
    lock_commit, lock_time = lock_commits[0].split("|", 1)
    locked_blob = _git("show", f"{lock_commit}:{lock_relative}")
    _require(
        seed_text in locked_blob,
        "PHASE7_BOOTSTRAP_LOCK_COMMIT_DOES_NOT_CARRY_SEED",
        lock_commit,
    )
    from datetime import datetime

    seed_at = datetime.fromisoformat(seed_time)
    lock_at = datetime.fromisoformat(lock_time)
    _require(
        seed_at <= lock_at,
        "PHASE7_BOOTSTRAP_SEED_AFTER_LOCK",
        {"seed_introduced_at": seed_time, "lock_created_at": lock_time},
    )
    return {
        "status": "PASS",
        "seed": int(C.BOOTSTRAP_SEED),
        "replicates": int(C.BOOTSTRAP_REPLICATES),
        "interval": C.BOOTSTRAP_INTERVAL,
        "resampling_unit": C.BOOTSTRAP_RESAMPLING_UNIT,
        "seed_source_path": source_relative,
        "seed_source_commit": seed_commit,
        "seed_introduced_at": seed_time,
        "lock_path": lock_relative,
        "lock_commit": lock_commit,
        "lock_created_at": lock_time,
        "seed_predates_lock": True,
        "result_driven": False,
        "attestation": "SINGLE_AUTHOR_LOCAL_HISTORY_NO_THIRD_PARTY_ATTESTATION",
    }


def build_bootstrap(m4_comparisons: Mapping[str, Any]) -> dict[str, Any]:
    """Draw the frozen paired bootstrap plan and publish the intervals."""

    provenance = bootstrap_seed_provenance()
    attention = m4_comparisons["attention"]
    recovery = m4_comparisons["recovery"]
    union_episodes = _union_episodes(attention, recovery)
    _require(
        bool(union_episodes), "PHASE7_BOOTSTRAP_EMPTY_EPISODE_SET"
    )
    plan = bootstrap_plan(
        tuple(union_episodes),
        replicates=int(C.BOOTSTRAP_REPLICATES),
        seed=int(C.BOOTSTRAP_SEED),
    )
    counts_by_episode = _counts_by_episode(plan, union_episodes)

    comparators: dict[str, Any] = {}
    for variant in S.COMPARATOR_VARIANTS:
        comparators[variant] = {
            "attention": _estimate(
                rows=attention["bootstrap_rows"].get(variant, ()),
                record=attention["comparators"][variant],
                loss_field="L_att",
                typed_state_when_undefined=N_A_NOT_DEFINED,
                counts_by_episode=counts_by_episode,
                mode="ATTENTION",
            ),
            "recovery": _estimate(
                rows=recovery["bootstrap_rows"].get(variant, ()),
                record=recovery["comparators"][variant],
                loss_field="L_rec",
                typed_state_when_undefined=ZERO_DENOMINATOR_STATE,
                counts_by_episode=counts_by_episode,
                mode="RECOVERY",
            ),
        }
    typed = sorted(
        {
            section["typed_state"]
            for record in comparators.values()
            for section in record.values()
            if section.get("typed_state")
        }
    )
    return {
        "seed": int(C.BOOTSTRAP_SEED),
        "replicates": int(C.BOOTSTRAP_REPLICATES),
        "interval": C.BOOTSTRAP_INTERVAL,
        "resampling_unit": C.BOOTSTRAP_RESAMPLING_UNIT,
        "paired": True,
        "plan_source": "exp.shared.resampling.bootstrap_plan",
        "interval_source": "exp.shared.resampling.interval",
        "seed_provenance": provenance,
        "episode_count": len(union_episodes),
        "episodes": list(union_episodes),
        "comparators": comparators,
        "typed_states": typed,
        "fixed_window_sensitivity_status": S.FIXED_WINDOW_SENSITIVITY_STATUS,
        "final_test_data_read": False,
    }


def _union_episodes(
    attention: Mapping[str, Any], recovery: Mapping[str, Any]
) -> tuple[str, ...]:
    episodes: set[str] = set()
    for variant in S.COMPARATOR_VARIANTS:
        for row in attention["bootstrap_rows"].get(variant, ()):
            episodes.add(str(row["episode_id"]))
        for row in recovery["bootstrap_rows"].get(variant, ()):
            episodes.add(str(row["episode_id"]))
    return tuple(sorted(episodes))


def _counts_by_episode(
    plan: np.ndarray, episodes: Sequence[str]
) -> dict[str, np.ndarray]:
    """Occurrence matrix ``(B, n_episodes)`` for the frozen plan draws."""

    draws = np.asarray(plan)
    episodes_array = np.asarray([str(value) for value in episodes])
    positions = np.searchsorted(episodes_array, draws)
    _require(
        bool(np.all(episodes_array[positions] == draws)),
        "PHASE7_BOOTSTRAP_DRAW_OUTSIDE_EPISODE_SET",
    )
    replicates, size = positions.shape
    counts = np.zeros((replicates, len(episodes)), dtype=np.int64)
    rows = np.repeat(np.arange(replicates), size)
    np.add.at(counts, (rows, positions.reshape(-1)), 1)
    return {episode: counts[:, index] for index, episode in enumerate(episodes)}


def _estimate(
    *,
    rows: Sequence[Mapping[str, Any]],
    record: Mapping[str, Any],
    loss_field: str,
    typed_state_when_undefined: str,
    counts_by_episode: Mapping[str, np.ndarray],
    mode: str,
) -> dict[str, Any]:
    if not rows:
        return {
            "status": "TYPED",
            "typed_state": typed_state_when_undefined,
            "reason_codes": list(record.get("reason_codes", ()))
            or ["PHASE7_BOOTSTRAP_ROWS_UNAVAILABLE"],
            "point_estimate": None,
            "ci": None,
            "ci_low": None,
            "ci_high": None,
            "valid_replicates": 0,
            "skipped_zero_denominator_replicates": 0,
        }
    point = float(record.get(loss_field)) if record.get(loss_field) is not None else None
    numerator_per_node, denominator_per_node = _node_vectors(rows, mode)
    episode_ids = [str(row["episode_id"]) for row in rows]
    unique = sorted(set(episode_ids))
    index = {episode: position for position, episode in enumerate(unique)}
    node_episode = np.asarray([index[value] for value in episode_ids], dtype=np.int64)
    numerator = np.bincount(
        node_episode, weights=numerator_per_node, minlength=len(unique)
    )
    denominator = np.bincount(
        node_episode, weights=denominator_per_node, minlength=len(unique)
    )
    counts = np.column_stack(
        [counts_by_episode[episode] for episode in unique]
    ).astype(float)
    replicate_numerator = counts @ numerator
    replicate_denominator = counts @ denominator
    if point is None:
        return {
            "status": "TYPED",
            "typed_state": typed_state_when_undefined,
            "reason_codes": list(record.get("reason_codes", ())),
            "point_estimate": None,
            "ci": None,
            "ci_low": None,
            "ci_high": None,
            "valid_replicates": 0,
            "skipped_zero_denominator_replicates": int(counts.shape[0]),
        }
    denominator_total = float(denominator.sum())
    if denominator_total > 0.0:
        recomputed = float(numerator.sum()) / denominator_total
        _require(
            abs(recomputed - point)
            <= POINT_ESTIMATE_TOLERANCE * max(1.0, abs(point)),
            "PHASE7_BOOTSTRAP_POINT_ESTIMATE_MISMATCH",
            {"recomputed": recomputed, "m4_record": point},
        )
    valid = replicate_denominator > 0.0
    values = (
        replicate_numerator[valid] / replicate_denominator[valid]
    )
    low, high = interval(values.tolist()) if values.size else (None, None)
    if values.size == 0:
        return {
            "status": "TYPED",
            "typed_state": typed_state_when_undefined,
            "reason_codes": ["PHASE7_BOOTSTRAP_ALL_REPLICATES_ZERO_DENOMINATOR"],
            "point_estimate": point,
            "ci": None,
            "ci_low": None,
            "ci_high": None,
            "valid_replicates": 0,
            "skipped_zero_denominator_replicates": int(counts.shape[0]),
        }
    return {
        "status": "PASS",
        "typed_state": None,
        "reason_codes": [],
        "point_estimate": point,
        "ci": [float(low), float(high)],
        "ci_low": float(low),
        "ci_high": float(high),
        "valid_replicates": int(values.size),
        "skipped_zero_denominator_replicates": int(counts.shape[0] - values.size),
        "replicate_mean": float(np.mean(values)),
    }


def _node_vectors(
    rows: Sequence[Mapping[str, Any]], mode: str
) -> tuple[np.ndarray, np.ndarray]:
    """Per-node ``(numerator, denominator)`` contributions of the estimand.

    ``L_att`` uses ``(ref - comparator) * priority`` over ``ref * priority``;
    ``L_rec`` uses ``delta_objective`` over the reference recoverable value.
    """
    _require(
        mode in {"ATTENTION", "RECOVERY"},
        "PHASE7_BOOTSTRAP_UNKNOWN_ESTIMAND_MODE",
        mode,
    )
    numerator: list[float] = []
    denominator: list[float] = []
    for row in rows:
        if mode == "ATTENTION":
            priority = float(row["reference_priority"])
            reference_flag = 1.0 if row["in_reference_shortlist"] else 0.0
            comparator_flag = 1.0 if row["in_comparator_shortlist"] else 0.0
            numerator.append(priority * (reference_flag - comparator_flag))
            denominator.append(priority * reference_flag)
        else:
            numerator.append(float(row["delta_objective"]))
            denominator.append(float(row["reference_value"]))
    return np.asarray(numerator, dtype=float), np.asarray(denominator, dtype=float)


__all__ = [
    "POINT_ESTIMATE_TOLERANCE",
    "ZERO_DENOMINATOR_STATE",
    "bootstrap_seed_provenance",
    "build_bootstrap",
]
