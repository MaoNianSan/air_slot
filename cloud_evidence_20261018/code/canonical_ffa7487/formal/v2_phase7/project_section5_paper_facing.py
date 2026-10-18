"""Deterministic read-only projection of the sealed canonical-v2 Final-Test
checkpoints into the committed Section-5 paper-facing results.

This tool performs NO scientific computation. Every reported quantity is
either copied verbatim from the sealed checkpoints of the canonical stage-
matched Final-Test epoch (``artifacts/experiment/final_test_v2_stage_matched_canonical_v2``)
or derived by an explicit definitional identity listed in the output
(``projection.derived_definitional_values``). It never reads Final-Test raw
data, never opens or re-opens an access epoch, never executes model code, and
never touches legacy epochs (``final_test_v2``, ``final_test_v2_stage_matched``,
``final_test_v2_stage_matched_canonical_v1``) or Development outputs.

Usage (from the repository root):

    python -m formal.v2_phase7.project_section5_paper_facing \
        --epoch-root <path to sealed canonical-v2 epoch root> \
        --out-dir <directory receiving the two result files> \
        [--materializer-sha256 <sha256 of the committed script blob>]

The script is fail-closed: any provenance, hash, seal-flag or cross-check
failure aborts materialization with a non-zero exit code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

PAPER_PRIMARY_BRANCH = "v2/paper-primary"
PAPER_PRIMARY_COMMIT = "b753db8251812faec2eb2dbdabf34c325eb76f9b"
FINAL_TEST_BRANCH = "v2/phase7-gate-a"
PHASE7_SCIENTIFIC_COMMIT = "8360dd7d88958ae139322d0ea5c66f1c5fe6455c"
FINAL_TEST_TAG = "jatm-final-test-freeze-20260920"
EPOCH_REPO_PATH = "artifacts/experiment/final_test_v2_stage_matched_canonical_v2"
SCRIPT_REPO_PATH = "formal/v2_phase7/project_section5_paper_facing.py"

REFERENCE_VARIANT = "HISTORY_JOINT"
COMPARATOR_VARIANTS = ("CURRENT_JOINT", "HISTORY_POINT", "HISTORY_MARGINAL")
ACTIONABLE_STAGES = ("PRE_IB", "POST_IB_PRE_OB")
STAGE_CLASS_BY_STAGE = {"PRE_IB": "PRE", "POST_IB_PRE_OB": "TURN"}
STAT_TOLERANCE = 1e-12

JSON_NAME = "PAPER_FACING_SECTION5_RESULTS.json"
MD_NAME = "PAPER_FACING_SECTION5_RESULTS.md"

_REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# deterministic helpers
# ---------------------------------------------------------------------------
def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _content_id(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _require(condition: bool, code: str, detail: Any = None) -> None:
    if not condition:
        raise RuntimeError(f"{code}: {detail}")


def _median(values: Sequence[float]) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    return ordered[len(ordered) // 2]


def _iqr(values: Sequence[float]) -> float | None:
    array = np.asarray([float(value) for value in values], dtype=float)
    if array.size == 0:
        return None
    return float(np.quantile(array, 0.75) - np.quantile(array, 0.25))


def _p90(values: Sequence[float]) -> float | None:
    array = np.asarray([float(value) for value in values], dtype=float)
    if array.size == 0:
        return None
    return float(np.quantile(array, 0.90))


def _close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= STAT_TOLERANCE


def _num(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


# ---------------------------------------------------------------------------
# materialization
# ---------------------------------------------------------------------------
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Project sealed canonical-v2 checkpoints into Section-5 "
        "paper-facing results (read-only, no scientific recomputation)."
    )
    parser.add_argument("--epoch-root", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--materializer-sha256", default=None)
    args = parser.parse_args(argv)

    epoch_root: Path = args.epoch_root
    out_dir: Path = args.out_dir
    materializer_sha256: str | None = args.materializer_sha256
    checkpoints = epoch_root / "checkpoints"

    # -- sealed evidence ----------------------------------------------------
    seal = _load(epoch_root / "EPOCH_SEAL.json")
    execution = _load(epoch_root / "FINAL_TEST_EXECUTION_RESULT.json")
    audit = _load(epoch_root / "POST_EXECUTION_AUDIT.json")
    freeze = _load(_REPO_ROOT / "formal" / "JATM_STAGE_MATCHED_FINAL_TEST_FREEZE_V2.json")

    # -- fail-closed seal verification --------------------------------------
    _require(seal.get("final_test_complete") is True, "SEAL_FLAG", "final_test_complete")
    _require(seal.get("paper_results_frozen") is True, "SEAL_FLAG", "paper_results_frozen")
    _require(seal.get("ready_for_freeze") is True, "SEAL_FLAG", "ready_for_freeze")
    _require(seal.get("execution_status") == "PASS", "SEAL_FLAG", "execution_status")
    _require(seal.get("audit_status") == "PASS", "SEAL_FLAG", "audit_status")
    _require(seal.get("status") == "SEALED_AUDIT_PASS", "SEAL_FLAG", "status")
    _require(seal.get("scientific_definition_changed") is False, "SEAL_FLAG", "changed")
    _require(seal.get("second_epoch_opened") is False, "SEAL_FLAG", "second_epoch_opened")
    _require(audit.get("status") == "PASS", "AUDIT_FLAG", audit.get("status"))
    _require(not audit.get("blocking_failure_codes"), "AUDIT_BLOCKING", audit.get("blocking_failure_codes"))
    _require(
        freeze.get("artifact_hash")
        == "sha256:05b6327ae842dc23b5449e61d541337a18da4aa388063f9ab6862ae2a1808ecc",
        "FREEZE_HASH",
        freeze.get("artifact_hash"),
    )

    # -- evidence file hash verification ------------------------------------
    evidence_hashes: dict[str, dict[str, Any]] = {}

    def _verify_file(name: str, path: Path, recorded: str | None) -> None:
        actual = _sha256_file(path)
        evidence_hashes[name] = {
            "file": path.name,
            "file_sha256": actual,
            "recorded_sha256": recorded,
            "match": recorded is None or actual == recorded,
        }
        _require(recorded is None or actual == recorded, "EVIDENCE_HASH", f"{name}: {actual} != {recorded}")

    _verify_file("EPOCH_SEAL.json", epoch_root / "EPOCH_SEAL.json", None)
    _verify_file(
        "FINAL_TEST_EXECUTION_RESULT.json",
        epoch_root / "FINAL_TEST_EXECUTION_RESULT.json",
        seal.get("execution_result_sha256"),
    )
    _verify_file(
        "POST_EXECUTION_AUDIT.json",
        epoch_root / "POST_EXECUTION_AUDIT.json",
        seal.get("post_execution_audit_json_sha256"),
    )
    _verify_file(
        "POST_EXECUTION_AUDIT.md",
        epoch_root / "POST_EXECUTION_AUDIT.md",
        seal.get("post_execution_audit_md_sha256"),
    )
    _verify_file(
        "PHASE7_ACCESS_AUDIT.json",
        epoch_root / "PHASE7_ACCESS_AUDIT.json",
        seal.get("access_audit_sha256"),
    )

    # -- checkpoint hash + payload identity verification ---------------------
    stage_records = execution["result"]["manifest"]["stage_records"]
    checkpoint_names = sorted(stage_records)
    usage_by_stage = {
        "PAPER_VIEWS": "section 5.1 capacity rows; section 5.5 axes/nominal base",
        "ATTENTION_DECISIONS": "Stage-I selection sets (upstream of M4 attention comparisons)",
        "REFERENCE_RECOVERY_COHORT": "section 5.2 R* cohort counts and support exclusions",
        "RECOVERY_DECISIONS": "section 5.2 descriptive recovery summaries",
        "M4_COMPARISONS": "sections 5.1/5.3 attention and recovery comparisons",
        "BOOTSTRAP": "sections 5.3 confidence intervals and paired increments",
        "ROBUSTNESS": "section 5.4 OFAT rows",
    }
    source_checkpoints: dict[str, dict[str, Any]] = {}
    for stage in checkpoint_names:
        record = stage_records[stage]
        checkpoint_path = checkpoints / f"{stage}.json"
        _require(checkpoint_path.exists(), "CHECKPOINT_MISSING", str(checkpoint_path))
        doc = _load(checkpoint_path)
        payload_hash = _content_id(doc["payload"])
        file_hash = _sha256_file(checkpoint_path)
        source_checkpoints[stage] = {
            "file": f"checkpoints/{stage}.json",
            "file_sha256": file_hash,
            "recorded_file_sha256": record.get("file_sha256"),
            "payload_hash": payload_hash,
            "recorded_payload_hash": record.get("payload_hash"),
            "file_hash_match": file_hash == record.get("file_sha256"),
            "payload_hash_match": payload_hash == record.get("payload_hash"),
            "declared_payload_hash_match": payload_hash == doc.get("payload_hash"),
            "used_for": usage_by_stage.get(stage, "upstream chain (verified, not read for values)"),
        }
        _require(
            source_checkpoints[stage]["file_hash_match"],
            "CHECKPOINT_FILE_HASH",
            stage,
        )
        _require(
            source_checkpoints[stage]["payload_hash_match"]
            and source_checkpoints[stage]["declared_payload_hash_match"],
            "CHECKPOINT_PAYLOAD_HASH",
            stage,
        )

    def ck_payload(stage: str) -> Mapping[str, Any]:
        return _load(checkpoints / f"{stage}.json")["payload"]

    paper_views = ck_payload("PAPER_VIEWS")
    attention_decisions = ck_payload("ATTENTION_DECISIONS")
    reference_cohort = ck_payload("REFERENCE_RECOVERY_COHORT")
    recovery_decisions = ck_payload("RECOVERY_DECISIONS")
    m4 = ck_payload("M4_COMPARISONS")
    bootstrap = ck_payload("BOOTSTRAP")
    robustness = ck_payload("ROBUSTNESS")

    # -- section 5.1: Stage-I attention --------------------------------------
    attention_nominal_q = float(paper_views["section_5_2"]["nominal_q"])
    capacity_rows: list[dict[str, Any]] = []
    for row in paper_views["section_5_2"]["rows"]:
        stage = row["stage"]
        q = float(row["q"])
        entry: dict[str, Any] = {
            "stage": stage,
            "q": q,
            "n_g": int(row["canonical_stage_node_count"]),
            "k_g": int(row["k"]),
            "cohort_size": int(row["cohort_size"]),
            "eligible_candidate_count": int(row["eligible_candidate_count"]),
            "abstaining_node_count": int(row["abstaining_node_count"]),
            "selected_node_count": int(row["selected_node_count"]),
            "selected_stage_counts": dict(row["selected_stage_counts"]),
            "selected_stage_class_counts": dict(row["selected_stage_class_counts"]),
            "attention_comparison": None,
            "attention_comparison_status": "NOT_AVAILABLE_AT_NON_NOMINAL_Q",
        }
        if stage == "OVERALL":
            entry["aggregation_note"] = (
                "OVERALL row = sum over actionable stages at fixed q; "
                "not a pooled PRE+TURN ranking"
            )
            if abs(q - attention_nominal_q) <= 1e-12:
                entry["attention_comparison_status"] = "SEE_OVERALL_ATTENTION_NOMINAL_Q"
        capacity_rows.append(entry)

    def _stage_attention_record(stage: str, comparator: str) -> dict[str, Any]:
        record = m4["attention"]["by_stage"][stage]["comparators"][comparator]
        reference_k = int(len(record["reference_shortlist"]))
        entered = len(record.get("entered") or ())
        displaced = len(record.get("displaced") or ())
        overlap = int(record["overlap_count"])
        _require(entered == displaced, "ATTENTION_SET_PARTITION", f"{stage}/{comparator}")
        _require(overlap + displaced == reference_k, "ATTENTION_SET_PARTITION", f"{stage}/{comparator}")
        loss = record.get("L_att")
        retained = None if loss is None else 1.0 - float(loss)
        reassigned = None if not reference_k else displaced / reference_k
        return {
            "reference_attention_value": record["reference_attention_value"],
            "comparator_attention_value": record["comparator_attention_value"],
            "delta_attention_value": record["delta_attention_value"],
            "L_att": loss,
            "retained_value": retained,
            "overlap_count": overlap,
            "entered_count": entered,
            "displaced_count": displaced,
            "reassigned_share": reassigned,
            "reference_shortlist_size": reference_k,
            "overlap_fraction_of_reference": record.get("overlap_fraction_of_reference"),
            "kendall_tau": record.get("kendall_tau"),
            "spearman_rho": record.get("spearman_rho"),
            "mean_rank_displacement": record.get("mean_rank_displacement"),
            "max_rank_displacement": record.get("max_rank_displacement"),
            "status": record.get("status"),
            "typed_state": record.get("typed_state"),
            "derived_definitional_values": ["retained_value = 1 - L_att", "reassigned_share = displaced_count / reference_shortlist_size"],
        }

    stage_comparison: dict[str, Any] = {}
    for stage in ACTIONABLE_STAGES:
        by_comparator = {
            comparator: _stage_attention_record(stage, comparator)
            for comparator in COMPARATOR_VARIANTS
        }
        stage_capacity = [
            row for row in capacity_rows if row["stage"] == stage and abs(row["q"] - attention_nominal_q) <= 1e-12
        ][0]
        stage_capacity["attention_comparison"] = {
            "scope": "NOMINAL_Q_ONLY",
            "q": attention_nominal_q,
            "reference_shortlist_size": int(by_comparator[COMPARATOR_VARIANTS[0]]["reference_shortlist_size"]),
            "by_comparator": by_comparator,
        }
        stage_capacity["attention_comparison_status"] = "SEALED_AT_NOMINAL_Q"
        stage_comparison[stage] = {
            "stage_class": STAGE_CLASS_BY_STAGE[stage],
            "n_g": int(stage_capacity["n_g"]),
            "k_g": int(stage_capacity["k_g"]),
            "by_comparator": by_comparator,
        }
        # attention comparison identity checks
        for comparator, record in by_comparator.items():
            reference_value = float(record["reference_attention_value"])
            delta = float(record["delta_attention_value"])
            loss = record["L_att"]
            _require(
                _close(reference_value - float(record["comparator_attention_value"]), delta),
                "ATTENTION_DELTA_IDENTITY",
                f"{stage}/{comparator}",
            )
            _require(
                loss is None or _close(delta / reference_value, float(loss)),
                "ATTENTION_LOSS_IDENTITY",
                f"{stage}/{comparator}",
            )

    overall_attention: dict[str, Any] = {}
    overall_reference = None
    for comparator in COMPARATOR_VARIANTS:
        record = m4["attention"]["comparators"][comparator]
        overall_reference = record["reference_attention_value"] if overall_reference is None else overall_reference
        reference_k = int(m4["cohort_size"])
        entered = len(record.get("entered") or ())
        displaced = len(record.get("displaced") or ())
        overlap = int(record["overlap_count"])
        _require(entered == displaced, "OVERALL_ATTENTION_PARTITION", comparator)
        _require(overlap + displaced == reference_k, "OVERALL_ATTENTION_PARTITION", comparator)
        _require(
            abs(float(overall_reference) - float(record["reference_attention_value"])) <= STAT_TOLERANCE,
            "OVERALL_REFERENCE_MISMATCH",
            comparator,
        )
        loss = record.get("L_att")
        overall_attention[comparator] = {
            "comparator_attention_value": record["comparator_attention_value"],
            "delta_attention_value": float(overall_reference) - float(record["comparator_attention_value"]),
            "L_att": loss,
            "retained_value": None if loss is None else 1.0 - float(loss),
            "overlap_count": overlap,
            "entered_count": entered,
            "displaced_count": displaced,
            "reassigned_share": displaced / reference_k,
        }
    stage_reference_sum = sum(
        float(stage_comparison[stage]["by_comparator"][COMPARATOR_VARIANTS[0]]["reference_attention_value"])
        for stage in ACTIONABLE_STAGES
    )
    _require(
        _close(stage_reference_sum, float(overall_reference)),
        "OVERALL_REFERENCE_COMPOSITION",
        (stage_reference_sum, overall_reference),
    )
    for comparator in COMPARATOR_VARIANTS:
        stage_overlap = sum(
            int(stage_comparison[stage]["by_comparator"][comparator]["overlap_count"])
            for stage in ACTIONABLE_STAGES
        )
        _require(
            stage_overlap == overall_attention[comparator]["overlap_count"],
            "OVERALL_OVERLAP_COMPOSITION",
            comparator,
        )
        stage_delta = sum(
            float(stage_comparison[stage]["by_comparator"][comparator]["delta_attention_value"])
            for stage in ACTIONABLE_STAGES
        )
        _require(
            _close(stage_delta, overall_attention[comparator]["delta_attention_value"]),
            "OVERALL_DELTA_COMPOSITION",
            comparator,
        )

    section_5_1 = {
        "reference_variant": REFERENCE_VARIANT,
        "reference_representation_id": paper_views["section_5_2"]["reference_representation_id"],
        "stage1_actionable_stages": list(ACTIONABLE_STAGES),
        "q_grid": list(paper_views["section_5_2"]["q_grid"]),
        "nominal_q": attention_nominal_q,
        "capacity_rule": paper_views["section_5_2"]["capacity_rule"],
        "overall_rule": paper_views["section_5_2"]["overall_rule"],
        "aggregation_confirmation": "OBJECTIVES_THEN_NORMALIZE",
        "pooled_stage1_ranking": False,
        "attention_values_note": (
            "Reference/comparator attention objectives and displacement diagnostics are "
            "sealed at the nominal q = 0.10 operating point only; rows at other q carry "
            "typed nulls and are never recomputed"
        ),
        "capacity_rows": capacity_rows,
        "stage_attention_comparison_nominal_q": stage_comparison,
        "overall_attention_nominal_q": {
            "aggregation": m4["attention"]["aggregation"],
            "aggregation_confirmation": "OBJECTIVES_THEN_NORMALIZE",
            "pooled_stage1_ranking_constructed": False,
            "reference_shortlist_size": int(m4["cohort_size"]),
            "aggregated_reference_objective": overall_reference,
            "by_comparator": overall_attention,
            "note": (
                "overall objectives are the stage objectives summed then normalized; "
                "stage-specific L_att values are never averaged"
            ),
        },
    }

    # -- section 5.2: Stage-II recovery --------------------------------------
    reference_rows = [
        row for row in recovery_decisions["rows"] if row.get("variant") == REFERENCE_VARIANT
    ]
    _require(bool(reference_rows), "RECOVERY_REFERENCE_ROWS_MISSING")
    grouped: dict[str, list[dict[str, float]]] = {"PRE": [], "TURN": []}
    for row in reference_rows:
        decision = row["decision"]
        stage_class = STAGE_CLASS_BY_STAGE[row["stage"]]
        grouped[stage_class].append(
            {
                "V": float(decision["recoverable_value"]),
                "u_star": float(decision["u_star"]),
            }
        )

    def _recovery_summary(pairs: Sequence[Mapping[str, float]]) -> dict[str, Any]:
        values = [float(pair["V"]) for pair in pairs]
        positive_u = [float(pair["u_star"]) for pair in pairs if float(pair["u_star"]) > 0.0]
        return {
            "N": len(values),
            "median_V": _median(values),
            "IQR_V": _iqr(values),
            "P90_V": _p90(values),
            "positive_V_share": (sum(value > 0.0 for value in values) / len(values)) if values else None,
            "activation_count": len(positive_u),
            "activation_share": (len(positive_u) / len(values)) if values else None,
            "positive_u_count": len(positive_u),
            "median_positive_u": _median(positive_u),
            "IQR_positive_u": _iqr(positive_u),
            "P90_positive_u": _p90(positive_u),
        }

    summary_by_stage = {
        "PRE": _recovery_summary(grouped["PRE"]),
        "TURN": _recovery_summary(grouped["TURN"]),
        "OVERALL": _recovery_summary([*grouped["PRE"], *grouped["TURN"]]),
    }

    robustness_nominal_rows = [row for row in robustness["rows"] if row["nominal_flag"]]
    robustness_cross_check: dict[str, Any] = {}
    for stage_class in ("PRE", "TURN"):
        sealed = [row for row in robustness_nominal_rows if row["stage"] == stage_class]
        _require(bool(sealed), "ROBUSTNESS_NOMINAL_ROW_MISSING", stage_class)
        matches = all(
            all(
                _close(summary_by_stage[stage_class][key], row[key])
                for key in (
                    "median_V",
                    "IQR_V",
                    "P90_V",
                    "positive_V_share",
                    "activation_share",
                    "median_positive_u",
                    "IQR_positive_u",
                    "P90_positive_u",
                )
            )
            and int(summary_by_stage[stage_class]["N"]) == int(row["N"])
            for row in sealed
        )
        robustness_cross_check[stage_class] = "MATCH" if matches else "MISMATCH"
        _require(matches, "ROBUSTNESS_CROSS_CHECK", stage_class)

    shortlist_stage_counts = reference_cohort["shortlist_stage_counts"]
    r_star_pre = int(shortlist_stage_counts["PRE_IB"])
    r_star_turn = int(shortlist_stage_counts["POST_IB_PRE_OB"])
    r_star_count = int(reference_cohort["shortlist_size"])
    _require(r_star_count == 16 and r_star_pre == 3 and r_star_turn == 13, "R_STAR_COUNTS", (r_star_count, r_star_pre, r_star_turn))
    _require(int(reference_cohort["stage2_cohort_size"]) == r_star_count, "R_STAR_COHORT_MISMATCH")
    _require(
        int(audit["counts"]["R_STAR_COUNT"]) == r_star_count
        and int(audit["counts"]["R_STAR_STAGE_COUNTS"]["PRE_IB"]) == r_star_pre
        and int(audit["counts"]["R_STAR_STAGE_COUNTS"]["POST_IB_PRE_OB"]) == r_star_turn,
        "R_STAR_AUDIT_MIRROR",
    )

    section_5_2 = {
        "cohort": {
            "cohort_id": reference_cohort["cohort_id"],
            "r_star_rule": "R* = R_PRE* ∪ R_TURN*",
            "r_star_count": r_star_count,
            "pre_count": r_star_pre,
            "turn_count": r_star_turn,
            "support_exclusion_count": int(reference_cohort["stage2_excluded_count"]),
            "support_excluded_node_ids": list(reference_cohort["stage2_excluded"]),
            "support_rule": reference_cohort["stage2_support_rule"],
            "flattened_union_semantics": reference_cohort["flattened_union_semantics"],
            "no_pooled_stage1_decision": bool(reference_cohort["no_pooled_stage1_decision"]),
        },
        "reference_variant": REFERENCE_VARIANT,
        "reference_representation_id": reference_cohort["reference_representation_id"],
        "stage_name_aliases": {"PRE": "PRE_IB", "TURN": "POST_IB_PRE_OB"},
        "stat_definitions": {
            "source": "definitional mirror of formal/v2_phase7/executor/robustness.py at 8360dd7 (same frozen definition, no second definition)",
            "median": "sorted[n // 2]",
            "IQR": "np.quantile(x, 0.75) - np.quantile(x, 0.25)",
            "P90": "np.quantile(x, 0.90)",
            "positive_V_share": "share of V_i > 0",
            "activation_share": "share of u_i* > 0",
            "positive_u_stats": "computed over rows with u_i* > 0",
        },
        "summary_by_stage": summary_by_stage,
        "sealed_robustness_nominal_row_cross_check": robustness_cross_check,
        "summary_source_note": (
            "descriptive deterministic summaries over the sealed RECOVERY_DECISIONS "
            "reference rows; per-stage values equal the sealed ROBUSTNESS nominal rows"
        ),
    }

    # -- section 5.3: information value --------------------------------------
    def _recovery_comparator(comparator: str) -> dict[str, Any]:
        record = m4["recovery"]["comparators"][comparator]
        bootstrap_record = bootstrap["comparators"][comparator]["recovery"]
        _require(
            _close(record["L_rec"], bootstrap_record["point_estimate"]),
            "RECOVERY_BOOTSTRAP_POINT",
            comparator,
        )
        cohort_size = int(m4["cohort_size"])
        diagnostics = record["diagnostics"]
        activation_change = float(diagnostics["comparator_activation_rate"]) - float(
            diagnostics["reference_activation_rate"]
        )
        return {
            "L_rec": record["L_rec"],
            "ci_95": list(bootstrap_record["ci"]),
            "ci_status": bootstrap_record["status"],
            "A0": record["A0"],
            "A5": record["A5"],
            "exact_agreement_count": int(record["exact_action_count"]),
            "exact_agreement_share": int(record["exact_action_count"]) / cohort_size,
            "within_5min_agreement_count": int(record["within_five_count"]),
            "within_5min_agreement_share": int(record["within_five_count"]) / cohort_size,
            "activation_events": dict(record["activation_events"]),
            "activation_rate": {
                "reference": diagnostics["reference_activation_rate"],
                "comparator": diagnostics["comparator_activation_rate"],
                "change": activation_change,
            },
            "delta_recovery_objective": record["delta_recovery_objective"],
            "reference_recoverable_value": record["reference_recoverable_value"],
            "status": record["status"],
            "derived_definitional_values": [
                "exact_agreement_share = exact_agreement_count / r_star_count",
                "within_5min_agreement_share = within_5min_agreement_count / r_star_count",
                "activation_rate.change = comparator - reference",
            ],
        }

    def _attention_comparator(comparator: str) -> dict[str, Any]:
        record = m4["attention"]["comparators"][comparator]
        bootstrap_record = bootstrap["comparators"][comparator]["attention"]
        _require(
            _close(record["L_att"], bootstrap_record["point_estimate"]),
            "ATTENTION_BOOTSTRAP_POINT",
            comparator,
        )
        reference_k = int(m4["cohort_size"])
        displaced = len(record.get("displaced") or ())
        return {
            "L_att": record["L_att"],
            "ci_95": list(bootstrap_record["ci"]),
            "ci_status": bootstrap_record["status"],
            "overlap_count": int(record["overlap_count"]),
            "entered_count": len(record.get("entered") or ()),
            "displaced_count": displaced,
            "reassigned_share": displaced / reference_k,
            "reference_shortlist_size": reference_k,
            "derived_definitional_values": ["reassigned_share = displaced_count / reference_shortlist_size"],
        }

    reference_record = {
        "comparator_id": REFERENCE_VARIANT,
        "L_att": m4["attention"]["self_reference"]["L_att"],
        "L_rec": m4["recovery"]["self_reference"]["L_rec"],
        "A0": m4["recovery"]["self_reference"]["A0"],
        "A5": m4["recovery"]["self_reference"]["A5"],
        "exact_agreement_count": int(m4["recovery"]["self_reference"]["exact_action_count"]),
        "within_5min_agreement_count": int(m4["recovery"]["self_reference"]["within_five_count"]),
        "note": "reference self-comparison identity: L_att = L_rec = 0, A0 = A5 = 1",
    }

    paired = bootstrap["marginal_uncertainty_increment"]
    attention_increment = paired["attention"]
    recovery_increment = paired["recovery"]
    _require(
        _close(attention_increment["estimate"], audit["scientific_results"]["MARGINAL_UNCERTAINTY_INCREMENT_L_ATT"])
        and _close(recovery_increment["estimate"], audit["scientific_results"]["MARGINAL_UNCERTAINTY_INCREMENT_L_REC"]),
        "MARGINAL_INCREMENT_AUDIT_MIRROR",
    )
    _require(
        list(attention_increment["ci"]) == list(audit["scientific_results"]["marginal_uncertainty_increment_L_att_ci"])
        and list(recovery_increment["ci"]) == list(audit["scientific_results"]["marginal_uncertainty_increment_L_rec_ci"]),
        "MARGINAL_INCREMENT_CI_AUDIT_MIRROR",
    )
    cross_state_attention = m4["attention"]["comparators"]["HISTORY_MARGINAL"]
    cross_state_recovery = m4["recovery"]["comparators"]["HISTORY_MARGINAL"]
    _require(
        _close(cross_state_attention["L_att"], audit["scientific_results"]["cross_state_dependence_L_att"])
        and _close(cross_state_recovery["L_rec"], audit["scientific_results"]["cross_state_dependence_L_rec"]),
        "CROSS_STATE_AUDIT_MIRROR",
    )

    section_5_3 = {
        "reference": reference_record,
        "comparators": [
            {
                "comparator_id": comparator,
                "stage1_attention": _attention_comparator(comparator),
                "stage2_recovery": _recovery_comparator(comparator),
            }
            for comparator in COMPARATOR_VARIANTS
        ],
        "marginal_uncertainty_increment": {
            "definition": "L_HISTORY_POINT - L_HISTORY_MARGINAL",
            "sealed_definition_label": paired["definition"],
            "stage1_attention": {
                "estimate": attention_increment["estimate"],
                "paired_ci_95": list(attention_increment["ci"]),
                "ci_low": attention_increment["ci_low"],
                "ci_high": attention_increment["ci_high"],
                "full_sample_increment": attention_increment["full_sample_increment"],
                "full_sample_increment_verification": attention_increment["full_sample_increment_verification"],
            },
            "stage2_recovery": {
                "estimate": recovery_increment["estimate"],
                "paired_ci_95": list(recovery_increment["ci"]),
                "ci_low": recovery_increment["ci_low"],
                "ci_high": recovery_increment["ci_high"],
                "full_sample_increment": recovery_increment["full_sample_increment"],
                "full_sample_increment_verification": recovery_increment["full_sample_increment_verification"],
            },
            "estimator": {
                "paired": bool(paired["paired"]),
                "interval": attention_increment["interval"],
                "replicates": attention_increment["replicate_count"],
                "resampling_unit": attention_increment["resampling_unit"],
                "seed": attention_increment["seed"],
            },
            "ci_source_note": "paired-bootstrap intervals are copied from the sealed BOOTSTRAP checkpoint; they are never derived by subtracting comparator intervals",
        },
        "cross_state_dependence": {
            "comparator": "HISTORY_MARGINAL",
            "reference": REFERENCE_VARIANT,
            "definition": "L_HISTORY_MARGINAL - L_HISTORY_JOINT",
            "L_att": cross_state_attention["L_att"],
            "L_rec": cross_state_recovery["L_rec"],
            "paired_ci_95": {
                "stage1_attention": list(bootstrap["comparators"]["HISTORY_MARGINAL"]["attention"]["ci"]),
                "stage2_recovery": list(bootstrap["comparators"]["HISTORY_MARGINAL"]["recovery"]["ci"]),
            },
            "ci_source": (
                "copied from the sealed BOOTSTRAP HISTORY_MARGINAL comparator intervals "
                "(paired against the HISTORY_JOINT reference, whose loss is 0 by "
                "self-reference); no CI is computed here"
            ),
        },
    }

    # -- section 5.4: robustness ---------------------------------------------
    required_robustness_fields = (
        "axis",
        "level",
        "stage",
        "nominal_flag",
        "median_V",
        "IQR_V",
        "P90_V",
        "positive_V_share",
        "activation_share",
        "median_positive_u",
        "IQR_positive_u",
        "P90_positive_u",
        "L_rec",
        "A5",
    )
    robustness_rows = []
    for row in robustness["rows"]:
        robustness_rows.append(
            {
                **{field: row[field] for field in required_robustness_fields},
                "N": int(row["N"]),
                "delta_J": row["delta_J"],
                "reference_V": row["reference_V"],
                "lambda": row["lambda"],
                "turnaround_lower_bound": row["turnaround_lower_bound"],
                "u_max": row["u_max"],
                "exact_enumeration": bool(row["exact_enumeration"]),
                "fixed_r_star": bool(row["fixed_r_star"]),
                "stage1_rerun": bool(row["stage1_rerun"]),
            }
        )
    _require(len(robustness_rows) == 20, "ROBUSTNESS_ROWS", len(robustness_rows))
    section_5_4 = {
        "design": robustness["design"],
        "fixed_r_star": bool(robustness["fixed_r_star"]),
        "r_star_count": int(robustness["cohort_size"]),
        "stage1_rerun": bool(robustness["stage1_rerun"]),
        "axes": [
            {"axis": "lambda", "grid": list(robustness["axis_grids"]["lambda"]), "nominal": robustness["nominal"]["lambda"]},
            {
                "axis": "turnaround_lower_bound",
                "grid": dict(robustness["axis_grids"]["turnaround_lower_bound"]),
                "nominal": robustness["nominal"]["turnaround_lower_bound"],
            },
            {"axis": "u_max", "grid": dict(robustness["axis_grids"]["u_max"]), "nominal": robustness["nominal"]["u_max"]},
        ],
        "nominal_base": {
            "q": paper_views["section_5_5"]["nominal_base"]["q"],
            "lambda": paper_views["section_5_5"]["nominal_base"]["lambda"],
            "turnaround_lower_bound": paper_views["section_5_5"]["nominal_base"]["turnaround_q20_minutes"],
            "u_max": paper_views["section_5_5"]["nominal_base"]["u_max_minutes"],
            "history_capacity": paper_views["section_5_5"]["nominal_base"]["history_capacity"],
            "m_cs": paper_views["section_5_5"]["nominal_base"]["m_cs"],
        },
        "rows": robustness_rows,
        "axis_note": "only the three frozen OFAT axes (lambda, turnaround_lower_bound, u_max) are reported; no other sensitivity axis is added",
    }

    # -- validation -----------------------------------------------------------
    guard_mirror = {
        key: audit["guard_results"][key]
        for key in sorted(audit["guard_results"])
    }
    validation = {
        "seal_flags": {
            "final_test_complete": seal["final_test_complete"],
            "paper_results_frozen": seal["paper_results_frozen"],
            "ready_for_freeze": seal["ready_for_freeze"],
            "execution_status": seal["execution_status"],
            "audit_status": seal["audit_status"],
            "epoch_seal_status": seal["status"],
            "scientific_definition_changed": seal["scientific_definition_changed"],
            "second_epoch_opened": seal["second_epoch_opened"],
        },
        "evidence_file_hashes": evidence_hashes,
        "checkpoint_hash_verification": {
            "checked": len(source_checkpoints),
            "all_file_hashes_match": all(entry["file_hash_match"] for entry in source_checkpoints.values()),
            "all_payload_hashes_match": all(entry["payload_hash_match"] for entry in source_checkpoints.values()),
        },
        "paper_views_payload_hash_recomputed": {
            "value": source_checkpoints["PAPER_VIEWS"]["payload_hash"],
            "recorded": source_checkpoints["PAPER_VIEWS"]["recorded_payload_hash"],
            "match": source_checkpoints["PAPER_VIEWS"]["payload_hash_match"],
        },
        "post_execution_audit_mirror_checks": [
            {"field": "R_STAR_COUNT", "audit": audit["counts"]["R_STAR_COUNT"], "artifact": r_star_count, "match": True},
            {
                "field": "R_STAR_STAGE_COUNTS",
                "audit": audit["counts"]["R_STAR_STAGE_COUNTS"],
                "artifact": {"PRE_IB": r_star_pre, "POST_IB_PRE_OB": r_star_turn},
                "match": True,
            },
            {
                "field": "MARGINAL_UNCERTAINTY_INCREMENT_L_ATT",
                "audit": audit["scientific_results"]["MARGINAL_UNCERTAINTY_INCREMENT_L_ATT"],
                "artifact": attention_increment["estimate"],
                "match": True,
            },
            {
                "field": "MARGINAL_UNCERTAINTY_INCREMENT_L_REC",
                "audit": audit["scientific_results"]["MARGINAL_UNCERTAINTY_INCREMENT_L_REC"],
                "artifact": recovery_increment["estimate"],
                "match": True,
            },
            {
                "field": "cross_state_dependence_L_att",
                "audit": audit["scientific_results"]["cross_state_dependence_L_att"],
                "artifact": cross_state_attention["L_att"],
                "match": True,
            },
            {
                "field": "cross_state_dependence_L_rec",
                "audit": audit["scientific_results"]["cross_state_dependence_L_rec"],
                "artifact": cross_state_recovery["L_rec"],
                "match": True,
            },
            {
                "field": "marginal_uncertainty_increment_L_att_ci",
                "audit": audit["scientific_results"]["marginal_uncertainty_increment_L_att_ci"],
                "artifact": list(attention_increment["ci"]),
                "match": True,
            },
            {
                "field": "marginal_uncertainty_increment_L_rec_ci",
                "audit": audit["scientific_results"]["marginal_uncertainty_increment_L_rec_ci"],
                "artifact": list(recovery_increment["ci"]),
                "match": True,
            },
        ],
        "robustness_nominal_cross_check": {
            "status": robustness_cross_check,
            "tolerance": STAT_TOLERANCE,
            "reference": "sealed ROBUSTNESS nominal rows (lambda = 0.25, turnaround Q20, u_max Q90)",
        },
        "internal_consistency_checks": {
            "attention_delta_identity": "PASS (reference - comparator = delta per stage/comparator)",
            "attention_loss_identity": "PASS (delta / reference = L_att per stage/comparator)",
            "overall_reference_composition": "PASS (overall reference = sum of stage references)",
            "overall_overlap_composition": "PASS (overall overlap = PRE + TURN overlap per comparator)",
            "overall_delta_composition": "PASS (overall delta = PRE + TURN delta per comparator)",
            "attention_set_partition": "PASS (displaced = entered; overlap + displaced = reference shortlist)",
        },
        "audit_guard_mirror": guard_mirror,
        "no_recomputation": {
            "final_test_raw_data_read": False,
            "final_test_rerun": False,
            "new_access_epoch_opened": False,
            "legacy_epochs_read": False,
            "development_results_used": False,
            "model_or_solver_code_executed": False,
        },
    }

    # -- assemble output ------------------------------------------------------
    output = {
        "schema_version": "AIR_SLOT_PAPER_FACING_SECTION5_RESULTS_V1",
        "artifact_kind": "MANUSCRIPT_FACING_READ_ONLY_PROJECTION",
        "projection_only": True,
        "scientific_recomputation_performed": False,
        "scientific_definition_changed": False,
        "authority": {
            "authority_files": ["CURRENT_PAPER_AUTHORITY.md", "CURRENT_PAPER_AUTHORITY.json"],
            "paper_primary": {"branch": PAPER_PRIMARY_BRANCH, "commit": PAPER_PRIMARY_COMMIT},
            "final_test": {
                "branch": FINAL_TEST_BRANCH,
                "scientific_commit": PHASE7_SCIENTIFIC_COMMIT,
                "freeze_tag": FINAL_TEST_TAG,
                "epoch": EPOCH_REPO_PATH,
            },
            "epoch_seal": {
                "path": f"{EPOCH_REPO_PATH}/EPOCH_SEAL.json",
                "file_sha256": evidence_hashes["EPOCH_SEAL.json"]["file_sha256"],
                "status": seal["status"],
            },
            "freeze": {
                "path": "formal/JATM_STAGE_MATCHED_FINAL_TEST_FREEZE_V2.json",
                "artifact_hash": freeze["artifact_hash"],
                "hash_semantics": "content identity hash (artifact_hash field) of the freeze payload, not a file byte hash",
            },
            "paper_views_checkpoint": {
                "path": f"{EPOCH_REPO_PATH}/checkpoints/PAPER_VIEWS.json",
                "file_sha256": source_checkpoints["PAPER_VIEWS"]["file_sha256"],
                "payload_hash": source_checkpoints["PAPER_VIEWS"]["payload_hash"],
                "schema_version": paper_views["schema_version"],
            },
            "post_execution_audit": {
                "json": f"{EPOCH_REPO_PATH}/POST_EXECUTION_AUDIT.json",
                "json_file_sha256": evidence_hashes["POST_EXECUTION_AUDIT.json"]["file_sha256"],
                "md": f"{EPOCH_REPO_PATH}/POST_EXECUTION_AUDIT.md",
                "md_file_sha256": evidence_hashes["POST_EXECUTION_AUDIT.md"]["file_sha256"],
                "status": audit["status"],
                "audit_timestamp": audit["audit_timestamp"],
            },
            "source_checkpoints": source_checkpoints,
        },
        "projection": {
            "materialization_script": {
                "path": SCRIPT_REPO_PATH,
                "sha256": materializer_sha256,
                "sha256_source": "committed git blob (LF, as stored in the repository)" if materializer_sha256 else "not provided",
            },
            "materialization_command": (
                f"python -m formal.v2_phase7.project_section5_paper_facing "
                f"--epoch-root {epoch_root} --out-dir {out_dir} "
                f"--materializer-sha256 {materializer_sha256 or '<script-sha256>'}"
            ),
            "epoch_root": str(epoch_root),
            "derived_definitional_values": [
                "retained_value = 1 - L_att",
                "reassigned_share = displaced_count / reference_shortlist_size",
                "overall delta_attention_value = aggregated reference objective - aggregated comparator objective",
                "exact_agreement_share = exact_agreement_count / r_star_count",
                "within_5min_agreement_share = within_5min_agreement_count / r_star_count",
                "activation_rate.change = comparator - reference",
            ],
            "not_recomputed_policy": (
                "any estimand absent from the sealed checkpoints is reported as null with an "
                "explicit status; nothing is recomputed from raw data, models or legacy epochs"
            ),
            "stat_definitions_source": "formal/v2_phase7/executor/robustness.py @ 8360dd7 (median / IQR / P90 / shares)",
        },
        "section_5_1_stage1_attention": section_5_1,
        "section_5_2_stage2_recovery": section_5_2,
        "section_5_3_information_value": section_5_3,
        "section_5_4_robustness": section_5_4,
        "validation": validation,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / JSON_NAME, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(output, indent=2, ensure_ascii=False, allow_nan=False))
        handle.write("\n")
    with open(out_dir / MD_NAME, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_markdown(output))
    print(f"wrote {out_dir / JSON_NAME}")
    print(f"wrote {out_dir / MD_NAME}")
    return 0


# ---------------------------------------------------------------------------
# markdown rendering
# ---------------------------------------------------------------------------
def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(_num(value) for value in row) + " |")
    return lines


def render_markdown(output: Mapping[str, Any]) -> str:
    authority = output["authority"]
    seal = authority["epoch_seal"]
    views = authority["paper_views_checkpoint"]
    audit = authority["post_execution_audit"]
    s51 = output["section_5_1_stage1_attention"]
    s52 = output["section_5_2_stage2_recovery"]
    s53 = output["section_5_3_information_value"]
    s54 = output["section_5_4_robustness"]

    lines: list[str] = []
    lines.append("# Air Slot — Section 5 Paper-Facing Results (sealed canonical-v2 projection)")
    lines.append("")
    lines.append("Read-only manuscript-facing projection of the sealed canonical stage-matched ")
    lines.append("Final-Test epoch. No scientific computation was performed, no epoch was ")
    lines.append("re-opened, and no value was taken from any legacy or Development source.")
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    for item in [
        f"- paper-primary: `{authority['paper_primary']['branch']}` @ `{authority['paper_primary']['commit']}`",
        f"- final-test authority: `{authority['final_test']['branch']}` @ `{authority['final_test']['scientific_commit']}` (tag `{authority['final_test']['freeze_tag']}`)",
        f"- epoch: `{authority['final_test']['epoch']}`",
        f"- EPOCH_SEAL: `{seal['path']}` — `{seal['file_sha256']}` — status `{seal['status']}`",
        f"- PAPER_VIEWS checkpoint: `{views['path']}` — file `{views['file_sha256']}`",
        f"- PAPER_VIEWS payload hash: `{views['payload_hash']}`",
        f"- POST_EXECUTION_AUDIT: `{audit['json']}` — `{audit['json_file_sha256']}` — status `{audit['status']}` (audited `{audit['audit_timestamp']}`)",
        f"- freeze artifact hash: `{authority['freeze']['artifact_hash']}`",
        f"- projection_only = true; scientific_recomputation_performed = false; scientific_definition_changed = false",
    ]:
        lines.append(item)
    lines.append("")
    lines.append("## 5.1 Stage-I attention")
    lines.append("")
    lines.append(f"- reference representation: `{s51['reference_representation_id']}` (`{s51['reference_variant']}`)")
    lines.append(f"- capacity rule: `{s51['capacity_rule']}`; q grid `{s51['q_grid']}`, nominal q = `{s51['nominal_q']}`")
    lines.append(f"- overall aggregation: `{s51['overall_rule']}` (confirmed `{s51['aggregation_confirmation']}`); pooled PRE+TURN ranking constructed: `{s51['pooled_stage1_ranking']}`")
    lines.append("")
    lines.append("### Capacity design (stage × q)")
    lines.append("")
    capacity_rows = [
        [
            row["stage"],
            row["q"],
            row["n_g"],
            row["k_g"],
            row["selected_node_count"],
            row["eligible_candidate_count"],
            row["abstaining_node_count"],
        ]
        for row in s51["capacity_rows"]
    ]
    lines.extend(_table(["stage", "q", "N_g", "K_g", "selected", "eligible", "abstaining"], capacity_rows))
    lines.append("")
    lines.append(f"- {s51['attention_values_note']}")
    lines.append("")
    lines.append(f"### Attention comparison at nominal q = {s51['nominal_q']} (per stage × comparator)")
    lines.append("")
    for stage in ("PRE_IB", "POST_IB_PRE_OB"):
        stage_block = s51["stage_attention_comparison_nominal_q"][stage]
        lines.append(f"**{stage}** ({stage_block['stage_class']}, N_g = {stage_block['n_g']}, K_g = {stage_block['k_g']})")
        lines.append("")
        rows = []
        for comparator, record in stage_block["by_comparator"].items():
            rows.append(
                [
                    comparator,
                    record["reference_attention_value"],
                    record["comparator_attention_value"],
                    record["delta_attention_value"],
                    record["L_att"],
                    record["retained_value"],
                    record["overlap_count"],
                    record["entered_count"],
                    record["displaced_count"],
                    record["reassigned_share"],
                ]
            )
        lines.extend(
            _table(
                ["comparator", "reference value", "comparator value", "Δ", "L_att", "retained", "overlap", "entered", "displaced", "reassigned share"],
                rows,
            )
        )
        lines.append("")
    lines.append("### Overall attention (OBJECTIVES_THEN_NORMALIZE)")
    lines.append("")
    overall = s51["overall_attention_nominal_q"]
    lines.append(
        f"- aggregation = `{overall['aggregation']}` (confirmed `{overall['aggregation_confirmation']}`); "
        f"pooled ranking constructed: `{overall['pooled_stage1_ranking_constructed']}`"
    )
    lines.append(f"- aggregated reference objective: `{overall['aggregated_reference_objective']}`")
    lines.append("")
    rows = []
    for comparator, record in overall["by_comparator"].items():
        rows.append(
            [
                comparator,
                record["comparator_attention_value"],
                record["delta_attention_value"],
                record["L_att"],
                record["retained_value"],
                record["overlap_count"],
                record["entered_count"],
                record["displaced_count"],
                record["reassigned_share"],
            ]
        )
    lines.extend(
        _table(
            ["comparator", "aggregated comparator objective", "overall Δ", "overall L_att", "retained", "overlap", "entered", "displaced", "reassigned share"],
            rows,
        )
    )
    lines.append("")
    lines.append(f"- stage-specific L_att values are never averaged; overall Δ = aggregated reference − aggregated comparator, overall L_att is sealed.")
    lines.append("")
    lines.append("## 5.2 Stage-II recovery")
    lines.append("")
    cohort = s52["cohort"]
    lines.append(
        f"- {cohort['r_star_rule']} — count `{cohort['r_star_count']}` (PRE `{cohort['pre_count']}`, TURN `{cohort['turn_count']}`), "
        f"support exclusions `{cohort['support_exclusion_count']}` (`{cohort['support_rule']}`)"
    )
    lines.append(f"- reference representation: `{s52['reference_representation_id']}` (`{s52['reference_variant']}`)")
    lines.append("")
    rows = []
    for stage in ("PRE", "TURN", "OVERALL"):
        stats = s52["summary_by_stage"][stage]
        rows.append(
            [
                stage,
                stats["N"],
                stats["median_V"],
                stats["IQR_V"],
                stats["P90_V"],
                stats["positive_V_share"],
                stats["activation_count"],
                stats["activation_share"],
                stats["median_positive_u"],
                stats["IQR_positive_u"],
                stats["P90_positive_u"],
            ]
        )
    lines.extend(
        _table(
            ["stage", "N", "median V", "IQR V", "P90 V", "positive-V share", "activations", "activation share", "median u*>0", "IQR u*>0", "P90 u*>0"],
            rows,
        )
    )
    lines.append("")
    lines.append(
        f"- {s52['summary_source_note']}; cross-check `{s52['sealed_robustness_nominal_row_cross_check']}`"
    )
    lines.append("")
    lines.append("## 5.3 Information value")
    lines.append("")
    lines.append("### Stage-I (attention) comparator summary")
    lines.append("")
    rows = []
    for entry in s53["comparators"]:
        record = entry["stage1_attention"]
        rows.append(
            [
                entry["comparator_id"],
                record["L_att"],
                record["ci_95"],
                record["overlap_count"],
                record["entered_count"],
                record["displaced_count"],
                record["reassigned_share"],
            ]
        )
    lines.extend(
        _table(["comparator", "L_att", "95% CI", "overlap", "entered", "displaced", "reassigned share"], rows)
    )
    lines.append("")
    lines.append("### Stage-II (recovery) comparator summary")
    lines.append("")
    rows = []
    for entry in s53["comparators"]:
        record = entry["stage2_recovery"]
        rows.append(
            [
                entry["comparator_id"],
                record["L_rec"],
                record["ci_95"],
                record["A0"],
                record["A5"],
                record["exact_agreement_count"],
                record["exact_agreement_share"],
                record["within_5min_agreement_count"],
                record["within_5min_agreement_share"],
                record["activation_events"],
            ]
        )
    lines.extend(
        _table(
            ["comparator", "L_rec", "95% CI", "A0", "A5", "exact (count)", "exact (share)", "within-5 (count)", "within-5 (share)", "activation events"],
            rows,
        )
    )
    lines.append("")
    lines.append("### Marginal uncertainty increment")
    lines.append("")
    increment = s53["marginal_uncertainty_increment"]
    lines.append(f"- definition: `{increment['definition']}` (sealed label `{increment['sealed_definition_label']}`)")
    lines.append(
        f"- Stage-I: estimate `{increment['stage1_attention']['estimate']}`, paired 95% CI `{increment['stage1_attention']['paired_ci_95']}`"
    )
    lines.append(
        f"- Stage-II: estimate `{increment['stage2_recovery']['estimate']}`, paired 95% CI `{increment['stage2_recovery']['paired_ci_95']}`"
    )
    lines.append(f"- {increment['ci_source_note']}")
    lines.append("")
    lines.append("### Cross-state dependence")
    lines.append("")
    cross = s53["cross_state_dependence"]
    lines.append(f"- definition: `{cross['definition']}` (comparator `{cross['comparator']}` vs `{cross['reference']}`)")
    lines.append(f"- L_att `{cross['L_att']}`; L_rec `{cross['L_rec']}`")
    lines.append(
        f"- paired 95% CI (copied from sealed bootstrap): Stage-I `{cross['paired_ci_95']['stage1_attention']}`, Stage-II `{cross['paired_ci_95']['stage2_recovery']}`"
    )
    lines.append("")
    lines.append("## 5.4 Robustness (fixed R*, one-factor-at-a-time)")
    lines.append("")
    lines.append(
        f"- design `{s54['design']}`; fixed R* `{s54['fixed_r_star']}` (size `{s54['r_star_count']}`); Stage-I rerun `{s54['stage1_rerun']}`"
    )
    lines.append(f"- nominal base: `{s54['nominal_base']}`")
    lines.append("")
    rows = []
    for row in s54["rows"]:
        rows.append(
            [
                row["axis"],
                row["level"],
                row["stage"],
                row["nominal_flag"],
                row["median_V"],
                row["IQR_V"],
                row["P90_V"],
                row["positive_V_share"],
                row["activation_share"],
                row["median_positive_u"],
                row["IQR_positive_u"],
                row["P90_positive_u"],
                row["L_rec"],
                row["A5"],
            ]
        )
    lines.extend(
        _table(
            ["axis", "level", "stage", "nominal", "median V", "IQR V", "P90 V", "positive-V share", "activation share", "median u*>0", "IQR u*>0", "P90 u*>0", "L_rec", "A5"],
            rows,
        )
    )
    lines.append("")
    lines.append("## Validation")
    lines.append("")
    validation = output["validation"]
    lines.append(
        "- seal flags: `" + json.dumps(validation["seal_flags"], ensure_ascii=False) + "`"
    )
    lines.append(
        f"- checkpoint hashes: {validation['checkpoint_hash_verification']['checked']} checked — "
        f"file hashes `{validation['checkpoint_hash_verification']['all_file_hashes_match']}`, "
        f"payload hashes `{validation['checkpoint_hash_verification']['all_payload_hashes_match']}`"
    )
    lines.append(
        f"- PAPER_VIEWS payload hash recomputed: `{validation['paper_views_payload_hash_recomputed']['value']}` — match `{validation['paper_views_payload_hash_recomputed']['match']}`"
    )
    lines.append("- POST_EXECUTION_AUDIT mirror checks (all match):")
    for check in validation["post_execution_audit_mirror_checks"]:
        lines.append(f"  - `{check['field']}`: audit `{check['audit']}` = artifact `{check['artifact']}`")
    lines.append(
        f"- robustness nominal cross-check: `{validation['robustness_nominal_cross_check']['status']}` (tolerance {validation['robustness_nominal_cross_check']['tolerance']})"
    )
    lines.append(f"- no recomputation: {validation['no_recomputation']}")
    lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
