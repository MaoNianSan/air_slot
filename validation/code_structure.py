"""Static repository structure audit used by the reconciliation report."""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from pathlib import Path


ROOTS = ("model", "exp", "validation")


def _modules(tree: ast.AST) -> tuple[str, ...]:
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.append(node.module)
    return tuple(sorted(set(result)))


def _responsibilities(path: Path, text: str, symbols: tuple[str, ...]) -> tuple[str, ...]:
    values = []
    lower = text.lower()
    if "pydantic" in lower or any(name.endswith(("Contract", "Request", "Result")) for name in symbols):
        values.append("contracts")
    if any(token in lower for token in ("read_text(", "write_text(", "read_csv", "open(")):
        values.append("io")
    if "yaml.safe_load" in lower or "load_config" in lower:
        values.append("config")
    if "registry" in lower:
        values.append("registry")
    if any(token in lower for token in ("transform", "canonical", "derive_", "map_")):
        values.append("scientific_transform")
    if any(token in lower for token in ("validate", "contracterror", "raise valueerror")):
        values.append("validation")
    if any(token in lower for token in ("json.dumps", "print(", "report", "manifest")):
        values.append("reporting")
    if "argparse" in lower or "def main" in lower:
        values.append("cli_orchestration")
    if any(token in lower for token in ("torch.", "nn.", "optimizer")):
        values.append("model_execution")
    if any(token in lower for token in ("scenario", "bootstrap", "metric")):
        values.append("evaluation_or_sampling")
    return tuple(dict.fromkeys(values)) or ("module_definition",)


def scan_code_structure(root: Path) -> list[dict]:
    records = []
    module_to_path = {}
    for top in ROOTS:
        for path in sorted((root / top).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(root).as_posix()
            module_to_path[rel[:-3].replace("/", ".")] = rel
    imported_by = defaultdict(set)
    parsed = {}
    for module, rel in module_to_path.items():
        path = root / rel
        text = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(text)
        imports = _modules(tree)
        parsed[rel] = (text, tree, imports)
        for imported in imports:
            if imported in module_to_path:
                imported_by[module_to_path[imported]].add(rel)
    for rel, (text, tree, imports) in sorted(parsed.items()):
        path = root / rel
        top_level = tuple(node.name for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)))
        public = tuple(name for name in top_level if not name.startswith("_"))
        internal = tuple(name for name in top_level if name.startswith("_"))
        responsibilities = _responsibilities(path, text, top_level)
        loc = len(text.splitlines())
        split_candidate = loc > 800 or (loc > 500 and len(responsibilities) >= 3) or (loc > 300 and len(responsibilities) >= 4)
        if loc > 800 or (loc > 500 and len(responsibilities) >= 4):
            status = "REFACTOR_REQUIRED"
        elif split_candidate:
            status = "REFACTOR_RECOMMENDED"
        else:
            status = "KEEP"
        risk = "HIGH" if status == "REFACTOR_REQUIRED" else "MEDIUM" if status == "REFACTOR_RECOMMENDED" else "LOW"
        records.append({
            "path": rel,
            "loc": loc,
            "size": path.stat().st_size,
            "symbols": top_level,
            "imports": imports,
            "imported_by": tuple(sorted(imported_by[rel])),
            "responsibilities": responsibilities,
            "public_api": public,
            "internal_helpers": internal,
            "side_effects": any(token in text for token in ("write_text(", "mkdir(", "print(")),
            "io_behavior": "READ_WRITE" if "write_text(" in text else "READ" if any(token in text for token in ("read_text(", "read_csv", "open(")) else "PURE_OR_IN_MEMORY",
            "config_access": "DIRECT" if "load_config" in text or "foundation.yaml" in text else "NONE",
            "registry_access": "DIRECT" if "load_registry" in text or "yaml.safe_load" in text else "NONE",
            "candidate_split": split_candidate,
            "risk": risk,
            "status": status,
        })
    return records


def render_markdown(records: list[dict]) -> str:
    counts = {status: sum(row["status"] == status for row in records)
              for status in ("KEEP", "REFACTOR_RECOMMENDED", "REFACTOR_REQUIRED")}
    lines = [
        "# Code Structure Audit",
        "",
        "Static snapshot of the current tree. The status combines size with responsibility count; it is not a mechanical LOC gate.",
        "",
        f"Files scanned: {len(records)}. KEEP: {counts['KEEP']}. REFACTOR_RECOMMENDED: {counts['REFACTOR_RECOMMENDED']}. REFACTOR_REQUIRED: {counts['REFACTOR_REQUIRED']}.",
        "",
        "| Path | LOC | Bytes | Top-level classes/functions | Imports | Imported by | Responsibilities | Public API | Internal helpers | Side effects / I/O | Config | Registry | Split | Risk | Status |",
        "| --- | ---: | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in records:
        def joined(values, limit=5):
            values = tuple(values)
            shown = values[:limit]
            suffix = f" +{len(values)-limit}" if len(values) > limit else ""
            return ", ".join(shown) + suffix if values else "-"
        lines.append(
            f"| `{row['path']}` | {row['loc']} | {row['size']} | {joined(row['symbols'])} | "
            f"{joined(row['imports'])} | {joined(row['imported_by'])} | {joined(row['responsibilities'])} | "
            f"{joined(row['public_api'])} | {joined(row['internal_helpers'])} | "
            f"{'YES' if row['side_effects'] else 'NO'} / {row['io_behavior']} | {row['config_access']} | "
            f"{row['registry_access']} | {'YES' if row['candidate_split'] else 'NO'} | {row['risk']} | {row['status']} |"
        )
    lines.extend(["", "## Priority findings", ""])
    findings = [row for row in records if row["status"] != "KEEP"]
    if findings:
        lines.extend(
            f"- `{row['path']}`: {row['status']} ({row['loc']} LOC; risk {row['risk']})."
            for row in findings
        )
    else:
        lines.append("- No current module crosses the responsibility-aware split gate.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_markdown(scan_code_structure(root)), encoding="utf-8")


if __name__ == "__main__":
    main()
