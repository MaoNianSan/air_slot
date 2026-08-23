"""Single source of truth for the current formal Development artifact binding.

Formal runners must bind the current M1 V2 scenario artifact and its upstream
model/schema/cohort/support plus the current M4 policy/design hashes.  Missing
or stale artifacts fail closed; no legacy V1 fallback is permitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from model.common.errors import ContractError


def _sha(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _load(path: Path) -> dict:
    if not path.is_file():
        raise ContractError(f"FROZEN_ARTIFACT_MISSING:{path.as_posix()}")
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class FrozenArtifactBinding:
    model_hash: str
    schema_hash: str
    cohort_hash: str
    scenario_hash: str
    support_hash: str
    m2_hash: str
    mapping_hash: str
    risk_policy_hash: str

    def as_dict(self) -> dict[str, str]:
        return {
            "model_hash": self.model_hash,
            "schema_hash": self.schema_hash,
            "cohort_hash": self.cohort_hash,
            "scenario_hash": self.scenario_hash,
            "support_hash": self.support_hash,
            "m2_hash": self.m2_hash,
            "mapping_hash": self.mapping_hash,
            "risk_policy_hash": self.risk_policy_hash,
        }


def load_current_development_binding(root: Path) -> FrozenArtifactBinding:
    root = Path(root).resolve()
    scenario_path = root / "artifacts/experiment/m1_v2_current_stage_scenarios_v4/M1_V2_CURRENT_STAGE_TYPED_JOINT_SCENARIOS.json"
    scenario_manifest_path = scenario_path.with_name("M1_V2_CURRENT_STAGE_TYPED_JOINT_SCENARIO_MANIFEST.json")
    cohort_path = root / "artifacts/experiment/exp2/DATA2_DEVELOPMENT_PILOT_COHORT_CURRENT_STAGE_V3.json"
    support_path = root / "artifacts/diagnostics/m1_v2_positive_tail_policy_freeze_v2/M1_V2_TARGET_SUPPORT_MANIFEST.json"
    m2_manifest_path = root / "artifacts/experiment/m2_v2_current_stage_consequences_v1/M2_V2_CURRENT_STAGE_TYPED_CONSEQUENCE_MANIFEST.json"
    m4_policy_path = root / "artifacts/experiment/exp2/DATA2_DEV_PILOT_M4_RISK_POLICY.json"
    m4_design_path = root / "registries/m4_v2_monetary_mapping_design.json"
    scenario = _load(scenario_path)
    scenario_manifest = _load(scenario_manifest_path)
    cohort = _load(cohort_path)
    support = _load(support_path)
    m2 = _load(m2_manifest_path)
    m4_policy = _load(m4_policy_path)
    if scenario_manifest.get("artifact_hash") != scenario.get("artifact_hash"):
        raise ContractError("FROZEN_SCENARIO_MANIFEST_HASH_MISMATCH")
    if scenario_manifest.get("status") != "M1_CURRENT_STAGE_JOINT_SCENARIO_ARTIFACT_MATERIALIZED":
        raise ContractError("FROZEN_SCENARIO_STATUS_INVALID")
    if scenario.get("scope") != "DATA2_DEVELOPMENT_CURRENT_STAGE_V3_NO_FINAL_TEST":
        raise ContractError("FROZEN_SCENARIO_SCOPE_INVALID")
    if scenario.get("cohort", {}).get("cohort_hash") != cohort.get("cohort_hash"):
        raise ContractError("FROZEN_COHORT_HASH_MISMATCH")
    if not str(scenario.get("feature_schema_hash", "")).startswith("sha256:"):
        raise ContractError("FROZEN_SCHEMA_HASH_MISSING")
    model_hash = scenario.get("checkpoint", {}).get("sha256")
    checkpoint_path = root / scenario.get("checkpoint", {}).get("path", "")
    if not model_hash or not checkpoint_path.is_file() or _sha(checkpoint_path) != model_hash:
        raise ContractError("FROZEN_MODEL_HASH_MISMATCH")
    support_hash = _sha(support_path)
    if scenario.get("support_hash") not in {support_hash, support.get("artifact_hash"), support.get("support_hash")}:
        raise ContractError("FROZEN_SUPPORT_HASH_MISMATCH")
    if m2.get("source_m1_artifact_hash") != scenario.get("artifact_hash"):
        raise ContractError("FROZEN_M2_SOURCE_HASH_MISMATCH")
    if m2.get("status") != "M2_V2_CONSEQUENCE_ARTIFACT_MATERIALIZED":
        raise ContractError("FROZEN_M2_STATUS_INVALID")
    for payload in (scenario_manifest, scenario, cohort, support, m2, m4_policy):
        safety = payload.get("safety", payload)
        if safety.get("FINAL_TEST_ACCESS_COUNT", payload.get("FINAL_TEST_ACCESS_COUNT")) != 0:
            raise ContractError("FROZEN_ARTIFACT_FINAL_TEST_ACCESS")
        if safety.get("PAPER_FULL_RUN", payload.get("PAPER_FULL_RUN")) is not False:
            raise ContractError("FROZEN_ARTIFACT_PAPER_FULL")
    if not m4_design_path.is_file():
        raise ContractError("FROZEN_M4_MAPPING_DESIGN_MISSING")
    return FrozenArtifactBinding(
        model_hash=model_hash,
        schema_hash=str(scenario["feature_schema_hash"]),
        cohort_hash=str(cohort["cohort_hash"]),
        scenario_hash=str(scenario["artifact_hash"]),
        support_hash=str(scenario.get("support_hash")),
        m2_hash=str(m2["artifact_hash"]),
        mapping_hash=_sha(m4_design_path),
        risk_policy_hash=str(m4_policy.get("artifact_hash")),
    )


__all__ = ["FrozenArtifactBinding", "load_current_development_binding"]
