from collections import defaultdict
import json
import os
import time
from hashlib import sha256
from pathlib import Path as _Path
from typing import Any, Iterable, Mapping

import requests

from exp.common.rng import stream_generator
from model.common.errors import ContractError


ALLOWED_JUDGEMENTS = {"ACCEPT", "ACCEPT_WITH_RESERVATIONS", "REJECT", "INSUFFICIENT_INFORMATION"}
ALLOWED_CONFIDENCE = {"LOW", "MEDIUM", "HIGH"}
REQUIRED_SECTIONS = (
    "PLAUSIBLE_OPERATIONAL_OUTCOMES", "PRIMARY_MITIGATION", "EXECUTION_BURDENS",
    "RESOURCE_DEPENDENCIES", "DOWNSTREAM_EFFECTS", "TIMING_FEASIBILITY",
    "MISSING_CRITICAL_INFORMATION", "FINAL_JUDGEMENT", "CONFIDENCE",
)

CASE_STRATA = (
    "formal_non_null_top1",
    "formal_a00_top1",
    "relaxed_only_invalidated_top1",
    "scenario_conditional_close_call",
)


def select_audit_cases(cases, *, target_episodes=400, global_seed=0):
    """Development-frozen stratified selection, at most one node per episode."""
    by_stratum = defaultdict(dict)
    for case in cases:
        stratum = case.get("stratum")
        if stratum not in CASE_STRATA:
            continue
        by_stratum[stratum].setdefault(case["episode_id"], case)
    quota = max(1, target_episodes // len(CASE_STRATA))
    selected = []
    used_episodes = set()
    for stratum in CASE_STRATA:
        candidates = [case for episode, case in sorted(by_stratum[stratum].items())
                      if episode not in used_episodes]
        rng = stream_generator("llm_case_selection", global_seed, stratum)
        order = rng.permutation(len(candidates)) if candidates else ()
        for index in order[:quota]:
            case = candidates[int(index)]
            selected.append(case)
            used_episodes.add(case["episode_id"])
    return tuple(selected)


def validate_audit_response(response):
    if not isinstance(response, dict) or any(name not in response for name in REQUIRED_SECTIONS):
        raise ValueError("DEEPSEEK_AUDIT_SCHEMA_INVALID")
    if response["FINAL_JUDGEMENT"] not in ALLOWED_JUDGEMENTS:
        raise ValueError("DEEPSEEK_AUDIT_JUDGEMENT_INVALID")
    if response["CONFIDENCE"] not in ALLOWED_CONFIDENCE:
        raise ValueError("DEEPSEEK_AUDIT_CONFIDENCE_INVALID")
    return response


def audit_cases(cases,provider=None,protocol="BLINDED_CHOICE"):
    if provider is None:return tuple({"case_id":case["case_id"],"protocol":protocol,"status":"NOT_RUN","reason_code":"LLM_PROVIDER_NOT_CONFIGURED"} for case in cases)
    results=[]
    for case in cases:
        response=validate_audit_response(provider.audit(case,protocol=protocol))
        results.append({"case_id":case["case_id"],"protocol":protocol,"status":"COMPLETED","response":response,"artifact_layer":"EVALUATION"})
    return tuple(results)


# =====================================================================
# V2 protocol: DeepSeek-only, cost-first model selection with quality
# gate, request-hash cache, pilot -> principal -> repeat-stability.
# =====================================================================

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_ENV_KEY_NAME = "DEEPSEEK_API_KEY"
MODEL_SELECTION_RULE = "COST_FIRST_WITH_QUALITY_GATE"

V2_VERDICTS = ("REASONABLE", "QUESTIONABLE", "UNREASONABLE", "INSUFFICIENT_INFORMATION")
V2_CONFIDENCE = ("LOW", "MEDIUM", "HIGH")
V2_SCHEMA_VERSION = "DEEPSEEK_AUDIT_RESPONSE_V2"
V2_PROTOCOL = "BLINDED_CHOICE_V2"
AUDIT_RUBRIC_VERSION = "AIR_SLOT_DEVELOPMENT_AUDIT_RUBRIC_V1"

# Documented DeepSeek API identifiers only; V4-Flash is used only if the
# account actually exposes it (discovered at runtime).
DOCUMENTED_MODEL_FALLBACK = ("deepseek-chat", "deepseek-reasoner")

PILOT_SCHEMA_PASS_RATE_MIN = 0.98
PILOT_UNRECOVERABLE_PARSE_FAILURE_MAX = 0.02
PILOT_PREREQUISITE_LOGIC_FAILURE_MAX = 0.05
PILOT_HALLUCINATION_MAX = 0

N_PILOT_DEFAULT = 50
N_PRINCIPAL_DEFAULT = 1200
REPEAT_FRACTION_DEFAULT = 0.10
MAX_LLM_CALLS_DEFAULT = 1500


class LLMApiKeyNotConfigured(ContractError):
    pass


class LLMModelEscalationExhausted(ContractError):
    pass


class LLMParseFailure(ContractError):
    pass


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def validate_audit_response_v2(response):
    if not isinstance(response, dict):
        raise ValueError("DEEPSEEK_AUDIT_V2_SCHEMA_INVALID")
    required = ("verdict", "justification", "prerequisite_logic_ok",
                "hallucinated_unsupported_numeric_effects",
                "missing_critical_information", "confidence")
    if any(name not in response for name in required):
        raise ValueError("DEEPSEEK_AUDIT_V2_SCHEMA_INVALID")
    if response["verdict"] not in V2_VERDICTS:
        raise ValueError("DEEPSEEK_AUDIT_V2_VERDICT_INVALID")
    if response["confidence"] not in V2_CONFIDENCE:
        raise ValueError("DEEPSEEK_AUDIT_V2_CONFIDENCE_INVALID")
    if not isinstance(response["justification"], str) or not response["justification"].strip():
        raise ValueError("DEEPSEEK_AUDIT_V2_JUSTIFICATION_EMPTY")
    if not isinstance(response["prerequisite_logic_ok"], bool):
        raise ValueError("DEEPSEEK_AUDIT_V2_PREREQUISITE_LOGIC_NOT_BOOL")
    if not isinstance(response["hallucinated_unsupported_numeric_effects"], bool):
        raise ValueError("DEEPSEEK_AUDIT_V2_HALLUCINATION_NOT_BOOL")
    if not isinstance(response["missing_critical_information"], list):
        raise ValueError("DEEPSEEK_AUDIT_V2_MISSING_INFO_NOT_LIST")
    return response


def audit_request_payload(case: Mapping[str, Any], *, protocol: str = V2_PROTOCOL,
                          model: str | None = None) -> dict:
    return {
        "schema_version": V2_SCHEMA_VERSION,
        "protocol": protocol,
        "rubric_version": AUDIT_RUBRIC_VERSION,
        "model": model,
        "case": dict(case),
    }


def request_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


class AuditCache:
    """Request-hash cache with atomic writes; never stores API keys."""

    def __init__(self, cache_dir: _Path):
        self.cache_dir = _Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, digest: str) -> _Path:
        if not digest.startswith("sha256:") or len(digest) != 71:
            raise ContractError("LLM_AUDIT_CACHE_HASH_INVALID")
        return self.cache_dir / f"{digest[7:]}.json"

    def get(self, digest: str):
        path = self.path_for(digest)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("response")

    def put(self, digest: str, response: Mapping[str, Any]) -> _Path:
        path = self.path_for(digest)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"request_hash": digest, "response": dict(response)},
                       indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(path)
        return path


def _system_prompt() -> str:
    return (
        "You are auditing an airline disruption decision case under a strict "
        "scientific contract. The principal Data1/Data2 environment has NO "
        "identified historical non-null action-attempt/outcome log: "
        "scenario-defined action response != empirical action response, and "
        "numerically evaluable action != FORMAL action. Judge only whether the "
        "case presentation is scientifically reasonable given this contract. "
        "Never invent numeric effects that the case does not claim. If "
        "prerequisite information is missing, say so. Respond ONLY with a JSON "
        "object matching this exact schema: "
        '{"verdict": "REASONABLE"|"QUESTIONABLE"|"UNREASONABLE"|"INSUFFICIENT_INFORMATION", '
        '"justification": "<short reasoning>", '
        '"prerequisite_logic_ok": true|false, '
        '"hallucinated_unsupported_numeric_effects": true|false, '
        '"missing_critical_information": ["<item>", ...], '
        '"confidence": "LOW"|"MEDIUM"|"HIGH"}'
    )


def _user_prompt(case: Mapping[str, Any], protocol: str) -> str:
    return (
        f"Protocol: {protocol}\n"
        f"Case JSON:\n{json.dumps(case, sort_keys=True, ensure_ascii=False, indent=2)}"
    )


class DeepSeekAuditClient:
    """DeepSeek-only chat client. The API key is read exclusively from the
    DEEPSEEK_API_KEY environment variable and is never written to logs,
    artifacts, manifests, or git."""

    def __init__(self, *, api_key: str | None = None, base_url: str = DEEPSEEK_BASE_URL,
                 model: str | None = None, timeout: int = 90, max_retries: int = 4):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.api_key = api_key if api_key is not None else os.environ.get(DEEPSEEK_ENV_KEY_NAME, "")
        if not self.api_key:
            raise LLMApiKeyNotConfigured("LLM_API_KEY_NOT_CONFIGURED")
        try:
            self.available_models = self.discover_models()
        except Exception as exc:
            raise LLMModelEscalationExhausted(
                f"DEEPSEEK_MODEL_DISCOVERY_FAILED:{exc}"
            ) from exc
        if not self.available_models:
            raise LLMModelEscalationExhausted("DEEPSEEK_MODEL_DISCOVERY_EMPTY")
        self.model = model or model_preference_order(self.available_models)[0]
        self._calls = 0

    def discover_models(self) -> tuple[str, ...]:
        response = requests.get(
            f"{self.base_url}/models",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        models = tuple(
            item["id"] for item in data.get("data", ())
            if isinstance(item, dict) and item.get("id")
        )
        return models or DOCUMENTED_MODEL_FALLBACK

    def set_model(self, model_id: str) -> None:
        self.model = model_id

    def chat_json(self, messages: list[dict]) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                    timeout=self.timeout,
                )
                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = f"HTTP_{response.status_code}"
                    time.sleep(min(2 ** attempt, 30))
                    continue
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                self._calls += 1
                return json.loads(_strip_code_fences(content))
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                self._calls += 1
                raise LLMParseFailure(f"DEEPSEEK_UNRECOVERABLE_PARSE_FAILURE:{exc}") from exc
            except requests.RequestException as exc:
                last_error = str(exc)
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(min(2 ** attempt, 30))
        raise ContractError(f"DEEPSEEK_API_CALL_FAILED:{last_error}")

    def audit_case(self, case: Mapping[str, Any], protocol: str = V2_PROTOCOL) -> dict:
        messages = [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _user_prompt(case, protocol)},
        ]
        return validate_audit_response_v2(self.chat_json(messages))


def model_preference_order(available: Iterable[str]) -> tuple[str, ...]:
    """Cost-first preference: flash-tagged ids first, then chat, then others.

    Only identifiers the account actually exposes are considered.
    """
    models = tuple(dict.fromkeys(available))
    flash = [name for name in models if "flash" in name.lower()]
    chat = [name for name in models if "flash" not in name.lower() and "chat" in name.lower()]
    rest = [name for name in models if name not in flash and name not in chat]
    return tuple(flash + chat + rest)


def evaluate_pilot_gates(results: Iterable[Mapping[str, Any]]) -> dict:
    rows = list(results)
    total = len(rows)
    schema_ok = sum(bool(row.get("schema_valid")) for row in rows)
    parse_failures = sum(bool(row.get("unrecoverable_parse_failure")) for row in rows)
    prereq_failures = sum(
        bool(row.get("response", {}).get("prerequisite_logic_ok") is False)
        for row in rows
    )
    hallucinations = sum(
        bool(row.get("response", {}).get("hallucinated_unsupported_numeric_effects"))
        for row in rows
    )
    schema_pass_rate = (schema_ok / total) if total else 0.0
    unrecoverable_parse_failure_rate = (parse_failures / total) if total else 0.0
    prereq_failure_rate = (prereq_failures / total) if total else 0.0
    hallucination_rate = (hallucinations / total) if total else 0.0
    passed = (
        total > 0
        and schema_pass_rate >= PILOT_SCHEMA_PASS_RATE_MIN
        and unrecoverable_parse_failure_rate <= PILOT_UNRECOVERABLE_PARSE_FAILURE_MAX
        and prereq_failure_rate <= PILOT_PREREQUISITE_LOGIC_FAILURE_MAX
        and hallucination_rate <= PILOT_HALLUCINATION_MAX
    )
    return {
        "pilot_n": total,
        "schema_valid_n": schema_ok,
        "unrecoverable_parse_failure_n": parse_failures,
        "prerequisite_logic_failure_n": prereq_failures,
        "hallucination_n": hallucinations,
        "schema_pass_rate": schema_pass_rate,
        "unrecoverable_parse_failure_rate": unrecoverable_parse_failure_rate,
        "prerequisite_logic_failure_rate": prereq_failure_rate,
        "hallucination_rate": hallucination_rate,
        "gates_passed": passed,
    }


def _run_case(client, cache: AuditCache, case, protocol: str, *, use_cache: bool = True) -> dict:
    payload = audit_request_payload(case, protocol=protocol, model=client.model)
    digest = request_hash(payload)
    if use_cache:
        cached = cache.get(digest)
        if cached is not None:
            return {"case_id": case["case_id"], "request_hash": digest, "status": "CACHED",
                    "response": cached, "schema_valid": True, "unrecoverable_parse_failure": False,
                    "cache_hit": True}
    try:
        response = client.audit_case(case, protocol=protocol)
        cache.put(digest, response)
        return {"case_id": case["case_id"], "request_hash": digest, "status": "COMPLETED",
                "response": response, "schema_valid": True,
                "unrecoverable_parse_failure": False, "cache_hit": False}
    except LLMParseFailure as exc:
        return {"case_id": case["case_id"], "request_hash": digest, "status": "PARSE_FAILURE",
                "response": None, "schema_valid": False,
                "unrecoverable_parse_failure": True, "reason_code": str(exc), "cache_hit": False}


def _checkpoint_path(artifact_dir: _Path) -> _Path:
    return _Path(artifact_dir) / "checkpoint.json"


def _write_checkpoint(artifact_dir: _Path, payload: Mapping[str, Any]) -> None:
    path = _checkpoint_path(artifact_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _load_checkpoint(artifact_dir: _Path) -> dict | None:
    path = _checkpoint_path(artifact_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def run_llm_audit(
    cases,
    *,
    artifact_dir,
    client=None,
    n_pilot=N_PILOT_DEFAULT,
    n_principal=N_PRINCIPAL_DEFAULT,
    repeat_fraction=REPEAT_FRACTION_DEFAULT,
    max_llm_calls=MAX_LLM_CALLS_DEFAULT,
    global_seed=0,
):
    """Pilot -> frozen-model principal -> repeat-stability, resumable.

    client may be a DeepSeekAuditClient or any object exposing set_model /
    audit_case / model; None attempts to construct one from the environment
    and yields a BLOCKED report when DEEPSEEK_API_KEY is not configured.
    """
    artifact_dir = _Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    report_path = artifact_dir / "DEEPSEEK_LLM_AUDIT_REPORT.json"
    if client is None:
        try:
            client = DeepSeekAuditClient()
        except LLMApiKeyNotConfigured:
            blocked = {
                "status": "BLOCKED",
                "reason_code": "LLM_API_KEY_NOT_CONFIGURED",
                "deepseek_env_key_name": DEEPSEEK_ENV_KEY_NAME,
                "model_selection_rule": MODEL_SELECTION_RULE,
                "n_pilot": n_pilot,
                "n_principal": n_principal,
                "repeat_fraction": repeat_fraction,
                "max_llm_calls": max_llm_calls,
                "calls_used": 0,
                "final_test_access_count": 0,
                "paper_full_run": False,
            }
            report_path.write_text(json.dumps(blocked, indent=2, sort_keys=True), encoding="utf-8")
            return blocked

    checkpoint = _load_checkpoint(artifact_dir) or {}
    pilot_model = checkpoint.get("pilot_model") or client.model
    if checkpoint.get("pilot_model"):
        client.set_model(checkpoint["pilot_model"])
    cache = AuditCache(artifact_dir / "cache")

    ordered = select_audit_cases(cases, target_episodes=n_pilot + n_principal, global_seed=global_seed)
    if len(ordered) < n_pilot:
        ordered = select_audit_cases(cases, target_episodes=n_principal, global_seed=global_seed)
    if len(ordered) < min(n_pilot, len(cases)):
        ordered = tuple(sorted(cases, key=lambda item: str(item.get("case_id", ""))))

    pilot_cases = ordered[:n_pilot]
    principal_cases = ordered[n_pilot:n_pilot + n_principal]

    selected_models = model_preference_order(getattr(client, "available_models", ()) or ())
    if client.model not in selected_models:
        selected_models = (client.model,) + tuple(
            name for name in selected_models if name != client.model
        )
    escalation_reason = ""
    escalation_occurred = False
    frozen_model = ""
    pilot_result = None

    for model_index, model_id in enumerate(selected_models):
        client.set_model(model_id)
        pilot_rows = [_run_case(client, cache, case, V2_PROTOCOL) for case in pilot_cases]
        pilot_result = evaluate_pilot_gates(pilot_rows)
        if pilot_result["gates_passed"]:
            frozen_model = model_id
            if model_index > 0:
                escalation_occurred = True
                escalation_reason = f"PILOT_GATE_FAILURE_ON_PRIOR_MODEL:{selected_models[0]}"
            break
        escalation_reason = (
            f"PILOT_GATE_FAILURE_ON_MODEL:{model_id}:"
            f"schema={pilot_result['schema_pass_rate']:.3f}"
            f" parse={pilot_result['unrecoverable_parse_failure_rate']:.3f}"
            f" prereq={pilot_result['prerequisite_logic_failure_rate']:.3f}"
            f" halluc={pilot_result['hallucination_rate']:.3f}"
        )
        pilot_model = model_id
        _write_checkpoint(artifact_dir, {
            "phase": "PILOT_ESCALATED", "pilot_model": model_id,
            "selected_models": list(selected_models), "global_seed": global_seed,
        })
    if not frozen_model:
        raise LLMModelEscalationExhausted("DEEPSEEK_PILOT_NO_MODEL_PASSED")

    client.set_model(frozen_model)
    principal_rows = []
    calls_used = sum(1 for row in pilot_rows if not row.get("cache_hit"))
    for case in principal_cases:
        if calls_used >= max_llm_calls:
            break
        row = _run_case(client, cache, case, V2_PROTOCOL)
        principal_rows.append(row)
        if not row.get("cache_hit"):
            calls_used += 1
    principal_completed = [row for row in principal_rows
                           if row.get("status") in {"COMPLETED", "CACHED"}]
    completed_indices = [index for index, row in enumerate(principal_rows)
                         if row.get("status") in {"COMPLETED", "CACHED"}]

    repeat_rng = stream_generator("llm_repetition", global_seed, frozen_model)
    repeat_count = min(max(1, int(round(len(completed_indices) * repeat_fraction))),
                       len(completed_indices))
    repeat_indices = set(int(index) for index in repeat_rng.choice(
        len(completed_indices), size=repeat_count, replace=False)) if repeat_count else set()
    repeat_rows = []
    stable_pairs = []
    for position in sorted(repeat_indices):
        index = completed_indices[position]
        case = principal_cases[index]
        if calls_used >= max_llm_calls:
            break
        # Repeat-stability requires a fresh verdict from the frozen model:
        # the cache must be bypassed so a true second opinion is produced.
        row = _run_case(client, cache, case, V2_PROTOCOL, use_cache=False)
        repeat_rows.append(row)
        if not row.get("cache_hit"):
            calls_used += 1
        first = principal_rows[index].get("response", {}).get("verdict")
        second = row.get("response", {}).get("verdict") if row.get("status") == "COMPLETED" else None
        if first and second:
            stable_pairs.append(first == second)

    stability = (sum(stable_pairs) / len(stable_pairs)) if stable_pairs else None

    report = {
        "status": "COMPLETED",
        "model_selection_rule": MODEL_SELECTION_RULE,
        "deepseek_model_id": frozen_model,
        "pilot_model": pilot_model,
        "pilot_schema_pass_rate": pilot_result["schema_pass_rate"],
        "pilot_gates": pilot_result,
        "model_escalation_occurred": escalation_occurred,
        "model_escalation_reason": escalation_reason,
        "n_pilot": len(pilot_cases),
        "n_principal_requested": len(principal_cases),
        "n_principal_completed": len(principal_completed),
        "n_repeat_stability": len(stable_pairs),
        "verdict_stability_agreement_rate": stability,
        "max_llm_calls": max_llm_calls,
        "calls_used": calls_used,
        "verdict_counts": {
            verdict: sum(1 for row in pilot_rows + principal_completed
                         if row.get("response", {}).get("verdict") == verdict)
            for verdict in V2_VERDICTS
        },
        "principal_results": [dict(row) for row in principal_rows],
        "pilot_results": [dict(row) for row in pilot_rows],
        "repeat_stability_results": [dict(row) for row in repeat_rows],
        "final_test_access_count": 0,
        "paper_full_run": False,
    }
    _write_checkpoint(artifact_dir, {
        "phase": "COMPLETED", "frozen_model": frozen_model,
        "selected_models": list(selected_models), "global_seed": global_seed,
    })
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
