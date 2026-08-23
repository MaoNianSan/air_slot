"""Exp3.7 LLM audit V2 - execution orchestration.

Pilot -> frozen-model principal (400-episode design, R=3) -> report. The
frozen prompt/schema/contract and deterministic case logic live in
exp/exp234/llm_audit_v2_contract.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from archive.exp.exp234.development_execution_legacy import OUT, AUDIT_CASES_PATH
from archive.exp.exp234.llm_audit_v2_contract_legacy import (
    DECISION_ID,
    MAX_LLM_CALLS_DEFAULT,
    N_PILOT_DEFAULT,
    PRINCIPAL_EPISODES_DEFAULT,
    REPETITIONS_PER_EPISODE,
    V1_PILOT_STATUS,
    _run_v2_case,
    contract_hash,
    evaluate_v2_pilot_gates,
    pilot_diagnostic_table,
    prompt_hash,
    schema_hash,
    select_principal_cases,
    serialize_case_v2,
    CASE_STRATA_ORDER,
    V2_VERDICTS,
    detect_prerequisite_handling_errors,
    detect_unsupported_fact_assertions,
    v2_request_payload,
    validate_audit_response_v2,
)
from exp.exp3.llm_audit import (
    AuditCache,
    DeepSeekAuditClient,
    LLMModelEscalationExhausted,
    model_preference_order,
    select_audit_cases,
)

def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _checkpoint_path(artifact_dir: Path) -> Path:
    return artifact_dir / "llm_audit_v2" / "checkpoint.json"


def _write_checkpoint(artifact_dir: Path, payload: Mapping[str, Any]) -> None:
    _write_json(_checkpoint_path(artifact_dir), payload)


def _load_checkpoint(artifact_dir: Path) -> dict | None:
    path = _checkpoint_path(artifact_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))

def _write_pilot_evidence(artifact_dir, pilot_rows, model_id, pilot_report, pilot_cases):
    """Section 14/18 artifacts: V2 pilot evidence + compact diagnostic table."""
    verdicts = {}
    for row in pilot_rows:
        response = row.get("response") or {}
        verdicts[response.get("final_judgement")] = verdicts.get(response.get("final_judgement"), 0) + 1
    evidence = {
        "artifact": "EXP234_LLM_AUDIT_PILOT_EVIDENCE_V2",
        "decision_id": DECISION_ID,
        "v1_status": V1_PILOT_STATUS,
        "v1_evidence_preserved": True,
        "v2_prompt_hash": prompt_hash(),
        "v2_schema_hash": schema_hash(),
        "v2_audit_contract_hash": contract_hash(),
        "model": model_id,
        "pilot_n": len(pilot_rows),
        "gates": pilot_report,
        "verdict_distribution": verdicts,
        "rows": [{
            "case_id": row.get("case_id"),
            "final_judgement": (row.get("response") or {}).get("final_judgement"),
            "confidence": (row.get("response") or {}).get("confidence"),
            "schema_valid": row.get("schema_valid"),
            "unsupported_fact_assertions": row.get("unsupported_fact_assertions") or [],
            "known_false_prerequisite_ignored": row.get("known_false_prerequisite_ignored") or [],
            "unknown_prerequisite_asserted_true": row.get("unknown_prerequisite_asserted_true") or [],
        } for row in pilot_rows],
    }
    _write_json(artifact_dir / "EXP234_LLM_AUDIT_PILOT_EVIDENCE_V2.json", evidence)
    _write_json(artifact_dir / "EXP234_LLM_AUDIT_PILOT_DIAGNOSTIC_V2.json", {
        "artifact": "EXP234_LLM_AUDIT_PILOT_DIAGNOSTIC_V2",
        "decision_id": DECISION_ID,
        "model": model_id,
        "table": pilot_diagnostic_table(pilot_rows),
    })
    return evidence


def run_v2_llm_audit(
    cases: list[Mapping[str, Any]],
    *,
    artifact_dir: Path = OUT,
    client=None,
    n_pilot: int = N_PILOT_DEFAULT,
    target_episodes: int = PRINCIPAL_EPISODES_DEFAULT,
    max_llm_calls: int = MAX_LLM_CALLS_DEFAULT,
    global_seed: int = 0,
    pilot_only: bool = False,
) -> dict:
    """V2 pilot -> frozen-model principal (400 episodes x 3 judgements)."""
    artifact_dir = Path(artifact_dir)
    v2_dir = artifact_dir / "llm_audit_v2"
    v2_dir.mkdir(parents=True, exist_ok=True)
    report_path = v2_dir / "DEEPSEEK_LLM_AUDIT_REPORT_V2.json"

    if client is None:
        client = DeepSeekAuditClient()

    checkpoint = _load_checkpoint(artifact_dir) or {}
    cache = AuditCache(v2_dir / "cache")

    pilot_cases = list(select_audit_cases(
        # Same deterministic selection call as the V1 pilot (section 15:
        # reuse the exact same 50 pilot cases where possible).
        cases, target_episodes=1250, global_seed=global_seed
    )[:n_pilot])
    if len(pilot_cases) < n_pilot:
        pilot_cases = list(cases)[:n_pilot]

    selected_models = list(model_preference_order(getattr(client, "available_models", ()) or ()))
    if client.model not in selected_models:
        selected_models = [client.model] + [m for m in selected_models if m != client.model]

    frozen_model = checkpoint.get("frozen_model")
    pilot_report = checkpoint.get("pilot_report")
    escalation_occurred = bool(checkpoint.get("escalation_occurred"))

    if not frozen_model:
        for model_index, model_id in enumerate(selected_models):
            client.set_model(model_id)
            pilot_rows = [
                _run_v2_case(client, cache, case, model=model_id) for case in pilot_cases
            ]
            pilot_report = evaluate_v2_pilot_gates(pilot_rows)
            if pilot_report["gates_passed"]:
                frozen_model = model_id
                escalation_occurred = model_index > 0
                _write_checkpoint(artifact_dir, {
                    "phase": "PILOT_PASSED",
                    "frozen_model": frozen_model,
                    "selected_models": selected_models,
                    "global_seed": global_seed,
                    "escalation_occurred": escalation_occurred,
                    "pilot_report": pilot_report,
                    "hashes": {
                        "prompt": prompt_hash(),
                        "schema": schema_hash(),
                        "contract": contract_hash(),
                    },
                })
                break
            _write_checkpoint(artifact_dir, {
                "phase": "PILOT_ESCALATED",
                "pilot_model": model_id,
                "selected_models": selected_models,
                "global_seed": global_seed,
                "pilot_report": pilot_report,
            })
        if not frozen_model:
            raise LLMModelEscalationExhausted("DEEPSEEK_V2_PILOT_NO_MODEL_PASSED")

    if pilot_rows:
        _write_pilot_evidence(artifact_dir, pilot_rows, frozen_model, pilot_report, pilot_cases)

    if pilot_only:
        return {"status": "PILOT_DONE", "frozen_model": frozen_model,
                "pilot_report": pilot_report, "hashes": {
                    "prompt": prompt_hash(), "schema": schema_hash(),
                    "contract": contract_hash()}}

    principal_cases, allocation = select_principal_cases(
        cases, target_episodes=target_episodes, global_seed=global_seed
    )
    client.set_model(frozen_model)
    calls_used = 0
    principal_rows: list[dict] = []
    for position, case in enumerate(principal_cases):
        for judgement_index in range(REPETITIONS_PER_EPISODE):
            row = _run_v2_case(client, cache, case, model=frozen_model,
                               judgement_index=judgement_index)
            if not row.get("cache_hit"):
                calls_used += 1
            principal_rows.append(row)
            if calls_used >= max_llm_calls:
                break
        if calls_used >= max_llm_calls:
            break

    completed = [row for row in principal_rows if row.get("status") in {"COMPLETED", "CACHED"}]
    judgements = [row["response"] for row in completed]
    from collections import Counter
    verdict_counts = Counter(response["final_judgement"] for response in judgements)
    confidence_counts = Counter(response["confidence"] for response in judgements)
    total = max(1, len(judgements))

    by_case: dict[str, list[dict]] = {}
    for row in completed:
        by_case.setdefault(row["case_id"], []).append(row["response"])
    stable_exact = 0
    stable_accept_family = 0
    stable_confidence = 0
    overlap_scores = []
    for case_id, responses in by_case.items():
        if len(responses) < 2:
            continue
        judgements_here = [r["final_judgement"] for r in responses]
        stable_exact += len(set(judgements_here)) == 1
        stable_accept_family += len({
            j if j in ("ACCEPT", "ACCEPT_WITH_RESERVATIONS") else "OTHER" for j in judgements_here
        }) == 1
        stable_confidence += len({r["confidence"] for r in responses}) == 1
        info_sets = [set(r.get("missing_critical_information") or []) for r in responses]
        if len(info_sets) >= 2:
            pairs = [(a, b) for i, a in enumerate(info_sets) for b in info_sets[i + 1:]]
            if pairs:
                overlap_scores.append(
                    sum(len(a & b) for a, b in pairs) / max(1, sum(len(a | b) for a, b in pairs))
                )
    multi = max(1, sum(1 for rs in by_case.values() if len(rs) >= 2))
    repeat_exact = stable_exact / multi
    repeat_accept_family = stable_accept_family / multi
    repeat_confidence = stable_confidence / multi
    missing_overlap = (sum(overlap_scores) / len(overlap_scores)) if overlap_scores else None

    report = {
        "closure_id": "AIR_SLOT_LLM_AUDIT_V2_CLOSURE",
        "decision_id": DECISION_ID,
        "status": "COMPLETED",
        "v1_pilot_preserved": True,
        "v1_status": V1_PILOT_STATUS,
        "v1_evidence_path": "EXP234_LLM_AUDIT_PILOT_EVIDENCE_V1.json",
        "v2_prompt_hash": prompt_hash(),
        "v2_schema_hash": schema_hash(),
        "v2_audit_contract_hash": contract_hash(),
        "deepseek_model_id": frozen_model,
        "model_selection_rule": MODEL_SELECTION_RULE,
        "model_escalation_occurred": escalation_occurred,
        "v2_pilot_n": pilot_report["pilot_n"],
        "schema_pass_rate": pilot_report["schema_pass_rate"],
        "parse_failure_rate": pilot_report["parse_failure_rate"],
        "unsupported_fact_assertion_rate": pilot_report["unsupported_fact_assertion_rate"],
        "known_false_prerequisite_ignored_rate": pilot_report[
            "known_false_prerequisite_ignored_rate"],
        "unknown_prerequisite_asserted_true_rate": pilot_report[
            "unknown_prerequisite_asserted_true_rate"],
        "v2_pilot_status": "PASS" if pilot_report["gates_passed"] else "FAIL",
        "principal_episodes": len(by_case),
        "repetitions_per_episode": REPETITIONS_PER_EPISODE,
        "total_judgements": len(judgements),
        "accept_rate": verdict_counts.get("ACCEPT", 0) / total,
        "accept_with_reservations_rate": verdict_counts.get("ACCEPT_WITH_RESERVATIONS", 0) / total,
        "reject_rate": verdict_counts.get("REJECT", 0) / total,
        "insufficient_information_rate": verdict_counts.get("INSUFFICIENT_INFORMATION", 0) / total,
        "verdict_distribution": dict(verdict_counts),
        "confidence_distribution": dict(confidence_counts),
        "repeat_exact_agreement": repeat_exact,
        "repeat_accept_family_agreement": repeat_accept_family,
        "repeat_confidence_agreement": repeat_confidence,
        "missing_information_overlap": missing_overlap,
        "allocation": allocation,
        "calls_used": calls_used,
        "max_llm_calls": max_llm_calls,
        "llm_to_model_feedback": False,
        "final_test_access_count": 0,
        "paper_full_run": False,
        "scientific_description": (
            "DeepSeek provides an auxiliary, state-conditioned operational explanation and "
            "reasonableness audit of frozen Air Slot recommendations. It does not validate model "
            "correctness, estimate counterfactual action effects, or modify the formal "
            "recommendation."
        ),
    }
    _write_json(report_path, report)
    _write_checkpoint(artifact_dir, {
        "phase": "COMPLETED",
        "frozen_model": frozen_model,
        "selected_models": selected_models,
        "global_seed": global_seed,
        "escalation_occurred": escalation_occurred,
        "pilot_report": pilot_report,
        "hashes": {
            "prompt": prompt_hash(),
            "schema": schema_hash(),
            "contract": contract_hash(),
        },
    })
    return report
def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Exp3.7 LLM audit V2")
    parser.add_argument("--verify-serializer", action="store_true",
                        help="serialize + print hashes, no API calls")
    parser.add_argument("--pilot-only", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    if args.verify_serializer:
        cases = json.loads(AUDIT_CASES_PATH.read_text(encoding="utf-8"))["cases"]
        v2 = [serialize_case_v2(c) for c in cases]
        unknown = sum(len(c["unknown_facts"]) for c in v2)
        print(json.dumps({
            "prompt_hash": prompt_hash(),
            "schema_hash": schema_hash(),
            "contract_hash": contract_hash(),
            "cases_serialized": len(v2),
            "unknown_facts_total": unknown,
            "model_metadata_isolated": True,
        }, indent=2, sort_keys=True))
        return 0

    cases = json.loads(AUDIT_CASES_PATH.read_text(encoding="utf-8"))["cases"]
    if args.limit:
        cases = cases[:args.limit]
    report = run_v2_llm_audit(cases, pilot_only=args.pilot_only)
    keys = ("status", "deepseek_model_id", "v2_pilot_status", "v2_prompt_hash",
            "v2_schema_hash", "v2_audit_contract_hash", "principal_episodes",
            "total_judgements", "accept_rate", "accept_with_reservations_rate",
            "reject_rate", "insufficient_information_rate",
            "repeat_exact_agreement", "repeat_accept_family_agreement", "calls_used")
    print(json.dumps({k: report.get(k) for k in keys}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


