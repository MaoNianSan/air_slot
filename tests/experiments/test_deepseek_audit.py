"""Offline focused tests for the DeepSeek LLM audit protocol (V2).

No network calls and no API key are required: clients are fakes. The
tests cover cost-first model preference, pilot gates, escalation,
cache/budget/resume, and the BLOCKED no-key path.
"""

import json

import pytest

from exp.exp3.llm_audit import (
    V2_VERDICTS,
    LLMApiKeyNotConfigured,
    LLMModelEscalationExhausted,
    AuditCache,
    DeepSeekAuditClient,
    evaluate_pilot_gates,
    model_preference_order,
    request_hash,
    run_llm_audit,
    validate_audit_response_v2,
)


class FakeClient:
    """Deterministic offline stand-in for DeepSeekAuditClient."""

    def __init__(self, models, *, verdict="REASONABLE", bad_models=(), parse_fail_models=()):
        self.available_models = list(models)
        self.model = models[0]
        self.verdict = verdict
        self.bad_models = set(bad_models)
        self.parse_fail_models = set(parse_fail_models)

    def set_model(self, model_id):
        self.model = model_id

    def audit_case(self, case, protocol="BLINDED_CHOICE_V2"):
        if self.model in self.parse_fail_models:
            from exp.exp3.llm_audit import LLMParseFailure
            raise LLMParseFailure("DEEPSEEK_UNRECOVERABLE_PARSE_FAILURE:test")
        if self.model in self.bad_models:
            return {
                "verdict": "UNREASONABLE",
                "justification": "hallucinated effect",
                "prerequisite_logic_ok": True,
                "hallucinated_unsupported_numeric_effects": True,
                "missing_critical_information": [],
                "confidence": "HIGH",
            }
        return {
            "verdict": self.verdict,
            "justification": "scientifically reasonable under the contract",
            "prerequisite_logic_ok": True,
            "hallucinated_unsupported_numeric_effects": False,
            "missing_critical_information": [],
            "confidence": "MEDIUM",
        }


def make_cases(n_per_stratum=8):
    strata = (
        "formal_non_null_top1", "formal_a00_top1",
        "relaxed_only_invalidated_top1", "scenario_conditional_close_call",
    )
    cases = []
    index = 0
    for stratum in strata:
        for offset in range(n_per_stratum):
            cases.append({
                "case_id": f"case-{index:03d}",
                "episode_id": f"episode-{index:03d}",
                "stratum": stratum,
                "decision_node_id": f"node-{index:03d}",
            })
            index += 1
    return cases


def test_model_preference_order_is_cost_first():
    order = model_preference_order([
        "deepseek-reasoner", "deepseek-chat", "deepseek-v4-flash", "deepseek-chat",
    ])
    assert order == ("deepseek-v4-flash", "deepseek-chat", "deepseek-reasoner")
    assert len(order) == 3


def test_validate_response_v2_rejects_bad_schema():
    with pytest.raises(ValueError, match="DEEPSEEK_AUDIT_V2_VERDICT_INVALID"):
        validate_audit_response_v2({
            "verdict": "ACCEPT", "justification": "x",
            "prerequisite_logic_ok": True,
            "hallucinated_unsupported_numeric_effects": False,
            "missing_critical_information": [], "confidence": "MEDIUM",
        })
    with pytest.raises(ValueError, match="DEEPSEEK_AUDIT_V2_SCHEMA_INVALID"):
        validate_audit_response_v2({"verdict": "REASONABLE"})
    good = validate_audit_response_v2({
        "verdict": "QUESTIONABLE", "justification": "x",
        "prerequisite_logic_ok": True,
        "hallucinated_unsupported_numeric_effects": False,
        "missing_critical_information": [], "confidence": "LOW",
    })
    assert good["verdict"] == "QUESTIONABLE"


def test_request_hash_is_deterministic():
    payload = {"schema_version": "DEEPSEEK_AUDIT_RESPONSE_V2", "case": {"a": 1}}
    assert request_hash(payload) == request_hash(payload)
    assert request_hash(payload) != request_hash({**payload, "case": {"a": 2}})


def test_pilot_gates_pass_and_fail_closed():
    good = [{"schema_valid": True, "unrecoverable_parse_failure": False,
             "response": {"prerequisite_logic_ok": True,
                          "hallucinated_unsupported_numeric_effects": False}}
            for _ in range(50)]
    assert evaluate_pilot_gates(good)["gates_passed"] is True
    hallucinated = list(good)
    hallucinated[0]["response"]["hallucinated_unsupported_numeric_effects"] = True
    assert evaluate_pilot_gates(hallucinated)["gates_passed"] is False
    parse_bad = list(good)
    parse_bad[0]["unrecoverable_parse_failure"] = True
    parse_bad[0]["schema_valid"] = False
    assert evaluate_pilot_gates(parse_bad)["gates_passed"] is False


def test_run_llm_audit_completes_pilot_principal_and_stability(tmp_path):
    client = FakeClient(["deepseek-chat"])
    report = run_llm_audit(
        make_cases(), artifact_dir=tmp_path / "audit", client=client,
        n_pilot=5, n_principal=20, repeat_fraction=0.1, max_llm_calls=100,
    )
    assert report["status"] == "COMPLETED"
    assert report["deepseek_model_id"] == "deepseek-chat"
    assert report["model_selection_rule"] == "COST_FIRST_WITH_QUALITY_GATE"
    assert report["pilot_schema_pass_rate"] == 1.0
    assert report["model_escalation_occurred"] is False
    assert report["n_principal_completed"] == report["n_principal_requested"]
    assert report["verdict_stability_agreement_rate"] == 1.0
    assert report["final_test_access_count"] == 0
    assert report["paper_full_run"] is False
    assert (tmp_path / "audit" / "DEEPSEEK_LLM_AUDIT_REPORT.json").exists()


def test_escalation_after_pilot_gate_failure(tmp_path):
    client = FakeClient(
        ["deepseek-chat", "deepseek-reasoner"], bad_models={"deepseek-chat"}
    )
    report = run_llm_audit(
        make_cases(), artifact_dir=tmp_path / "audit", client=client,
        n_pilot=5, n_principal=20, repeat_fraction=0.1, max_llm_calls=100,
    )
    assert report["status"] == "COMPLETED"
    assert report["deepseek_model_id"] == "deepseek-reasoner"
    assert report["model_escalation_occurred"] is True
    assert "deepseek-chat" in report["model_escalation_reason"]


def test_all_models_fail_pilot_is_exhausted(tmp_path):
    client = FakeClient(
        ["deepseek-chat", "deepseek-reasoner"], bad_models={"deepseek-chat", "deepseek-reasoner"}
    )
    with pytest.raises(LLMModelEscalationExhausted, match="DEEPSEEK_PILOT_NO_MODEL_PASSED"):
        run_llm_audit(
            make_cases(), artifact_dir=tmp_path / "audit", client=client,
            n_pilot=5, n_principal=20, repeat_fraction=0.1, max_llm_calls=100,
        )


def test_cache_reuse_drops_calls_to_zero(tmp_path):
    cases = make_cases()
    artifact_dir = tmp_path / "audit"
    first = run_llm_audit(
        cases, artifact_dir=artifact_dir, client=FakeClient(["deepseek-chat"]),
        n_pilot=5, n_principal=20, repeat_fraction=0.1, max_llm_calls=100,
    )
    assert first["calls_used"] > 0
    second = run_llm_audit(
        cases, artifact_dir=artifact_dir, client=FakeClient(["deepseek-chat"]),
        n_pilot=5, n_principal=20, repeat_fraction=0.1, max_llm_calls=100,
    )
    # pilot + principal are served from cache; only the fresh repeat-stability
    # verdicts (10% of the principal cohort) require new calls
    assert second["calls_used"] == 2
    assert second["n_principal_completed"] == first["n_principal_completed"]


def test_budget_caps_principal_calls(tmp_path):
    client = FakeClient(["deepseek-chat"])
    report = run_llm_audit(
        make_cases(), artifact_dir=tmp_path / "audit", client=client,
        n_pilot=5, n_principal=200, repeat_fraction=0.0, max_llm_calls=7,
    )
    assert report["calls_used"] <= 7
    assert report["n_principal_completed"] < 200


def test_no_api_key_returns_blocked_report(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    report = run_llm_audit(
        make_cases(), artifact_dir=tmp_path / "audit", client=None,
        n_pilot=5, n_principal=20,
    )
    assert report["status"] == "BLOCKED"
    assert report["reason_code"] == "LLM_API_KEY_NOT_CONFIGURED"
    assert report["final_test_access_count"] == 0
    assert report["paper_full_run"] is False


def test_cache_round_trip_and_unknown_hash_rejected(tmp_path):
    cache = AuditCache(tmp_path / "cache")
    digest = request_hash({"case": {"x": 1}})
    assert cache.get(digest) is None
    cache.put(digest, {"verdict": "REASONABLE"})
    assert cache.get(digest)["verdict"] == "REASONABLE"
    with pytest.raises(Exception, match="LLM_AUDIT_CACHE_HASH_INVALID"):
        cache.path_for("not-a-hash")


def test_client_requires_env_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(LLMApiKeyNotConfigured, match="LLM_API_KEY_NOT_CONFIGURED"):
        DeepSeekAuditClient()
