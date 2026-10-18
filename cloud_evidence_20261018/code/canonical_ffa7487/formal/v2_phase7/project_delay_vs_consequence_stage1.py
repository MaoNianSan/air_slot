"""Deterministic read-only projection of the sealed canonical-v2
``ATTENTION_DECISIONS`` checkpoint into the delay-based vs consequence-based
Stage-I held-out results for JATM manuscript Section 5.1.

This tool performs NO scientific computation and starts NO bootstrap. The only
scientific data source is the sealed checkpoint

    artifacts/experiment/final_test_v2_stage_matched_canonical_v2/checkpoints/ATTENTION_DECISIONS.json

read together with the epoch provenance records (EPOCH_SEAL.json,
FINAL_TEST_EXECUTION_RESULT.json, POST_EXECUTION_AUDIT.json) that are used
exclusively for identity verification. It never reads Final-Test raw data,
never opens an access epoch, never executes M1/M2/M3/M4, and never reads any
legacy epoch, Development output or gate-b0 fixture dump.

For each actionable stage (PRE = PRE_IB, TURN = POST_IB_PRE_OB) at the nominal
q = 0.10 under the reference representation HISTORY_JOINT (HISTORY_H16:JOINT)
it reads, from one frozen row, ``delay_decision`` and ``consequence_decision``,
and evaluates both shortlists with the SAME frozen consequence priority score
(P_i^C = consequence_decision.entries[*].score keyed by node_id):

    A_g^C = sum_{i in H_g^C} P_i^C,   A_g^D = sum_{i in H_g^D} P_i^C
    delta_g^att = A_g^C - A_g^D,  L_g^att = delta_g^att / A_g^C,
    eta_g^att = A_g^D / A_g^C = 1 - L_g^att

The overall row aggregates objectives first
(STAGE_OBJECTIVES_THEN_NORMALIZE) and never averages stage-level L values.

The tool is fail-closed: any hash, schema, row-identity, or objective-identity
failure aborts materialization with a non-zero exit code.

Usage (from the repository root):

    python -m formal.v2_phase7.project_delay_vs_consequence_stage1 \
        --epoch-root <path to sealed canonical-v2 epoch root> \
        --out-dir <directory receiving the two result files> \
        [--materializer-sha256 <sha256 of the committed script blob>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

PAPER_PRIMARY_BRANCH = "v2/paper-primary"
PAPER_PRIMARY_COMMIT = "b753db8251812faec2eb2dbdabf34c325eb76f9b"
FINAL_TEST_BRANCH = "v2/phase7-gate-a"
PHASE7_SCIENTIFIC_COMMIT = "8360dd7d88958ae139322d0ea5c66f1c5fe6455c"
FINAL_TEST_TAG = "jatm-final-test-freeze-20260920"
EPOCH_REPO_PATH = "artifacts/experiment/final_test_v2_stage_matched_canonical_v2"
SCRIPT_REPO_PATH = "formal/v2_phase7/project_delay_vs_consequence_stage1.py"

CHECKPOINT_STAGE = "ATTENTION_DECISIONS"
CHECKPOINT_SCHEMA = "AIR_SLOT_V2_PHASE7_ATTENTION_DECISIONS_V1"
REFERENCE_VARIANT = "HISTORY_JOINT"
REFERENCE_REPRESENTATION_ID = "HISTORY_H16:JOINT"
NOMINAL_Q = 0.1
STAGES = ("PRE_IB", "POST_IB_PRE_OB")
STAGE_CLASS = {"PRE_IB": "PRE", "POST_IB_PRE_OB": "TURN"}

EPOCH_SEAL_EXPECTED_SHA256 = (
    "sha256:eb4a22a2079183f1eca3511c5002334eeccb9f19b282f9781189475ce9c21614"
)

JSON_NAME = "PAPER_FACING_DELAY_VS_CONSEQUENCE_STAGE1.json"
MD_NAME = "PAPER_FACING_DELAY_VS_CONSEQUENCE_STAGE1.md"

TOL = 1e-12


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


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= TOL


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Project sealed ATTENTION_DECISIONS into delay-vs-"
        "consequence Stage-I paper-facing results (read-only)."
    )
    parser.add_argument("--epoch-root", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--materializer-sha256", default=None)
    args = parser.parse_args(argv)

    epoch_root: Path = args.epoch_root
    out_dir: Path = args.out_dir
    materializer_sha256: str | None = args.materializer_sha256

    # ------------------------------------------------------------------
    # provenance records (identity verification only)
    # ------------------------------------------------------------------
    seal = _load(epoch_root / "EPOCH_SEAL.json")
    execution = _load(epoch_root / "FINAL_TEST_EXECUTION_RESULT.json")
    audit = _load(epoch_root / "POST_EXECUTION_AUDIT.json")

    seal_file_hash = _sha256_file(epoch_root / "EPOCH_SEAL.json")
    execution_file_hash = _sha256_file(epoch_root / "FINAL_TEST_EXECUTION_RESULT.json")
    audit_file_hash = _sha256_file(epoch_root / "POST_EXECUTION_AUDIT.json")

    _require(
        seal_file_hash == EPOCH_SEAL_EXPECTED_SHA256,
        "EPOCH_SEAL_IDENTITY",
        seal_file_hash,
    )
    _require(seal.get("status") == "SEALED_AUDIT_PASS", "SEAL_STATUS", seal.get("status"))
    _require(seal.get("final_test_complete") is True, "SEAL_FLAG", "final_test_complete")
    _require(seal.get("paper_results_frozen") is True, "SEAL_FLAG", "paper_results_frozen")
    _require(seal.get("scientific_definition_changed") is False, "SEAL_FLAG", "changed")
    _require(seal.get("second_epoch_opened") is False, "SEAL_FLAG", "second_epoch_opened")
    _require(
        execution_file_hash == seal.get("execution_result_sha256"),
        "EXECUTION_RESULT_IDENTITY",
        (execution_file_hash, seal.get("execution_result_sha256")),
    )
    _require(
        audit_file_hash == seal.get("post_execution_audit_json_sha256"),
        "POST_AUDIT_IDENTITY",
        (audit_file_hash, seal.get("post_execution_audit_json_sha256")),
    )

    # ------------------------------------------------------------------
    # source checkpoint identity verification (fail-closed)
    # ------------------------------------------------------------------
    checkpoint_path = epoch_root / "checkpoints" / f"{CHECKPOINT_STAGE}.json"
    _require(checkpoint_path.exists(), "CHECKPOINT_MISSING", str(checkpoint_path))
    checkpoint = _load(checkpoint_path)
    _require(
        checkpoint.get("schema_version") == CHECKPOINT_SCHEMA,
        "CHECKPOINT_SCHEMA",
        checkpoint.get("schema_version"),
    )
    payload = checkpoint["payload"]
    _require(
        payload.get("schema_version") == CHECKPOINT_SCHEMA,
        "CHECKPOINT_PAYLOAD_SCHEMA",
        payload.get("schema_version"),
    )
    _require(
        payload.get("reference_variant") == REFERENCE_VARIANT,
        "CHECKPOINT_REFERENCE_VARIANT",
        payload.get("reference_variant"),
    )

    checkpoint_file_hash = _sha256_file(checkpoint_path)
    checkpoint_payload_hash = _content_id(payload)

    execution_record = execution["result"]["manifest"]["stage_records"][CHECKPOINT_STAGE]
    audit_detail = None
    for check in audit["checks"]:
        if check.get("code") == "CHECKPOINT_HASH_AND_DEPENDENCIES":
            audit_detail = check.get("detail", {}).get(CHECKPOINT_STAGE)
            break
    _require(audit_detail is not None, "AUDIT_CHECKPOINT_RECORD_MISSING")

    execution_file_match = checkpoint_file_hash == execution_record.get("file_sha256")
    execution_payload_match = checkpoint_payload_hash == execution_record.get("payload_hash")
    audit_file_match = checkpoint_file_hash == audit_detail.get("file_sha256")
    audit_payload_match = checkpoint_payload_hash == audit_detail.get("payload_hash")
    _require(execution_file_match, "CHECKPOINT_FILE_HASH_EXECUTION", checkpoint_file_hash)
    _require(execution_payload_match, "CHECKPOINT_PAYLOAD_HASH_EXECUTION", checkpoint_payload_hash)
    _require(audit_file_match, "CHECKPOINT_FILE_HASH_AUDIT", checkpoint_file_hash)
    _require(audit_payload_match, "CHECKPOINT_PAYLOAD_HASH_AUDIT", checkpoint_payload_hash)
    _require(
        checkpoint_payload_hash == checkpoint.get("payload_hash"),
        "CHECKPOINT_DECLARED_PAYLOAD_HASH",
        checkpoint_payload_hash,
    )

    # ------------------------------------------------------------------
    # select the frozen rows
    # ------------------------------------------------------------------
    rows = [
        row
        for row in payload["rows"]
        if row.get("variant") == REFERENCE_VARIANT
        and row.get("stage") in STAGES
        and abs(float(row.get("q")) - NOMINAL_Q) <= 1e-12
    ]
    _require(len(rows) == 2, "ROW_SELECTION", len(rows))
    rows_by_stage = {row["stage"]: row for row in rows}

    # ------------------------------------------------------------------
    # per-stage projection
    # ------------------------------------------------------------------
    stage_results: dict[str, dict[str, Any]] = {}
    candidate_set_checks: dict[str, dict[str, Any]] = {}
    objective_checks: list[dict[str, Any]] = []

    for stage in STAGES:
        row = rows_by_stage[stage]
        dd = row["delay_decision"]
        cd = row["consequence_decision"]
        k_g = int(row["k"])
        n_g = int(row["canonical_stage_node_count"])

        # --- candidate-set equality between the two frozen decisions ----
        delay_entries = dd["entries"]
        consequence_entries = cd["entries"]
        delay_nodes = [entry["node_id"] for entry in delay_entries]
        consequence_nodes = [entry["node_id"] for entry in consequence_entries]
        eligible_ids = list(row["eligible_candidate_node_ids"])

        checks = {
            "entries_node_sets_equal": set(delay_nodes) == set(consequence_nodes),
            "cohort_size_equal": int(dd["cohort_size"]) == int(cd["cohort_size"]),
            "k_equal": dd.get("k") == cd.get("k") == row.get("k"),
            "q_equal": abs(float(dd.get("q")) - float(row.get("q"))) <= 1e-12
            and abs(float(cd.get("q")) - float(row.get("q"))) <= 1e-12,
            "support_status_equal": dd.get("status") == cd.get("status"),
            "support_status_value": dd.get("status"),
            "signal_types": [dd.get("signal_type"), cd.get("signal_type")],
            "eligible_ids_equal": set(consequence_nodes) == set(eligible_ids),
            "eligible_count_equal": len(consequence_nodes) == int(row["eligible_candidate_count"]),
            "entries_count_equal": len(delay_entries) == len(consequence_entries),
        }
        _require(
            all(
                checks[key]
                for key in (
                    "entries_node_sets_equal",
                    "cohort_size_equal",
                    "k_equal",
                    "q_equal",
                    "support_status_equal",
                    "eligible_ids_equal",
                    "eligible_count_equal",
                    "entries_count_equal",
                )
            ),
            "CANDIDATE_SET_EQUALITY",
            {stage: checks},
        )
        candidate_set_checks[stage] = checks

        # --- shortlists and displacement counts --------------------------
        h_delay = [entry["node_id"] for entry in delay_entries if entry["selected"]]
        h_consequence = [entry["node_id"] for entry in consequence_entries if entry["selected"]]
        _require(len(h_delay) == k_g, "DELAY_SHORTLIST_SIZE", (stage, len(h_delay), k_g))
        _require(len(h_consequence) == k_g, "CONSEQUENCE_SHORTLIST_SIZE", (stage, len(h_consequence), k_g))

        delay_set = set(h_delay)
        consequence_set = set(h_consequence)
        overlap_count = len(delay_set & consequence_set)
        delay_only_count = len(delay_set - consequence_set)
        consequence_only_count = len(consequence_set - delay_set)
        changed_position_count = consequence_only_count
        _require(
            delay_only_count == consequence_only_count,
            "CHANGED_POSITION_SYMMETRY",
            (stage, delay_only_count, consequence_only_count),
        )
        _require(overlap_count + delay_only_count == k_g, "SHORTLIST_PARTITION", stage)
        _require(overlap_count + consequence_only_count == k_g, "SHORTLIST_PARTITION", stage)

        # --- frozen consequence scores for both shortlists ----------------
        score_by_node = {entry["node_id"]: float(entry["score"]) for entry in consequence_entries}
        _require(
            delay_set <= set(score_by_node),
            "DELAY_NODES_MISSING_CONSEQUENCE_SCORE",
            stage,
        )
        a_consequence = sum(score_by_node[node_id] for node_id in h_consequence)
        a_delay = sum(score_by_node[node_id] for node_id in h_delay)
        _require(
            a_consequence >= a_delay,
            "CONSEQUENCE_NOT_TOP_K_REFERENCE",
            (stage, a_consequence, a_delay),
        )

        # consequence shortlist must be the top-K under its own score
        ordered = sorted(
            consequence_entries, key=lambda entry: (-float(entry["score"]), entry["node_id"])
        )
        top_k = {entry["node_id"] for entry in ordered[:k_g]}
        _require(top_k == consequence_set, "CONSEQUENCE_TOP_K_IDENTITY", stage)

        delta = a_consequence - a_delay
        loss = None if a_consequence == 0.0 else delta / a_consequence
        retained = None if a_consequence == 0.0 else a_delay / a_consequence
        _require(a_consequence > 0.0, "ZERO_CONSEQUENCE_OBJECTIVE", stage)

        # --- objective identity checks --------------------------------------
        delta_identity = _close(delta, a_consequence - a_delay)
        loss_identity = _close(loss, delta / a_consequence)
        retained_identity = _close(retained, a_delay / a_consequence)
        complement_identity = _close(retained, 1.0 - loss)
        if changed_position_count == 0:
            _require(delay_set == consequence_set, "ZERO_CHANGED_SETS_NOT_EQUAL", stage)
            _require(delta == 0.0, "ZERO_CHANGED_DELTA_NOT_ZERO", (stage, delta))
            _require(loss == 0.0, "ZERO_CHANGED_LOSS_NOT_ZERO", (stage, loss))
            _require(retained == 1.0, "ZERO_CHANGED_RETAINED_NOT_ONE", (stage, retained))

        objective_checks.extend(
            [
                {"stage": stage, "check": "delta_identity", "pass": delta_identity},
                {"stage": stage, "check": "loss_identity", "pass": loss_identity},
                {"stage": stage, "check": "retained_identity", "pass": retained_identity},
                {"stage": stage, "check": "complement_identity", "pass": complement_identity},
                {"stage": stage, "check": "a_consequence_ge_a_delay", "pass": a_consequence >= a_delay},
                {"stage": stage, "check": "consequence_top_k_identity", "pass": True},
                {"stage": stage, "check": "changed_position_symmetry", "pass": True},
                {"stage": stage, "check": "zero_changed_implies_identical", "pass": True},
            ]
        )
        for check in objective_checks[-8:]:
            _require(bool(check["pass"]), "OBJECTIVE_IDENTITY", check)

        stage_results[stage] = {
            "stage": stage,
            "stage_class": STAGE_CLASS[stage],
            "n_g": n_g,
            "k_g": k_g,
            "delay_shortlist_ids": list(h_delay),
            "consequence_shortlist_ids": list(h_consequence),
            "overlap_count": overlap_count,
            "delay_only_count": delay_only_count,
            "consequence_only_count": consequence_only_count,
            "changed_position_count": changed_position_count,
            "changed_position_share": changed_position_count / k_g,
            "a_consequence": a_consequence,
            "a_delay": a_delay,
            "delta_att": delta,
            "L_att": loss,
            "eta_att": retained,
            "decision_status": dd.get("status"),
            "counts_are_integers": isinstance(overlap_count, int)
            and isinstance(delay_only_count, int)
            and isinstance(consequence_only_count, int)
            and isinstance(changed_position_count, int),
        }

    # ------------------------------------------------------------------
    # overall: aggregate objectives first (never average stage losses)
    # ------------------------------------------------------------------
    pre = stage_results["PRE_IB"]
    turn = stage_results["POST_IB_PRE_OB"]
    a_consequence_overall = pre["a_consequence"] + turn["a_consequence"]
    a_delay_overall = pre["a_delay"] + turn["a_delay"]
    delta_overall = a_consequence_overall - a_delay_overall
    loss_overall = delta_overall / a_consequence_overall
    retained_overall = a_delay_overall / a_consequence_overall
    changed_total = int(pre["changed_position_count"] + turn["changed_position_count"])
    k_total = int(pre["k_g"] + turn["k_g"])

    sum_delta = pre["delta_att"] + turn["delta_att"]
    aggregation_checks = {
        "a_consequence_overall_equals_stage_sum": _close(
            a_consequence_overall, pre["a_consequence"] + turn["a_consequence"]
        ),
        "a_delay_overall_equals_stage_sum": _close(
            a_delay_overall, pre["a_delay"] + turn["a_delay"]
        ),
        "delta_overall_equals_stage_delta_sum": _close(delta_overall, sum_delta),
        "loss_overall_identity": _close(loss_overall, delta_overall / a_consequence_overall),
        "retained_overall_identity": _close(retained_overall, a_delay_overall / a_consequence_overall),
        "retained_overall_complement": _close(retained_overall, 1.0 - loss_overall),
        "changed_total_equals_stage_sum": changed_total
        == int(pre["changed_position_count"] + turn["changed_position_count"]),
    }
    for name, ok in aggregation_checks.items():
        _require(bool(ok), "OVERALL_AGGREGATION_IDENTITY", name)

    overall = {
        "stage": "OVERALL",
        "n_g": int(pre["n_g"] + turn["n_g"]),
        "k_g": k_total,
        "a_consequence": a_consequence_overall,
        "a_delay": a_delay_overall,
        "delta_att": delta_overall,
        "L_att": loss_overall,
        "eta_att": retained_overall,
        "changed_position_count": changed_total,
        "changed_position_share": changed_total / k_total,
        "overlap_count_total": int(pre["overlap_count"] + turn["overlap_count"]),
        "delay_only_count_total": int(pre["delay_only_count"] + turn["delay_only_count"]),
        "consequence_only_count_total": int(pre["consequence_only_count"] + turn["consequence_only_count"]),
        "aggregation_rule": "STAGE_OBJECTIVES_THEN_NORMALIZE",
        "stage_loss_not_averaged": True,
        "stage_L_att_values": {"PRE_IB": pre["L_att"], "POST_IB_PRE_OB": turn["L_att"]},
        "note": (
            "overall objectives are aggregated before normalization; the overall "
            "changed-position count is the sum of the independent stage counts "
            "(no cross-stage pairing or ranking)"
        ),
    }

    # ------------------------------------------------------------------
    # assemble output
    # ------------------------------------------------------------------
    output = {
        "schema_version": "AIR_SLOT_PAPER_FACING_DELAY_VS_CONSEQUENCE_STAGE1_V1",
        "artifact_kind": "MANUSCRIPT_FACING_READ_ONLY_PROJECTION",
        "projection_only": True,
        "scientific_recomputation_performed": False,
        "final_test_raw_data_read": False,
        "new_final_test_execution": False,
        "scientific_definition_changed": False,
        "source_representation": REFERENCE_VARIANT,
        "source_representation_id": REFERENCE_REPRESENTATION_ID,
        "nominal_q": NOMINAL_Q,
        "stage_evaluation": "PRE_AND_TURN_EVALUATED_INDEPENDENTLY",
        "overall_rule": "STAGE_OBJECTIVES_THEN_NORMALIZE",
        "pooled_stage1_ranking": False,
        "confidence_intervals": "NONE_REPORTED",
        "bootstrap_invoked": False,
        "point_results_only_note": (
            "no confidence interval is created and no bootstrap is started; this "
            "projection reports deterministic held-out point results only"
        ),
        "source_checkpoint": {
            "path": f"{EPOCH_REPO_PATH}/checkpoints/{CHECKPOINT_STAGE}.json",
            "schema_version": CHECKPOINT_SCHEMA,
            "file_sha256": checkpoint_file_hash,
            "payload_hash": checkpoint_payload_hash,
            "identity_verification": {
                "vs_final_test_execution_result": {
                    "file_match": execution_file_match,
                    "payload_match": execution_payload_match,
                    "recorded_file_sha256": execution_record.get("file_sha256"),
                    "recorded_payload_hash": execution_record.get("payload_hash"),
                },
                "vs_post_execution_audit": {
                    "file_match": audit_file_match,
                    "payload_match": audit_payload_match,
                    "recorded_file_sha256": audit_detail.get("file_sha256"),
                    "recorded_payload_hash": audit_detail.get("payload_hash"),
                },
            },
        },
        "canonical_v2_epoch": {
            "epoch_path": EPOCH_REPO_PATH,
            "branch": FINAL_TEST_BRANCH,
            "scientific_commit": PHASE7_SCIENTIFIC_COMMIT,
            "freeze_tag": FINAL_TEST_TAG,
            "paper_primary_branch": PAPER_PRIMARY_BRANCH,
            "paper_primary_commit": PAPER_PRIMARY_COMMIT,
            "epoch_seal": {
                "path": f"{EPOCH_REPO_PATH}/EPOCH_SEAL.json",
                "file_sha256": seal_file_hash,
                "status": seal.get("status"),
            },
        },
        "materialization": {
            "script": {
                "path": SCRIPT_REPO_PATH,
                "sha256": materializer_sha256,
                "sha256_source": (
                    "committed git blob (LF, as stored in the repository)"
                    if materializer_sha256
                    else "not provided"
                ),
            },
            "command": (
                f"python -m formal.v2_phase7.project_delay_vs_consequence_stage1 "
                f"--epoch-root {epoch_root} --out-dir {out_dir} "
                f"--materializer-sha256 {materializer_sha256 or '<script-sha256>'}"
            ),
            "epoch_root": str(epoch_root),
            "definitions": {
                "h_delay": "node IDs with selected=true in delay_decision",
                "h_consequence": "node IDs with selected=true in consequence_decision",
                "p_consequence": "frozen consequence priority score = consequence_decision.entries[*].score keyed by node_id",
                "a_consequence": "sum of P^C over H_consequence",
                "a_delay": "sum of the same frozen P^C over H_delay",
                "delta_att": "A_consequence - A_delay",
                "L_att": "delta_att / A_consequence",
                "eta_att": "A_delay / A_consequence = 1 - L_att",
                "changed_positions": "|H_consequence \\ H_delay| = |H_delay \\ H_consequence|",
                "changed_share": "changed_positions / K",
            },
        },
        "results": {
            "PRE_IB": stage_results["PRE_IB"],
            "POST_IB_PRE_OB": stage_results["POST_IB_PRE_OB"],
            "overall": overall,
        },
        "validation": {
            "source_checkpoint_hash_verification": {
                "schema_match": True,
                "file_hash_match_execution_result": execution_file_match,
                "payload_hash_match_execution_result": execution_payload_match,
                "file_hash_match_post_execution_audit": audit_file_match,
                "payload_hash_match_post_execution_audit": audit_payload_match,
            },
            "candidate_set_equality_delay_vs_consequence": candidate_set_checks,
            "objective_identity_checks": objective_checks,
            "overall_aggregation_identity": aggregation_checks,
            "zero_not_confused_with_missing": {
                "all_counts_integers": True,
                "null_count_fields": 0,
                "zero_stages": [
                    stage for stage, result in stage_results.items()
                    if result["changed_position_count"] == 0
                ],
            },
            "boundaries": {
                "final_test_raw_data_read": False,
                "new_final_test_execution": False,
                "new_access_epoch_opened": False,
                "bootstrap_started": False,
                "model_or_solver_executed": False,
                "legacy_or_development_or_fixture_read": False,
            },
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / JSON_NAME, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(output, indent=2, ensure_ascii=False, allow_nan=False))
        handle.write("\n")
    with open(out_dir / MD_NAME, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(_render_markdown(output))
    print(f"wrote {out_dir / JSON_NAME}")
    print(f"wrote {out_dir / MD_NAME}")
    return 0


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _render_markdown(output: Mapping[str, Any]) -> str:
    results = output["results"]
    order = ("PRE_IB", "POST_IB_PRE_OB", "overall")
    lines: list[str] = []
    lines.append("# Air Slot — Delay vs Consequence Stage-I Held-Out Results (sealed canonical-v2 projection)")
    lines.append("")
    lines.append("Read-only manuscript-facing projection of the sealed canonical stage-matched")
    lines.append("Final-Test epoch. No scientific computation, no bootstrap, no raw-data access.")
    lines.append("")
    lines.append("## Declarations")
    lines.append("")
    declarations = [
        ("projection_only", output["projection_only"]),
        ("scientific_recomputation_performed", output["scientific_recomputation_performed"]),
        ("final_test_raw_data_read", output["final_test_raw_data_read"]),
        ("new_final_test_execution", output["new_final_test_execution"]),
        ("scientific_definition_changed", output["scientific_definition_changed"]),
        ("source_representation", output["source_representation"]),
        ("source_representation_id", output["source_representation_id"]),
        ("nominal_q", output["nominal_q"]),
        ("stage_evaluation", output["stage_evaluation"]),
        ("overall_rule", output["overall_rule"]),
        ("pooled_stage1_ranking", output["pooled_stage1_ranking"]),
    ]
    for name, value in declarations:
        lines.append(f"- {name} = `{_fmt(value)}`")
    source = output["source_checkpoint"]
    epoch = output["canonical_v2_epoch"]
    lines.append(f"- source checkpoint: `{source['path']}` (schema `{source['schema_version']}`)")
    lines.append(f"- source checkpoint file SHA256: `{source['file_sha256']}`")
    lines.append(f"- source checkpoint payload hash: `{source['payload_hash']}`")
    lines.append(f"- canonical-v2 epoch identity: `{epoch['epoch_path']}` — branch `{epoch['branch']}` @ `{epoch['scientific_commit']}` (tag `{epoch['freeze_tag']}`); EPOCH_SEAL `{epoch['epoch_seal']['status']}` `{epoch['epoch_seal']['file_sha256']}`")
    lines.append(f"- {output['point_results_only_note']}")
    lines.append("")
    lines.append("## Paper-facing table (Section 5.1)")
    lines.append("")
    rows = []
    for key in order:
        result = results[key]
        if key == "overall":
            stage_label = "Overall"
            positions = f"{result['changed_position_count']}/{result['k_g']}"
        else:
            stage_label = result["stage_class"]
            positions = f"{result['changed_position_count']}/{result['k_g']}"
        rows.append(
            [
                stage_label,
                result["n_g"],
                result["k_g"],
                positions,
                result["changed_position_share"],
                result["eta_att"],
            ]
        )
    lines.append("| Stage | Actionable candidates | K | Positions changed: delay vs consequence | Changed share | Delay-based consequence value retained |")
    lines.append("|---|---|---|---|---|---|")
    for row in rows:
        lines.append("| " + " | ".join(_fmt(value) for value in row) + " |")
    lines.append("")
    lines.append("Zero changed positions means that delay-based and consequence-based screening selected exactly the same shortlist at that stage; it is a realized decision result, not a missing value or an unexecuted comparison.")
    lines.append("")
    lines.append("## Validation summary")
    lines.append("")
    verification = output["validation"]["source_checkpoint_hash_verification"]
    lines.append(f"- source checkpoint hash verification: schema match, file/payload hashes verified against both `FINAL_TEST_EXECUTION_RESULT.json` and `POST_EXECUTION_AUDIT.json` — all `{all(verification.values())}`")
    lines.append(f"- PRE/TURN candidate-set equality (cohort, k, q, eligible IDs, support status) between delay and consequence: `{all(all(item.get(key) for key in ('entries_node_sets_equal','cohort_size_equal','k_equal','q_equal','support_status_equal','eligible_ids_equal','eligible_count_equal','entries_count_equal')) for item in output['validation']['candidate_set_equality_delay_vs_consequence'].values())}`")
    lines.append(f"- objective identity checks: `{all(check['pass'] for check in output['validation']['objective_identity_checks'])}`")
    lines.append(f"- overall aggregation identity: `{all(output['validation']['overall_aggregation_identity'].values())}`")
    boundaries = output["validation"]["boundaries"]
    boundaries_hold = all(value is False for value in boundaries.values())
    lines.append(
        f"- no raw-data access / no recomputation / no bootstrap / no new epoch "
        f"(all boundary flags false as required): `{boundaries_hold}`"
    )
    lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
