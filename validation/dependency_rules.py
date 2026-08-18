import ast
from pathlib import Path


# Approved scientific-status field usages (user-approved registry contracts).
APPROVED_STATUS_SCHEMA_PAIRS = {
    "model/M3/response_registry.py": 'scientific_status: str = "HUMAN_APPROVED_SCENARIO_SPECIFICATION"',
    "registries/m3_response_scenarios.yaml": "scientific_status: HUMAN_APPROVED_SCENARIO_SPECIFICATION",
}
# The rule definition file itself necessarily contains the token.
STATUS_SCHEMA_RULE_SOURCE = "validation/dependency_rules.py"


def scan_dependency_boundaries(root: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in {".specify", "specs", "outputs"} for part in path.parts):
            continue
        try: tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError): continue
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): modules += [x.name for x in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module: modules.append(node.module)
        rel = path.relative_to(root).as_posix()
        bad = []
        if rel.startswith("model/") and any(m == "exp" or m.startswith("exp.") for m in modules): bad.append("MODEL_IMPORTS_EXP")
        if rel.startswith("model/") and any(m == "validation" or m.startswith("validation.") for m in modules): bad.append("MODEL_IMPORTS_VALIDATION")
        if rel.startswith("model/") and any(m == "exp.reporting" or m.startswith("exp.reporting.") for m in modules): bad.append("MODEL_IMPORTS_REPORTING")
        if rel.startswith("model/PRE/") and any(m.startswith("model.M") for m in modules): bad.append("PRE_IMPORTS_DOWNSTREAM")
        if rel.startswith("model/M1/") and any(m.startswith("model.PRE.adapters") or m.startswith("model.PRE.realized") for m in modules): bad.append("M1_IMPORTS_RAW_OR_REALIZED")
        if rel.startswith("model/M2/") and any(m.startswith("model.PRE.adapters") or m.startswith("model.PRE.realized") for m in modules): bad.append("M2_IMPORTS_RAW_OR_REALIZED")
        if rel.startswith("model/M3/") and any(m.startswith("model.M2") or m.startswith("model.PRE.adapters") for m in modules): bad.append("M3_IMPORTS_FORBIDDEN_SOURCE")
        if rel.startswith("model/M4/") and any(m.startswith("model.PRE.adapters") or m.startswith("model.PRE.realized") or m == "exp" or m.startswith("exp.") for m in modules): bad.append("M4_IMPORTS_FORBIDDEN_SOURCE")
        if rel.startswith("model/M1/"):
            source = path.read_text(encoding="utf-8")
            if "dataset ==" in source or "dataset_instance_id ==" in source:
                bad.append("M1_DATASET_SPECIFIC_BRANCH")
        findings.append({"check_id": "DEPENDENCY_BOUNDARY", "status": "FAIL" if bad else "PASS",
                         "path": rel, "message": ",".join(bad)})
    return findings


def scan_prohibited_artifacts(root: Path) -> list[dict[str, str]]:
    """Audit implementation/config artifacts without interpreting negative tests as violations."""
    findings: list[dict[str, str]] = []
    roots = [root / "model", root / "validation", root / "configs", root / "registries",
             root / "metadata"]
    forbidden = {"LEGACY_GITHUB_IMPORT": "git" + "hub.com/", "MACHINE_PATH": "D:" + "\\research\\",
                 "VENV_BOOTSTRAP": "python -m " + "venv",
                 "UNAPPROVED_STATUS_SCHEMA": "scientific_" + "status"}
    for base in roots:
        if not base.exists():
            continue
        for path in sorted(p for p in base.rglob("*") if p.suffix in {".py", ".yaml", ".yml"}):
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(root).as_posix()
            bad = []
            for code, token in forbidden.items():
                if token.lower() not in text.lower():
                    continue
                if code == "UNAPPROVED_STATUS_SCHEMA":
                    if rel == STATUS_SCHEMA_RULE_SOURCE:
                        continue
                    if rel in APPROVED_STATUS_SCHEMA_PAIRS:
                        if APPROVED_STATUS_SCHEMA_PAIRS[rel] in text:
                            continue
                bad.append(code)
            findings.append({"check_id": "PROHIBITED_ARTIFACT", "status": "FAIL" if bad else "PASS",
                "path": rel, "message": ",".join(bad)})
    return findings
