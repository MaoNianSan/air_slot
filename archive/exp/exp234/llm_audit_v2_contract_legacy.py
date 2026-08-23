"""Exp3.7 LLM audit V2 - frozen contract layer.

Frozen V2 prompt/schema/audit-contract, deterministic case serializer,
experiment-side error detectors, pilot gates, diagnostic table and principal
selection. Execution orchestration (run_v2_llm_audit / CLI) lives in
exp/exp234/llm_audit_v2.py.

DECISION_ID = AIR_SLOT_LLM_AUDIT_V2_STATE_CONDITIONED_EXPLANATION (APPROVED)
"""
from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, Mapping

from archive.exp.exp234.exp234_helpers_legacy import _ACTION_META
from exp.exp3.llm_audit import (
    AuditCache,
    LLMParseFailure,
    request_hash,
    select_audit_cases,
)

# ---------------------------------------------------------------------------

DECISION_ID = "AIR_SLOT_LLM_AUDIT_V2_STATE_CONDITIONED_EXPLANATION"
V1_PILOT_STATUS = "DIAGNOSTIC_FAIL_UNDER_SUPERSEDED_AUDIT_CONSTRUCT"

V2_PROMPT_VERSION = "DEEPSEEK_AUDIT_PROMPT_V2"
V2_SCHEMA_VERSION = "DEEPSEEK_AUDIT_RESPONSE_V2_STATE_CONDITIONED"
V2_PROTOCOL = "STATE_CONDITIONED_EXPLANATION"
V2_RUBRIC_VERSION = "AIR_SLOT_OPERATIONAL_REASONABLENESS_RUBRIC_V1"
MODEL_SELECTION_RULE = "COST_FIRST_WITH_QUALITY_GATE"

V2_VERDICTS = ("ACCEPT", "ACCEPT_WITH_RESERVATIONS", "REJECT", "INSUFFICIENT_INFORMATION")
V2_CONFIDENCE = ("LOW", "MEDIUM", "HIGH")
V2_TIMING_ASSESSMENTS = ("FEASIBLE", "CONDITIONAL", "INFEASIBLE", "UNCLEAR")

# Section 17 gate limits.
V2_SCHEMA_PASS_RATE_MIN = 0.98
V2_PARSE_FAILURE_MAX = 0.02
V2_UNSUPPORTED_FACT_ASSERTION_MAX = 0.0
V2_KNOWN_FALSE_PREREQUISITE_IGNORED_MAX = 0.05
V2_UNKNOWN_PREREQUISITE_ASSERTED_TRUE_MAX = 0.0

N_PILOT_DEFAULT = 50
PRINCIPAL_EPISODES_DEFAULT = 400
REPETITIONS_PER_EPISODE = 3
MAX_LLM_CALLS_DEFAULT = 1500

CASE_STRATA_ORDER = (
    "formal_non_null_top1",
    "formal_a00_top1",
    "relaxed_only_invalidated_top1",
    "scenario_conditional_close_call",
)
PRINCIPAL_TARGET_PER_STRATUM = 100
REDISTRIBUTION_ORDER = ("formal_a00_top1", "scenario_conditional_close_call")
# ---------------------------------------------------------------------------
# Frozen V2 prompt (section 11 of the decision). The system text below is the
# exact frozen prompt text; prompt_hash covers system + user template.
# ---------------------------------------------------------------------------

V2_SYSTEM_PROMPT = (
    "You are acting as an airline operations decision reviewer.\n"
    "\n"
    "You will receive a snapshot of the information available at one specific decision time and a "
    "recovery action recommended by an external decision model.\n"
    "\n"
    "Your task is not to optimize the decision, estimate a causal treatment effect, reconstruct "
    "hidden information, or predict the exact future.\n"
    "\n"
    "Evaluate whether the recommended action is operationally reasonable given ONLY the supplied "
    "current-state information.\n"
    "\n"
    "You must:\n"
    "1. identify the main operational reason the action could help;\n"
    "2. identify execution burdens and resource dependencies;\n"
    "3. assess whether the action can plausibly be initiated in the available time;\n"
    "4. explicitly identify important missing or unresolved information;\n"
    "5. distinguish supplied facts from assumptions;\n"
    "6. never assume an UNKNOWN resource or prerequisite is available;\n"
    "7. never invent exact numerical effects that are not supplied;\n"
    "8. provide a concise explanation of why the model recommendation appears reasonable, "
    "questionable, or insufficiently supported by current information.\n"
    "\n"
    "Missing information is not automatically a reason to reject the action.\n"
    "If the recommendation is plausible but depends on unresolved information, use "
    "ACCEPT_WITH_RESERVATIONS.\n"
    "Use INSUFFICIENT_INFORMATION only when the missing information is so central that an "
    "operational reasonableness judgment cannot responsibly be made.\n"
    "\n"
    "Do not modify the action. Do not propose a different optimization model. Do not treat your "
    "answer as ground truth.\n"
    "\n"
    "Respond ONLY with a JSON object matching this exact schema:\n"
    '{"plausible_operational_outcomes": ["<str>", ...], '
    '"primary_mitigation": ["<str>", ...], '
    '"execution_burdens": ["<str>", ...], '
    '"resource_dependencies": ["<str>", ...], '
    '"downstream_effects": ["<str>", ...], '
    '"timing_feasibility": {"assessment": "FEASIBLE|CONDITIONAL|INFEASIBLE|UNCLEAR", "reason": "<str>"}, '
    '"missing_critical_information": ["<str>", ...], '
    '"state_grounded_explanation": "<str>", '
    '"final_judgement": "ACCEPT|ACCEPT_WITH_RESERVATIONS|REJECT|INSUFFICIENT_INFORMATION", '
    '"confidence": "LOW|MEDIUM|HIGH"}'
)

V2_USER_PROMPT_TEMPLATE = (
    "Decision-time case snapshot (current-state information only; "
    "model metadata is labeled and is not an operational fact):\n"
    "{case_json}"
)

# ---------------------------------------------------------------------------
# Frozen V2 output schema (section 12).
# ---------------------------------------------------------------------------

V2_SCHEMA_JSON = {
    "schema_version": V2_SCHEMA_VERSION,
    "fields": {
        "plausible_operational_outcomes": {"type": "list[str]", "required": True},
        "primary_mitigation": {"type": "list[str]", "required": True},
        "execution_burdens": {"type": "list[str]", "required": True},
        "resource_dependencies": {"type": "list[str]", "required": True},
        "downstream_effects": {"type": "list[str]", "required": True},
        "timing_feasibility": {"type": "object", "required": True,
                               "assessment_enum": list(V2_TIMING_ASSESSMENTS)},
        "missing_critical_information": {"type": "list[str]", "required": True},
        "state_grounded_explanation": {"type": "str", "required": True, "nonempty": True},
        "final_judgement": {"type": "str", "required": True, "enum": list(V2_VERDICTS)},
        "confidence": {"type": "str", "required": True, "enum": list(V2_CONFIDENCE)},
    },
}

# ---------------------------------------------------------------------------
# Frozen V2 audit contract (sections 1-4, 13, 17, 19-21 of the decision).
# ---------------------------------------------------------------------------

V2_AUDIT_CONTRACT = (
    "DEEPSEEK V2 AUDIT CONTRACT\n"
    "Role: AUXILIARY / EVALUATION-ONLY / STATE-CONDITIONED / MODEL-OUTPUT EXPLANATION AND "
    "OPERATIONAL REASONABLENESS AUDIT. Not ground truth, expert oracle, counterfactual simulator, "
    "causal estimator, M4 validator, formal-support validator, model-selection or parameter-tuning "
    "mechanism.\n"
    "Mapping: CURRENT DECISION-TIME STATE + MODEL RECOMMENDED ACTION + DECLARED ACTION MECHANISM + "
    "KNOWN CONSTRAINTS/UNKNOWN INFORMATION -> OPERATIONAL REASONABLENESS EXPLANATION.\n"
    "No post-hoc information: realized delays, passenger outcomes, recovery results, unchosen-action "
    "outcomes, Final Test outcomes, post-hoc labels, or future information are never supplied.\n"
    "Missing information semantics: MISSING INFORMATION != LLM FAILURE and != LLM ASSUMPTION.\n"
    "Metadata (action_family, M4 lane, provenance labels, registry ids, implementation status) are "
    "not decision-state facts; null/NOT_RUN/NOT_AVAILABLE values must not automatically cause "
    "audit failure.\n"
    "Judgements: ACCEPT (mechanism matches state, no known blocking fact, requirements supported); "
    "ACCEPT_WITH_RESERVATIONS (plausible but unresolved resources/prerequisites/downstream "
    "consequences - a common legitimate outcome); REJECT (supplied facts contradict the action, "
    "timing infeasible, burdens dominate, or a required prerequisite is explicitly false); "
    "INSUFFICIENT_INFORMATION (state too incomplete to judge plausibility at all - not for one "
    "noncritical missing field).\n"
    "Pilot gates: SCHEMA_PASS_RATE>=0.98, PARSE_FAILURE_RATE<=0.02, "
    "UNSUPPORTED_FACT_ASSERTION_RATE=0, KNOWN_FALSE_PREREQUISITE_IGNORED_RATE<=0.05, "
    "UNKNOWN_PREREQUISITE_ASSERTED_TRUE_RATE=0. Missing-prerequisite rate is NOT a failure metric.\n"
    "Sample design: 400 independent episodes x 3 repeated judgements = 1200 judgements; "
    "repetitions measure LLM audit stability, not empirical sample size; "
    "empirical denominator remains N_episode=400.\n"
    "No model feedback: LLM output never changes PRE/M1/M2/M3/M4 or Exp2/3/4 frozen settings.\n"
)

# ---------------------------------------------------------------------------
# Hashes
# ---------------------------------------------------------------------------


def _sha256_text(text: str) -> str:
    return f"sha256:{sha256(text.encode('utf-8')).hexdigest()}"


def prompt_hash() -> str:
    return _sha256_text(V2_PROMPT_VERSION + "\n" + V2_SYSTEM_PROMPT + "\n" + V2_USER_PROMPT_TEMPLATE)


def schema_hash() -> str:
    canonical = json.dumps(V2_SCHEMA_JSON, sort_keys=True, separators=(",", ":"))
    return _sha256_text(V2_SCHEMA_VERSION + "\n" + canonical)


def contract_hash() -> str:
    return _sha256_text(V2_AUDIT_CONTRACT)
# ---------------------------------------------------------------------------
# V2 case serializer (whitelisted decision-time fields + deterministic
# registry-known metadata enrichment + UNKNOWN preservation).
# ---------------------------------------------------------------------------

# Fields admitted into the V2 case. Post-hoc/outcome fields are not part of
# the V1 case file; this whitelist is a guard so future field additions that
# would leak decision-time information are rejected by construction.
_V2_CASE_KEYS = (
    "case_id",
    "episode_id",
    "decision_node_id",
    "stratum",
    "decision_time",
    "operational_stage",
    "admissible_operational_state",
    "major_uncertainty",
    "m2_consequence_profile",
    "recommended_action",
    "action_family",
    "preconditions",
    "preparation_time_minutes",
    "authority_requirements",
    "model_metadata",
)

_MODEL_METADATA_KEYS = (
    "m3_response_provenance",
    "m3_scenario_parameters",
    "m4_lane",
    "m4_blocker",
    "m4_score_rank",
    "exp3_row",
    "exp4_sensitivity_base_top1",
    "closest_alternatives",
)


class ContractErrorV2(Exception):
    pass


def _unknown_fact_entries(case_v1: Mapping[str, Any]) -> list[dict]:
    """UNKNOWN operational facts at decision time, mechanically derived."""
    entries: list[dict] = []
    state = case_v1.get("admissible_operational_state") or {}
    for field, value in sorted(state.items()):
        if value is None:
            entries.append({"field": field, "value": "UNKNOWN", "critical": False})
    preconditions = case_v1.get("preconditions")
    if preconditions == "UNKNOWN":
        entries.append({"field": "preconditions", "value": "UNKNOWN", "critical": True})
    return entries


def serialize_case_v2(case_v1: Mapping[str, Any]) -> dict:
    """Build the V2 LLM case: decision-time state + recommended action +
    declared mechanism + known constraints/unknowns + labeled metadata.

    Metadata fields are mechanically enriched from the frozen M3 structural
    template map (_ACTION_META) where the source case has no value, and are
    always separated into model_metadata so they cannot be mistaken for
    operational facts.
    """
    state = dict(case_v1.get("admissible_operational_state") or {})
    action_id = case_v1.get("recommended_action")
    family = case_v1.get("action_family")
    if family in (None, "", "null") and action_id in _ACTION_META:
        family = _ACTION_META[action_id][0]
    preparation = case_v1.get("preparation_time_minutes")
    if preparation is None and action_id in _ACTION_META:
        preparation = _ACTION_META[action_id][1]
    authority = case_v1.get("authority_requirements")
    if not authority and action_id in _ACTION_META:
        authority = list(_ACTION_META[action_id][2])

    presented_state = {
        field: ("UNKNOWN" if value is None else value)
        for field, value in state.items()
    }

    serialized = {
        "case_id": case_v1.get("case_id"),
        "episode_id": case_v1.get("episode_id"),
        "decision_node_id": case_v1.get("decision_node_id"),
        "stratum": case_v1.get("stratum"),
        "decision_time": case_v1.get("decision_time"),
        "operational_stage": case_v1.get("operational_stage"),
        "admissible_operational_state": presented_state,
        "unknown_facts": _unknown_fact_entries(case_v1),
        "major_uncertainty": dict(case_v1.get("major_uncertainty") or {}),
        "m2_consequence_profile": dict(case_v1.get("m2_consequence_profile") or {}),
        "recommended_action": action_id,
        "action_family": family,
        "preconditions": case_v1.get("preconditions"),
        "preparation_time_minutes": preparation,
        "authority_requirements": authority,
        "model_metadata": {
            key: case_v1.get(key)
            for key in _MODEL_METADATA_KEYS
        },
    }
    for key in _V2_CASE_KEYS:
        if key not in serialized:
            raise ContractErrorV2(f"LLM_V2_SERIALIZER_MISSING_KEY:{key}")
    return serialized


# ---------------------------------------------------------------------------
# Response validation (frozen schema).
# ---------------------------------------------------------------------------


def validate_audit_response_v2(response: Mapping[str, Any]) -> dict:
    if not isinstance(response, dict):
        raise ValueError("DEEPSEEK_AUDIT_V2_SCHEMA_INVALID")
    required = (
        "plausible_operational_outcomes",
        "primary_mitigation",
        "execution_burdens",
        "resource_dependencies",
        "downstream_effects",
        "timing_feasibility",
        "missing_critical_information",
        "state_grounded_explanation",
        "final_judgement",
        "confidence",
    )
    if any(name not in response for name in required):
        raise ValueError("DEEPSEEK_AUDIT_V2_SCHEMA_INVALID")
    for name in (
        "plausible_operational_outcomes",
        "primary_mitigation",
        "execution_burdens",
        "resource_dependencies",
        "downstream_effects",
        "missing_critical_information",
    ):
        if not isinstance(response[name], list) or not all(
            isinstance(item, str) for item in response[name]
        ):
            raise ValueError("DEEPSEEK_AUDIT_V2_SCHEMA_INVALID")
    timing = response["timing_feasibility"]
    if not isinstance(timing, dict) or timing.get("assessment") not in V2_TIMING_ASSESSMENTS:
        raise ValueError("DEEPSEEK_AUDIT_V2_SCHEMA_INVALID")
    if not isinstance(timing.get("reason"), str) or not timing["reason"].strip():
        raise ValueError("DEEPSEEK_AUDIT_V2_SCHEMA_INVALID")
    if response["final_judgement"] not in V2_VERDICTS:
        raise ValueError("DEEPSEEK_AUDIT_V2_VERDICT_INVALID")
    if response["confidence"] not in V2_CONFIDENCE:
        raise ValueError("DEEPSEEK_AUDIT_V2_CONFIDENCE_INVALID")
    if not isinstance(response["state_grounded_explanation"], str) or not response[
        "state_grounded_explanation"
    ].strip():
        raise ValueError("DEEPSEEK_AUDIT_V2_JUSTIFICATION_EMPTY")
    return dict(response)
# ---------------------------------------------------------------------------
# Experiment-side deterministic error detection (sections 5-6).
# ---------------------------------------------------------------------------

_HEDGE_WORDS = (
    "if ",
    "assuming",
    "assume",
    "provided",
    "unless",
    "subject to",
    "pending",
    "unknown",
    "unresolved",
    "uncertain",
    "unclear",
    "not confirmed",
    "not available",
    "not met",
    "not satisfied",
    "cannot",
    "can't",
    "may not",
    "might not",
    "depends",
    "contingent",
    "no evidence",
    "remains",
    "to be confirmed",
    "unavailable",
    "in question",
    "would need",
    "would require",
    "needs to be",
    "must be",
)

_ASSERT_PATTERNS = (
    "is available",
    "are available",
    "will be available",
    "can be made available",
    "has been secured",
    "is secured",
    "is in place",
    "are in place",
    "is met",
    "are met",
    "is satisfied",
    "are satisfied",
    "has been confirmed",
    "is confirmed",
    "is ready",
    "are ready",
    "can accommodate",
    "can be executed",
    "can be performed",
    "will be met",
)

_FACT_TOKENS = {
    "observed_delta_ob_minutes": ("delta ob", "observed delay", "ob delay"),
    "observed_t_tx_minutes": ("turnaround time", "turn time", "turnaround", "t tx"),
    "observed_r_ib_minutes": ("observed r ib", "r ib"),
    "preconditions": ("precondition", "prerequisite", "prereq"),
}


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]


def _response_text(response: Mapping[str, Any]) -> str:
    parts = [str(response.get("state_grounded_explanation") or "")]
    timing = response.get("timing_feasibility") or {}
    parts.append(str(timing.get("reason") or ""))
    for name in (
        "plausible_operational_outcomes",
        "primary_mitigation",
        "execution_burdens",
        "resource_dependencies",
        "downstream_effects",
        "missing_critical_information",
    ):
        for item in response.get(name) or []:
            if isinstance(item, str):
                parts.append(item)
    return " ".join(parts)


def _assertion_in_sentence(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(pattern in lowered for pattern in _ASSERT_PATTERNS)


def _hedged(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(hedge in lowered for hedge in _HEDGE_WORDS)


def detect_unsupported_fact_assertions(
    response: Mapping[str, Any], case_v2: Mapping[str, Any]
) -> list[str]:
    """Section 5.1: count only assertions of a factual operational state that
    is not supplied (UNKNOWN) or contradicts the supplied state. Sentences
    that hedge (if/assuming/subject to/unresolved/...) are not assertions."""
    evidence: list[str] = []
    text = _response_text(response)
    unknown = {entry["field"]: entry for entry in case_v2.get("unknown_facts") or []}
    for field, entry in unknown.items():
        if entry.get("critical"):
            continue  # critical unknowns are prerequisite-handling territory
        tokens = _FACT_TOKENS.get(field, (field,))
        for sentence in _sentences(text):
            lowered = sentence.lower()
            if not any(token in lowered for token in tokens):
                continue
            if _assertion_in_sentence(lowered) and not _hedged(lowered):
                evidence.append(f"unsupported_fact_assertion:{field}:{sentence[:160]}")
    return evidence


def detect_prerequisite_handling_errors(
    response: Mapping[str, Any], case_v2: Mapping[str, Any]
) -> list[str]:
    """Section 6: PREREQUISITE_HANDLING_ERROR only when
    1) a prerequisite is explicitly FALSE and treated as satisfied;
    2) a prerequisite is UNKNOWN and asserted satisfied;
    3) a critical prerequisite is UNKNOWN and the LLM gives an unconditional
       ACCEPT while failing to mention the uncertainty."""
    evidence: list[str] = []
    judgement = response.get("final_judgement")
    preconditions = case_v2.get("preconditions")
    text = _response_text(response)

    if preconditions == "FALSE" and judgement == "ACCEPT":
        evidence.append("known_false_prerequisite_ignored:ACCEPT_despite_explicit_FALSE")

    if preconditions == "UNKNOWN":
        tokens = _FACT_TOKENS["preconditions"]
        for sentence in _sentences(text):
            lowered = sentence.lower()
            if any(token in lowered for token in tokens):
                if _assertion_in_sentence(lowered) and not _hedged(lowered):
                    evidence.append(
                        f"unknown_prerequisite_asserted_true:{sentence[:160]}"
                    )
        if judgement == "ACCEPT":
            unknown_labels = " ".join(
                str(entry.get("field")) for entry in (case_v2.get("unknown_facts") or [])
            ).lower()
            mentioned = any(label in text.lower() for label in unknown_labels.split())
            if not mentioned and not _hedged(text):
                evidence.append(
                    "unknown_prerequisite_asserted_true:unconditional_ACCEPT_without_uncertainty_mention"
                )
    return evidence


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
# ---------------------------------------------------------------------------
# V2 pilot gates + diagnostic table (sections 17-18).
# ---------------------------------------------------------------------------


def evaluate_v2_pilot_gates(rows: list[Mapping[str, Any]]) -> dict:
    total = len(rows)
    schema_ok = sum(bool(row.get("schema_valid")) for row in rows)
    parse_failures = sum(bool(row.get("unrecoverable_parse_failure")) for row in rows)
    unsupported = sum(bool(row.get("unsupported_fact_assertions")) for row in rows)
    known_false = sum(bool(row.get("known_false_prerequisite_ignored")) for row in rows)
    unknown_true = sum(bool(row.get("unknown_prerequisite_asserted_true")) for row in rows)
    schema_pass_rate = (schema_ok / total) if total else 0.0
    parse_failure_rate = (parse_failures / total) if total else 0.0
    unsupported_rate = (unsupported / total) if total else 0.0
    known_false_rate = (known_false / total) if total else 0.0
    unknown_true_rate = (unknown_true / total) if total else 0.0
    passed = (
        total > 0
        and schema_pass_rate >= V2_SCHEMA_PASS_RATE_MIN
        and parse_failure_rate <= V2_PARSE_FAILURE_MAX
        and unsupported_rate <= V2_UNSUPPORTED_FACT_ASSERTION_MAX
        and known_false_rate <= V2_KNOWN_FALSE_PREREQUISITE_IGNORED_MAX
        and unknown_true_rate <= V2_UNKNOWN_PREREQUISITE_ASSERTED_TRUE_MAX
    )
    return {
        "pilot_n": total,
        "schema_valid_n": schema_ok,
        "unrecoverable_parse_failure_n": parse_failures,
        "unsupported_fact_assertion_n": unsupported,
        "known_false_prerequisite_ignored_n": known_false,
        "unknown_prerequisite_asserted_true_n": unknown_true,
        "schema_pass_rate": schema_pass_rate,
        "parse_failure_rate": parse_failure_rate,
        "unsupported_fact_assertion_rate": unsupported_rate,
        "known_false_prerequisite_ignored_rate": known_false_rate,
        "unknown_prerequisite_asserted_true_rate": unknown_true_rate,
        "gates_passed": passed,
    }


def pilot_diagnostic_table(rows: list[Mapping[str, Any]]) -> list[dict]:
    """Section 18: compact diagnostic table (audit validation only)."""
    table = []
    for row in rows:
        response = row.get("response") or {}
        table.append({
            "case_id": row.get("case_id"),
            "recommended_action": row.get("recommended_action"),
            "known_blocking_fact": row.get("known_blocking_fact"),
            "unknown_critical_fact_count": row.get("unknown_critical_fact_count"),
            "final_judgement": response.get("final_judgement"),
            "missing_information_count": len(response.get("missing_critical_information") or []),
            "unsupported_fact_assertion": bool(row.get("unsupported_fact_assertions")),
            "prerequisite_handling_error": bool(
                row.get("known_false_prerequisite_ignored")
                or row.get("unknown_prerequisite_asserted_true")
            ),
            "schema_pass": bool(row.get("schema_valid")),
        })
    return table
# ---------------------------------------------------------------------------
# V2 principal case selection (sections 19-20).
# ---------------------------------------------------------------------------


def _ranked(candidates, stream_tag: str, global_seed: int) -> list[dict]:
    """Local deterministic ranking (sha256 over tag|seed|episode) for the
    Exp3.7 V2 principal selection. Kept inside the Exp3.7 layer so the
    shared V5 RNG stream contract (exp/common/rng.py) is not modified."""
    def key(case):
        digest = sha256(
            f"{stream_tag}|{global_seed}|{case['episode_id']}".encode("utf-8")
        ).hexdigest()
        return digest
    return sorted(candidates, key=key)


def select_principal_cases(cases: list[Mapping[str, Any]], *, target_episodes=400,
                           global_seed=0) -> tuple[tuple[dict, ...], dict]:
    """400 episodes, 1 node per episode, strata targets 100/100/100/100 with
    deterministic redistribution for undersupplied strata."""
    by_stratum: dict[str, dict] = {}
    for case in cases:
        stratum = case.get("stratum")
        if stratum not in CASE_STRATA_ORDER:
            continue
        bucket = by_stratum.setdefault(stratum, {})
        bucket.setdefault(case["episode_id"], case)

    target_per = PRINCIPAL_TARGET_PER_STRATUM
    allocation: dict[str, dict] = {}
    selected: list[dict] = []
    used_episodes: set[str] = set()

    for stratum in CASE_STRATA_ORDER:
        bucket = by_stratum.get(stratum, {})
        candidates = [case for episode, case in sorted(bucket.items())
                      if episode not in used_episodes]
        available = len(bucket)
        ordered_candidates = _ranked(candidates, "llm_v2_principal", global_seed)
        picked = []
        for case in ordered_candidates[:target_per]:
            picked.append(case)
            used_episodes.add(case["episode_id"])
        selected.extend(picked)
        allocation[stratum] = {
            "TARGET_N": target_per,
            "AVAILABLE_N": available,
            "ACTUAL_N": len(picked),
            "REDISTRIBUTED_N": max(0, target_per - len(picked)),
        }

    shortfall = sum(entry["REDISTRIBUTED_N"] for entry in allocation.values())
    if shortfall > 0:
        remaining: dict[str, list[dict]] = {}
        for stratum in REDISTRIBUTION_ORDER:
            bucket = by_stratum.get(stratum, {})
            remaining[stratum] = [case for episode, case in sorted(bucket.items())
                                  if episode not in used_episodes]
        for stratum in REDISTRIBUTION_ORDER:
            if shortfall <= 0:
                break
            cap = min(PRINCIPAL_TARGET_PER_STRATUM, shortfall)
            picked = []
            for case in _ranked(remaining[stratum], "llm_v2_principal_redist", global_seed):
                if shortfall <= 0 or len(picked) >= cap:
                    break
                picked.append(case)
                used_episodes.add(case["episode_id"])
                shortfall -= 1
            selected.extend(picked)
            if picked:
                allocation[stratum]["REDISTRIBUTED_N"] += len(picked)
                allocation[stratum]["ACTUAL_N"] += len(picked)

    return tuple(selected), {
        "TARGET_EPISODES": target_episodes,
        "ACTUAL_EPISODES": len(selected),
        "ALLOCATION": allocation,
        "GLOBAL_SEED": global_seed,
        "RULE": "1 decision node per episode; deterministic redistribution in order "
                + ",".join(REDISTRIBUTION_ORDER),
    }
# ---------------------------------------------------------------------------
# V2 execution
# ---------------------------------------------------------------------------


def v2_messages(case_v2: Mapping[str, Any]) -> list[dict]:
    case_json = json.dumps(case_v2, sort_keys=True, ensure_ascii=False, indent=2)
    return [
        {"role": "system", "content": V2_SYSTEM_PROMPT},
        {"role": "user", "content": V2_USER_PROMPT_TEMPLATE.format(case_json=case_json)},
    ]


def v2_request_payload(case_v2: Mapping[str, Any], *, model: str,
                       judgement_index: int = 0) -> dict:
    return {
        "schema_version": V2_SCHEMA_VERSION,
        "protocol": V2_PROTOCOL,
        "prompt_version": V2_PROMPT_VERSION,
        "rubric_version": V2_RUBRIC_VERSION,
        "model": model,
        "judgement_index": int(judgement_index),
        "case": case_v2,
    }


def _row_for_case(case_v1: Mapping[str, Any], response: Mapping[str, Any] | None,
                  *, schema_valid: bool, parse_failure: bool) -> dict:
    case_v2 = serialize_case_v2(case_v1)
    response = dict(response or {})
    unsupported = _dedupe(detect_unsupported_fact_assertions(response, case_v2))
    prereq = _dedupe(detect_prerequisite_handling_errors(response, case_v2))
    known_false = [e for e in prereq if e.startswith("known_false_prerequisite_ignored")]
    unknown_true = [e for e in prereq if e.startswith("unknown_prerequisite_asserted_true")]
    return {
        "case_id": case_v1.get("case_id"),
        "recommended_action": case_v1.get("recommended_action"),
        "known_blocking_fact": ("EXPLICIT_FALSE" if case_v1.get("preconditions") == "FALSE"
                                else "NONE"),
        "unknown_critical_fact_count": sum(
            1 for entry in _unknown_fact_entries(case_v1) if entry.get("critical")
        ),
        "status": "COMPLETED" if schema_valid and not parse_failure else "PARSE_FAILURE",
        "response": response,
        "schema_valid": schema_valid,
        "unrecoverable_parse_failure": parse_failure,
        "unsupported_fact_assertions": unsupported,
        "known_false_prerequisite_ignored": known_false,
        "unknown_prerequisite_asserted_true": unknown_true,
    }


def _run_v2_case(client, cache: AuditCache, case_v1: Mapping[str, Any], *,
                 model: str, judgement_index: int = 0, use_cache: bool = True) -> dict:
    case_v2 = serialize_case_v2(case_v1)
    payload = v2_request_payload(case_v2, model=model, judgement_index=judgement_index)
    digest = request_hash(payload)
    if use_cache:
        cached = cache.get(digest)
        if cached is not None:
            row = _row_for_case(case_v1, cached, schema_valid=True, parse_failure=False)
            row.update({"status": "CACHED", "request_hash": digest, "cache_hit": True})
            return row
    try:
        response = validate_audit_response_v2(client.chat_json(v2_messages(case_v2)))
        cache.put(digest, response)
        row = _row_for_case(case_v1, response, schema_valid=True, parse_failure=False)
        row.update({"request_hash": digest, "cache_hit": False})
        return row
    except LLMParseFailure as exc:
        row = _row_for_case(case_v1, None, schema_valid=False, parse_failure=True)
        row.update({"request_hash": digest, "cache_hit": False, "reason_code": str(exc)})
        return row


