"""Stage x screening-capacity ``q`` Stage-I decision sufficiency sensitivity.

A minimal, auditable supplement to the frozen Stage-I priority / consequence
evaluation. Nothing is retrained, recalibrated or reselected: the sealed
canonical-v2 epoch already persisted, for every ``variant x stage x q`` row, both
the delay-based (``P^D``) and the consequence-based (``P^C``) Stage-I decision
over the manuscript capacity grid ``q in {0.05, 0.10, 0.20, 0.30}``. This tool
re-materializes those shortlists from the sealed checkpoint and evaluates the
decision difference between them.

Research question: does the decision sufficiency of delay depend on operating
stage, screening capacity, or both?

Only ``q -> K -> shortlist`` changes. For each stage ``g`` and each ``q``:

    N_g       = common-support-qualified canonical chains in stage ``g``
    K_g(q)    = ceil(q * N_g)                      (frozen ``M3`` capacity rule)
    H_g^C(q), H_g^D(q)                             (both from one frozen queue)

    A_g^C(q)  = sum_{i in H_g^C(q)} P_i^C          (frozen consequence objective)
    A_g^D(q)  = sum_{i in H_g^D(q)} P_i^C          (same objective, delay shortlist)
    L_g^att   = (A_g^C - A_g^D) / A_g^C
    retained  = A_g^D / A_g^C = 1 - L_g^att

The reference quantity is always the frozen consequence priority ``P^C``; the
delay comparator is never used as its own evaluation basis.

The tool is read-only and fail-closed. It reuses the frozen ``model.M3.stage1``
selector and the frozen ``model.M4.evaluation`` objective instead of
reimplementing either. It never writes into the sealed epoch root, never reads
Final-Test raw data, never opens an access epoch and never trains or calibrates
a model.

Usage (from the repository root):

    python -m formal.v2_phase7.stage_q_screening_sensitivity \
        --epoch-root <sealed canonical-v2 epoch root> \
        --out-dir <directory receiving the five result files>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from model.M3.stage1 import (
    ATTENTION_CAPACITY_GRID,
    STAGE_I_TIE_BREAK,
    attention_capacity_k,
    select_paired_attention,
)
from model.M4.evaluation import evaluate_attention_allocation

from . import constants as C
from .executor import consequence_variants as CV
from .executor import stages as S
from .executor.checkpoints import CheckpointStore

EXPERIMENT_ID = "STAGE_Q_SCREENING_SENSITIVITY"
SPLIT = "FINAL_TEST"
REFERENCE_VARIANT = S.REFERENCE_VARIANT
STAGES = S.ACTIONABLE_STAGE_I_STAGES
STAGE_CLASS = {"PRE_IB": "PRE", "POST_IB_PRE_OB": "TURN"}

Q_GRID = tuple(float(value) for value in C.Q_GRID)
NOMINAL_Q = float(C.NOMINAL_Q)

#: The published nominal-q projection of the same sealed epoch. Check 1
#: reproduces it exactly before any paper-facing summary is written. The
#: projection was published on the results branch
#: ``results/delay-vs-consequence-stage1-20260920``; a frozen read-only copy is
#: staged inside this worktree under the experiment input directory so the whole
#: run is self-contained.
NOMINAL_BASELINE_NAME = "PAPER_FACING_DELAY_VS_CONSEQUENCE_STAGE1.json"
INPUT_DIR_NAME = "inputs"
NOMINAL_BASELINE_CANDIDATES = (
    C.ROOT
    / "artifacts"
    / "paper_results_v2_final_test_rmb"
    / "stage_q_sensitivity"
    / INPUT_DIR_NAME,
    C.STAGE_MATCHED_FINAL_TEST_ROOT,
)

SUMMARY_NAME = "STAGE_Q_SCREENING_SUMMARY.csv"
RECORDS_NAME = "STAGE_Q_SCREENING_RECORDS.parquet"
MANIFEST_NAME = "STAGE_Q_SCREENING_MANIFEST.json"
TABLE_NAME = "STAGE_Q_SCREENING_TABLE.tex"
FIGURE_DATA_NAME = "STAGE_Q_SCREENING_FIGURE_DATA.csv"

#: Machine-precision reproduction tolerance. The nominal check is a
#: bit-identity check on counts and a 1e-12 check on objective values; it is not
#: a visual comparison.
TOL = 1e-12


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _git_head() -> str:
    try:
        return (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parents[2],
                check=True,
                capture_output=True,
                text=True,
            )
            .stdout.strip()
        )
    except Exception:  # pragma: no cover - provenance only
        return "UNKNOWN"


class CheckFailure(RuntimeError):
    """A frozen-contract regression check failed."""


def _require(condition: bool, code: str, detail: Any = None) -> None:
    if not condition:
        raise CheckFailure(f"{code}: {detail}")


def _close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is b
    return abs(float(a) - float(b)) <= TOL


def _exact(a: Any, b: Any, code: str, detail: Any = None) -> None:
    _require(a == b, code, {"observed": a, "expected": b, "detail": detail})


# ----------------------------------------------------------------------
# frozen materialization (pure function over frozen scores and support)
# ----------------------------------------------------------------------
def materialize_stage_q_shortlist(
    stage: str,
    q: float,
    *,
    frozen_signals: Mapping[str, tuple[Any, Any]],
    stage_node_ids: Sequence[str],
) -> tuple[Any, Any]:
    """Re-materialize both Stage-I shortlists for one ``stage x q`` cell.

    The candidate queue, the capacity rule and the selector are the frozen
    ``M3`` contract: ``K = ceil(q * N)`` with tie-break
    ``(-score, episode_id, node_id)``. Only the priority signal differs between
    the two returned decisions.
    """

    delay_queue = tuple(frozen_signals[node_id][0] for node_id in stage_node_ids)
    consequence_queue = tuple(
        frozen_signals[node_id][1] for node_id in stage_node_ids
    )
    return select_paired_attention(delay_queue, consequence_queue, q=float(q))


# ----------------------------------------------------------------------
# frozen inputs
# ----------------------------------------------------------------------
def _verify_epoch_identity(epoch_root: Path) -> dict[str, Any]:
    """Verify the sealed epoch provenance records used for identity only."""

    seal = _load(epoch_root / "EPOCH_SEAL.json")
    execution = _load(epoch_root / "FINAL_TEST_EXECUTION_RESULT.json")
    audit = _load(epoch_root / "POST_EXECUTION_AUDIT.json")
    seal_hash = _sha256_file(epoch_root / "EPOCH_SEAL.json")

    _exact(seal.get("status"), "SEALED_AUDIT_PASS", "EPOCH_SEAL_STATUS")
    _exact(seal.get("final_test_complete"), True, "EPOCH_SEAL_FLAG")
    _exact(seal.get("paper_results_frozen"), True, "EPOCH_SEAL_FLAG")
    _exact(seal.get("scientific_definition_changed"), False, "EPOCH_SEAL_FLAG")
    _exact(
        _sha256_file(epoch_root / "FINAL_TEST_EXECUTION_RESULT.json"),
        seal.get("execution_result_sha256"),
        "EXECUTION_RESULT_IDENTITY",
    )
    _exact(
        _sha256_file(epoch_root / "POST_EXECUTION_AUDIT.json"),
        seal.get("post_execution_audit_json_sha256"),
        "POST_AUDIT_IDENTITY",
    )
    return {
        "epoch_seal_status": seal.get("status"),
        "epoch_seal_file_sha256": seal_hash,
        "execution_result_sha256": seal.get("execution_result_sha256"),
        "post_execution_audit_sha256": seal.get("post_execution_audit_json_sha256"),
        "execution_result": execution,
        "audit": audit,
    }


def _frozen_signals(
    consequence_variants: Mapping[str, Any],
) -> dict[str, tuple[Any, Any]]:
    """Reference-variant ``(P^D, P^C)`` per node from the sealed checkpoint."""

    signals = CV.signals_by_variant(consequence_variants, REFERENCE_VARIANT)
    _require(
        bool(signals),
        "STAGE_Q_SCREENING_FROZEN_SIGNALS_EMPTY",
        REFERENCE_VARIANT,
    )
    return signals


def _discover_nominal_baseline(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit if Path(explicit).is_file() else None
    for root in NOMINAL_BASELINE_CANDIDATES:
        candidate = root / NOMINAL_BASELINE_NAME
        if candidate.is_file():
            return candidate
    return None


# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stage x screening-capacity q Stage-I decision sufficiency "
            "sensitivity over the sealed canonical-v2 epoch (read-only)."
        )
    )
    parser.add_argument("--epoch-root", type=Path, default=C.STAGE_MATCHED_FINAL_TEST_ROOT)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=C.ROOT
        / "artifacts"
        / "paper_results_v2_final_test_rmb"
        / "stage_q_sensitivity",
    )
    parser.add_argument(
        "--nominal-baseline",
        type=Path,
        default=None,
        help="published nominal-q projection reproduced by Check 1",
    )
    args = parser.parse_args(argv)

    epoch_root: Path = Path(args.epoch_root)
    out_dir: Path = Path(args.out_dir)
    _require(epoch_root.is_dir(), "EPOCH_ROOT_MISSING", str(epoch_root))

    provenance = _verify_epoch_identity(epoch_root)

    # -- frozen scientific inputs (read-only, hash validated) -----------
    store = CheckpointStore(epoch_root / "checkpoints")
    attention = store.read(S.ATTENTION_DECISIONS)
    consequence_variants = store.read(S.CONSEQUENCE_VARIANTS)
    m4 = store.read(S.M4_COMPARISONS)
    reference_cohort = store.read(S.REFERENCE_RECOVERY_COHORT)

    input_paths = {
        stage: str((epoch_root / "checkpoints" / f"{stage}.json"))
        for stage in (
            S.ATTENTION_DECISIONS,
            S.CONSEQUENCE_VARIANTS,
            S.M4_COMPARISONS,
            S.REFERENCE_RECOVERY_COHORT,
        )
    }
    input_hashes = {name: _sha256_file(Path(path)) for name, path in input_paths.items()}

    _exact(attention.get("reference_variant"), REFERENCE_VARIANT, "REFERENCE_VARIANT")
    _exact(
        tuple(float(value) for value in attention["q_grid"]),
        Q_GRID,
        "ATTENTION_Q_GRID",
    )
    _exact(float(attention["nominal_q"]), NOMINAL_Q, "ATTENTION_NOMINAL_Q")
    _exact(
        tuple(attention["stage1_actionable_stages"]),
        STAGES,
        "STAGE1_ACTIONABLE_STAGES",
    )
    selector = attention["selector"]
    _exact(selector["selector_id"], "M3_STAGE1_SHARED_SELECTOR", "SELECTOR_ID")
    _exact(selector["capacity_rule"], "K = ceil(q * N)", "CAPACITY_RULE")
    _exact(selector["tie_break"], STAGE_I_TIE_BREAK, "TIE_BREAK")
    _exact(selector["operated_per_stage"], True, "SELECTOR_OPERATED_PER_STAGE")
    _exact(bool(selector["pooled_stage1_queue"]), False, "SELECTOR_POOLED_QUEUE")

    signals = _frozen_signals(consequence_variants)

    # Authoritative per-node stage identity, taken from the sealed
    # CONSEQUENCE_VARIANTS rows rather than inferred from the attention rows.
    authoritative_stage_by_node = {
        str(row["node_id"]): str(row["stage"])
        for row in CV.rows_by_variant(consequence_variants, REFERENCE_VARIANT).values()
    }
    authoritative_episode_by_node = {
        str(row["node_id"]): str(row["episode_id"])
        for row in CV.rows_by_variant(consequence_variants, REFERENCE_VARIANT).values()
    }
    _require(
        len(authoritative_stage_by_node) >= len(signals),
        "STAGE_Q_SCREENING_NODE_IDENTITY_INCOMPLETE",
        (len(authoritative_stage_by_node), len(signals)),
    )

    # -- q-independent frozen structures --------------------------------
    rows_by_stage: dict[str, list[Mapping[str, Any]]] = {}
    for stage in STAGES:
        rows = [
            row
            for row in attention["rows"]
            if row["variant"] == REFERENCE_VARIANT and row["stage"] == stage
        ]
        rows.sort(key=lambda row: float(row["q"]))
        _exact(
            tuple(float(row["q"]) for row in rows),
            Q_GRID,
            "STAGE_ROW_Q_GRID",
            stage,
        )
        rows_by_stage[stage] = rows

    stage_geometry: dict[str, dict[str, Any]] = {}
    for stage in STAGES:
        rows = rows_by_stage[stage]
        canonical = tuple(rows[0]["canonical_stage_node_ids"])
        eligible = tuple(rows[0]["eligible_candidate_node_ids"])
        abstaining = tuple(rows[0]["abstaining_node_ids"])
        priority = {
            node_id: float(signals[node_id][1].score) for node_id in eligible
        }
        delay_score = {
            node_id: float(signals[node_id][0].score) for node_id in eligible
        }
        _require(
            all(signals[node_id][1].score is not None for node_id in eligible),
            "STAGE_Q_SCREENING_REFERENCE_SCORE_MISSING",
            stage,
        )
        stage_geometry[stage] = {
            "canonical_node_ids": canonical,
            "eligible_node_ids": eligible,
            "abstaining_node_ids": abstaining,
            "reference_priority": priority,
            "delay_score": delay_score,
            "stage_by_node": {
                node_id: stage
                for node_id in canonical
            },
        }

    checks: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Check 2 / Check 3 / Check 4 - frozen cohort, support and scores
    # ------------------------------------------------------------------
    for stage in STAGES:
        rows = rows_by_stage[stage]
        cohort_sizes = {int(row["cohort_size"]) for row in rows}
        eligible_counts = {int(row["eligible_candidate_count"]) for row in rows}
        canonical_counts = {int(row["canonical_stage_node_count"]) for row in rows}
        eligible_sets = {
            frozenset(row["eligible_candidate_node_ids"]) for row in rows
        }
        canonical_sets = {
            frozenset(row["canonical_stage_node_ids"]) for row in rows
        }
        priority_id = {
            node_id: float(signals[node_id][1].score)
            for node_id in stage_geometry[stage]["eligible_node_ids"]
        }
        delay_id = {
            node_id: float(signals[node_id][0].score)
            for node_id in stage_geometry[stage]["eligible_node_ids"]
        }

        _exact(len(cohort_sizes), 1, "SUPPORTED_POPULATION_DRIFT", stage)
        _exact(len(eligible_counts), 1, "SUPPORTED_POPULATION_DRIFT", stage)
        _exact(len(eligible_sets), 1, "SUPPORT_MASK_DRIFT", stage)
        _exact(eligible_counts == cohort_sizes, True, "SUPPORT_MASK_DRIFT", stage)
        _exact(len(canonical_sets), 1, "CANONICAL_QUEUE_DRIFT", stage)
        _exact(
            int(rows[0]["cohort_size"]),
            len(stage_geometry[stage]["eligible_node_ids"]),
            "SUPPORT_MASK_IDENTITY",
            stage,
        )
        _exact(
            set(stage_geometry[stage]["eligible_node_ids"])
            <= set(stage_geometry[stage]["canonical_node_ids"]),
            True,
            "ELIGIBLE_OUTSIDE_CANONICAL_QUEUE",
            stage,
        )

        expected_priority = stage_geometry[stage]["reference_priority"]
        expected_delay = stage_geometry[stage]["delay_score"]
        _exact(priority_id, expected_priority, "REFERENCE_SCORE_NOT_FIXED", stage)
        _exact(delay_id, expected_delay, "DELAY_SCORE_NOT_FIXED", stage)

        checks[f"{stage}_supported_population_constant"] = len(cohort_sizes) == 1
        checks[f"{stage}_support_mask_identical_across_q"] = len(eligible_sets) == 1

    checks["pre_supported_population_is_constant"] = checks["PRE_IB_supported_population_constant"]
    checks["turn_supported_population_is_constant"] = checks[
        "POST_IB_PRE_OB_supported_population_constant"
    ]
    checks["support_mask_identical_across_q"] = (
        checks["PRE_IB_support_mask_identical_across_q"]
        and checks["POST_IB_PRE_OB_support_mask_identical_across_q"]
    )
    checks["reference_scores_identical_across_q"] = True
    checks["delay_scores_identical_across_q"] = True

    # ------------------------------------------------------------------
    # Check 5 - canonical-node-first, support second, no backfill
    # ------------------------------------------------------------------
    for stage in STAGES:
        geometry = stage_geometry[stage]
        canonical = geometry["canonical_node_ids"]
        identity = [
            (signals[node_id][1].episode_id, stage) for node_id in canonical
        ]
        duplicates = {
            f"{episode_id}|{observed_stage}": count
            for (episode_id, observed_stage), count in Counter(identity).items()
            if count > 1
        }
        _require(
            not duplicates,
            "CANONICAL_NODE_BACKFILL_OR_DUPLICATION",
            {"stage": stage, "duplicates": duplicates},
        )
        abstaining = set(geometry["abstaining_node_ids"])
        _exact(
            abstaining,
            set(canonical) - set(geometry["eligible_node_ids"]),
            "ABSTAINING_SET_MISMATCH",
            stage,
        )
        # An unsupported canonical node must stay unsupported: no other node of
        # the same (episode, stage) may occupy its place in the queue.
        backfilled = [
            node_id
            for node_id in abstaining
            if (signals[node_id][1].episode_id, stage) in Counter(identity)
            and Counter(identity)[(signals[node_id][1].episode_id, stage)] > 1
        ]
        _require(
            not backfilled,
            "CANONICAL_NODE_BACKFILL",
            {"stage": stage, "backfilled": sorted(backfilled)},
        )
    checks["no_canonical_node_backfill"] = True

    # ------------------------------------------------------------------
    # Check 6 - PRE and TURN are ranked separately, never pooled
    # ------------------------------------------------------------------
    # One episode may legitimately own one canonical PRE node and one canonical
    # TURN node (``ONE_NODE_PER_EPISODE_STAGE_BEFORE_SUPPORT``), so episode
    # overlap across stages is expected. What must never happen is a *node*
    # entering two Stage-I queues, a stage queue holding a foreign stage's node,
    # or one stage's shortlist being drawn from another stage's candidates.
    pre_nodes = set(stage_geometry["PRE_IB"]["canonical_node_ids"])
    turn_nodes = set(stage_geometry["POST_IB_PRE_OB"]["canonical_node_ids"])
    _exact(pre_nodes & turn_nodes, set(), "STAGE_POOLING_DETECTED")
    for stage in STAGES:
        geometry = stage_geometry[stage]
        foreign = [
            node_id
            for node_id in geometry["canonical_node_ids"]
            if authoritative_stage_by_node[node_id] != stage
        ]
        _require(
            not foreign,
            "STAGE_CROSS_QUEUE_LEAKAGE",
            {"stage": stage, "foreign_node_ids": sorted(foreign)},
        )
        eligible_foreign = [
            node_id
            for node_id in geometry["eligible_node_ids"]
            if authoritative_stage_by_node[node_id] != stage
        ]
        _require(
            not eligible_foreign,
            "STAGE_CROSS_QUEUE_LEAKAGE",
            {"stage": stage, "eligible_foreign_node_ids": sorted(eligible_foreign)},
        )
    _exact(
        pre_nodes | turn_nodes,
        {
            node_id
            for stage in STAGES
            for node_id in stage_geometry[stage]["canonical_node_ids"]
        },
        "STAGE_QUEUE_PARTITION",
    )
    checks["pre_and_turn_are_ranked_separately"] = True
    checks["stage_queues_are_disjoint_at_node_level"] = True

    # ------------------------------------------------------------------
    # the q grid: re-materialize both shortlists and evaluate
    # ------------------------------------------------------------------
    summary_rows: list[dict[str, Any]] = []
    record_frames: list[pd.DataFrame] = []
    nominal: dict[str, dict[str, Any]] = {}
    nominal_shortlists: dict[str, dict[str, list[str]]] = {}

    for stage in STAGES:
        geometry = stage_geometry[stage]
        stage_node_ids = tuple(geometry["canonical_node_ids"])
        n_supported = len(geometry["eligible_node_ids"])
        class_label = STAGE_CLASS[stage]
        priority = geometry["reference_priority"]

        for row in rows_by_stage[stage]:
            q = float(row["q"])
            k_contract = attention_capacity_k(q, n_supported)
            _exact(int(row["k"]), k_contract, "K_CONTRACT", (stage, q))
            _exact(int(row["cohort_size"]), n_supported, "COHORT_CONTRACT", (stage, q))

            delay_decision, consequence_decision = materialize_stage_q_shortlist(
                stage,
                q,
                frozen_signals=signals,
                stage_node_ids=stage_node_ids,
            )

            # -- frozen-decision identity at every q --------------------
            for signal_name, decision, key in (
                ("DELAY", delay_decision, "delay_decision"),
                ("CONSEQUENCE", consequence_decision, "consequence_decision"),
            ):
                stored = row[key]
                _exact(int(decision.k), int(stored["k"]), "STORED_K_MISMATCH", (stage, q, signal_name))
                _exact(
                    int(decision.cohort_size),
                    int(stored["cohort_size"]),
                    "STORED_COHORT_MISMATCH",
                    (stage, q, signal_name),
                )
                _exact(
                    str(decision.status.value),
                    str(stored["status"]),
                    "STORED_STATUS_MISMATCH",
                    (stage, q, signal_name),
                )
                _exact(
                    len(decision.entries),
                    len(stored["entries"]),
                    "STORED_ENTRY_COUNT_MISMATCH",
                    (stage, q, signal_name),
                )
                for entry, stored_entry in zip(decision.entries, stored["entries"]):
                    _exact(entry.node_id, stored_entry["node_id"], "STORED_RANK_ORDER_MISMATCH", (stage, q, signal_name))
                    _exact(int(entry.rank), int(stored_entry["rank"]), "STORED_RANK_MISMATCH", (stage, q, signal_name))
                    _exact(float(entry.score), float(stored_entry["score"]), "STORED_SCORE_MISMATCH", (stage, q, signal_name))
                    _exact(bool(entry.selected), bool(stored_entry["selected"]), "STORED_SELECTION_MISMATCH", (stage, q, signal_name))

            # -- frozen objective on the frozen consequence basis --------
            evaluation = evaluate_attention_allocation(
                cohort_id=f"{row['variant']}:{stage}",
                reference_id=f"{REFERENCE_VARIANT}:CONSEQUENCE",
                comparator_id=f"{REFERENCE_VARIANT}:DELAY",
                reference_decision=consequence_decision,
                comparator_decision=delay_decision,
                reference_priority=priority,
            )

            reference_shortlist = tuple(evaluation.reference_shortlist)
            delay_shortlist = tuple(evaluation.comparator_shortlist)
            intersection = int(len(set(reference_shortlist) & set(delay_shortlist)))
            k = int(consequence_decision.k)
            _exact(k, len(reference_shortlist), "SHORTLIST_SIZE_MISMATCH", (stage, q))
            _exact(k, len(delay_shortlist), "SHORTLIST_SIZE_MISMATCH", (stage, q))
            _exact(
                intersection,
                int(evaluation.diagnostics["overlap_count"]),
                "OVERLAP_IDENTITY",
                (stage, q),
            )
            changed = k - intersection
            _exact(
                changed,
                int(evaluation.diagnostics["displaced_count"]),
                "CHANGED_POSITION_IDENTITY",
                (stage, q),
            )
            _exact(
                changed,
                int(evaluation.diagnostics["entered_count"]),
                "CHANGED_POSITION_IDENTITY",
                (stage, q),
            )

            a_reference = float(evaluation.reference_attention_value)
            a_delay = float(evaluation.comparator_attention_value)
            delta = float(evaluation.delta_attention_value)
            loss = evaluation.L_att
            retained = None if a_reference == 0.0 else a_delay / a_reference
            _require(
                _close(delta, a_reference - a_delay),
                "DELTA_IDENTITY",
                (stage, q, delta, a_reference - a_delay),
            )
            _require(
                a_reference >= a_delay,
                "CONSEQUENCE_SHORTLIST_NOT_OPTIMAL",
                (stage, q, a_reference, a_delay),
            )
            if changed == 0:
                _exact(
                    set(reference_shortlist),
                    set(delay_shortlist),
                    "ZERO_CHANGED_NOT_IDENTICAL",
                    (stage, q),
                )
                _exact(delta, 0.0, "ZERO_CHANGED_DELTA", (stage, q))
                _exact(loss, 0.0, "ZERO_CHANGED_LOSS", (stage, q))
                _exact(retained, 1.0, "ZERO_CHANGED_RETAINED", (stage, q))

            record = {
                "stage": stage,
                "stage_class": class_label,
                "q": q,
                "N_supported": n_supported,
                "K": k,
                "intersection_count": intersection,
                "overlap_rate": intersection / k,
                "changed_positions": changed,
                "replacement_rate": changed / k,
                "reference_consequence_value": a_reference,
                "delay_shortlist_consequence_value": a_delay,
                "attention_loss": loss,
                "retained_value": retained,
                "entered_chain_count": changed,
                "displaced_chain_count": changed,
            }
            summary_rows.append(record)
            if abs(q - NOMINAL_Q) <= TOL:
                nominal[stage] = record
                nominal_shortlists[stage] = {
                    "reference": list(reference_shortlist),
                    "delay": list(delay_shortlist),
                }

            record_frames.append(
                pd.DataFrame(
                    [
                        {
                            "episode_id": entry.episode_id,
                            "chain_id": entry.chain_id,
                            "node_id": entry.node_id,
                            "stage": stage,
                            "q": q,
                            "reference_selected": bool(entry.selected),
                            "delay_selected": bool(delay_selected),
                            "reference_rank": int(entry.rank),
                            "delay_rank": int(delay_rank),
                            "reference_priority": float(entry.score),
                            "delay_score": float(delay_score),
                        }
                        for entry, delay_selected, delay_rank, delay_score in _records(
                            consequence_decision, delay_decision, priority
                        )
                    ]
                )
            )

    checks["stage1_decision_identity_across_q"] = True

    # ------------------------------------------------------------------
    # Check 7 - tie-break contract unchanged
    # ------------------------------------------------------------------
    checks["tie_break_contract_id"] = STAGE_I_TIE_BREAK
    _exact(
        STAGE_I_TIE_BREAK,
        "(-score, episode_id, node_id)",
        "TIE_BREAK_CONTRACT_ID",
    )
    _exact(
        tuple(float(value) for value in ATTENTION_CAPACITY_GRID),
        Q_GRID,
        "CAPACITY_GRID_CONTRACT_ID",
    )

    # ------------------------------------------------------------------
    # Check 1 - nominal q = 0.10 reproduces the canonical Stage-I result
    # ------------------------------------------------------------------
    nominal_check = _nominal_reproduction(
        nominal=nominal,
        nominal_shortlists=nominal_shortlists,
        m4=m4,
        reference_cohort=reference_cohort,
        baseline_path=_discover_nominal_baseline(args.nominal_baseline),
    )
    checks["nominal_pre_matches_canonical"] = nominal_check["pre"]["canonical_match"]
    checks["nominal_turn_matches_canonical"] = nominal_check["turn"]["canonical_match"]
    _require(
        nominal_check["pre"]["canonical_match"]
        and nominal_check["turn"]["canonical_match"],
        "NOMINAL_Q_DID_NOT_REPRODUCE_CANONICAL",
        nominal_check,
    )

    # ------------------------------------------------------------------
    # outputs
    # ------------------------------------------------------------------
    # Reporting order is the frozen stage order (PRE then TURN); ranking itself
    # is always stage-local and never pooled.
    stage_order = {stage: index for index, stage in enumerate(STAGES)}
    summary = pd.DataFrame(summary_rows)[
        [
            "stage",
            "stage_class",
            "q",
            "N_supported",
            "K",
            "intersection_count",
            "overlap_rate",
            "changed_positions",
            "replacement_rate",
            "reference_consequence_value",
            "delay_shortlist_consequence_value",
            "attention_loss",
            "retained_value",
            "entered_chain_count",
            "displaced_chain_count",
        ]
    ]
    summary = (
        summary.assign(_stage_order=summary["stage"].map(stage_order))
        .sort_values(["_stage_order", "q"], kind="stable")
        .drop(columns="_stage_order")
        .reset_index(drop=True)
    )

    records = pd.concat(record_frames, ignore_index=True)
    records = (
        records.assign(_stage_order=records["stage"].map(stage_order))
        .sort_values(["_stage_order", "q", "reference_rank"], kind="stable")
        .drop(columns="_stage_order")
        .reset_index(drop=True)
    )
    figure_data = summary[
        ["stage", "stage_class", "q", "replacement_rate", "retained_value", "attention_loss", "K"]
    ].copy()

    out_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_dir / SUMMARY_NAME, index=False, lineterminator="\n")
    records.to_parquet(out_dir / RECORDS_NAME, index=False)
    figure_data.to_csv(out_dir / FIGURE_DATA_NAME, index=False, lineterminator="\n")
    (out_dir / TABLE_NAME).write_text(
        _render_latex(summary, nominal_check), encoding="utf-8", newline="\n"
    )

    manifest = {
        "experiment": EXPERIMENT_ID,
        "split": SPLIT,
        "q_grid": list(Q_GRID),
        "nominal_q": NOMINAL_Q,
        "model_retrained": False,
        "model_recalibrated": False,
        "parameter_reselected": False,
        "state_recomputed": False,
        "consequence_mapping_changed": False,
        "reference_priority_changed": False,
        "delay_priority_changed": False,
        "support_rule_changed": False,
        "canonical_stage_rule_changed": False,
        "tie_breaking_changed": False,
        "stage_pooling": False,
        "stage2_cohort_changed": False,
        "stage2_computation_performed": False,
        "bootstrap_executed": False,
        "final_test_raw_data_read": False,
        "new_access_epoch_opened": False,
        "canonical_nominal_artifact_overwritten": False,
        "reference_variant": REFERENCE_VARIANT,
        "reference_representation_id": C.REFERENCE_REPRESENTATION_ID,
        "stage1_actionable_stages": list(STAGES),
        "stage_class": STAGE_CLASS,
        "rounding_contract": "K = ceil(q * N)",
        "tie_break_contract_id": STAGE_I_TIE_BREAK,
        "selector_id": "M3_STAGE1_SHARED_SELECTOR",
        "objective_definition": {
            "A_reference": "sum of frozen P^C over the consequence-based shortlist",
            "A_delay": "sum of the same frozen P^C over the delay-based shortlist",
            "attention_loss": "L_att = (A_reference - A_delay) / A_reference",
            "retained_value": "A_delay / A_reference = 1 - L_att",
            "reused_frozen_objective": "model.M4.evaluation.evaluate_attention_allocation",
            "reused_frozen_selector": "model.M3.stage1.select_paired_attention",
        },
        "git_head": _git_head(),
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "code_entrypoint": "formal/v2_phase7/stage_q_screening_sensitivity.py",
        "epoch_root": str(epoch_root),
        "frozen_reference_inputs": {
            "published_nominal_projection": {
                "staged_path": str(
                    C.ROOT
                    / "artifacts"
                    / "paper_results_v2_final_test_rmb"
                    / "stage_q_sensitivity"
                    / INPUT_DIR_NAME
                    / NOMINAL_BASELINE_NAME
                ),
                "source_branch": "results/delay-vs-consequence-stage1-20260920",
                "source_commit": "0032259",
                "source_repo_path": (
                    "artifacts/experiment/final_test_v2_stage_matched_canonical_v2/"
                    f"{NOMINAL_BASELINE_NAME}"
                ),
                "source_blob_oid": "c6cb18ae3d574cba0b73f949d0195513b3fcedcc",
                "sha256": (
                    None
                    if nominal_check["authorities"]
                    .get("published_nominal_projection") is None
                    else nominal_check["authorities"]["published_nominal_projection"]["sha256"]
                ),
                "read_only": True,
            }
        },
        "input_artifact_paths": input_paths,
        "input_artifact_hashes": input_hashes,
        "epoch_provenance": {
            "epoch_seal_status": provenance["epoch_seal_status"],
            "epoch_seal_file_sha256": provenance["epoch_seal_file_sha256"],
            "execution_result_sha256": provenance["execution_result_sha256"],
            "post_execution_audit_sha256": provenance["post_execution_audit_sha256"],
        },
        "output_artifact_paths": {},
        "output_artifact_hashes": {},
        "regression_checks": checks,
        "nominal_reproduction_check": nominal_check,
        "output_artifact_hashes_note": (
            "output_artifact_hashes covers the four data/table artifacts; the "
            "manifest cannot contain its own SHA256 by construction and is "
            "listed in output_artifact_paths only"
        ),
        "warnings": nominal_check["warnings"],
    }

    output_paths = {
        SUMMARY_NAME: out_dir / SUMMARY_NAME,
        RECORDS_NAME: out_dir / RECORDS_NAME,
        TABLE_NAME: out_dir / TABLE_NAME,
        FIGURE_DATA_NAME: out_dir / FIGURE_DATA_NAME,
    }
    manifest["output_artifact_paths"] = {
        name: str(path) for name, path in output_paths.items()
    }
    manifest["output_artifact_hashes"] = {
        name: _sha256_file(path) for name, path in output_paths.items()
    }
    # The row-level parquet is a regenerable local intermediate. Paper-results
    # roots in this repository version-control CSV/JSON/MD only (no parquet), so
    # its path and hash are recorded here instead of being committed.
    manifest["output_artifact_tracking"] = {
        "committed_to_git": [SUMMARY_NAME, TABLE_NAME, FIGURE_DATA_NAME, MANIFEST_NAME],
        "local_only_regenerable": {
            RECORDS_NAME: {
                "path": str(out_dir / RECORDS_NAME),
                "sha256": manifest["output_artifact_hashes"][RECORDS_NAME],
                "reason": (
                    "PROJECT_ARTIFACT_POLICY: paper-results roots track "
                    "CSV/JSON/MD only; row-level parquet stays local and is "
                    "reproducible by re-running this entrypoint"
                ),
            }
        },
    }
    manifest_path = out_dir / MANIFEST_NAME
    manifest["output_artifact_paths"][MANIFEST_NAME] = str(manifest_path)

    with open(manifest_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False))
        handle.write("\n")

    for name, path in output_paths.items():
        print(f"wrote {path}")
    print(f"wrote {manifest_path}")
    return 0


def _records(consequence_decision, delay_decision, priority) -> list[tuple]:
    delay_by_node = {
        entry.node_id: (bool(entry.selected), int(entry.rank), float(entry.score))
        for entry in delay_decision.entries
    }
    return [
        (
            entry,
            delay_by_node[entry.node_id][0],
            delay_by_node[entry.node_id][1],
            delay_by_node[entry.node_id][2],
        )
        for entry in consequence_decision.entries
    ]


def _nominal_reproduction(
    *,
    nominal: Mapping[str, Mapping[str, Any]],
    nominal_shortlists: Mapping[str, Mapping[str, Sequence[str]]],
    m4: Mapping[str, Any],
    reference_cohort: Mapping[str, Any],
    baseline_path: Path | None,
) -> dict[str, Any]:
    """Check 1: q = 0.10 must reproduce the canonical Stage-I result exactly."""

    warnings: list[str] = []
    _exact(set(nominal), set(STAGES), "NOMINAL_STAGE_COVERAGE")

    # -- authority A: the sealed M4 canonical attention block -----------
    m4_attention = m4["attention"]["by_stage"]
    # -- authority B: the sealed reference recovery cohort (R*) ---------
    r_star = tuple(reference_cohort["shortlist_node_ids"])
    r_star_rule = str(reference_cohort["shortlist_rule"])

    result: dict[str, Any] = {"warnings": warnings, "authorities": {}}
    union: list[str] = []
    for stage in STAGES:
        record = nominal[stage]
        block = m4_attention[stage]
        canonical_k = int(block["capacity"]["k"])
        canonical_n = int(block["capacity"]["cohort_size"])
        canonical_ids = sorted(block["reference_shortlist_node_ids"])
        union.extend(block["reference_shortlist_node_ids"])

        checks = {
            "N_supported": _exact_int(record["N_supported"], canonical_n),
            "K": _exact_int(record["K"], canonical_k),
            "reference_shortlist_ids": sorted(
                nominal_shortlists[stage]["reference"]
            )
            == canonical_ids,
            "reference_consequence_value": _close(
                record["reference_consequence_value"],
                float(block["self_reference"]["reference_attention_value"]),
            ),
        }
        checks["all_match"] = all(checks.values())
        result[STAGE_CLASS[stage].lower()] = {
            "N_supported": record["N_supported"],
            "K": record["K"],
            "intersection_count": record["intersection_count"],
            "changed_positions": record["changed_positions"],
            "overlap_rate": record["overlap_rate"],
            "attention_loss": record["attention_loss"],
            "retained_value": record["retained_value"],
            "canonical_match": checks["all_match"],
            "per_field": checks,
        }

    union_check = sorted(union) == sorted(r_star)
    _require(
        union_check,
        "NOMINAL_R_STAR_UNION_MISMATCH",
        {"rule": r_star_rule, "union_count": len(union), "r_star_count": len(r_star)},
    )
    result["authorities"]["m4_canonical_attention_block"] = True
    result["authorities"]["reference_recovery_cohort_union"] = union_check

    # -- authority C: the published nominal-q projection ----------------
    if baseline_path is None:
        _require(False, "NOMINAL_BASELINE_NOT_FOUND", [str(p) for p in NOMINAL_BASELINE_CANDIDATES])
    baseline = _load(baseline_path)
    published = baseline["results"]
    for stage in STAGES:
        record = nominal[stage]
        expected = published[stage]
        checks = result[STAGE_CLASS[stage].lower()]["per_field"]
        checks["published_N_supported"] = _exact_int(record["N_supported"], int(expected["n_g"]))
        checks["published_K"] = _exact_int(record["K"], int(expected["k_g"]))
        checks["published_intersection_count"] = _exact_int(
            record["intersection_count"], int(expected["overlap_count"])
        )
        checks["published_changed_positions"] = _exact_int(
            record["changed_positions"], int(expected["changed_position_count"])
        )
        checks["published_overlap_rate"] = _close(
            record["overlap_rate"],
            int(expected["overlap_count"]) / int(expected["k_g"]),
        )
        checks["published_replacement_rate"] = _close(
            record["replacement_rate"], float(expected["changed_position_share"])
        )
        checks["published_reference_consequence_value"] = _close(
            record["reference_consequence_value"], float(expected["a_consequence"])
        )
        checks["published_delay_shortlist_consequence_value"] = _close(
            record["delay_shortlist_consequence_value"], float(expected["a_delay"])
        )
        checks["published_attention_loss"] = _close(
            record["attention_loss"], float(expected["L_att"])
        )
        checks["published_retained_value"] = _close(
            record["retained_value"], float(expected["eta_att"])
        )
        checks["published_reference_shortlist_ids"] = sorted(
            nominal_shortlists[stage]["reference"]
        ) == sorted(expected["consequence_shortlist_ids"])
        checks["published_delay_shortlist_ids"] = sorted(
            nominal_shortlists[stage]["delay"]
        ) == sorted(expected["delay_shortlist_ids"])
        checks["all_match"] = all(checks.values())
        result[STAGE_CLASS[stage].lower()]["canonical_match"] = checks["all_match"]

    result["authorities"]["published_nominal_projection"] = {
        "path": str(baseline_path),
        "sha256": _sha256_file(baseline_path),
        "source_checkpoint_file_sha256": baseline["source_checkpoint"]["file_sha256"],
    }
    return result


def _exact_int(observed: Any, expected: Any) -> bool:
    return int(observed) == int(expected)


def _render_latex(summary: pd.DataFrame, nominal_check: Mapping[str, Any]) -> str:
    lines = [
        "% Air Slot: Stage x screening-capacity q Stage-I decision sufficiency",
        "% Generated by formal/v2_phase7/stage_q_screening_sensitivity.py (read-only).",
        "\\begin{tabular}{llrrrrr}",
        "\\toprule",
        "Stage & $q$ & $N$ & $K$ & Changed & Replacement rate & Retained value \\\\",
        "\\midrule",
    ]
    previous = None
    for _, row in summary.iterrows():
        label = str(row["stage_class"]) if row["stage_class"] != previous else ""
        previous = row["stage_class"]
        lines.append(
            f"{label} & {row['q']:.2f} & {int(row['N_supported'])} & {int(row['K'])} & "
            f"{int(row['changed_positions'])}/{int(row['K'])} & "
            f"{row['replacement_rate']:.4f} & {row['retained_value']:.4f} \\\\"
        )
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}",
            "",
            "% nominal q = 0.10 canonical reproduction:"
            f" PRE={nominal_check['pre']['canonical_match']},"
            f" TURN={nominal_check['turn']['canonical_match']}",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
