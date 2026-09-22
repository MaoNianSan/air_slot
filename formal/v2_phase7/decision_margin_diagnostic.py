"""Decision-margin mechanism diagnostic over the sealed canonical-v2 epoch.

A ``POST_HOC_MECHANISM_DIAGNOSTIC`` that maps the manuscript decision-stability
principle onto decisions that are already frozen. It is not a new experiment
family, not a new model comparison, not a new representation and not a new
Final-Test specification: nothing is retrained, recalibrated or reselected, and
the Final-Test population, canonical-node rule, support rules, Stage-I priority
definitions, consequence mapping, ``q = 0.10`` primary setting, ``R*`` cohort,
``lambda``, turnaround lower bound and tie-breaking rule are consumed exactly as
sealed.

For each pairwise information increment (alternative -> reference):

* Stage-I, per actionable stage at the nominal ``q = 0.10``::

      m_g     = P^r_{(K_g),g} - P^r_{(K_g + 1),g}          reference cutoff margin
      delta_i = P^a_{i,g} - P^r_{i,g}                      per-chain perturbation
      eps_g   = max_i |delta_i|                            information-induced perturbation
      span_g  = max_i delta_i - min_i delta_i              additive-shift-insensitive span
      s_g     = m_g - 2 * eps_g                            certificate slack

* Stage-II, per ``R*`` chain on the frozen finite recovery grid::

      gamma   = J^r(u_second) - J^r(u*)                    action gap
      eps^II  = max_u |J^a(u) - J^r(u)|                    objective perturbation
      span^II = max_u delta(u) - min_u delta(u)            additive-shift-insensitive span
      s^II    = gamma - 2 * eps^II                         certificate slack

The certificates are **sufficient** stability certificates, never necessary
conditions. Only four statuses exist: ``CERTIFIED_STABLE``, ``NOT_CERTIFIED``,
``NO_STRICT_REFERENCE_MARGIN`` and ``ABSTAIN_NO_COMMON_SUPPORT``. A
``CERTIFIED_STABLE`` certificate must correspond to an empirically stable
decision; a non-certificate must never be read as a predicted change, and
``NOT_CERTIFIED`` routinely coexists with an unchanged decision.

``perturbation_span`` is materialized next to ``epsilon_inf`` for later
assessment only. Because ``span = max delta - min delta <= 2 * max|delta| =
2 * eps``, a span certificate is never more conservative than the ``2 * eps``
certificate and can be strictly tighter when a common additive shift is
present; it does **not** enter any status reported here, which stays on the
frozen ``2 * eps < m`` / ``2 * eps < gamma`` formulation.

The Stage-II objective curves are the one thing the sealed epoch did not persist
for the three non-reference variants, so they are re-materialized from the
sealed state sets with the frozen ``model.M3.stage2.objective_by_grid``. That
replay path is licensed by two gates that must pass first: the sealed
``HISTORY_JOINT`` curve is reproduced point by point, and the frozen action
selector is replayed for all four variants to reproduce every sealed ``u*``.

Nothing is written into the sealed epoch root. Every artifact is written into a
staging directory first and materialized transactionally: a fresh run is a
single same-filesystem rename, a regeneration (same git head, same input hashes,
same diagnostic source hash) is a backup swap with rollback, and a failed run
never leaves a partial directory in the official location.

Usage (from the repository root)::

    python -m formal.v2_phase7.decision_margin_diagnostic \
        --epoch-root <sealed canonical-v2 epoch root> \
        --out-dir <directory receiving the eight result files>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Mapping, Sequence

import pandas as pd

from model.M3.stage1 import STAGE_I_TIE_BREAK, attention_capacity_k
from model.M3.stage2 import RecoveryPolicy, objective_by_grid
from model.M3.transition import TransitionContext
from model.M4.evaluation import (
    evaluate_attention_allocation,
    evaluate_recovery_loss,
)

from . import constants as C
from .executor import stages as S
from .executor.checkpoints import CheckpointStore
from .executor.codec import (
    attention_decision_from_payload,
    recovery_decision_from_payload,
)

ANALYSIS_NAME = "DECISION_MARGIN_MECHANISM_DIAGNOSTIC"
ANALYSIS_TYPE = "POST_HOC_MECHANISM_DIAGNOSTIC"
SPLIT = "FINAL_TEST"
REFERENCE_VARIANT = S.REFERENCE_VARIANT
STAGES = S.ACTIONABLE_STAGE_I_STAGES
STAGE_CLASS = {"PRE_IB": "PRE", "POST_IB_PRE_OB": "TURN"}

NOMINAL_Q = float(C.NOMINAL_Q)
Q_GRID = tuple(float(value) for value in C.Q_GRID)

#: Frozen Stage-I anchors of the sealed epoch; the diagnostic must reproduce them.
EXPECTED_STAGE1_N = {"PRE_IB": 29, "POST_IB_PRE_OB": 127}
EXPECTED_STAGE1_K = {"PRE_IB": 3, "POST_IB_PRE_OB": 13}
EXPECTED_STAGE2_N = 16
EXPECTED_STAGE2_STAGE_COUNTS = {"PRE_IB": 3, "POST_IB_PRE_OB": 13}
EXPECTED_ACTION_GRID = tuple(float(value) for value in range(0, 46, 5))

CERTIFIED_STABLE = "CERTIFIED_STABLE"
NOT_CERTIFIED = "NOT_CERTIFIED"
NO_STRICT_REFERENCE_MARGIN = "NO_STRICT_REFERENCE_MARGIN"
ABSTAIN_NO_COMMON_SUPPORT = "ABSTAIN_NO_COMMON_SUPPORT"

#: The only statuses this diagnostic may report.
ALLOWED_CERTIFICATE_STATUSES: tuple[str, ...] = (
    ABSTAIN_NO_COMMON_SUPPORT,
    CERTIFIED_STABLE,
    NO_STRICT_REFERENCE_MARGIN,
    NOT_CERTIFIED,
)

#: Never used to describe a certificate failure.
PROHIBITED_CERTIFICATE_TERMS: tuple[str, ...] = (
    "FAILED_STABILITY",
    "PREDICTED_CHANGE",
    "UNSTABLE",
)

#: A certificate is a mechanism diagnostic, not a classifier.
PROHIBITED_METRIC_KEYS: tuple[str, ...] = (
    "accuracy",
    "auc",
    "f1",
    "precision",
    "recall",
    "roc",
)

#: The frozen numerical comparison tolerance is reused, never re-invented. The
#: two roles stay distinct even though they currently share one constant:
#: replay consistency is not the same concept as margin strictness.
MARGIN_TOLERANCE = float(C.M3_NUMERICAL_COMPARISON_TOLERANCE)
MARGIN_TOLERANCE_SOURCE = "C.M3_NUMERICAL_COMPARISON_TOLERANCE"
REPLAY_TOLERANCE = float(C.M3_NUMERICAL_COMPARISON_TOLERANCE)
REPLAY_TOLERANCE_SOURCE = "C.M3_NUMERICAL_COMPARISON_TOLERANCE"

STAGE1_RECORDS_NAME = "DECISION_MARGIN_STAGE1_RECORDS.parquet"
STAGE1_SUMMARY_NAME = "DECISION_MARGIN_STAGE1_SUMMARY.csv"
STAGE2_CURVES_NAME = "DECISION_MARGIN_STAGE2_ACTION_CURVES.parquet"
STAGE2_CHAIN_NAME = "DECISION_MARGIN_STAGE2_CHAIN_SUMMARY.csv"
STAGE2_SUMMARY_NAME = "DECISION_MARGIN_STAGE2_SUMMARY.csv"
STAGE_Q_BOUNDARY_NAME = "DECISION_MARGIN_STAGE_Q_BOUNDARY.csv"
MANIFEST_NAME = "DECISION_MARGIN_DIAGNOSTIC_MANIFEST.json"
REPORT_NAME = "DECISION_MARGIN_DIAGNOSTIC_REPORT.md"

#: Hashed into the manifest. The manifest cannot contain its own SHA256 by
#: construction, so it is listed in ``output_artifact_paths`` only.
PAYLOAD_ARTIFACTS: tuple[str, ...] = (
    STAGE1_RECORDS_NAME,
    STAGE1_SUMMARY_NAME,
    STAGE2_CURVES_NAME,
    STAGE2_CHAIN_NAME,
    STAGE2_SUMMARY_NAME,
    STAGE_Q_BOUNDARY_NAME,
    REPORT_NAME,
)

#: Row-level frames stay local and regenerable; paper-results roots in this
#: repository version-control CSV/JSON/MD only.
LOCAL_ONLY_ARTIFACTS: tuple[str, ...] = (STAGE1_RECORDS_NAME, STAGE2_CURVES_NAME)

STAGING_SUFFIX = ".__staging__"
PREVIOUS_SUFFIX = ".__previous__"
SOURCE_RELATIVE_PATH = "formal/v2_phase7/decision_margin_diagnostic.py"
TEST_RELATIVE_PATH = "tests/phase7/test_decision_margin_diagnostic.py"

#: Tracked paths this diagnostic must never modify: the sealed Final-Test
#: epochs, the frozen registries, the sealed runner and its own sources.
PROTECTED_TRACKED_PREFIXES: tuple[str, ...] = (
    "artifacts/experiment/final_test_v2",
    "registries/",
    "formal/",
    "tests/phase7/test_decision_margin_diagnostic.py",
)

WRITE_MODE = "STAGED_TRANSACTIONAL_MATERIALIZATION"
FRESH_ATOMIC_RENAME = "FRESH_ATOMIC_RENAME"
BACKUP_SWAP_WITH_ROLLBACK = "BACKUP_SWAP_WITH_ROLLBACK"

STAGE_Q_SUMMARY_NAME = "STAGE_Q_SCREENING_SUMMARY.csv"
STAGE_Q_ROOT = (
    C.ROOT / "artifacts" / "paper_results_v2_final_test_rmb" / "stage_q_sensitivity"
)
#: Frozen Stage-x-q column -> this descriptor's column. The published summary
#: names the retained consequence value ``retained_value`` and the attention
#: loss ``attention_loss``; no ``retained_consequence_value`` field exists
#: anywhere in this repository and none is fabricated here.
STAGE_Q_FIELD_ALIASES: dict[str, str] = {
    "N_supported": "N_supported",
    "K": "K",
    "changed_positions": "delay_consequence_changed_positions",
    "intersection_count": "delay_consequence_intersection_count",
    "overlap_rate": "delay_consequence_overlap_rate",
    "retained_value": "retained_value",
    "attention_loss": "attention_loss",
}
#: Requested diagnostic field -> the frozen column it is read from.
REQUESTED_FIELD_SOURCES: dict[str, str] = {
    "retained_consequence_value": "STAGE_Q_SCREENING_SUMMARY.retained_value",
    "L_att": "STAGE_Q_SCREENING_SUMMARY.attention_loss",
}

RECOVERY_EVENT_KEYS: tuple[str, ...] = (
    "MISSED_ACTIVATION",
    "FALSE_ACTIVATION",
    "UNDER_RECOVERY",
    "OVER_RECOVERY",
)


@dataclass(frozen=True)
class ComparisonSpec:
    """One pairwise information increment: alternative -> reference."""

    comparison_id: str
    alternative_variant: str
    reference_variant: str
    mechanism: str
    headline_note: str


PAIRWISE_COMPARISONS: tuple[ComparisonSpec, ...] = (
    ComparisonSpec(
        comparison_id="CURRENT_JOINT__TO__HISTORY_JOINT",
        alternative_variant="CURRENT_JOINT",
        reference_variant="HISTORY_JOINT",
        mechanism="TEMPORAL_HISTORY_INFORMATION_INCREMENT",
        headline_note="SHARES_THE_HEADLINE_REFERENCE_HISTORY_JOINT",
    ),
    ComparisonSpec(
        comparison_id="HISTORY_POINT__TO__HISTORY_MARGINAL",
        alternative_variant="HISTORY_POINT",
        reference_variant="HISTORY_MARGINAL",
        mechanism="MARGINAL_UNCERTAINTY_INCREMENT",
        headline_note=(
            "DIAGNOSTIC_ONLY_NOT_THE_HEADLINE_HISTORY_POINT_MINUS_HISTORY_JOINT"
        ),
    ),
    ComparisonSpec(
        comparison_id="HISTORY_MARGINAL__TO__HISTORY_JOINT",
        alternative_variant="HISTORY_MARGINAL",
        reference_variant="HISTORY_JOINT",
        mechanism="CROSS_STATE_DEPENDENCE_INCREMENT",
        headline_note="SHARES_THE_HEADLINE_REFERENCE_HISTORY_JOINT",
    ),
)


class CheckFailure(RuntimeError):
    """A frozen-contract regression check or a diagnostic gate failed."""


def _require(condition: bool, code: str, detail: Any = None) -> None:
    if not condition:
        raise CheckFailure(f"{code}: {detail}")


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=C.ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_head() -> str:
    try:
        return _git("rev-parse", "HEAD")
    except Exception:  # pragma: no cover - provenance only
        return "UNKNOWN"


def _rename(source: Path, target: Path) -> None:
    """Single filesystem rename; the transaction's only mutation primitive."""

    source.rename(target)


# ----------------------------------------------------------------------
# pure decision-margin primitives
# ----------------------------------------------------------------------
def ranked_reference_scores(decision: Any) -> tuple[tuple[str, float], ...]:
    """Frozen ``P^r`` per chain in frozen rank order, replayed and validated.

    The sealed decision stores every eligible candidate with its ``score`` and
    ``rank``. The order is re-derived with the frozen Stage-I key
    ``(-score, episode_id, node_id)`` and must reproduce the stored order; a
    mismatch means a ranking-direction or tie-breaking error, not a finding.
    """

    entries = sorted(decision.entries, key=lambda item: int(item.rank))
    _require(
        [int(entry.rank) for entry in entries] == list(range(1, len(entries) + 1)),
        "DECISION_MARGIN_BLOCKED_STAGE1_AUTHORITY_REPLAY",
        {"reason": "RANK_SEQUENCE_NOT_CONTIGUOUS"},
    )
    replayed = sorted(
        entries,
        key=lambda item: (-float(item.score), item.episode_id, item.node_id),
    )
    _require(
        [entry.node_id for entry in replayed] == [entry.node_id for entry in entries],
        "DECISION_MARGIN_BLOCKED_STAGE1_AUTHORITY_REPLAY",
        {
            "reason": "RANK_ORDER_REPLAY_MISMATCH",
            "stored": [entry.node_id for entry in entries],
            "replayed": [entry.node_id for entry in replayed],
        },
    )
    return tuple((entry.node_id, float(entry.score)) for entry in entries)


def selected_node_ids(decision: Any) -> tuple[str, ...]:
    """Frozen shortlist in frozen rank order, cross-checked against the flag."""

    ordered = sorted(decision.entries, key=lambda item: int(item.rank))
    selected = tuple(entry.node_id for entry in ordered if entry.selected)
    flagged = tuple(entry.node_id for entry in ordered if bool(entry.selected))
    _require(
        selected == flagged,
        "DECISION_MARGIN_BLOCKED_STAGE1_AUTHORITY_REPLAY",
        {"reason": "SELECTION_FLAG_INCONSISTENT"},
    )
    return selected


def stage1_pair_margin(
    *,
    reference_ranking: Sequence[tuple[str, float]],
    alternative_scores: Mapping[str, float],
    k: int,
) -> dict[str, Any]:
    """``m``, ``delta``, ``eps``, ``span`` and the reference cutoff identities."""

    total = len(reference_ranking)
    if total == 0:
        return {
            "N_common": 0,
            "K": 0,
            "reference_kth_chain": None,
            "reference_kplus1_chain": None,
            "reference_kth_score": None,
            "reference_kplus1_score": None,
            "cutoff_margin": None,
            "epsilon_inf": None,
            "perturbation_span": None,
            "certificate_slack": None,
            "reference_scores": {},
            "priority_delta": {},
        }
    reference_scores = dict(reference_ranking)
    deltas = {
        node_id: float(alternative_scores[node_id]) - reference_scores[node_id]
        for node_id, _score in reference_ranking
    }
    epsilon = max(abs(value) for value in deltas.values())
    span = max(deltas.values()) - min(deltas.values())

    has_next = 0 < k < total
    kth_chain = reference_ranking[k - 1][0] if 0 < k <= total else None
    kth_score = reference_ranking[k - 1][1] if 0 < k <= total else None
    kplus1_chain = reference_ranking[k][0] if has_next else None
    kplus1_score = reference_ranking[k][1] if has_next else None
    margin = None if not has_next else kth_score - kplus1_score
    slack = None if margin is None else margin - 2.0 * epsilon
    return {
        "N_common": total,
        "K": int(k),
        "reference_kth_chain": kth_chain,
        "reference_kplus1_chain": kplus1_chain,
        "reference_kth_score": kth_score,
        "reference_kplus1_score": kplus1_score,
        "cutoff_margin": margin,
        "epsilon_inf": epsilon,
        "perturbation_span": span,
        "certificate_slack": slack,
        "reference_scores": reference_scores,
        "priority_delta": deltas,
    }


def stage1_certificate_status(
    *,
    has_common_cohort: bool,
    margin: float | None,
    slack: float | None,
    tolerance: float = MARGIN_TOLERANCE,
) -> str:
    """The four-valued Stage-I certificate status.

    ``NO_STRICT_REFERENCE_MARGIN`` covers both a zero or negative cutoff margin
    and a cohort too small to expose a ``(K + 1)``-th chain: in neither case does
    a strict reference margin exist, which is all the certificate would need.
    """

    if not has_common_cohort:
        return ABSTAIN_NO_COMMON_SUPPORT
    if margin is None or slack is None:
        return NO_STRICT_REFERENCE_MARGIN
    if margin <= tolerance:
        return NO_STRICT_REFERENCE_MARGIN
    if slack > tolerance:
        return CERTIFIED_STABLE
    return NOT_CERTIFIED


def stage1_decision_outcome(
    *,
    reference_selected: Sequence[str],
    alternative_selected: Sequence[str],
) -> dict[str, Any]:
    """Observed shortlist agreement between the two frozen decisions."""

    reference = set(reference_selected)
    alternative = set(alternative_selected)
    entered = tuple(sorted(alternative - reference))
    displaced = tuple(sorted(reference - alternative))
    return {
        "shortlist_identical": reference == alternative,
        "intersection_count": len(reference & alternative),
        "changed_positions": len(entered),
        "entered_count": len(entered),
        "displaced_count": len(displaced),
        "entered": list(entered),
        "displaced": list(displaced),
    }


def alternative_boundary_separation(
    *,
    reference_selected: Sequence[str],
    alternative_scores: Mapping[str, float],
    cohort: Sequence[str],
) -> dict[str, Any]:
    """``min_{i in H^r} P^a_i - max_{j not in H^r} P^a_j`` (descriptive only)."""

    reference = set(reference_selected)
    members = [node_id for node_id in cohort if node_id in reference]
    outsiders = [node_id for node_id in cohort if node_id not in reference]
    if not members or not outsiders:
        return {
            "alternative_boundary_separation": None,
            "reason": "BOUNDARY_SEPARATION_UNDEFINED_ON_EMPTY_SIDE",
        }
    lowest_member = min(float(alternative_scores[node_id]) for node_id in members)
    highest_outsider = max(float(alternative_scores[node_id]) for node_id in outsiders)
    return {
        "alternative_boundary_separation": lowest_member - highest_outsider,
        "reason": None,
    }


def reference_optimum(table: Sequence[tuple[float, float]]) -> tuple[float, float]:
    """Frozen Stage-II action selector: objective ties resolve to smaller ``u``."""

    _require(
        bool(table),
        "DECISION_MARGIN_BLOCKED_OBJECTIVE_REPLAY_MISMATCH",
        {"reason": "EMPTY_OBJECTIVE_TABLE"},
    )
    u_star, j_star = min(table, key=lambda item: (float(item[1]), float(item[0])))
    return float(u_star), float(j_star)


def second_best_action(
    table: Sequence[tuple[float, float]], u_star: float
) -> tuple[float, float] | None:
    """Best feasible action other than ``u_star`` under the frozen tie-break."""

    others = [item for item in table if float(item[0]) != float(u_star)]
    if not others:
        return None
    u_second, j_second = min(others, key=lambda item: (float(item[1]), float(item[0])))
    return float(u_second), float(j_second)


def stage2_pair_margin(
    *,
    reference_table: Sequence[tuple[float, float]],
    alternative_table: Sequence[tuple[float, float]],
) -> dict[str, Any]:
    """``gamma``, ``eps^II``, ``span^II``, slack and both optima."""

    reference_grid = tuple(float(u) for u, _value in reference_table)
    alternative_grid = tuple(float(u) for u, _value in alternative_table)
    if not reference_grid or not alternative_grid:
        return {
            "common_feasible_set": (),
            "reference_best_u": None,
            "reference_best_objective": None,
            "reference_second_best_u": None,
            "reference_second_best_objective": None,
            "alternative_best_u": None,
            "alternative_best_objective": None,
            "action_gap": None,
            "epsilon_inf": None,
            "perturbation_span": None,
            "certificate_slack": None,
            "objective_delta": {},
        }
    common = tuple(sorted(set(reference_grid) & set(alternative_grid)))
    _require(
        bool(common),
        "DECISION_MARGIN_BLOCKED_OBJECTIVE_REPLAY_MISMATCH",
        {"reason": "EMPTY_COMMON_FEASIBLE_SET"},
    )
    reference_by_u = {float(u): float(value) for u, value in reference_table}
    alternative_by_u = {float(u): float(value) for u, value in alternative_table}
    reference_common = tuple((u, reference_by_u[u]) for u in common)
    alternative_common = tuple((u, alternative_by_u[u]) for u in common)

    u_ref, j_ref = reference_optimum(reference_common)
    u_alt, j_alt = reference_optimum(alternative_common)
    second = second_best_action(reference_common, u_ref)
    gamma = None if second is None else second[1] - j_ref
    deltas = {u: alternative_by_u[u] - reference_by_u[u] for u in common}
    epsilon = max(abs(value) for value in deltas.values())
    span = max(deltas.values()) - min(deltas.values())
    slack = None if gamma is None else gamma - 2.0 * epsilon
    return {
        "common_feasible_set": common,
        "reference_best_u": u_ref,
        "reference_best_objective": j_ref,
        "reference_second_best_u": None if second is None else second[0],
        "reference_second_best_objective": None if second is None else second[1],
        "alternative_best_u": u_alt,
        "alternative_best_objective": j_alt,
        "action_gap": gamma,
        "epsilon_inf": epsilon,
        "perturbation_span": span,
        "certificate_slack": slack,
        "objective_delta": deltas,
    }


def stage2_certificate_status(
    *,
    has_common_actions: bool,
    action_gap: float | None,
    slack: float | None,
    tolerance: float = MARGIN_TOLERANCE,
) -> str:
    """The four-valued Stage-II certificate status.

    ``NO_STRICT_REFERENCE_MARGIN`` covers a zero action gap, which arises even
    when the frozen tie-break still reports a unique ``u*``: no strict objective
    margin exists, so no certificate can be issued.
    """

    if not has_common_actions:
        return ABSTAIN_NO_COMMON_SUPPORT
    if action_gap is None or slack is None:
        return NO_STRICT_REFERENCE_MARGIN
    if action_gap <= tolerance:
        return NO_STRICT_REFERENCE_MARGIN
    if slack > tolerance:
        return CERTIFIED_STABLE
    return NOT_CERTIFIED


def certified_stable_requires_unchanged(
    *,
    certificate_status: str,
    reference_value: Any,
    alternative_value: Any,
    context: Mapping[str, Any],
) -> None:
    """A ``CERTIFIED_STABLE`` certificate must correspond to a stable decision.

    Only this direction is asserted. ``NOT_CERTIFIED`` carries no implication
    about the observed decision and is never checked against it.
    """

    if certificate_status != CERTIFIED_STABLE:
        return
    _require(
        reference_value == alternative_value,
        "DECISION_MARGIN_BLOCKED_CERTIFIED_STABLE_DECISION_CHANGED",
        {
            **dict(context),
            "certificate_status": certificate_status,
            "reference_value": reference_value,
            "alternative_value": alternative_value,
        },
    )


def certificate_class_counts(
    rows: Sequence[Mapping[str, Any]], *, changed_key: str
) -> dict[str, int]:
    """The five status/outcome classes of the certificate counts."""

    certified_stable = 0
    not_certified_but_stable = 0
    not_certified_and_changed = 0
    no_strict_reference_margin = 0
    abstain = 0
    for row in rows:
        status = str(row["certificate_status"])
        _require(
            status in ALLOWED_CERTIFICATE_STATUSES,
            "DECISION_MARGIN_STATUS_OUTSIDE_ALLOWED_SET",
            status,
        )
        changed = bool(row[changed_key])
        if status == CERTIFIED_STABLE:
            certified_stable += 1
        elif status == NOT_CERTIFIED:
            if changed:
                not_certified_and_changed += 1
            else:
                not_certified_but_stable += 1
        elif status == NO_STRICT_REFERENCE_MARGIN:
            no_strict_reference_margin += 1
        else:
            abstain += 1
    return {
        "N_certified_stable": certified_stable,
        "N_not_certified_but_stable": not_certified_but_stable,
        "N_not_certified_and_changed": not_certified_and_changed,
        "N_no_strict_reference_margin": no_strict_reference_margin,
        "N_abstain": abstain,
    }


def recovery_event_flags(u_ref: float, u_alt: float) -> dict[str, bool]:
    """Frozen Stage-II action taxonomy, mirrored from ``model.M4.evaluation``."""

    flags = {
        "ref_activation": u_ref > 0.0,
        "alt_activation": u_alt > 0.0,
        "missed_activation": False,
        "false_activation": False,
        "under_recovery": False,
        "over_recovery": False,
    }
    if u_ref > 0.0 and u_alt == 0.0:
        flags["missed_activation"] = True
    elif u_ref == 0.0 and u_alt > 0.0:
        flags["false_activation"] = True
    elif u_ref > 0.0 and u_alt > 0.0 and u_alt < u_ref:
        flags["under_recovery"] = True
    elif u_ref > 0.0 and u_alt > 0.0 and u_alt > u_ref:
        flags["over_recovery"] = True
    return flags


# ----------------------------------------------------------------------
# frozen inputs
# ----------------------------------------------------------------------
def _verify_epoch_identity(epoch_root: Path) -> dict[str, Any]:
    """Verify the sealed epoch provenance records used for identity only."""

    seal = _load(epoch_root / "EPOCH_SEAL.json")
    _require(
        seal.get("status") == "SEALED_AUDIT_PASS"
        and seal.get("final_test_complete") is True
        and seal.get("paper_results_frozen") is True
        and seal.get("scientific_definition_changed") is False,
        "DECISION_MARGIN_EPOCH_SEAL_INVALID",
        {
            key: seal.get(key)
            for key in (
                "status",
                "final_test_complete",
                "paper_results_frozen",
                "scientific_definition_changed",
            )
        },
    )
    _require(
        _sha256_file(epoch_root / "FINAL_TEST_EXECUTION_RESULT.json")
        == seal.get("execution_result_sha256"),
        "DECISION_MARGIN_EPOCH_EXECUTION_RESULT_IDENTITY",
    )
    _require(
        _sha256_file(epoch_root / "POST_EXECUTION_AUDIT.json")
        == seal.get("post_execution_audit_json_sha256"),
        "DECISION_MARGIN_EPOCH_POST_AUDIT_IDENTITY",
    )
    return {
        "epoch_seal_status": seal.get("status"),
        "epoch_seal_file_sha256": _sha256_file(epoch_root / "EPOCH_SEAL.json"),
        "execution_result_sha256": seal.get("execution_result_sha256"),
        "post_execution_audit_sha256": seal.get("post_execution_audit_json_sha256"),
    }


CHECKPOINT_INPUTS: tuple[str, ...] = (
    S.ATTENTION_DECISIONS,
    S.CANONICAL_NODES,
    S.M4_COMPARISONS,
    S.RECOVERY_DECISIONS,
    S.REFERENCE_RECOVERY_COHORT,
    S.STATE_VARIANTS,
)

EPOCH_INPUTS: tuple[str, ...] = (
    "EPOCH_SEAL.json",
    "FINAL_TEST_EXECUTION_RESULT.json",
    "POST_EXECUTION_AUDIT.json",
)


def _frozen_service_inputs() -> dict[str, Path]:
    from .executor.services import (
        CURRENT_CHECKPOINT,
        CURRENT_MANIFEST,
        H16_CHECKPOINT,
        H16_MANIFEST,
        M2_REGISTRY_PATH,
        TAIL_MANIFEST_PATH,
    )

    return {
        "H16_CHECKPOINT": H16_CHECKPOINT,
        "H16_MANIFEST": H16_MANIFEST,
        "CURRENT_CHECKPOINT": CURRENT_CHECKPOINT,
        "CURRENT_MANIFEST": CURRENT_MANIFEST,
        "TAIL_MANIFEST_PATH": TAIL_MANIFEST_PATH,
        "M2_REGISTRY_PATH": M2_REGISTRY_PATH,
        "TRAIN_SUPPORT_SUMMARY_PATH": C.TRAIN_SUPPORT_SUMMARY_PATH,
    }


def collect_input_paths(
    epoch_root: Path, *, stage_q_summary: Path | None
) -> dict[str, str]:
    """Every frozen input is path- and hash-recorded in the manifest."""

    paths: dict[str, str] = {
        f"checkpoints/{stage}": str(epoch_root / "checkpoints" / f"{stage}.json")
        for stage in CHECKPOINT_INPUTS
    }
    paths.update({f"epoch/{name}": str(epoch_root / name) for name in EPOCH_INPUTS})
    paths.update(
        {
            f"frozen_service/{name}": str(path)
            for name, path in _frozen_service_inputs().items()
        }
    )
    if stage_q_summary is not None and Path(stage_q_summary).is_file():
        paths["stage_q_frozen_summary"] = str(stage_q_summary)
    return paths


def discover_stage_q_summary(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return Path(explicit) if Path(explicit).is_file() else None
    candidate = STAGE_Q_ROOT / STAGE_Q_SUMMARY_NAME
    return candidate if candidate.is_file() else None


# ----------------------------------------------------------------------
# Gate A - repository authority and output collision
# ----------------------------------------------------------------------
def gate_repository_authority(*, out_dir: Path) -> dict[str, Any]:
    """Branch, head, worktree classification and residue checks.

    A tracked modification that already exists when the run starts is recorded
    rather than fatal: other tooling in this repository legitimately refreshes
    its own provenance files, so a pristine worktree is not a stable invariant.
    What must hold is that *this* run introduces no tracked modification at all
    and that no protected scientific path is dirty in either direction.
    """

    try:
        branch = _git("rev-parse", "--abbrev-ref", "HEAD")
        head_start = _git("rev-parse", "HEAD")
        porcelain = _git("status", "--porcelain")
    except Exception as error:  # pragma: no cover - environment dependent
        raise CheckFailure(
            f"DECISION_MARGIN_BLOCKED_REPO_AUTHORITY: git unavailable: {error}"
        ) from error

    tracked_modifications = [
        entry[3:].strip()
        for entry in porcelain.splitlines()
        if entry and not entry.startswith("??")
    ]
    protected = [
        path
        for path in tracked_modifications
        if any(path.startswith(prefix) for prefix in PROTECTED_TRACKED_PREFIXES)
    ]
    _require(
        not protected,
        "DECISION_MARGIN_BLOCKED_REPO_AUTHORITY",
        {"reason": "PROTECTED_TRACKED_FILE_MODIFIED", "entries": protected},
    )
    preexisting_untracked = [
        entry[3:].strip() for entry in porcelain.splitlines() if entry.startswith("??")
    ]
    staging = staging_path(out_dir)
    previous = previous_path(out_dir)
    _require(
        not staging.exists(),
        "DECISION_MARGIN_BLOCKED_STAGING_RESIDUE",
        {"staging_path": str(staging)},
    )
    _require(
        not previous.exists(),
        "DECISION_MARGIN_BLOCKED_MATERIALIZATION_RESIDUE",
        {"previous_path": str(previous)},
    )
    return {
        "repo_root": str(C.ROOT),
        "branch": branch,
        "head_start": head_start,
        "preexisting_untracked": preexisting_untracked,
        "tracked_modifications_start": tracked_modifications,
        "tracked_modifications_start_note": (
            "PRE_EXISTING_TRACKED_MODIFICATIONS_FROM_OTHER_TOOLING_ARE_RECORDED_"
            "NOT_FATAL_THIS_RUN_MUST_INTRODUCE_NONE"
        ),
        "protected_tracked_modifications": protected,
        "protected_tracked_prefixes": list(PROTECTED_TRACKED_PREFIXES),
    }


def check_output_collision(
    *,
    out_dir: Path,
    head: str,
    input_hashes: Mapping[str, str],
    diagnostic_source_sha256: str | None,
) -> dict[str, Any]:
    """An existing result is only regenerated by an identical run.

    Identical means the same git head, the same input hashes **and** the same
    diagnostic source hash: a human edit of this module must never silently
    overwrite an earlier result.
    """

    manifest_path = out_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        _require(
            not out_dir.exists(),
            "DECISION_MARGIN_BLOCKED_OUTPUT_COLLISION",
            {"reason": "OUTPUT_DIRECTORY_WITHOUT_MANIFEST", "out_dir": str(out_dir)},
        )
        return {"collision_check": "NO_PREVIOUS_RESULT", "regeneration": False}

    previous = _load(manifest_path)
    mismatches: dict[str, Any] = {}
    if previous.get("git_head") != head:
        mismatches["git_head"] = {"previous": previous.get("git_head"), "current": head}
    previous_inputs = dict(previous.get("input_artifact_hashes", {}))
    if previous_inputs != dict(input_hashes):
        mismatches["input_artifact_hashes"] = {
            "changed_keys": sorted(
                key
                for key in set(previous_inputs) | set(input_hashes)
                if previous_inputs.get(key) != input_hashes.get(key)
            )
        }
    if previous.get("diagnostic_source_sha256") != diagnostic_source_sha256:
        mismatches["diagnostic_source_sha256"] = {
            "previous": previous.get("diagnostic_source_sha256"),
            "current": diagnostic_source_sha256,
        }
    _require(
        not mismatches,
        "DECISION_MARGIN_BLOCKED_OUTPUT_COLLISION",
        {
            "reason": "EXISTING_RESULT_FROM_A_DIFFERENT_RUN",
            "out_dir": str(out_dir),
            "mismatches": mismatches,
        },
    )
    return {
        "collision_check": "IDENTICAL_PRIOR_RUN",
        "regeneration": True,
        "previous_git_head": previous.get("git_head"),
        "previous_run_timestamp": previous.get("run_timestamp"),
    }


# ----------------------------------------------------------------------
# Gate B - Stage-I authority replay
# ----------------------------------------------------------------------
def stage1_authority_replay(
    *, attention: Mapping[str, Any], m4: Mapping[str, Any]
) -> dict[str, Any]:
    """Cohort, capacity, ranking and score-provenance checks at ``q = 0.10``."""

    eligible_by_stage: dict[str, tuple[str, ...]] = {}
    for stage in STAGES:
        eligible: dict[str, tuple[str, ...]] = {}
        for row in attention["rows"]:
            if row["stage"] != stage or abs(float(row["q"]) - NOMINAL_Q) > 1e-12:
                continue
            _require(
                int(row["abstaining_node_count"]) == 0,
                "DECISION_MARGIN_BLOCKED_STAGE1_AUTHORITY_REPLAY",
                {"reason": "UNEXPECTED_STAGE1_ABSTENTION", "stage": stage},
            )
            eligible[str(row["variant"])] = tuple(
                str(value) for value in row["eligible_candidate_node_ids"]
            )
        _require(
            len(set(eligible.values())) == 1,
            "DECISION_MARGIN_BLOCKED_STAGE1_AUTHORITY_REPLAY",
            {"reason": "ELIGIBLE_SETS_DIFFER_ACROSS_VARIANTS", "stage": stage},
        )
        common = next(iter(eligible.values()))
        _require(
            len(common) == EXPECTED_STAGE1_N[stage],
            "DECISION_MARGIN_BLOCKED_STAGE1_AUTHORITY_REPLAY",
            {
                "reason": "N_SUPPORTED_MISMATCH",
                "stage": stage,
                "observed": len(common),
                "expected": EXPECTED_STAGE1_N[stage],
            },
        )
        _require(
            attention_capacity_k(NOMINAL_Q, len(common)) == EXPECTED_STAGE1_K[stage],
            "DECISION_MARGIN_BLOCKED_STAGE1_AUTHORITY_REPLAY",
            {"reason": "CAPACITY_RULE_MISMATCH", "stage": stage},
        )
        eligible_by_stage[stage] = common

    provenance = score_provenance_check(attention=attention, m4=m4)
    return {
        "eligible_candidate_node_ids_by_stage": {
            stage: list(eligible_by_stage[stage]) for stage in STAGES
        },
        "expected_n_by_stage": {stage: EXPECTED_STAGE1_N[stage] for stage in STAGES},
        "expected_k_by_stage": {stage: EXPECTED_STAGE1_K[stage] for stage in STAGES},
        "abstaining_node_count": 0,
        "eligible_sets_identical_across_variants": True,
        "pairwise_common_support_equals_each_variant_eligible_set": True,
        "no_support_backfill": True,
        "score_provenance": provenance,
    }


def score_provenance_check(
    *, attention: Mapping[str, Any], m4: Mapping[str, Any]
) -> dict[str, Any]:
    """``M4_COMPARISONS.bootstrap_rows`` as a second source for ``P^C``.

    The rows are never a computational authority: they only corroborate the
    scores already frozen in ``ATTENTION_DECISIONS``. Repeated occurrences of one
    ``(variant, node_id)`` score must agree within the frozen tolerance; a spread
    beyond it is a provenance conflict and blocks the run rather than being
    resolved by deduplication.
    """

    rows = m4["attention"]["bootstrap_rows"]
    _require(
        isinstance(rows, dict),
        "DECISION_MARGIN_BLOCKED_STAGE1_AUTHORITY_REPLAY",
        {"reason": "BOOTSTRAP_ROWS_NOT_KEYED_BY_VARIANT"},
    )
    observed: dict[tuple[str, str], list[float]] = {}
    for variant, variant_rows in rows.items():
        for row in variant_rows:
            node_id = str(row["node_id"])
            observed.setdefault((REFERENCE_VARIANT, node_id), []).append(
                float(row["reference_score"])
            )
            observed.setdefault((str(variant), node_id), []).append(
                float(row["comparator_score"])
            )

    conflicts = [
        {
            "variant": key[0],
            "node_id": key[1],
            "min": min(values),
            "max": max(values),
            "occurrences": len(values),
        }
        for key, values in observed.items()
        if max(values) - min(values) > REPLAY_TOLERANCE
    ]
    if conflicts:
        raise CheckFailure(
            "BLOCKED_SCORE_PROVENANCE_CONFLICT: "
            + json.dumps({"conflicts": conflicts[:20]}, sort_keys=True)
        )

    resolved = {key: values[0] for key, values in observed.items()}
    mismatches: list[dict[str, Any]] = []
    compared = 0
    for row in attention["rows"]:
        if abs(float(row["q"]) - NOMINAL_Q) > 1e-12:
            continue
        decision = attention_decision_from_payload(row["consequence_decision"])
        for entry in decision.entries:
            key = (str(row["variant"]), entry.node_id)
            expected_score = resolved.get(key)
            if expected_score is None:
                mismatches.append(
                    {"variant": key[0], "node_id": key[1], "reason": "MISSING"}
                )
                continue
            compared += 1
            if abs(float(entry.score) - expected_score) > REPLAY_TOLERANCE:
                mismatches.append(
                    {
                        "variant": key[0],
                        "node_id": key[1],
                        "reason": "SCORE_MISMATCH",
                        "decision_score": float(entry.score),
                        "bootstrap_score": expected_score,
                    }
                )
    _require(
        not mismatches,
        "DECISION_MARGIN_BLOCKED_STAGE1_AUTHORITY_REPLAY",
        {"reason": "SCORE_PROVENANCE_MISMATCH", "mismatches": mismatches[:20]},
    )
    return {
        "source": "M4_COMPARISONS.bootstrap_rows",
        "computational_authority": False,
        "role": "SECOND_SOURCE_VALIDATION_ONLY",
        "occurrences": sum(len(values) for values in observed.values()),
        "unique_variant_node_keys": len(resolved),
        "scores_compared": compared,
        "conflicts": 0,
        "mismatches": 0,
    }


# ----------------------------------------------------------------------
# Gate C - Stage-II objective replay
# ----------------------------------------------------------------------
def recovery_rows_by_variant(
    recovery_decisions: Mapping[str, Any], variant: str
) -> dict[str, Mapping[str, Any]]:
    return {
        str(row["node_id"]): row
        for row in recovery_decisions["rows"]
        if row["variant"] == variant
    }


def stage2_objective_replay(
    *,
    nodes_payload: Mapping[str, Any],
    state_variants: Mapping[str, Any],
    recovery_decisions: Mapping[str, Any],
    reference_cohort: Mapping[str, Any],
) -> dict[str, Any]:
    """Re-materialize every frozen objective curve and replay every decision.

    Level 1 replays the sealed ``HISTORY_JOINT`` objective curve point by point.
    Level 2 replays the frozen action selector for all four primary variants and
    must reproduce every sealed ``u*``. Either level failing blocks the run
    before any decision-margin quantity is produced.
    """

    from .executor.nodes import nodes_by_id
    from .executor.services import binding_from_node, load_frozen_services
    from .executor.state_variants import state_sets_by_node

    nodes = nodes_by_id(nodes_payload)
    services = load_frozen_services()
    headroom = services.headroom_summary
    policy = RecoveryPolicy(lambda_policy=C.NOMINAL_LAMBDA).validate()
    cohort = tuple(
        str(value) for value in reference_cohort["stage2_actionable_node_ids"]
    )

    state_sets = {
        variant: state_sets_by_node(state_variants, variant)
        for variant in S.PRIMARY_STATE_VARIANTS
    }
    sealed_rows = {
        variant: recovery_rows_by_variant(recovery_decisions, variant)
        for variant in S.PRIMARY_STATE_VARIANTS
    }
    curves: dict[str, dict[str, tuple[tuple[float, float], ...]]] = {
        variant: {} for variant in S.PRIMARY_STATE_VARIANTS
    }
    level1_points = 0
    level1_expected = 0
    level1_max_deviation = 0.0
    level2_cases = 0
    level2_max_deviation = 0.0
    mismatches: list[dict[str, Any]] = []
    reference_objectives = recovery_decisions["reference_objectives"]

    for node_id in cohort:
        node = nodes.get(node_id)
        _require(
            node is not None,
            "DECISION_MARGIN_BLOCKED_OBJECTIVE_REPLAY_MISMATCH",
            {"reason": "NODE_NOT_MATERIALIZED", "node_id": node_id},
        )
        context = TransitionContext(
            sobt_minutes=float(node.sobt_minutes),
            turnaround_lower_bound_minutes=float(headroom.turnaround_lower_bound_q),
        )
        service = services.consequence_service({node.node_id: binding_from_node(node)})
        for variant in S.PRIMARY_STATE_VARIANTS:
            state_set = state_sets[variant].get(node_id)
            _require(
                state_set is not None,
                "DECISION_MARGIN_BLOCKED_OBJECTIVE_REPLAY_MISMATCH",
                {"level": 2, "reason": "STATE_SET_MISSING", "node_id": node_id, "variant": variant},
            )
            table = objective_by_grid(
                state_set,
                context=context,
                service=service,
                u_max=headroom.u_max,
                policy=policy,
                floor_to_minutes=headroom.floor_to_minutes,
            )
            curves[variant][node_id] = table

            sealed = sealed_rows[variant].get(node_id)
            _require(
                sealed is not None and sealed.get("decision") is not None,
                "DECISION_MARGIN_BLOCKED_OBJECTIVE_REPLAY_MISMATCH",
                {
                    "level": 2,
                    "reason": "SEALED_DECISION_MISSING",
                    "node_id": node_id,
                    "variant": variant,
                },
            )
            decision = recovery_decision_from_payload(sealed["decision"])
            replay_u, replay_j = reference_optimum(table)
            replay_zero = float(table[0][1])
            near_tie = sum(
                1
                for _u, value in table
                if value <= replay_j + C.M3_NUMERICAL_COMPARISON_TOLERANCE
            )
            level2_cases += 1
            if (
                replay_u != float(decision.u_star)
                or replay_zero != float(decision.j_zero)
                or replay_j != float(decision.j_star)
            ):
                mismatches.append(
                    {
                        "level": 2,
                        "reason": "SEALED_DECISION_NOT_REPRODUCED",
                        "node_id": node_id,
                        "variant": variant,
                        "replay": [replay_u, replay_j, replay_zero],
                        "sealed": [
                            float(decision.u_star),
                            float(decision.j_star),
                            float(decision.j_zero),
                        ],
                    }
                )
                continue
            level2_max_deviation = max(
                level2_max_deviation,
                abs(replay_j - float(decision.j_star)),
                abs(replay_zero - float(decision.j_zero)),
            )
            if bool(decision.tie_break_applied) != (near_tie > 1) or int(
                decision.near_tie_candidate_count
            ) != near_tie:
                mismatches.append(
                    {
                        "level": 2,
                        "reason": "TIE_DIAGNOSTIC_NOT_REPRODUCED",
                        "node_id": node_id,
                        "variant": variant,
                        "replayed_near_tie_count": near_tie,
                        "sealed_near_tie_count": int(decision.near_tie_candidate_count),
                    }
                )
                continue
            if float(decision.u_max or 0.0) != float(headroom.u_max):
                mismatches.append(
                    {
                        "level": 2,
                        "reason": "U_MAX_MISMATCH",
                        "node_id": node_id,
                        "variant": variant,
                    }
                )
                continue
            if variant != REFERENCE_VARIANT:
                continue

            sealed_table = reference_objectives.get(node_id)
            _require(
                sealed_table is not None,
                "DECISION_MARGIN_BLOCKED_OBJECTIVE_REPLAY_MISMATCH",
                {
                    "level": 1,
                    "reason": "SEALED_REFERENCE_CURVE_MISSING",
                    "node_id": node_id,
                },
            )
            sealed_pairs = [
                (float(action), float(value))
                for action, value in sealed_table["objective_by_action"]
            ]
            if tuple(u for u, _value in sealed_pairs) != tuple(u for u, _value in table):
                mismatches.append(
                    {"level": 1, "reason": "GRID_IDENTITY_MISMATCH", "node_id": node_id}
                )
                continue
            for (u_sealed, value_sealed), (_u, value_replay) in zip(table, sealed_pairs):
                level1_points += 1
                deviation = abs(value_replay - value_sealed)
                level1_max_deviation = max(level1_max_deviation, deviation)
                if deviation > REPLAY_TOLERANCE:
                    mismatches.append(
                        {
                            "level": 1,
                            "reason": "OBJECTIVE_POINT_MISMATCH",
                            "node_id": node_id,
                            "u": u_sealed,
                            "sealed": value_sealed,
                            "replay": value_replay,
                        }
                    )
            level1_expected += len(sealed_pairs)

    if mismatches:
        raise CheckFailure(
            "BLOCKED_OBJECTIVE_REPLAY_MISMATCH: "
            + json.dumps(
                {"level": mismatches[0].get("level"), "mismatches": mismatches[:20]},
                sort_keys=True,
                default=str,
            )
        )
    _require(
        level1_points == level1_expected > 0,
        "DECISION_MARGIN_BLOCKED_OBJECTIVE_REPLAY_MISMATCH",
        {
            "level": 1,
            "reason": "INCOMPLETE_CURVE_REPLAY",
            "points": level1_points,
            "expected": level1_expected,
        },
    )
    _require(
        level2_cases == len(S.PRIMARY_STATE_VARIANTS) * len(cohort),
        "DECISION_MARGIN_BLOCKED_OBJECTIVE_REPLAY_MISMATCH",
        {"level": 2, "reason": "INCOMPLETE_DECISION_REPLAY", "cases": level2_cases},
    )
    return {
        "curves": curves,
        "headroom": headroom,
        "cohort": cohort,
        "level1_points_matched": level1_points,
        "level1_points_expected": level1_expected,
        "level1_max_abs_deviation": level1_max_deviation,
        "level2_cases_matched": level2_cases,
        "level2_cases_expected": len(S.PRIMARY_STATE_VARIANTS) * len(cohort),
        "level2_max_abs_deviation": level2_max_deviation,
    }


# ----------------------------------------------------------------------
# Gate D - Stage-I margins
# ----------------------------------------------------------------------
def _entry_index(attention: Mapping[str, Any]) -> dict[tuple[str, str], Any]:
    """``(variant, node_id) -> entry`` at the nominal capacity, built once."""

    index: dict[tuple[str, str], Any] = {}
    for row in attention["rows"]:
        if abs(float(row["q"]) - NOMINAL_Q) > 1e-12:
            continue
        decision = attention_decision_from_payload(row["consequence_decision"])
        for entry in decision.entries:
            index[(str(row["variant"]), entry.node_id)] = entry
    return index


def build_stage1_diagnostic(
    *,
    attention: Mapping[str, Any],
    m4: Mapping[str, Any],
    decision_time_by_node: Mapping[str, Any],
    cohort_by_stage: Mapping[str, Sequence[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Pairwise Stage-I records and summary at the nominal capacity."""

    entries = _entry_index(attention)
    records: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    anchors: list[dict[str, Any]] = []
    anchor_mismatches: list[dict[str, Any]] = []

    for spec in PAIRWISE_COMPARISONS:
        for stage in STAGES:
            common = tuple(str(value) for value in cohort_by_stage[stage])
            reference_row = _attention_row(attention, spec.reference_variant, stage)
            alternative_row = _attention_row(attention, spec.alternative_variant, stage)
            reference_decision = attention_decision_from_payload(
                reference_row["consequence_decision"]
            )
            alternative_decision = attention_decision_from_payload(
                alternative_row["consequence_decision"]
            )
            context = {"stage": stage, "comparison_id": spec.comparison_id}

            reference_ranking = ranked_reference_scores(reference_decision)
            _require(
                {node_id for node_id, _score in reference_ranking} == set(common)
                and len(reference_ranking) == len(common),
                "DECISION_MARGIN_BLOCKED_STAGE1_AUTHORITY_REPLAY",
                {**context, "reason": "REFERENCE_RANKING_DOES_NOT_COVER_COMMON_SUPPORT"},
            )
            _require(
                tuple(
                    str(value)
                    for value in alternative_row["eligible_candidate_node_ids"]
                )
                == common,
                "DECISION_MARGIN_BLOCKED_STAGE1_AUTHORITY_REPLAY",
                {**context, "reason": "PAIRWISE_COMMON_SUPPORT_BACKFILL"},
            )
            k = attention_capacity_k(NOMINAL_Q, len(common))
            _require(
                k == int(reference_row["k"]) == int(alternative_row["k"]),
                "DECISION_MARGIN_BLOCKED_STAGE1_AUTHORITY_REPLAY",
                {**context, "reason": "PAIRWISE_CAPACITY_MISMATCH"},
            )

            reference_scores = {node_id: score for node_id, score in reference_ranking}
            alternative_scores = {
                entry.node_id: float(entry.score)
                for entry in alternative_decision.entries
            }
            _require(
                set(alternative_scores) == set(reference_scores),
                "DECISION_MARGIN_BLOCKED_STAGE1_AUTHORITY_REPLAY",
                {**context, "reason": "PAIRWISE_SCORE_COVERAGE_MISMATCH"},
            )

            margin = stage1_pair_margin(
                reference_ranking=reference_ranking,
                alternative_scores=alternative_scores,
                k=k,
            )
            status = stage1_certificate_status(
                has_common_cohort=bool(common),
                margin=margin["cutoff_margin"],
                slack=margin["certificate_slack"],
            )
            reference_selected = selected_node_ids(reference_decision)
            alternative_selected = selected_node_ids(alternative_decision)
            outcome = stage1_decision_outcome(
                reference_selected=reference_selected,
                alternative_selected=alternative_selected,
            )
            certified_stable_requires_unchanged(
                certificate_status=status,
                reference_value=reference_selected,
                alternative_value=alternative_selected,
                context=context,
            )
            boundary = alternative_boundary_separation(
                reference_selected=reference_selected,
                alternative_scores=alternative_scores,
                cohort=common,
            )
            pairwise = evaluate_attention_allocation(
                cohort_id=f"{spec.comparison_id}_{STAGE_CLASS[stage]}",
                reference_id=spec.reference_variant,
                comparator_id=spec.alternative_variant,
                reference_decision=reference_decision,
                comparator_decision=alternative_decision,
                reference_priority=reference_scores,
            )
            _require(
                int(pairwise.overlap_count) == outcome["intersection_count"],
                "DECISION_MARGIN_BLOCKED_STAGE1_AUTHORITY_REPLAY",
                {**context, "reason": "PAIRWISE_OVERLAP_IDENTITY_MISMATCH"},
            )

            reference_rank = {
                entry.node_id: int(entry.rank) for entry in reference_decision.entries
            }
            alternative_rank = {
                entry.node_id: int(entry.rank) for entry in alternative_decision.entries
            }
            reference_members = set(reference_selected)
            alternative_members = set(alternative_selected)
            for node_id in common:
                records.append(
                    {
                        "comparison_id": spec.comparison_id,
                        "stage": stage,
                        "stage_class": STAGE_CLASS[stage],
                        "chain_id": entries[(spec.reference_variant, node_id)].chain_id,
                        "node_id": node_id,
                        "episode_id": entries[(spec.reference_variant, node_id)].episode_id,
                        "decision_time": decision_time_by_node.get(node_id),
                        "reference_variant": spec.reference_variant,
                        "alternative_variant": spec.alternative_variant,
                        "q": NOMINAL_Q,
                        "N_common": margin["N_common"],
                        "K": margin["K"],
                        "priority_ref": reference_scores[node_id],
                        "priority_alt": alternative_scores[node_id],
                        "priority_delta": margin["priority_delta"][node_id],
                        "abs_priority_delta": abs(margin["priority_delta"][node_id]),
                        "rank_ref": reference_rank[node_id],
                        "rank_alt": alternative_rank[node_id],
                        "selected_ref": node_id in reference_members,
                        "selected_alt": node_id in alternative_members,
                        "boundary_crossed": (node_id in reference_members)
                        != (node_id in alternative_members),
                    }
                )

            summary.append(
                {
                    "comparison_id": spec.comparison_id,
                    "stage": stage,
                    "stage_class": STAGE_CLASS[stage],
                    "reference_variant": spec.reference_variant,
                    "alternative_variant": spec.alternative_variant,
                    "mechanism": spec.mechanism,
                    "N_common": margin["N_common"],
                    "q": NOMINAL_Q,
                    "K": margin["K"],
                    "reference_kth_chain": margin["reference_kth_chain"],
                    "reference_kplus1_chain": margin["reference_kplus1_chain"],
                    "reference_kth_score": margin["reference_kth_score"],
                    "reference_kplus1_score": margin["reference_kplus1_score"],
                    "cutoff_margin": margin["cutoff_margin"],
                    "epsilon_inf": margin["epsilon_inf"],
                    "perturbation_span": margin["perturbation_span"],
                    "certificate_slack": margin["certificate_slack"],
                    "certificate_status": status,
                    "alternative_boundary_separation": boundary[
                        "alternative_boundary_separation"
                    ],
                    "boundary_separation_reason": boundary["reason"],
                    "shortlist_identical": outcome["shortlist_identical"],
                    "intersection_count": outcome["intersection_count"],
                    "changed_positions": outcome["changed_positions"],
                    "entered_count": outcome["entered_count"],
                    "displaced_count": outcome["displaced_count"],
                    "pairwise_reference_value": pairwise.reference_attention_value,
                    "pairwise_alternative_value": pairwise.comparator_attention_value,
                    "pairwise_attention_loss": pairwise.L_att,
                }
            )

            if spec.reference_variant == REFERENCE_VARIANT:
                anchors.append(
                    _compare_attention_anchor(
                        spec=spec,
                        stage=stage,
                        m4=m4,
                        pairwise=pairwise,
                        outcome=outcome,
                        mismatches=anchor_mismatches,
                    )
                )

    _require(
        not anchor_mismatches,
        "DECISION_MARGIN_BLOCKED_STAGE1_AUTHORITY_REPLAY",
        {"reason": "M4_ATTENTION_ANCHOR_MISMATCH", "mismatches": anchor_mismatches[:20]},
    )
    checks = {
        "anchors": anchors,
        "certified_stable_rows": sum(
            1 for row in summary if row["certificate_status"] == CERTIFIED_STABLE
        ),
        "certified_stable_rows_stable": all(
            bool(row["shortlist_identical"])
            for row in summary
            if row["certificate_status"] == CERTIFIED_STABLE
        ),
        "not_certified_but_stable": sum(
            1
            for row in summary
            if row["certificate_status"] == NOT_CERTIFIED and row["shortlist_identical"]
        ),
    }
    assert_stage1_certificates_hold(records=records, summary=summary)
    return records, summary, checks


def assert_stage1_certificates_hold(
    *,
    records: Sequence[Mapping[str, Any]],
    summary: Sequence[Mapping[str, Any]],
) -> None:
    """Test A at chain level: no ``CERTIFIED_STABLE`` row may move a chain.

    The converse is deliberately not asserted: ``NOT_CERTIFIED`` rows are free
    to be either stable or changed, and both are counted separately.
    """

    for row in summary:
        if row["certificate_status"] != CERTIFIED_STABLE:
            continue
        moved = [
            record["node_id"]
            for record in records
            if record["comparison_id"] == row["comparison_id"]
            and record["stage"] == row["stage"]
            and bool(record["selected_ref"]) != bool(record["selected_alt"])
        ]
        _require(
            not moved,
            "DECISION_MARGIN_BLOCKED_CERTIFIED_STABLE_DECISION_CHANGED",
            {
                "scope": "STAGE_I",
                "comparison_id": row["comparison_id"],
                "stage": row["stage"],
                "moved_chains": moved,
            },
        )


def _compare_attention_anchor(
    *,
    spec: ComparisonSpec,
    stage: str,
    m4: Mapping[str, Any],
    pairwise: Any,
    outcome: Mapping[str, Any],
    mismatches: list[dict[str, Any]],
) -> dict[str, Any]:
    """The sealed M4 attention record for a ``HISTORY_JOINT``-referenced pair."""

    record = m4["attention"]["by_stage"][stage]["comparators"].get(
        spec.alternative_variant
    )
    if record is None or record.get("record_kind") != "EVALUATED":
        mismatches.append(
            {
                "comparison_id": spec.comparison_id,
                "stage": stage,
                "reason": "M4_ATTENTION_RECORD_NOT_EVALUATED",
            }
        )
        return {"comparison_id": spec.comparison_id, "stage": stage, "status": "MISSING"}

    def _exact(field: str, sealed: Any, observed: Any) -> None:
        if sealed != observed:
            mismatches.append(
                {
                    "comparison_id": spec.comparison_id,
                    "stage": stage,
                    "field": field,
                    "sealed": sealed,
                    "observed": observed,
                }
            )

    def _close(field: str, sealed: Any, observed: Any) -> None:
        if sealed is None or observed is None:
            if sealed is not observed:
                mismatches.append(
                    {
                        "comparison_id": spec.comparison_id,
                        "stage": stage,
                        "field": field,
                        "sealed": sealed,
                        "observed": observed,
                    }
                )
            return
        if abs(float(sealed) - float(observed)) > MARGIN_TOLERANCE:
            mismatches.append(
                {
                    "comparison_id": spec.comparison_id,
                    "stage": stage,
                    "field": field,
                    "sealed": sealed,
                    "observed": observed,
                }
            )

    _exact(
        "reference_shortlist",
        sorted(str(value) for value in record["reference_shortlist"]),
        sorted(pairwise.reference_shortlist),
    )
    _exact(
        "comparator_shortlist",
        sorted(str(value) for value in record["comparator_shortlist"]),
        sorted(pairwise.comparator_shortlist),
    )
    _exact("overlap_count", int(record["overlap_count"]), outcome["intersection_count"])
    _exact(
        "entered",
        sorted(str(value) for value in record["entered"]),
        sorted(outcome["entered"]),
    )
    _exact(
        "displaced",
        sorted(str(value) for value in record["displaced"]),
        sorted(outcome["displaced"]),
    )
    _close(
        "reference_attention_value",
        record["reference_attention_value"],
        pairwise.reference_attention_value,
    )
    _close(
        "comparator_attention_value",
        record["comparator_attention_value"],
        pairwise.comparator_attention_value,
    )
    _close("attention_loss", record["L_att"], pairwise.L_att)
    return {
        "comparison_id": spec.comparison_id,
        "stage": stage,
        "status": "MATCHED",
        "sealed_attention_loss": record["L_att"],
    }


def _attention_row(
    attention: Mapping[str, Any], variant: str, stage: str
) -> Mapping[str, Any]:
    for row in attention["rows"]:
        if (
            row["variant"] == variant
            and row["stage"] == stage
            and abs(float(row["q"]) - NOMINAL_Q) <= 1e-12
        ):
            return row
    raise CheckFailure(
        "DECISION_MARGIN_BLOCKED_STAGE1_AUTHORITY_REPLAY: "
        f"{{'reason': 'ATTENTION_ROW_MISSING', 'variant': '{variant}', "
        f"'stage': '{stage}'}}"
    )


# ----------------------------------------------------------------------
# Gate D - Stage-II margins
# ----------------------------------------------------------------------
def build_stage2_diagnostic(
    *,
    replay: Mapping[str, Any],
    recovery_decisions: Mapping[str, Any],
    m4: Mapping[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    """Pairwise Stage-II action curves, chain summaries and aggregates."""

    cohort = tuple(str(value) for value in replay["cohort"])
    curves = replay["curves"]
    stage_by_node = {
        str(row["node_id"]): str(row["stage"])
        for row in recovery_decisions["rows"]
        if row["variant"] == REFERENCE_VARIANT
    }
    episode_by_node = {
        str(row["node_id"]): str(row["episode_id"])
        for row in recovery_decisions["rows"]
        if row["variant"] == REFERENCE_VARIANT
    }
    sealed_rows = {
        variant: recovery_rows_by_variant(recovery_decisions, variant)
        for variant in S.PRIMARY_STATE_VARIANTS
    }

    curve_rows: list[dict[str, Any]] = []
    chain_rows: list[dict[str, Any]] = []
    aggregate_rows: list[dict[str, Any]] = []
    anchors: list[dict[str, Any]] = []
    anchor_mismatches: list[dict[str, Any]] = []

    for spec in PAIRWISE_COMPARISONS:
        reference_variant = spec.reference_variant
        alternative_variant = spec.alternative_variant
        reference_actions: dict[str, float] = {}
        alternative_actions: dict[str, float] = {}
        reference_values: dict[str, float] = {}
        reference_objectives: dict[tuple[str, float], float] = {}
        chain_ids: dict[str, str] = {}
        comparison_rows: list[dict[str, Any]] = []

        for node_id in cohort:
            reference_table = curves[reference_variant][node_id]
            alternative_table = curves[alternative_variant][node_id]
            margin = stage2_pair_margin(
                reference_table=reference_table,
                alternative_table=alternative_table,
            )
            _require(
                tuple(margin["common_feasible_set"]) == EXPECTED_ACTION_GRID,
                "DECISION_MARGIN_BLOCKED_OBJECTIVE_REPLAY_MISMATCH",
                {
                    "reason": "COMMON_FEASIBLE_SET_MISMATCH",
                    "node_id": node_id,
                    "comparison_id": spec.comparison_id,
                    "observed": list(margin["common_feasible_set"]),
                },
            )
            status = stage2_certificate_status(
                has_common_actions=bool(margin["common_feasible_set"]),
                action_gap=margin["action_gap"],
                slack=margin["certificate_slack"],
            )
            u_ref = margin["reference_best_u"]
            u_alt = margin["alternative_best_u"]
            sealed_reference = recovery_decision_from_payload(
                sealed_rows[reference_variant][node_id]["decision"]
            )
            sealed_alternative = recovery_decision_from_payload(
                sealed_rows[alternative_variant][node_id]["decision"]
            )
            _require(
                u_ref == float(sealed_reference.u_star)
                and u_alt == float(sealed_alternative.u_star),
                "DECISION_MARGIN_BLOCKED_OBJECTIVE_REPLAY_MISMATCH",
                {
                    "level": 2,
                    "reason": "SEALED_ACTION_NOT_REPRODUCED_FOR_PAIR",
                    "node_id": node_id,
                    "comparison_id": spec.comparison_id,
                },
            )
            certified_stable_requires_unchanged(
                certificate_status=status,
                reference_value=u_ref,
                alternative_value=u_alt,
                context={
                    "scope": "STAGE_II",
                    "comparison_id": spec.comparison_id,
                    "node_id": node_id,
                },
            )
            reference_actions[node_id] = u_ref
            alternative_actions[node_id] = u_alt
            reference_values[node_id] = float(reference_table[0][1]) - float(
                margin["reference_best_objective"]
            )
            for u, value in reference_table:
                reference_objectives[(node_id, float(u))] = float(value)
            chain_ids[node_id] = str(sealed_reference.chain_id)

            comparison_rows.append(
                {
                    "comparison_id": spec.comparison_id,
                    "stage": stage_by_node[node_id],
                    "stage_class": STAGE_CLASS[stage_by_node[node_id]],
                    "chain_id": chain_ids[node_id],
                    "node_id": node_id,
                    "episode_id": episode_by_node[node_id],
                    "reference_variant": reference_variant,
                    "alternative_variant": alternative_variant,
                    "u_ref": u_ref,
                    "u_alt": u_alt,
                    "action_changed": u_ref != u_alt,
                    "action_difference_minutes": abs(u_alt - u_ref),
                    "reference_best_u": margin["reference_best_u"],
                    "reference_best_objective": margin["reference_best_objective"],
                    "reference_second_best_u": margin["reference_second_best_u"],
                    "reference_second_best_objective": margin[
                        "reference_second_best_objective"
                    ],
                    "action_gap": margin["action_gap"],
                    "epsilon_inf": margin["epsilon_inf"],
                    "perturbation_span": margin["perturbation_span"],
                    "certificate_slack": margin["certificate_slack"],
                    "certificate_status": status,
                    "common_feasible_actions": len(margin["common_feasible_set"]),
                    **recovery_event_flags(u_ref, u_alt),
                }
            )
            alternative_by_u = {float(u): float(v) for u, v in alternative_table}
            for u, value_ref in reference_table:
                curve_rows.append(
                    {
                        "comparison_id": spec.comparison_id,
                        "stage": stage_by_node[node_id],
                        "stage_class": STAGE_CLASS[stage_by_node[node_id]],
                        "chain_id": chain_ids[node_id],
                        "node_id": node_id,
                        "episode_id": episode_by_node[node_id],
                        "reference_variant": reference_variant,
                        "alternative_variant": alternative_variant,
                        "u_minutes": float(u),
                        "J_ref": float(value_ref),
                        "J_alt": alternative_by_u[float(u)],
                        "objective_delta": float(margin["objective_delta"][float(u)]),
                        "abs_objective_delta": abs(
                            float(margin["objective_delta"][float(u)])
                        ),
                        "is_ref_optimal": float(u) == u_ref,
                        "is_alt_optimal": float(u) == u_alt,
                        "feasible_ref": float(u) in set(margin["common_feasible_set"]),
                        "feasible_alt": float(u) in set(margin["common_feasible_set"]),
                        "common_feasible": float(u)
                        in set(margin["common_feasible_set"]),
                    }
                )

        evaluation = evaluate_recovery_loss(
            cohort_id=spec.comparison_id,
            reference_id=reference_variant,
            comparator_id=alternative_variant,
            fixed_cohort=cohort,
            reference_actions=reference_actions,
            comparator_actions=alternative_actions,
            reference_objectives=reference_objectives,
            reference_recoverable_values=reference_values,
        )
        _require_per_chain_taxonomy_matches(comparison_rows, evaluation, spec)
        for row in comparison_rows:
            row["reference_regret_of_alt_action"] = float(
                evaluation.delta_objectives[row["node_id"]]
            )
            _require(
                float(row["reference_regret_of_alt_action"]) >= -MARGIN_TOLERANCE,
                "DECISION_MARGIN_REGRET_BELOW_NEGATIVE_TOLERANCE",
                {
                    "comparison_id": spec.comparison_id,
                    "node_id": row["node_id"],
                    "reference_regret_of_alt_action": row[
                        "reference_regret_of_alt_action"
                    ],
                },
            )
        chain_rows.extend(comparison_rows)
        aggregate_rows.append(
            _stage2_aggregate_row(
                spec=spec, scope="ALL", chain_rows=comparison_rows, evaluation=evaluation
            )
        )
        for stage in STAGES:
            sub_cohort = tuple(
                node_id for node_id in cohort if stage_by_node[node_id] == stage
            )
            if not sub_cohort:
                continue
            sub_evaluation = evaluate_recovery_loss(
                cohort_id=f"{spec.comparison_id}_{STAGE_CLASS[stage]}",
                reference_id=reference_variant,
                comparator_id=alternative_variant,
                fixed_cohort=sub_cohort,
                reference_actions={
                    node_id: reference_actions[node_id] for node_id in sub_cohort
                },
                comparator_actions={
                    node_id: alternative_actions[node_id] for node_id in sub_cohort
                },
                reference_objectives={
                    key: value
                    for key, value in reference_objectives.items()
                    if key[0] in set(sub_cohort)
                },
                reference_recoverable_values={
                    node_id: reference_values[node_id] for node_id in sub_cohort
                },
            )
            aggregate_rows.append(
                _stage2_aggregate_row(
                    spec=spec,
                    scope=STAGE_CLASS[stage],
                    chain_rows=[
                        row for row in comparison_rows if row["stage"] == stage
                    ],
                    evaluation=sub_evaluation,
                )
            )

        if reference_variant == REFERENCE_VARIANT:
            anchors.append(
                _compare_recovery_anchor(
                    spec=spec, m4=m4, evaluation=evaluation, mismatches=anchor_mismatches
                )
            )

    _require(
        not anchor_mismatches,
        "DECISION_MARGIN_BLOCKED_STAGE2_AUTHORITY_REPLAY",
        {"reason": "M4_RECOVERY_ANCHOR_MISMATCH", "mismatches": anchor_mismatches[:20]},
    )
    checks = {
        "anchors": anchors,
        "certified_stable_rows": sum(
            1 for row in chain_rows if row["certificate_status"] == CERTIFIED_STABLE
        ),
        "certified_stable_rows_stable": all(
            row["u_ref"] == row["u_alt"]
            for row in chain_rows
            if row["certificate_status"] == CERTIFIED_STABLE
        ),
        "not_certified_but_stable": sum(
            1
            for row in chain_rows
            if row["certificate_status"] == NOT_CERTIFIED and not row["action_changed"]
        ),
    }
    return curve_rows, chain_rows, aggregate_rows, checks


def _require_per_chain_taxonomy_matches(
    comparison_rows: Sequence[Mapping[str, Any]],
    evaluation: Any,
    spec: ComparisonSpec,
) -> None:
    """The per-chain taxonomy flags must sum to the frozen event counts."""

    observed = {
        key: sum(1 for row in comparison_rows if bool(row[key.lower()]))
        for key in RECOVERY_EVENT_KEYS
    }
    sealed = {
        str(key): int(value) for key, value in dict(evaluation.activation_events).items()
    }
    _require(
        observed == sealed,
        "DECISION_MARGIN_BLOCKED_STAGE2_AUTHORITY_REPLAY",
        {
            "reason": "ACTIVATION_TAXONOMY_MISMATCH",
            "comparison_id": spec.comparison_id,
            "observed": observed,
            "sealed": sealed,
        },
    )


def _stage2_aggregate_row(
    *,
    spec: ComparisonSpec,
    scope: str,
    chain_rows: Sequence[Mapping[str, Any]],
    evaluation: Any,
) -> dict[str, Any]:
    counts = certificate_class_counts(chain_rows, changed_key="action_changed")
    gaps = [
        float(row["action_gap"]) for row in chain_rows if row["action_gap"] is not None
    ]
    epsilons = [
        float(row["epsilon_inf"]) for row in chain_rows if row["epsilon_inf"] is not None
    ]
    spans = [
        float(row["perturbation_span"])
        for row in chain_rows
        if row["perturbation_span"] is not None
    ]
    slacks = [
        float(row["certificate_slack"])
        for row in chain_rows
        if row["certificate_slack"] is not None
    ]
    regrets = [float(row["reference_regret_of_alt_action"]) for row in chain_rows]
    changed = sum(1 for row in chain_rows if bool(row["action_changed"]))
    supported = sum(
        1
        for row in chain_rows
        if row["certificate_status"] != ABSTAIN_NO_COMMON_SUPPORT
    )
    event_counts = {
        f"n_{key.lower()}": sum(1 for row in chain_rows if bool(row[key.lower()]))
        for key in RECOVERY_EVENT_KEYS
    }
    return {
        "comparison_id": spec.comparison_id,
        "scope": scope,
        "reference_variant": spec.reference_variant,
        "alternative_variant": spec.alternative_variant,
        "N_chain_total": len(chain_rows),
        "N_chain_supported": supported,
        "N_action_changed": changed,
        "N_action_unchanged": len(chain_rows) - changed,
        "N_exact_agreement": len(chain_rows) - changed,
        **counts,
        **event_counts,
        "median_action_gap": median(gaps) if gaps else None,
        "mean_action_gap": mean(gaps) if gaps else None,
        "median_epsilon_inf": median(epsilons) if epsilons else None,
        "mean_epsilon_inf": mean(epsilons) if epsilons else None,
        "median_perturbation_span": median(spans) if spans else None,
        "mean_perturbation_span": mean(spans) if spans else None,
        "median_certificate_slack": median(slacks) if slacks else None,
        "mean_certificate_slack": mean(slacks) if slacks else None,
        "mean_reference_regret": mean(regrets) if regrets else None,
        "median_reference_regret": median(regrets) if regrets else None,
        "reference_recoverable_value": float(evaluation.reference_recoverable_value),
        "delta_recovery_objective": float(evaluation.delta_recovery_objective),
        "reference_recovery_loss": evaluation.L_rec,
        "A0": float(evaluation.A0),
        "A5": float(evaluation.A5),
        "exact_action_count": int(evaluation.exact_action_count),
        "within_five_count": int(evaluation.within_five_count),
    }


def _compare_recovery_anchor(
    *,
    spec: ComparisonSpec,
    m4: Mapping[str, Any],
    evaluation: Any,
    mismatches: list[dict[str, Any]],
) -> dict[str, Any]:
    """The sealed M4 recovery aggregate for a ``HISTORY_JOINT``-referenced pair."""

    record = m4["recovery"]["comparators"].get(spec.alternative_variant)
    if record is None or record.get("record_kind") != "EVALUATED":
        mismatches.append(
            {
                "comparison_id": spec.comparison_id,
                "reason": "M4_RECOVERY_RECORD_NOT_EVALUATED",
            }
        )
        return {"comparison_id": spec.comparison_id, "status": "MISSING"}

    for field in ("exact_action_count", "within_five_count"):
        if int(record[field]) != int(getattr(evaluation, field)):
            mismatches.append(
                {
                    "comparison_id": spec.comparison_id,
                    "field": field,
                    "sealed": record[field],
                    "observed": int(getattr(evaluation, field)),
                }
            )
    for field in (
        "L_rec",
        "A0",
        "A5",
        "delta_recovery_objective",
        "reference_recoverable_value",
    ):
        sealed = record.get(field)
        observed = getattr(evaluation, field)
        if sealed is None or observed is None:
            if sealed is not observed:
                mismatches.append(
                    {
                        "comparison_id": spec.comparison_id,
                        "field": field,
                        "sealed": sealed,
                        "observed": observed,
                    }
                )
            continue
        if abs(float(sealed) - float(observed)) > MARGIN_TOLERANCE:
            mismatches.append(
                {
                    "comparison_id": spec.comparison_id,
                    "field": field,
                    "sealed": sealed,
                    "observed": observed,
                }
            )
    sealed_events = {
        str(key): int(value) for key, value in dict(record["activation_events"]).items()
    }
    observed_events = {
        str(key): int(value) for key, value in dict(evaluation.activation_events).items()
    }
    if sealed_events != observed_events:
        mismatches.append(
            {
                "comparison_id": spec.comparison_id,
                "field": "activation_events",
                "sealed": sealed_events,
                "observed": observed_events,
            }
        )
    return {
        "comparison_id": spec.comparison_id,
        "status": "MATCHED",
        "sealed_recovery_loss": record["L_rec"],
    }


# ----------------------------------------------------------------------
# Gate D - Stage x q boundary descriptor
# ----------------------------------------------------------------------
def build_stage_q_boundary(
    *, attention: Mapping[str, Any], frozen_summary: Path | None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Boundary location only: no delay perturbation certificate is ever built."""

    recomputed: dict[tuple[str, float], dict[str, Any]] = {}
    for row in attention["rows"]:
        if row["variant"] != REFERENCE_VARIANT:
            continue
        stage = str(row["stage"])
        q = float(row["q"])
        consequence = attention_decision_from_payload(row["consequence_decision"])
        delay = attention_decision_from_payload(row["delay_decision"])
        ranking = ranked_reference_scores(consequence)
        priority = {node_id: score for node_id, score in ranking}
        evaluation = evaluate_attention_allocation(
            cohort_id=f"STAGE_Q_{STAGE_CLASS[stage]}_q{int(round(q * 100)):02d}",
            reference_id="CONSEQUENCE",
            comparator_id="DELAY",
            reference_decision=consequence,
            comparator_decision=delay,
            reference_priority=priority,
        )
        k = int(consequence.k)
        has_next = 0 < k < len(ranking)
        recomputed[(stage, q)] = {
            "stage": stage,
            "stage_class": STAGE_CLASS[stage],
            "q": q,
            "N_supported": int(consequence.cohort_size),
            "K": k,
            "consequence_kth_score": ranking[k - 1][1] if 0 < k <= len(ranking) else None,
            "consequence_kplus1_score": ranking[k][1] if has_next else None,
            "consequence_cutoff_margin": (
                ranking[k - 1][1] - ranking[k][1] if has_next else None
            ),
            "delay_consequence_changed_positions": len(evaluation.displaced),
            "delay_consequence_intersection_count": int(evaluation.overlap_count),
            "delay_consequence_overlap_rate": (
                evaluation.overlap_count / k if k else None
            ),
            "retained_value": (
                None if evaluation.L_att is None else 1.0 - float(evaluation.L_att)
            ),
            "attention_loss": evaluation.L_att,
            "reference_consequence_value": float(evaluation.reference_attention_value),
            "delay_shortlist_consequence_value": float(
                evaluation.comparator_attention_value
            ),
        }

    order = {stage: index for index, stage in enumerate(STAGES)}
    rows = [
        recomputed[key] for key in sorted(recomputed, key=lambda k: (order[k[0]], k[1]))
    ]
    cross_check: dict[str, Any] = {
        "frozen_summary_path": None if frozen_summary is None else str(frozen_summary),
        "cross_check_executed": False,
        "rows_compared": 0,
        "fields_per_row": len(STAGE_Q_FIELD_ALIASES),
        "comparisons": 0,
        "max_abs_deviation": 0.0,
        "mismatches": [],
    }
    if frozen_summary is None:
        return rows, cross_check

    frame = pd.read_csv(frozen_summary)
    frozen_by_key: dict[tuple[str, float], Mapping[str, Any]] = {
        (str(record["stage"]), float(record["q"])): record
        for _index, record in frame.iterrows()
    }
    _require(
        set(frozen_by_key) == set(recomputed),
        "DECISION_MARGIN_BLOCKED_STAGE_Q_CROSS_CHECK",
        {
            "reason": "FROZEN_STAGE_Q_COVERAGE_MISMATCH",
            "frozen": sorted(f"{s}@{q}" for s, q in frozen_by_key),
            "recomputed": sorted(f"{s}@{q}" for s, q in recomputed),
        },
    )
    cross_check["cross_check_executed"] = True
    for key, record in recomputed.items():
        frozen = frozen_by_key[key]
        cross_check["rows_compared"] += 1
        for frozen_field, alias in STAGE_Q_FIELD_ALIASES.items():
            sealed = float(frozen[frozen_field])
            observed = float(record[alias])
            cross_check["comparisons"] += 1
            deviation = abs(sealed - observed)
            cross_check["max_abs_deviation"] = max(
                cross_check["max_abs_deviation"], deviation
            )
            if deviation > MARGIN_TOLERANCE:
                cross_check["mismatches"].append(
                    {
                        "stage": key[0],
                        "q": key[1],
                        "frozen_field": frozen_field,
                        "sealed": sealed,
                        "observed": observed,
                    }
                )
    _require(
        not cross_check["mismatches"],
        "DECISION_MARGIN_BLOCKED_STAGE_Q_CROSS_CHECK",
        cross_check["mismatches"][:20],
    )
    return rows, cross_check


# ----------------------------------------------------------------------
# schema guards
# ----------------------------------------------------------------------
def assert_no_prohibited_columns(
    *, frames: Mapping[str, pd.DataFrame], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Forbidden fields are excluded at schema level, never by text search.

    Prose is free to explain why something is absent; a metric or field may not
    exist.
    """

    forbidden_columns = ("delay_epsilon", "delay_certificate", "L_att")
    for name, frame in frames.items():
        columns = [str(column) for column in frame.columns]
        for column in forbidden_columns:
            _require(
                column not in columns,
                "DECISION_MARGIN_PROHIBITED_COLUMN",
                {"artifact": name, "column": column},
            )
        lowered = {column.lower() for column in columns}
        for key in PROHIBITED_METRIC_KEYS:
            _require(
                key not in lowered,
                "DECISION_MARGIN_PROHIBITED_METRIC_COLUMN",
                {"artifact": name, "column": key},
            )
        if "certificate_status" in columns:
            observed_statuses = {
                str(value) for value in frame["certificate_status"].dropna()
            }
            _require(
                observed_statuses <= set(ALLOWED_CERTIFICATE_STATUSES),
                "DECISION_MARGIN_STATUS_OUTSIDE_ALLOWED_SET",
                {"artifact": name, "observed": sorted(observed_statuses)},
            )
    manifest_keys = _all_mapping_keys(manifest)
    for key in PROHIBITED_METRIC_KEYS:
        _require(
            key not in manifest_keys,
            "DECISION_MARGIN_PROHIBITED_METRIC_KEY",
            key,
        )
    for term in ("delay_epsilon", "delay_certificate"):
        _require(
            term not in manifest_keys,
            "DECISION_MARGIN_PROHIBITED_METRIC_KEY",
            term,
        )
    for term in PROHIBITED_CERTIFICATE_TERMS:
        _require(
            term.lower() not in manifest_keys,
            "DECISION_MARGIN_PROHIBITED_STATUS_NAME",
            term,
        )
    return {
        "forbidden_columns_checked": list(forbidden_columns),
        "metric_keys_checked": list(PROHIBITED_METRIC_KEYS),
        "manifest_keys_scanned": len(manifest_keys),
        "allowed_certificate_statuses": list(ALLOWED_CERTIFICATE_STATUSES),
        "prohibited_status_terms": list(PROHIBITED_CERTIFICATE_TERMS),
    }


def _all_mapping_keys(value: Any, *, depth: int = 6) -> set[str]:
    """Every mapping key in a manifest-shaped payload, lower-cased."""

    keys: set[str] = set()
    if depth < 0:
        return keys
    if isinstance(value, Mapping):
        for key, nested in value.items():
            keys.add(str(key).lower())
            keys |= _all_mapping_keys(nested, depth=depth - 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys |= _all_mapping_keys(item, depth=depth - 1)
    return keys


# ----------------------------------------------------------------------
# reporting
# ----------------------------------------------------------------------
def _format(value: Any, digits: int = 6) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    return str(value)


def render_report(
    *,
    manifest: Mapping[str, Any],
    stage1_summary: pd.DataFrame,
    stage2_aggregate: pd.DataFrame,
    stage_q_boundary: pd.DataFrame,
) -> str:
    lines: list[str] = []
    lines.append("# Decision-Margin Mechanism Diagnostic")
    lines.append("")
    lines.append(
        "Post-hoc mechanism diagnostic over the sealed canonical-v2 Final-Test "
        "epoch. Nothing is retrained, recalibrated, reselected or redefined."
    )
    lines.append("")
    lines.append(
        f"- analysis: `{manifest['analysis_name']}` (`{manifest['analysis_type']}`)"
    )
    lines.append(f"- split: `{manifest['split']}`")
    lines.append(f"- git head: `{manifest['git_head']}`")
    lines.append(f"- epoch root: `{manifest['epoch_root']}`")
    lines.append(
        f"- write mode: `{manifest['write_mode']}` "
        f"(`{manifest['materialization_mode']}`)"
    )
    lines.append(
        "- stage-I primary capacity: "
        f"`q = {manifest['stage1_primary_q']}`; stage-II cohort: "
        f"`{manifest['stage2_reference_cohort']}` with `N = {manifest['stage2_N']}`"
    )
    lines.append(
        "- tolerances: margin strictness `{}` from `{}`; objective replay `{}` from `{}`".format(
            manifest["numerical_tolerance"]["value"],
            manifest["numerical_tolerance"]["source"],
            manifest["objective_replay_tolerance"]["value"],
            manifest["objective_replay_tolerance"]["source"],
        )
    )
    lines.append("")
    lines.append("## Gates")
    lines.append("")
    gates = manifest["gates"]
    replay = gates["replay"]
    lines.append("| gate | result | evidence |")
    lines.append("| --- | --- | --- |")
    lines.append(
        f"| A repository authority | {'PASS' if gates['gate_a_passed'] else 'FAIL'} | "
        f"head `{manifest['head_start'][:7]}` stable, "
        f"{len(manifest['preexisting_untracked'])} pre-existing untracked entries, "
        f"{len(manifest['tracked_modifications_start'])} pre-existing tracked "
        "modifications, none introduced by this run |"
    )
    lines.append(
        f"| B stage-I authority replay | {'PASS' if gates['gate_b_passed'] else 'FAIL'} | "
        f"N {gates['stage1']['expected_n_by_stage']}, "
        f"K {gates['stage1']['expected_k_by_stage']}, "
        f"{gates['stage1']['score_provenance']['scores_compared']} scores corroborated "
        "against the sealed M4 rows |"
    )
    lines.append(
        f"| C-L1 HISTORY_JOINT curve replay | "
        f"{'PASS' if gates['gate_c_level1_passed'] else 'FAIL'} | "
        f"{replay['level1_points_matched']}/{replay['level1_points_expected']} points, "
        f"max deviation {_format(replay['level1_max_abs_deviation'], 3)} |"
    )
    lines.append(
        f"| C-L2 four-variant decision replay | "
        f"{'PASS' if gates['gate_c_level2_passed'] else 'FAIL'} | "
        f"{replay['level2_cases_matched']}/{replay['level2_cases_expected']} sealed "
        "actions reproduced |"
    )
    lines.append(
        f"| D margin materialization | {'PASS' if gates['gate_d_passed'] else 'FAIL'} | "
        f"stage-x-q cross-check "
        f"{'ran' if manifest['stage_q_cross_check']['cross_check_executed'] else 'not run'} "
        f"({manifest['stage_q_cross_check']['comparisons']} comparisons, max deviation "
        f"{_format(manifest['stage_q_cross_check']['max_abs_deviation'], 3)}) |"
    )
    lines.append("")
    lines.append("## Stage-I diagnostics")
    lines.append("")
    lines.append(
        "`m` is the reference cutoff margin, `eps` the information-induced priority "
        "perturbation, `span` the additive-shift-insensitive perturbation span "
        "(`span <= 2*eps`, reported only and never used for a status), and `m - 2*eps` "
        "the certificate slack."
    )
    lines.append("")
    lines.append(
        "| comparison | stage | m | eps | span | m-2*eps | certificate | shortlist changed |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for _index, row in stage1_summary.iterrows():
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} |".format(
                row["comparison_id"],
                row["stage_class"],
                _format(row["cutoff_margin"]),
                _format(row["epsilon_inf"]),
                _format(row["perturbation_span"]),
                _format(row["certificate_slack"]),
                row["certificate_status"],
                "no" if row["shortlist_identical"] else "yes",
            )
        )
    lines.append("")
    lines.append(
        "`pairwise_reference_value`, `pairwise_alternative_value` and "
        "`pairwise_attention_loss` are the pair-specific diagnostic analogue of the "
        "attention-loss construction, computed with the frozen M4 objective under each "
        "pair's own reference basis. They are **not** the primary HISTORY_JOINT-"
        "referenced `L^att` and must never be reported as it."
    )
    lines.append("")
    lines.append("## Stage-II diagnostics")
    lines.append("")
    lines.append(
        "Gap and perturbation statistics are medians over the fixed `R*` cohort unless "
        "`scope` narrows them. `changed` counts action changes; `NC` abbreviates "
        "`NOT_CERTIFIED`."
    )
    lines.append("")
    lines.append(
        "| comparison | scope | N | changed | median gamma | median eps | median span "
        "| certified stable | NC but stable | NC and changed | no strict margin | abstain |"
    )
    lines.append(
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    for _index, row in stage2_aggregate.iterrows():
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                row["comparison_id"],
                row["scope"],
                row["N_chain_supported"],
                row["N_action_changed"],
                _format(row["median_action_gap"]),
                _format(row["median_epsilon_inf"]),
                _format(row["median_perturbation_span"]),
                row["N_certified_stable"],
                row["N_not_certified_but_stable"],
                row["N_not_certified_and_changed"],
                row["N_no_strict_reference_margin"],
                row["N_abstain"],
            )
        )
    lines.append("")
    lines.append("## Stage x q consequence-boundary descriptor")
    lines.append("")
    lines.append(
        "Boundary location only. No delay-versus-consequence perturbation certificate "
        "is constructed anywhere in this diagnostic, because delay priority and "
        "consequence priority are not a perturbation pair on a shared numerical scale. "
        "`retained_value` is the published `retained_consequence_value` and "
        "`attention_loss` the published `L_att` of the Stage-x-q experiment; the frozen "
        "`STAGE_Q_SCREENING_SUMMARY.csv` is the authority for those columns."
    )
    lines.append("")
    lines.append(
        "| stage | q | N | K | consequence cutoff margin | changed positions "
        "| overlap rate | retained value | attention loss |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for _index, row in stage_q_boundary.iterrows():
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                row["stage_class"],
                row["q"],
                row["N_supported"],
                row["K"],
                _format(row["consequence_cutoff_margin"]),
                row["delay_consequence_changed_positions"],
                _format(row["delay_consequence_overlap_rate"]),
                _format(row["retained_value"]),
                _format(row["attention_loss"]),
            )
        )
    lines.append("")
    lines.append("## Reading rules")
    lines.append("")
    lines.append(
        "- The certificates are **sufficient** stability certificates, never necessary "
        "conditions. `NOT_CERTIFIED` says the certificate is inconclusive; it never "
        "predicts or implies a changed decision, and the "
        "`N_not_certified_but_stable` counts exist precisely because that case is "
        "expected."
    )
    lines.append(
        "- `CERTIFIED_STABLE` must correspond to an empirically stable decision. A "
        "`CERTIFIED_STABLE` row with a changed decision would indicate an implementation "
        "error in the formula, the score orientation, the ranking direction, the "
        "tie-breaking, the objective orientation or the common-support construction, and "
        "blocks the run instead of being reported."
    )
    lines.append(
        "- A certificate is a mechanism diagnostic, not a classifier: no accuracy, "
        "precision, recall, F1, ROC or AUC is computed, and no such field exists in any "
        "artifact schema."
    )
    lines.append(
        "- The manifest deliberately does not contain its own SHA256 "
        "(`SELF_REFERENTIAL_HASH_NOT_DEFINED`): its hash would have to include "
        "itself, which is not a well-defined value. `output_artifact_hashes` "
        "therefore covers the seven payload artifacts only, and the manifest is "
        "listed in `output_artifact_paths` alone."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------
# staging and transactional materialization
# ----------------------------------------------------------------------
def staging_path(out_dir: Path) -> Path:
    return Path(out_dir).parent / (Path(out_dir).name + STAGING_SUFFIX)


def previous_path(out_dir: Path) -> Path:
    return Path(out_dir).parent / (Path(out_dir).name + PREVIOUS_SUFFIX)


def write_staging(
    *, staging: Path, frames: Mapping[str, pd.DataFrame], report: str
) -> None:
    """Write every payload artifact into a fresh staging tree."""

    staging.mkdir(parents=True, exist_ok=False)
    for name, frame in frames.items():
        target = staging / name
        if target.suffix.lower() == ".parquet":
            frame.to_parquet(target, index=False)
        else:
            frame.to_csv(target, index=False, lineterminator="\n")
    (staging / REPORT_NAME).write_text(report, encoding="utf-8", newline="\n")


def write_manifest(*, staging: Path, manifest: Mapping[str, Any]) -> None:
    """Write the manifest last, so it describes artifacts that already exist."""

    with open(staging / MANIFEST_NAME, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False))
        handle.write("\n")


def materialize(*, staging: Path, out_dir: Path, hashes: Mapping[str, str]) -> str:
    """Move a completed staging tree into place; never expose a partial result.

    A fresh run is a single same-filesystem rename. A regeneration is a backup
    swap: the completed previous result is moved aside, staging is moved in, the
    materialized tree is verified against its recorded hashes, and only then is
    the backup removed. If the swap fails the previous result is restored; if
    even that fails, all three directories are preserved and named in the error.
    """

    out_dir = Path(out_dir)
    previous = previous_path(out_dir)
    if not out_dir.exists():
        _rename(staging, out_dir)
        _verify_materialized(out_dir=out_dir, hashes=hashes)
        return FRESH_ATOMIC_RENAME

    _require(
        not previous.exists(),
        "DECISION_MARGIN_BLOCKED_MATERIALIZATION_RESIDUE",
        {"previous_path": str(previous)},
    )
    _rename(out_dir, previous)
    try:
        _rename(staging, out_dir)
    except OSError as error:
        try:
            _rename(previous, out_dir)
        except OSError as rollback_error:
            raise CheckFailure(
                "DECISION_MARGIN_BLOCKED_MATERIALIZATION_ROLLBACK: "
                + json.dumps(
                    {
                        "target_path": str(out_dir),
                        "previous_path": str(previous),
                        "staging_path": str(staging),
                        "swap_error": str(error),
                        "rollback_error": str(rollback_error),
                    },
                    sort_keys=True,
                )
            ) from rollback_error
        shutil.rmtree(staging, ignore_errors=True)
        raise CheckFailure(
            "DECISION_MARGIN_BLOCKED_MATERIALIZATION: "
            + json.dumps(
                {
                    "target_path": str(out_dir),
                    "previous_path": str(previous),
                    "staging_path": str(staging),
                    "swap_error": str(error),
                    "rollback": "SUCCEEDED_PREVIOUS_RESULT_RESTORED",
                },
                sort_keys=True,
            )
        ) from error
    _verify_materialized(out_dir=out_dir, hashes=hashes)
    shutil.rmtree(previous)
    return BACKUP_SWAP_WITH_ROLLBACK


def _verify_materialized(*, out_dir: Path, hashes: Mapping[str, str]) -> None:
    mismatches: dict[str, Any] = {}
    for name, digest in hashes.items():
        observed = _sha256_file(out_dir / name)
        if observed != digest:
            mismatches[name] = {"expected": digest, "observed": observed}
    _require(
        not mismatches,
        "DECISION_MARGIN_BLOCKED_MATERIALIZATION_VERIFICATION",
        mismatches,
    )


# ----------------------------------------------------------------------
# orchestration
# ----------------------------------------------------------------------
def run(
    *, epoch_root: Path, out_dir: Path, stage_q_summary: Path | None = None
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Execute Gates A-D and return the artifact frames plus the manifest."""

    epoch_root = Path(epoch_root)
    out_dir = Path(out_dir)
    _require(epoch_root.is_dir(), "DECISION_MARGIN_EPOCH_ROOT_MISSING", str(epoch_root))

    authority = gate_repository_authority(out_dir=out_dir)
    provenance = _verify_epoch_identity(epoch_root)
    frozen_stage_q = discover_stage_q_summary(stage_q_summary)
    input_paths = collect_input_paths(epoch_root, stage_q_summary=frozen_stage_q)
    input_hashes = {
        name: _sha256_file(Path(path)) for name, path in input_paths.items()
    }
    source = C.ROOT / SOURCE_RELATIVE_PATH
    diagnostic_source_sha256 = _sha256_file(source) if source.is_file() else None
    test_source = C.ROOT / TEST_RELATIVE_PATH
    test_source_sha256 = _sha256_file(test_source) if test_source.is_file() else None
    collision = check_output_collision(
        out_dir=out_dir,
        head=authority["head_start"],
        input_hashes=input_hashes,
        diagnostic_source_sha256=diagnostic_source_sha256,
    )

    store = CheckpointStore(epoch_root / "checkpoints")
    attention = store.read(S.ATTENTION_DECISIONS)
    nodes_payload = store.read(S.CANONICAL_NODES)
    m4 = store.read(S.M4_COMPARISONS)
    recovery_decisions = store.read(S.RECOVERY_DECISIONS)
    reference_cohort = store.read(S.REFERENCE_RECOVERY_COHORT)
    state_variants = store.read(S.STATE_VARIANTS)

    # -- Gate B ------------------------------------------------------
    stage1_replay = stage1_authority_replay(attention=attention, m4=m4)

    # -- Gate C ------------------------------------------------------
    replay = stage2_objective_replay(
        nodes_payload=nodes_payload,
        state_variants=state_variants,
        recovery_decisions=recovery_decisions,
        reference_cohort=reference_cohort,
    )
    r_star_counts = r_star_stage_counts(recovery_decisions, reference_cohort)

    # -- Gate D ------------------------------------------------------
    decision_time_index = {
        str(row["node_id"]): row.get("decision_time")
        for row in nodes_payload["nodes"]
    }
    stage1_records, stage1_summary, stage1_checks = build_stage1_diagnostic(
        attention=attention,
        m4=m4,
        decision_time_by_node=decision_time_index,
        cohort_by_stage=stage1_replay["eligible_candidate_node_ids_by_stage"],
    )
    curve_rows, chain_rows, aggregate_rows, stage2_checks = build_stage2_diagnostic(
        replay=replay,
        recovery_decisions=recovery_decisions,
        m4=m4,
    )
    boundary_rows, stage_q_cross_check = build_stage_q_boundary(
        attention=attention, frozen_summary=frozen_stage_q
    )

    comparison_order = {
        spec.comparison_id: index for index, spec in enumerate(PAIRWISE_COMPARISONS)
    }
    stage_order = {stage: index for index, stage in enumerate(STAGES)}
    categorical = {"comparison_id": comparison_order, "stage": stage_order}
    stage1_records_frame = _ordered(
        pd.DataFrame(stage1_records),
        ["comparison_id", "stage", "rank_ref"],
        categorical=categorical,
    )
    stage1_summary_frame = _ordered(
        pd.DataFrame(stage1_summary),
        ["comparison_id", "stage"],
        categorical=categorical,
    )
    chain_frame = _ordered(
        pd.DataFrame(chain_rows),
        ["comparison_id", "stage", "node_id"],
        categorical=categorical,
    )
    curves_frame = _ordered(
        pd.DataFrame(curve_rows),
        ["comparison_id", "stage", "node_id", "u_minutes"],
        categorical=categorical,
    )
    aggregate_frame = pd.DataFrame(aggregate_rows)

    stage1_counts = certificate_class_counts(
        [
            {
                "certificate_status": row["certificate_status"],
                "decision_changed": not bool(row["shortlist_identical"]),
            }
            for row in stage1_summary
        ],
        changed_key="decision_changed",
    )
    stage2_counts = certificate_class_counts(chain_rows, changed_key="action_changed")

    frames = {
        STAGE1_RECORDS_NAME: stage1_records_frame,
        STAGE1_SUMMARY_NAME: stage1_summary_frame,
        STAGE2_CURVES_NAME: curves_frame,
        STAGE2_CHAIN_NAME: chain_frame,
        STAGE2_SUMMARY_NAME: aggregate_frame,
        STAGE_Q_BOUNDARY_NAME: pd.DataFrame(boundary_rows),
    }

    manifest: dict[str, Any] = {
        "analysis_name": ANALYSIS_NAME,
        "analysis_type": ANALYSIS_TYPE,
        "experiment": ANALYSIS_NAME,
        "split": SPLIT,
        "model_retrained": False,
        "model_recalibrated": False,
        "parameter_reselected": False,
        "final_test_cohort_changed": False,
        "canonical_node_rule_changed": False,
        "support_rule_changed": False,
        "representation_redefined": False,
        "consequence_mapping_changed": False,
        "reference_priority_changed": False,
        "tie_breaking_changed": False,
        "stage_pooling": False,
        "stage2_cohort_changed": False,
        "bootstrap_executed": False,
        "final_test_raw_data_read": False,
        "new_access_epoch_opened": False,
        "canonical_nominal_artifact_overwritten": False,
        "stage1_primary_q": NOMINAL_Q,
        "stage1_actionable_stages": list(STAGES),
        "stage_class": STAGE_CLASS,
        "stage2_reference_cohort": str(reference_cohort["cohort_id"]),
        "stage2_reference_cohort_changed": False,
        "stage2_N": int(reference_cohort["stage2_cohort_size"]),
        "stage2_r_star_stage_counts": r_star_counts,
        "stage2_action_selector": "EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID",
        "stage2_tie_break": C.DETERMINISTIC_TIE_BREAK,
        "stage2_lambda": float(C.NOMINAL_LAMBDA),
        "stage2_u_max": float(replay["headroom"].u_max),
        "stage2_turnaround_lower_bound_q": float(
            replay["headroom"].turnaround_lower_bound_q
        ),
        "stage2_action_floor_minutes": float(replay["headroom"].floor_to_minutes),
        "stage2_objective_replay_performed": True,
        "certificate_is_sufficient_only": True,
        "certificate_failure_implies_change": False,
        "allowed_certificate_statuses": list(ALLOWED_CERTIFICATE_STATUSES),
        "prohibited_certificate_terms": list(PROHIBITED_CERTIFICATE_TERMS),
        "certificate_span_note": (
            "perturbation_span = max(delta) - min(delta) <= 2 * max|delta| = "
            "2 * epsilon_inf: a span certificate is never more conservative than the "
            "2 * epsilon certificate and can be strictly tighter when a common additive "
            "shift is present. No status reported here uses it."
        ),
        "certificate_counts": {"stage1": stage1_counts, "stage2": stage2_counts},
        "pairwise_attention_loss_is_primary": False,
        "stage1_loss_field_note": (
            "pairwise_reference_value / pairwise_alternative_value / "
            "pairwise_attention_loss are pair-specific diagnostic quantities computed "
            "with the frozen model.M4.evaluation objective under each pair's own "
            "reference basis; they are not the primary HISTORY_JOINT-referenced L_att "
            "and must never be reported as it"
        ),
        "delay_consequence_certificate_constructed": False,
        "stage_q_descriptor_scope": "BOUNDARY_LOCATION_ONLY",
        "stage_q_field_mapping": {
            **REQUESTED_FIELD_SOURCES,
            "repository_column_names_used": list(STAGE_Q_FIELD_ALIASES.values()),
        },
        "tie_break_contract_id": STAGE_I_TIE_BREAK,
        "capacity_rule": "K = ceil(q * N)",
        "selector_id": "M3_STAGE1_SHARED_SELECTOR",
        "numerical_tolerance": {
            "name": "M3_NUMERICAL_COMPARISON_TOLERANCE",
            "value": MARGIN_TOLERANCE,
            "source": MARGIN_TOLERANCE_SOURCE,
            "role": "DECISION_MARGIN_STRICTNESS_TEST",
            "scientific_parameter": False,
        },
        "objective_replay_tolerance": {
            "name": "M3_NUMERICAL_COMPARISON_TOLERANCE",
            "value": REPLAY_TOLERANCE,
            "source": REPLAY_TOLERANCE_SOURCE,
            "role": "OBJECTIVE_REPLAY_CONSISTENCY",
            "scientific_parameter": False,
        },
        "tolerance_role_note": (
            "REPLAY_CONSISTENCY_AND_MARGIN_STRICTNESS_ARE_DISTINCT_CONCEPTS_SHARING_"
            "ONE_FROZEN_CONSTANT"
        ),
        "write_mode": WRITE_MODE,
        "partial_output_exposed": False,
        "staging_directory": str(staging_path(out_dir)),
        "manifest_self_hash_included": False,
        "manifest_self_hash_reason": "SELF_REFERENTIAL_HASH_NOT_DEFINED",
        "git_head": authority["head_start"],
        "branch": authority["branch"],
        "head_start": authority["head_start"],
        "preexisting_untracked": authority["preexisting_untracked"],
        "tracked_modifications_start": authority["tracked_modifications_start"],
        "tracked_modifications_start_note": authority[
            "tracked_modifications_start_note"
        ],
        "protected_tracked_modifications": authority[
            "protected_tracked_modifications"
        ],
        "protected_tracked_prefixes": authority["protected_tracked_prefixes"],
        "diagnostic_source_path": SOURCE_RELATIVE_PATH,
        "diagnostic_source_sha256": diagnostic_source_sha256,
        "test_source_path": TEST_RELATIVE_PATH,
        "test_source_sha256": test_source_sha256,
        "test_source_role": "AUDIT_ONLY_NOT_AN_OUTPUT_COLLISION_GATE",
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "code_entrypoint": SOURCE_RELATIVE_PATH,
        "epoch_root": str(epoch_root),
        "epoch_provenance": provenance,
        "output_collision": collision,
        "input_artifact_paths": input_paths,
        "input_artifact_hashes": input_hashes,
        "stage_q_cross_check": stage_q_cross_check,
        "gates": {
            "gate_a_passed": True,
            "gate_b_passed": True,
            "gate_c_level1_passed": replay["level1_points_matched"]
            == replay["level1_points_expected"],
            "gate_c_level2_passed": replay["level2_cases_matched"]
            == replay["level2_cases_expected"],
            "gate_d_passed": True,
            "stage1": stage1_replay,
            "replay": {
                "level1_points_matched": replay["level1_points_matched"],
                "level1_points_expected": replay["level1_points_expected"],
                "level1_max_abs_deviation": replay["level1_max_abs_deviation"],
                "level2_cases_matched": replay["level2_cases_matched"],
                "level2_cases_expected": replay["level2_cases_expected"],
                "level2_max_abs_deviation": replay["level2_max_abs_deviation"],
                "replay_path": (
                    "SEALED_STATE_VARIANTS_VIA_FROZEN_M3_OBJECTIVE_BY_GRID"
                ),
                "headroom_semantics": (
                    "ONE_GLOBAL_FROZEN_HEADROOM_FOR_EVERY_VARIANT_AND_NODE"
                ),
            },
            "stage1_checks": stage1_checks,
            "stage2_checks": stage2_checks,
            "r_star_counts": r_star_counts,
        },
        "output_artifact_paths": {
            name: str(out_dir / name) for name in (*PAYLOAD_ARTIFACTS, MANIFEST_NAME)
        },
        "output_artifact_hashes": {},
    }
    _require(
        manifest["gates"]["gate_c_level1_passed"]
        and manifest["gates"]["gate_c_level2_passed"],
        "DECISION_MARGIN_BLOCKED_OBJECTIVE_REPLAY_MISMATCH",
        {"reason": "REPLAY_GATE_COUNT_MISMATCH"},
    )
    return frames, manifest


def _ordered(
    frame: pd.DataFrame,
    columns: Sequence[str],
    *,
    categorical: Mapping[str, Mapping[str, int]],
) -> pd.DataFrame:
    """Deterministic reporting order; ranking itself is always stage-local."""

    ordered = frame.copy()
    keys: list[str] = []
    helper_columns: list[str] = []
    for column in columns:
        if column in categorical:
            helper = f"__order_{column}"
            ordered[helper] = ordered[column].map(categorical[column])
            keys.append(helper)
            helper_columns.append(helper)
        else:
            keys.append(column)
    return (
        ordered.sort_values(keys, kind="stable")
        .drop(columns=helper_columns)
        .reset_index(drop=True)
    )


def r_star_stage_counts(
    recovery_decisions: Mapping[str, Any], reference_cohort: Mapping[str, Any]
) -> dict[str, Any]:
    """The fixed reference cohort must still be 16 with PRE 3 / TURN 13."""

    cohort = tuple(
        str(value) for value in reference_cohort["stage2_actionable_node_ids"]
    )
    stage_by_node = {
        str(row["node_id"]): str(row["stage"])
        for row in recovery_decisions["rows"]
        if row["variant"] == REFERENCE_VARIANT
    }
    counts: dict[str, int] = {}
    for node_id in cohort:
        counts[stage_by_node[node_id]] = counts.get(stage_by_node[node_id], 0) + 1
    _require(
        len(cohort) == EXPECTED_STAGE2_N
        and counts == EXPECTED_STAGE2_STAGE_COUNTS,
        "DECISION_MARGIN_R_STAR_COUNTS_CHANGED",
        {"total": len(cohort), "by_stage": counts},
    )
    return {"total": len(cohort), "by_stage": counts, "r_star_unchanged": True}


def planned_materialization_mode(out_dir: Path) -> str:
    """Which transaction the target's current state calls for."""

    return (
        FRESH_ATOMIC_RENAME
        if not Path(out_dir).exists()
        else BACKUP_SWAP_WITH_ROLLBACK
    )


def publish(
    *,
    out_dir: Path,
    frames: Mapping[str, pd.DataFrame],
    report: str,
    manifest: dict[str, Any],
) -> str:
    """Stage every artifact, then materialize the tree transactionally.

    Only the staging phase cleans up after itself. Once the swap starts, a
    failure preserves whatever already exists so a partial run can never be
    mistaken for a result and a complete result is never lost.
    """

    out_dir = Path(out_dir)
    staging = staging_path(out_dir)
    _require(
        not staging.exists(),
        "DECISION_MARGIN_BLOCKED_STAGING_RESIDUE",
        {"staging_path": str(staging)},
    )
    manifest["materialization_mode"] = planned_materialization_mode(out_dir)
    try:
        write_staging(staging=staging, frames=frames, report=report)
        hashes = {name: _sha256_file(staging / name) for name in PAYLOAD_ARTIFACTS}
        manifest["output_artifact_hashes"] = dict(hashes)
        manifest["output_artifact_tracking"] = {
            "committed_to_git": [
                name for name in PAYLOAD_ARTIFACTS if name not in LOCAL_ONLY_ARTIFACTS
            ]
            + [MANIFEST_NAME],
            "local_only_regenerable": {
                name: {
                    "path": str(out_dir / name),
                    "sha256": hashes[name],
                    "reason": (
                        "PROJECT_ARTIFACT_POLICY: paper-results roots track "
                        "CSV/JSON/MD only; row-level parquet stays local and is "
                        "reproducible by re-running this entrypoint"
                    ),
                }
                for name in LOCAL_ONLY_ARTIFACTS
            },
        }
        manifest["head_end"] = _git_head()
        manifest["head_stable"] = manifest["head_end"] == manifest["head_start"]
        _require(
            manifest["head_stable"],
            "DECISION_MARGIN_BLOCKED_REPO_AUTHORITY",
            {
                "reason": "HEAD_CHANGED_DURING_RUN",
                "head_start": manifest["head_start"],
                "head_end": manifest["head_end"],
            },
        )
        tracked_modifications_end = [
            entry[3:].strip()
            for entry in _git("status", "--porcelain").splitlines()
            if entry and not entry.startswith("??")
        ]
        manifest["tracked_modifications_end"] = tracked_modifications_end
        introduced = sorted(
            set(tracked_modifications_end)
            - set(manifest["tracked_modifications_start"])
        )
        manifest["tracked_modifications_introduced_by_run"] = introduced
        _require(
            not introduced,
            "DECISION_MARGIN_BLOCKED_REPO_AUTHORITY",
            {
                "reason": "TRACKED_MODIFICATIONS_INTRODUCED_BY_RUN",
                "entries": introduced,
            },
        )
        write_manifest(staging=staging, manifest=manifest)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    mode = materialize(staging=staging, out_dir=out_dir, hashes=hashes)
    _require(
        mode == manifest["materialization_mode"],
        "DECISION_MARGIN_MATERIALIZATION_MODE_MISMATCH",
        {"planned": manifest["materialization_mode"], "observed": mode},
    )
    return mode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Decision-margin mechanism diagnostic over the sealed canonical-v2 "
            "Final-Test epoch (read-only)."
        )
    )
    parser.add_argument(
        "--epoch-root", type=Path, default=C.STAGE_MATCHED_FINAL_TEST_ROOT
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=C.ROOT
        / "artifacts"
        / "paper_results_v2_final_test_rmb"
        / "decision_margin_diagnostic",
    )
    parser.add_argument(
        "--stage-q-summary",
        type=Path,
        default=None,
        help="frozen Stage-x-q summary cross-checked by the boundary descriptor",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    frames, manifest = run(
        epoch_root=Path(args.epoch_root),
        out_dir=out_dir,
        stage_q_summary=args.stage_q_summary,
    )
    assert_no_prohibited_columns(frames=frames, manifest=manifest)
    manifest["materialization_mode"] = planned_materialization_mode(out_dir)
    report = render_report(
        manifest=manifest,
        stage1_summary=frames[STAGE1_SUMMARY_NAME],
        stage2_aggregate=frames[STAGE2_SUMMARY_NAME],
        stage_q_boundary=frames[STAGE_Q_BOUNDARY_NAME],
    )
    mode = publish(
        out_dir=out_dir, frames=frames, report=report, manifest=manifest
    )
    for name in (*PAYLOAD_ARTIFACTS, MANIFEST_NAME):
        print(f"wrote {out_dir / name}")
    print(f"materialization mode: {mode}")
    print(f"certificate counts stage-I: {manifest['certificate_counts']['stage1']}")
    print(f"certificate counts stage-II: {manifest['certificate_counts']['stage2']}")
    return 0


__all__ = [
    "ABSTAIN_NO_COMMON_SUPPORT",
    "ALLOWED_CERTIFICATE_STATUSES",
    "ANALYSIS_NAME",
    "ANALYSIS_TYPE",
    "BACKUP_SWAP_WITH_ROLLBACK",
    "CERTIFIED_STABLE",
    "EXPECTED_ACTION_GRID",
    "EXPECTED_STAGE1_K",
    "EXPECTED_STAGE1_N",
    "EXPECTED_STAGE2_N",
    "FRESH_ATOMIC_RENAME",
    "MARGIN_TOLERANCE",
    "NO_STRICT_REFERENCE_MARGIN",
    "NOT_CERTIFIED",
    "PAIRWISE_COMPARISONS",
    "REPLAY_TOLERANCE",
    "WRITE_MODE",
    "alternative_boundary_separation",
    "assert_no_prohibited_columns",
    "assert_stage1_certificates_hold",
    "build_stage1_diagnostic",
    "build_stage2_diagnostic",
    "build_stage_q_boundary",
    "certificate_class_counts",
    "certified_stable_requires_unchanged",
    "check_output_collision",
    "discover_stage_q_summary",
    "gate_repository_authority",
    "main",
    "materialize",
    "previous_path",
    "publish",
    "r_star_stage_counts",
    "ranked_reference_scores",
    "recovery_event_flags",
    "reference_optimum",
    "render_report",
    "run",
    "score_provenance_check",
    "second_best_action",
    "selected_node_ids",
    "stage1_authority_replay",
    "stage1_certificate_status",
    "stage1_decision_outcome",
    "stage1_pair_margin",
    "stage2_certificate_status",
    "stage2_objective_replay",
    "stage2_pair_margin",
    "staging_path",
    "write_manifest",
    "write_staging",
]


if __name__ == "__main__":
    raise SystemExit(main())
