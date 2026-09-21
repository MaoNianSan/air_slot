"""``BOOTSTRAP``: paired episode-cluster bootstrap over the M4 comparisons.

The frozen inference plan is the one locked in
``formal/FINAL_TEST_LOCK_20260907.md`` and implemented by
``exp.shared.resampling``: cluster = episode, ``B = 2000``, percentile 95% CI,
seed ``20260906``. The executor never re-implements the resampling; it calls
``bootstrap_plan`` and ``interval`` directly.

One draw is made per run over the union of participating episodes. Every
comparator and every estimand uses that same draw. For attention estimands the
draw is expanded into explicit bootstrap-instance identities and the frozen M3
Stage-I selector and M4 evaluator are rerun per replicate. For recovery
estimands the draw is applied to the fixed Stage-II cohort and the same M4
recovery evaluator is used. A replicate whose denominator is zero remains
typed; it is never coerced to a numeric zero loss.

Point/Marginal uncertainty is persisted as a paired ablation. The point
estimate is the full-sample ``HISTORY_POINT - HISTORY_MARGINAL`` difference and
the interval is the percentile interval of the per-replicate paired
differences, never the subtraction of two marginal intervals.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from functools import lru_cache
from typing import Any, Mapping, Sequence

import numpy as np

from model.M3.stage1 import select_attention
from model.M4.evaluation import evaluate_attention_allocation
from model.common.decision_contracts import (
    PrioritySignal,
    SignalKind,
    TypedStatus,
)
from model.common.enums import SupportState

from exp.shared.resampling import bootstrap_plan, interval

from .. import constants as C
from ..errors import TypedBlocker, _require
from ..materialization import _git
from . import stages as S
from .m4_comparisons import N_A_NOT_DEFINED

ZERO_DENOMINATOR_STATE = "UNDEFINED_ZERO_RECOVERABLE_VALUE"
POINT_ESTIMATE_TOLERANCE = 1e-9
MARGINAL_INCREMENT_DEFINITION = "HISTORY_POINT_MINUS_HISTORY_MARGINAL"
PAIRED_ASSERTION_CODES = (
    "POINT_MARGINAL_REPLICATE_IDS_IDENTICAL",
    "POINT_MARGINAL_RESAMPLED_EPISODES_IDENTICAL",
    "POINT_MARGINAL_CANONICAL_IDENTITIES_IDENTICAL",
    "POINT_MARGINAL_REFERENCE_EVALUATOR_IDENTICAL",
)


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
    """Draw the frozen paired bootstrap plan and publish all intervals."""

    provenance = bootstrap_seed_provenance()
    attention = m4_comparisons["attention"]
    recovery = m4_comparisons["recovery"]
    union_episodes = _union_episodes(attention, recovery)
    _require(bool(union_episodes), "PHASE7_BOOTSTRAP_EMPTY_EPISODE_SET")
    plan = bootstrap_plan(
        tuple(union_episodes),
        replicates=int(C.BOOTSTRAP_REPLICATES),
        seed=int(C.BOOTSTRAP_SEED),
    )
    plan_hash = _plan_hash(plan)

    comparators: dict[str, Any] = {}
    for variant in S.COMPARATOR_VARIANTS:
        attention_record = attention["comparators"][variant]
        recovery_record = recovery["comparators"][variant]
        attention_replicates = _attention_bootstrap(
            rows=attention["bootstrap_rows"].get(variant, ()),
            record=attention_record,
            variant=variant,
            plan=plan,
            plan_hash=plan_hash,
        )
        recovery_replicates = _recovery_bootstrap(
            rows=recovery["bootstrap_rows"].get(variant, ()),
            record=recovery_record,
            variant=variant,
            plan=plan,
            plan_hash=plan_hash,
        )
        comparators[variant] = {
            "attention": attention_replicates,
            "recovery": recovery_replicates,
        }

    paired_attention = _paired_marginal_increment(
        point_record=comparators["HISTORY_POINT"]["attention"],
        marginal_record=comparators["HISTORY_MARGINAL"]["attention"],
        mode="ATTENTION",
    )
    paired_recovery = _paired_marginal_increment(
        point_record=comparators["HISTORY_POINT"]["recovery"],
        marginal_record=comparators["HISTORY_MARGINAL"]["recovery"],
        mode="RECOVERY",
    )
    typed = sorted(
        {
            section.get("typed_state")
            for record in comparators.values()
            for section in record.values()
            if section.get("typed_state")
        }
        | {
            paired_attention.get("typed_state"),
            paired_recovery.get("typed_state"),
        }
        - {None}
    )
    return {
        "seed": int(C.BOOTSTRAP_SEED),
        "replicates": int(C.BOOTSTRAP_REPLICATES),
        "interval": C.BOOTSTRAP_INTERVAL,
        "resampling_unit": C.BOOTSTRAP_RESAMPLING_UNIT,
        "paired": True,
        "plan_hash": plan_hash,
        "plan_source": "exp.shared.resampling.bootstrap_plan",
        "interval_source": "exp.shared.resampling.interval",
        "seed_provenance": provenance,
        "episode_count": len(union_episodes),
        "episodes": list(union_episodes),
        "comparators": comparators,
        "marginal_uncertainty_increment": {
            "definition": MARGINAL_INCREMENT_DEFINITION,
            "paired": True,
            "attention": paired_attention,
            "recovery": paired_recovery,
        },
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


def _plan_hash(plan: np.ndarray) -> str:
    digest = hashlib.sha256()
    for replicate, draw in enumerate(np.asarray(plan)):
        digest.update(
            json.dumps(
                {"replicate_id": replicate, "episodes": [str(v) for v in draw]},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        )
        digest.update(b"\n")
    return "sha256:" + digest.hexdigest()


def _attention_bootstrap(
    *,
    rows: Sequence[Mapping[str, Any]],
    record: Mapping[str, Any],
    variant: str,
    plan: np.ndarray,
    plan_hash: str,
) -> dict[str, Any]:
    point = record.get("L_att")
    if not rows:
        return _empty_replicate_record(
            variant=variant,
            mode="ATTENTION",
            point_estimate=point,
            typed_state=N_A_NOT_DEFINED,
            plan_hash=plan_hash,
            rows=rows,
        )
    by_episode: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_episode.setdefault(str(row["episode_id"]), []).append(row)
    canonical_identity_hash = _identity_hash(rows, mode="ATTENTION")
    evaluator_id = _reference_evaluator_id(mode="ATTENTION")
    values: list[dict[str, Any]] = []
    for replicate_id, draw in enumerate(np.asarray(plan)):
        stage_evaluations: list[Any] = []
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        for instance, episode in enumerate(draw):
            for source in by_episode.get(str(episode), ()):
                grouped.setdefault(str(source["stage"]), []).append(
                    {"source": source, "instance": instance}
                )
        for stage in S.ACTIONABLE_STAGE_I_STAGES:
            instances = grouped.get(stage, ())
            if not instances:
                continue
            stage_evaluations.append(
                _attention_stage_replicate(
                    instances,
                    variant=variant,
                    replicate_id=replicate_id,
                    stage=stage,
                )
            )
        value, status = _aggregate_attention_replicate(stage_evaluations)
        values.append(
            {
                "replicate_id": replicate_id,
                "value": value,
                "status": status,
                "delta_J": None,
            }
        )
    return _summarize_replicates(
        variant=variant,
        mode="ATTENTION",
        point_estimate=point,
        typed_state_when_undefined=N_A_NOT_DEFINED,
        plan_hash=plan_hash,
        canonical_identity_hash=canonical_identity_hash,
        reference_evaluator_id=evaluator_id,
        values=values,
    )


def _attention_stage_replicate(
    instances: Sequence[Mapping[str, Any]],
    *,
    variant: str,
    replicate_id: int,
    stage: str,
) -> Any:
    reference_signals: list[PrioritySignal] = []
    comparator_signals: list[PrioritySignal] = []
    reference_priority: dict[str, float] = {}
    for item in instances:
        source = item["source"]
        occurrence = int(item["instance"])
        suffix = f"::BOOTSTRAP:{replicate_id}:{occurrence}"
        reference_node_id = f"{source['node_id']}{suffix}"
        reference_score = float(source["reference_score"])
        comparator_score = float(source["comparator_score"])
        reference_priority[reference_node_id] = reference_score
        reference_signals.append(
            _bootstrap_signal(
                source,
                suffix=suffix,
                score=reference_score,
                representation_id=C.REFERENCE_REPRESENTATION_ID,
            )
        )
        comparator_signals.append(
            _bootstrap_signal(
                source,
                suffix=suffix,
                score=comparator_score,
                representation_id=variant,
            )
        )
    reference_decision = select_attention(reference_signals, q=C.NOMINAL_Q)
    comparator_decision = select_attention(comparator_signals, q=C.NOMINAL_Q)
    return evaluate_attention_allocation(
        cohort_id=f"BOOTSTRAP_{stage}",
        reference_id=S.REFERENCE_VARIANT,
        comparator_id=variant,
        reference_decision=reference_decision,
        comparator_decision=comparator_decision,
        reference_priority=reference_priority,
    )


def _bootstrap_signal(
    source: Mapping[str, Any],
    *,
    suffix: str,
    score: float,
    representation_id: str,
) -> PrioritySignal:
    return PrioritySignal(
        signal_type=SignalKind.CONSEQUENCE,
        episode_id=f"{source['episode_id']}{suffix}",
        chain_id=f"{source.get('chain_id', source['episode_id'])}{suffix}",
        node_id=f"{source['node_id']}{suffix}",
        representation_id=representation_id,
        score=float(score),
        support=SupportState.SUPPORTED,
        status=TypedStatus.SUPPORTED,
        comparison_support_mass=float(source["support_mass"]),
        comparison_support_threshold=float(source["support_threshold"]),
    )


def _aggregate_attention_replicate(
    evaluations: Sequence[Any],
) -> tuple[float | None, str]:
    if not evaluations:
        return None, N_A_NOT_DEFINED
    reference = sum(
        float(evaluation.reference_attention_value)
        for evaluation in evaluations
    )
    comparator = sum(
        float(evaluation.comparator_attention_value)
        for evaluation in evaluations
    )
    if reference <= 0.0:
        return None, N_A_NOT_DEFINED
    return (reference - comparator) / reference, "DEFINED"


def _recovery_bootstrap(
    *,
    rows: Sequence[Mapping[str, Any]],
    record: Mapping[str, Any],
    variant: str,
    plan: np.ndarray,
    plan_hash: str,
) -> dict[str, Any]:
    point = record.get("L_rec")
    if not rows:
        return _empty_replicate_record(
            variant=variant,
            mode="RECOVERY",
            point_estimate=point,
            typed_state=ZERO_DENOMINATOR_STATE,
            plan_hash=plan_hash,
            rows=rows,
        )
    by_episode: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_episode.setdefault(str(row["episode_id"]), []).append(row)
    canonical_identity_hash = _identity_hash(rows, mode="RECOVERY")
    evaluator_id = _reference_evaluator_id(mode="RECOVERY")
    values: list[dict[str, Any]] = []
    for replicate_id, draw in enumerate(np.asarray(plan)):
        denominator = 0.0
        numerator = 0.0
        delta_j = 0.0
        for episode in draw:
            for row in by_episode.get(str(episode), ()):
                denominator += float(row["reference_value"])
                numerator += float(row["delta_objective"])
                delta_j += float(row["delta_objective"])
        if denominator <= 0.0:
            value = None
            status = ZERO_DENOMINATOR_STATE
        else:
            value = numerator / denominator
            status = "DEFINED"
        values.append(
            {
                "replicate_id": replicate_id,
                "value": value,
                "status": status,
                "delta_J": delta_j,
            }
        )
    return _summarize_replicates(
        variant=variant,
        mode="RECOVERY",
        point_estimate=point,
        typed_state_when_undefined=ZERO_DENOMINATOR_STATE,
        plan_hash=plan_hash,
        canonical_identity_hash=canonical_identity_hash,
        reference_evaluator_id=evaluator_id,
        values=values,
    )


def _empty_replicate_record(
    *,
    variant: str,
    mode: str,
    point_estimate: Any,
    typed_state: str,
    plan_hash: str,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "variant": variant,
        "mode": mode,
        "status": "TYPED",
        "typed_state": typed_state,
        "point_estimate": None if point_estimate is None else float(point_estimate),
        "ci": None,
        "ci_low": None,
        "ci_high": None,
        "valid_replicates": 0,
        "replicate_count": int(C.BOOTSTRAP_REPLICATES),
        "skipped_zero_denominator_replicates": int(C.BOOTSTRAP_REPLICATES),
        "replicates": [],
        "resampled_episodes_hash": plan_hash,
        "canonical_identity_hash": _identity_hash(rows, mode=mode),
        "reference_evaluator_id": _reference_evaluator_id(mode=mode),
        "reason_codes": ["PHASE7_BOOTSTRAP_ROWS_UNAVAILABLE"],
    }


def _summarize_replicates(
    *,
    variant: str,
    mode: str,
    point_estimate: Any,
    typed_state_when_undefined: str,
    plan_hash: str,
    canonical_identity_hash: str,
    reference_evaluator_id: str,
    values: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    numeric = [
        float(row["value"])
        for row in values
        if row.get("value") is not None
        and math.isfinite(float(row["value"]))
    ]
    point = None if point_estimate is None else float(point_estimate)
    reason_counts = Counter(
        str(row["status"])
        for row in values
        if row.get("value") is None
    )
    if point is None:
        return {
            "variant": variant,
            "mode": mode,
            "status": "TYPED",
            "typed_state": typed_state_when_undefined,
            "reason_codes": [f"PHASE7_BOOTSTRAP_STATUS_{key}" for key in reason_counts],
            "point_estimate": None,
            "ci": None,
            "ci_low": None,
            "ci_high": None,
            "valid_replicates": len(numeric),
            "replicate_count": len(values),
            "skipped_zero_denominator_replicates": sum(reason_counts.values()),
            "replicates": [dict(row) for row in values],
            "resampled_episodes_hash": plan_hash,
            "canonical_identity_hash": canonical_identity_hash,
            "reference_evaluator_id": reference_evaluator_id,
            "undefined_reason_counts": dict(sorted(reason_counts.items())),
        }
    low, high = interval(numeric)
    if low is None:
        return {
            "variant": variant,
            "mode": mode,
            "status": "TYPED",
            "typed_state": typed_state_when_undefined,
            "reason_codes": ["PHASE7_BOOTSTRAP_ALL_REPLICATES_TYPED"],
            "point_estimate": point,
            "ci": None,
            "ci_low": None,
            "ci_high": None,
            "valid_replicates": 0,
            "replicate_count": len(values),
            "skipped_zero_denominator_replicates": sum(reason_counts.values()),
            "replicates": [dict(row) for row in values],
            "resampled_episodes_hash": plan_hash,
            "canonical_identity_hash": canonical_identity_hash,
            "reference_evaluator_id": reference_evaluator_id,
            "undefined_reason_counts": dict(sorted(reason_counts.items())),
        }
    return {
        "variant": variant,
        "mode": mode,
        "status": "PASS",
        "typed_state": None,
        "reason_codes": [],
        "point_estimate": point,
        "ci": [float(low), float(high)],
        "ci_low": float(low),
        "ci_high": float(high),
        "valid_replicates": len(numeric),
        "replicate_count": len(values),
        "skipped_zero_denominator_replicates": sum(reason_counts.values()),
        "replicate_mean": float(np.mean(numeric)),
        "replicates": [dict(row) for row in values],
        "resampled_episodes_hash": plan_hash,
        "canonical_identity_hash": canonical_identity_hash,
        "reference_evaluator_id": reference_evaluator_id,
        "undefined_reason_counts": dict(sorted(reason_counts.items())),
    }


def _paired_marginal_increment(
    *,
    point_record: Mapping[str, Any],
    marginal_record: Mapping[str, Any],
    mode: str,
) -> dict[str, Any]:
    point_replicates = {
        int(row["replicate_id"]): row for row in point_record.get("replicates", ())
    }
    marginal_replicates = {
        int(row["replicate_id"]): row
        for row in marginal_record.get("replicates", ())
    }
    point_ids = tuple(sorted(point_replicates))
    marginal_ids = tuple(sorted(marginal_replicates))
    assertions = {
        "POINT_MARGINAL_REPLICATE_IDS_IDENTICAL": point_ids == marginal_ids,
        "POINT_MARGINAL_RESAMPLED_EPISODES_IDENTICAL": (
            point_record.get("resampled_episodes_hash")
            == marginal_record.get("resampled_episodes_hash")
        ),
        "POINT_MARGINAL_CANONICAL_IDENTITIES_IDENTICAL": (
            point_record.get("canonical_identity_hash")
            == marginal_record.get("canonical_identity_hash")
        ),
        "POINT_MARGINAL_REFERENCE_EVALUATOR_IDENTICAL": (
            point_record.get("reference_evaluator_id")
            == marginal_record.get("reference_evaluator_id")
        ),
    }
    for code in PAIRED_ASSERTION_CODES:
        _require(
            assertions[code] is True,
            code,
            {
                "point_replicate_count": len(point_ids),
                "marginal_replicate_count": len(marginal_ids),
                "point_resampled_episodes_hash": point_record.get(
                    "resampled_episodes_hash"
                ),
                "marginal_resampled_episodes_hash": marginal_record.get(
                    "resampled_episodes_hash"
                ),
                "point_canonical_identity_hash": point_record.get(
                    "canonical_identity_hash"
                ),
                "marginal_canonical_identity_hash": marginal_record.get(
                    "canonical_identity_hash"
                ),
                "point_reference_evaluator_id": point_record.get(
                    "reference_evaluator_id"
                ),
                "marginal_reference_evaluator_id": marginal_record.get(
                    "reference_evaluator_id"
                ),
            },
        )
    paired_rows: list[dict[str, Any]] = []
    delta_losses: list[float] = []
    reason_counts: Counter[str] = Counter()
    point_field = "L_att_point" if mode == "ATTENTION" else "L_rec_point"
    marginal_field = (
        "L_att_marginal" if mode == "ATTENTION" else "L_rec_marginal"
    )
    delta_field = (
        "delta_L_att_marginal"
        if mode == "ATTENTION"
        else "delta_L_rec_marginal"
    )
    for replicate_id in point_ids:
        point_row = point_replicates[replicate_id]
        marginal_row = marginal_replicates[replicate_id]
        point_value = point_row.get("value")
        marginal_value = marginal_row.get("value")
        if point_value is None or marginal_value is None:
            delta = None
            status = "TYPED_UNDEFINED"
            reason_counts[
                f"POINT_{point_row.get('status')}|MARGINAL_{marginal_row.get('status')}"
            ] += 1
        else:
            delta = float(point_value) - float(marginal_value)
            delta_losses.append(delta)
            status = "DEFINED"
        row: dict[str, Any] = {
            "replicate_id": replicate_id,
            point_field: None if point_value is None else float(point_value),
            marginal_field: (
                None if marginal_value is None else float(marginal_value)
            ),
            delta_field: delta,
            f"{point_field}_status": str(point_row.get("status")),
            f"{marginal_field}_status": str(marginal_row.get("status")),
            "increment_status": status,
        }
        if mode == "RECOVERY":
            point_delta_j = point_row.get("delta_J")
            marginal_delta_j = marginal_row.get("delta_J")
            row["delta_J_point"] = (
                None if point_delta_j is None else float(point_delta_j)
            )
            row["delta_J_marginal"] = (
                None if marginal_delta_j is None else float(marginal_delta_j)
            )
            row["delta_J_marginal_increment"] = (
                None
                if point_delta_j is None or marginal_delta_j is None
                else float(point_delta_j) - float(marginal_delta_j)
            )
        paired_rows.append(row)

    point_estimate = point_record.get("point_estimate")
    marginal_estimate = marginal_record.get("point_estimate")
    point_loss = None if point_estimate is None else float(point_estimate)
    marginal_loss = (
        None if marginal_estimate is None else float(marginal_estimate)
    )
    estimate = (
        None
        if point_loss is None or marginal_loss is None
        else point_loss - marginal_loss
    )
    low, high = interval(delta_losses)
    if estimate is None:
        full_sample_verified = "TYPED"
        verification_error = None
    else:
        verification_error = abs(
            float(estimate) - (float(point_loss) - float(marginal_loss))
        )
        tolerance = POINT_ESTIMATE_TOLERANCE * max(
            1.0, abs(float(point_loss)), abs(float(marginal_loss))
        )
        _require(
            math.isfinite(float(estimate))
            and verification_error <= tolerance,
            "PHASE7_MARGINAL_INCREMENT_FULL_SAMPLE_MISMATCH",
            {
                "point_loss": point_loss,
                "marginal_loss": marginal_loss,
                "full_sample_increment": estimate,
                "absolute_error": verification_error,
                "tolerance": tolerance,
            },
        )
        full_sample_verified = "PASS"
    return {
        "definition": MARGINAL_INCREMENT_DEFINITION,
        "paired": True,
        "mode": mode,
        "replicate_count": int(C.BOOTSTRAP_REPLICATES),
        "seed": int(C.BOOTSTRAP_SEED),
        "resampling_unit": C.BOOTSTRAP_RESAMPLING_UNIT,
        "interval": C.BOOTSTRAP_INTERVAL,
        "status": "PASS" if delta_losses else "TYPED",
        "typed_state": None if delta_losses else ZERO_DENOMINATOR_STATE,
        "point_loss": point_loss,
        "marginal_loss": marginal_loss,
        "estimate": estimate,
        "ci": None if low is None else [float(low), float(high)],
        "ci_low": None if low is None else float(low),
        "ci_high": None if high is None else float(high),
        "numeric_replicate_count": len(delta_losses),
        "undefined_replicate_count": len(paired_rows) - len(delta_losses),
        "undefined_reason_counts": dict(sorted(reason_counts.items())),
        "full_sample_increment": estimate,
        "full_sample_increment_verification": full_sample_verified,
        "full_sample_increment_verification_error": verification_error,
        "paired_assertions": assertions,
        "replicates": paired_rows,
    }


def _identity_hash(
    rows: Sequence[Mapping[str, Any]], *, mode: str
) -> str:
    if mode == "ATTENTION":
        body = [
            {
                "stage": str(row["stage"]),
                "episode_id": str(row["episode_id"]),
                "node_id": str(row["node_id"]),
            }
            for row in rows
        ]
    else:
        body = [
            {
                "episode_id": str(row["episode_id"]),
                "node_id": str(row["node_id"]),
                "stage": str(row.get("stage", "")),
            }
            for row in rows
        ]
    body.sort(
        key=lambda item: (
            item.get("stage", ""),
            item["episode_id"],
            item["node_id"],
        )
    )
    return _hash_json({"mode": mode, "identities": body})


def _reference_evaluator_id(*, mode: str) -> str:
    return _hash_json(
        {
            "mode": mode,
            "reference_variant": S.REFERENCE_VARIANT,
            "evaluator": (
                "model.M4.evaluation.evaluate_attention_allocation"
                if mode == "ATTENTION"
                else "model.M4.evaluation.evaluate_recovery_loss"
            ),
            "aggregation": (
                "OBJECTIVE_THEN_NORMALIZE"
                if mode == "ATTENTION"
                else "FIXED_RSTAR_WEIGHTED_RATIO"
            ),
        }
    )


def _hash_json(value: Any) -> str:
    body = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


__all__ = [
    "MARGINAL_INCREMENT_DEFINITION",
    "PAIRED_ASSERTION_CODES",
    "POINT_ESTIMATE_TOLERANCE",
    "ZERO_DENOMINATOR_STATE",
    "bootstrap_seed_provenance",
    "build_bootstrap",
]
