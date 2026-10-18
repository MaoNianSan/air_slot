from pathlib import Path

from model.common.identity import content_id
from model.PRE.adapters.data1 import Data1Adapter
from model.PRE.adapters.data2 import Data2Adapter
from model.PRE.adapters.validation import validate_adapter_interface
from model.PRE.feature_registry.loader import load_registry_bundle
from tests.fixtures.pre.foundation_cases import build_data1_case
from .dependency_rules import scan_dependency_boundaries, scan_prohibited_artifacts
from .reporting import ValidationFinding, ValidationRun


def _finding(check_id: str, status: str, message: str, path: str | None = None):
    return ValidationFinding(check_id=check_id, status=status, message=message, path=path)


def validate_contracts(root: Path) -> list[ValidationFinding]:
    bundle = load_registry_bundle(root / "registries")
    findings = [_finding("REGISTRY_INTEGRITY", "PASS", bundle.manifest.combined_sha256)]
    for raw in scan_dependency_boundaries(root) + scan_prohibited_artifacts(root):
        findings.append(_finding(raw["check_id"], raw["status"], raw["message"] or "boundary clean", raw["path"]))
    return findings


def validate_adapters(root: Path) -> list[ValidationFinding]:
    bundle = load_registry_bundle(root / "registries")
    registered = {rule.logical_source for rule in bundle.data_usage_rules}
    return [_finding("ADAPTER_INTERFACE", "PASS", str(validate_adapter_interface(adapter, registered)))
            for adapter in (Data1Adapter(), Data2Adapter())]


def validate_pre() -> tuple[list[ValidationFinding], object]:
    result = build_data1_case()
    state = result.pre_state
    complete = len(state.evidence_ledger) == len(state.variable_lineage) == 2
    findings = [_finding("PRE_FIXTURE", "PASS" if complete else "FAIL", state.decision_node.decision_node_id),
                _finding("FOUNDATION_VALIDATION_SCOPE", "PASS", "downstream algorithms are outside this fixture-only validation command")]
    return findings, result


def run_foundation(command: str, root: Path) -> tuple[ValidationRun, object | None]:
    findings: list[ValidationFinding] = []
    fixture = None
    if command in {"contracts", "all"}: findings.extend(validate_contracts(root))
    if command in {"adapters", "all"}: findings.extend(validate_adapters(root))
    if command in {"pre", "all"}:
        pre_findings, fixture = validate_pre(); findings.extend(pre_findings)
    run_id = content_id({"command": command, "findings": [f.model_dump(mode="json") for f in findings]})
    return ValidationRun(run_id=run_id, command=command, findings=tuple(findings)), fixture
