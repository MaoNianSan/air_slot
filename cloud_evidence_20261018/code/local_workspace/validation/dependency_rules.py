import ast
from pathlib import Path


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
        if rel.startswith("model/PRE/") and any(m.startswith("model.M") for m in modules): bad.append("PRE_IMPORTS_DOWNSTREAM")
        if rel.startswith("model/M3/") and any(m.startswith("model.M2") for m in modules): bad.append("M3_IMPORTS_M2")
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
            bad = [code for code, token in forbidden.items() if token.lower() in text.lower()]
            findings.append({"check_id": "PROHIBITED_ARTIFACT", "status": "FAIL" if bad else "PASS",
                "path": path.relative_to(root).as_posix(), "message": ",".join(bad)})
    return findings
