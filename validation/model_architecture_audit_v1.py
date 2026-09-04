"""Read-only inventory and ownership audit for the model refactor.

The audit intentionally performs no imports of project modules and no file
moves.  It records static evidence so the subsequent refactor can be reviewed
against a frozen pre-refactor picture.
"""

from __future__ import annotations

import ast
import csv
import importlib.util
import json
import re
from collections import defaultdict
from pathlib import Path

from model.common.paths import PROJECT_ROOT


ROOTS = ("model", "registries", "configs", "validation", "tests", "formal")
OUT = PROJECT_ROOT / "reports/model_refactor"
MODEL_LAYERS = ("common", "PRE", "M1", "M2", "M3", "M4")
ALLOWED_LAYER_DEPENDENCIES = {
    "common": {"common"},
    "PRE": {"common", "PRE"},
    "M1": {"common", "PRE", "M1"},
    "M2": {"common", "PRE", "M1", "M2"},
    "M3": {"common", "PRE", "M1", "M2", "M3"},
    "M4": {"common", "M3", "M4"},
}
TARGET_SYMBOLS = {
    "EvidenceClass",
    "SupportState",
    "SourceType",
    "ReasonCode",
    "ScenarioState",
    "ScenarioSupport",
    "Lineage",
    "ComponentName",
    "NumericalEvaluationState",
    "RiskEvaluationSupport",
    "ActionInstantiationRecord",
    "M1V2Scenario",
    "AlignedScenario",
    "ConsequenceComparisonScope",
}
LEGACY_TOKENS = (
    "V1",
    "V2",
    "V3",
    "legacy",
    "deprecated",
    "compat",
    "superseded",
    "old_",
    "historical",
    "exp1",
    "exp2",
    "exp3",
    "exp4",
    "paper",
    "section5",
    "final_test",
    "paper_result",
    "ranking_at_k",
)
CONCEPT_TOKENS = {
    "EvidenceClass": r"EvidenceClass",
    "SupportState": r"SupportState",
    "ReasonCode": r"ReasonCode|reason_code",
    "Scenario": r"scenario_id|scenario_weight|T_IB_A00|D_OB|D_TX|D_TO",
    "ConsequenceOntology": r"F_continuity|F_execution|F_propagation|P_time|P_itinerary|P_service|R_operating",
    "RegistryInfrastructure": r"yaml\.safe_load|json\.loads|sha256|content_id|registry_hash|freeze_id",
}


def _files() -> list[Path]:
    paths: list[Path] = []
    for root in ROOTS:
        base = PROJECT_ROOT / root
        if not base.exists():
            continue
        paths.extend(
            path
            for path in base.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".py", ".json", ".yaml", ".yml", ".toml", ".md"}
            and "__pycache__" not in path.parts
        )
    return sorted(paths)


def _rel(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _owner(path: str) -> str:
    if path.startswith("model/common/"):
        return "common"
    for layer in ("PRE", "M1", "M2", "M3", "M4"):
        if path.startswith(f"model/{layer}/"):
            return layer
    if path.startswith("registries/") or path.startswith("configs/"):
        return "scientific_configuration"
    if path.startswith("validation/") or path.startswith("tests/"):
        return "validation_or_tests"
    return "provenance_or_other"


def _responsibility(path: str) -> str:
    if path.startswith("model/common/"):
        return "typed cross-module primitive"
    if path.startswith("model/PRE/"):
        return "evidence and PRE state/reference"
    if path.startswith("model/M1/"):
        return "operating-state distribution and scenarios"
    if path.startswith("model/M2/"):
        return "baseline consequence and CU representation"
    if path.startswith("model/M3/"):
        return "action contract and conditioned consequence"
    if path.startswith("model/M4/"):
        return "common-basis monetary/risk comparison"
    return "supporting artifact or validation"


def _classification(path: str, text: str) -> str:
    if path.startswith("model/common/"):
        return "CANONICAL"
    if path.startswith("model/"):
        if any(token in path.lower() for token in ("legacy", "compat", "deprecated", "old_")):
            return "REVIEW"
        return "CANONICAL"
    if path.startswith("registries/") or path.startswith("configs/"):
        return "CANONICAL"
    if path.startswith("validation/") or path.startswith("tests/"):
        return "REVIEW"
    return "PROVENANCE_ONLY"


def _raw_imports(path: Path, text: str) -> list[tuple[str, int, tuple[str, ...]]]:
    if path.suffix != ".py":
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ["<SYNTAX_ERROR>"]
    result: list[tuple[str, int, tuple[str, ...]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend((alias.name, 0, ()) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            result.append(
                (
                    node.module or "",
                    node.level,
                    tuple(alias.name for alias in node.names if alias.name != "*"),
                )
            )
    return sorted(set(result))


def _symbols(path: Path, text: str) -> list[str]:
    if path.suffix != ".py":
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    symbols = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in TARGET_SYMBOLS:
                symbols.append(node.name)
    return sorted(set(symbols))


def _module_name(path: str) -> str | None:
    if not path.endswith(".py"):
        return None
    module = path[:-3].replace("/", ".")
    if module.endswith(".__init__"):
        module = module[: -len(".__init__")]
    return module


def _resolve_imports(
    source_module: str | None,
    raw_imports: list[tuple[str, int, tuple[str, ...]]],
    module_to_path: dict[str, str],
) -> list[dict[str, str]]:
    resolved: dict[tuple[str, str], dict[str, str]] = {}
    source_package = None
    if source_module:
        source_path = module_to_path.get(source_module, "")
        source_package = (
            source_module
            if source_path.endswith("/__init__.py")
            else source_module.rpartition(".")[0]
        )
    for imported, level, aliases in raw_imports:
        literal = ("." * level) + imported
        target_module = imported
        if level:
            if not source_package:
                continue
            try:
                target_module = importlib.util.resolve_name(literal, source_package)
            except (ImportError, ValueError):
                target_module = literal
        candidates = [target_module]
        if aliases:
            candidates.extend(f"{target_module}.{alias}" for alias in aliases)
        matched = False
        for candidate in candidates:
            target_path = module_to_path.get(candidate)
            if target_path is None:
                continue
            matched = True
            resolved[(literal, target_path)] = {
                "literal": literal,
                "module": candidate,
                "target": target_path,
            }
        if not matched:
            resolved[(literal, "")] = {
                "literal": literal,
                "module": target_module,
                "target": "",
            }
    return sorted(resolved.values(), key=lambda item: (item["literal"], item["target"]))


def _public_contract_import(target_module: str, target_owner: str) -> bool:
    if target_owner == "common":
        return True
    package = f"model.{target_owner}"
    return (
        target_module == package
        or target_module == f"{package}.contracts"
        or target_module.startswith(f"{package}.contracts.")
    )


def _edge_status(source_owner: str, target_owner: str, target_module: str) -> str:
    if source_owner == target_owner:
        return "SAME_LAYER"
    if source_owner not in MODEL_LAYERS or target_owner not in MODEL_LAYERS:
        return "NON_MODEL_BOUNDARY"
    if target_owner not in ALLOWED_LAYER_DEPENDENCIES[source_owner]:
        return "ILLEGAL_DIRECTION"
    if not _public_contract_import(target_module, target_owner):
        return "PRIVATE_CROSS_LAYER_IMPORT"
    return "ALLOWED_PUBLIC_CONTRACT"


def _legacy_evidence(path: str, text: str) -> tuple[list[str], str]:
    path_hits = {
        token for token in LEGACY_TOKENS if token.lower() in path.lower()
    }
    executable_names: set[str] = set()
    string_hits: set[str] = set()
    if path.endswith(".py"):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Name):
                    names.append(node.id)
                elif isinstance(node, ast.Attribute):
                    names.append(node.attr)
                elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.append(node.name)
                for name in names:
                    executable_names.update(
                        token
                        for token in LEGACY_TOKENS
                        if token.lower() in name.lower()
                    )
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    string_hits.update(
                        token
                        for token in LEGACY_TOKENS
                        if token.lower() in node.value.lower()
                    )
    else:
        string_hits.update(
            token for token in LEGACY_TOKENS if token.lower() in text.lower()
        )
    hits = sorted(path_hits | executable_names | string_hits)
    if executable_names:
        kind = "EXECUTABLE_IDENTIFIER_REVIEW"
    elif path_hits:
        kind = "PATH_NAME_REVIEW"
    else:
        kind = "TEXT_OR_PROVENANCE"
    return hits, kind


def build() -> dict:
    files = _files()
    rows = []
    module_to_path = {}
    contents = {}
    raw_by_path = {}
    for path in files:
        rel = _rel(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        contents[rel] = text
        module = _module_name(rel)
        if module:
            module_to_path[module] = rel
        raw_by_path[rel] = _raw_imports(path, text)
        rows.append(
            {
                "path": rel,
                "current_responsibility": _responsibility(rel),
                "scientific_owner": _owner(rel),
                "imported_by": "",
                "imports": "",
                "active_runtime": "YES" if rel.startswith("model/") else "NO",
                "classification": _classification(rel, text),
                "symbols": ";".join(_symbols(path, text)),
            }
        )

    reverse: dict[str, set[str]] = defaultdict(set)
    edges = []
    for row in rows:
        source = row["path"]
        source_module = _module_name(source)
        imports = _resolve_imports(
            source_module, raw_by_path[source], module_to_path
        )
        row["imports"] = ";".join(item["literal"] for item in imports)
        for imported in imports:
            target = imported["target"]
            if not target:
                continue
            reverse[target].add(source)
            source_owner = _owner(source)
            target_owner = _owner(target)
            edges.append(
                {
                    "from": source,
                    "to": target,
                    "import": imported["literal"],
                    "resolved_module": imported["module"],
                    "source_owner": source_owner,
                    "target_owner": target_owner,
                    "status": _edge_status(
                        source_owner, target_owner, imported["module"]
                    ),
                }
            )
    for row in rows:
        row["imported_by"] = ";".join(sorted(reverse.get(row["path"], ())))

    symbol_owners: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        for symbol in filter(None, row["symbols"].split(";")):
            symbol_owners[symbol].append(row["path"])

    concept_hits = {}
    for concept, pattern in CONCEPT_TOKENS.items():
        hit_files = []
        for path, text in contents.items():
            if re.search(pattern, text, flags=re.IGNORECASE):
                hit_files.append(path)
        concept_hits[concept] = sorted(hit_files)

    legacy_rows = []
    for path, text in contents.items():
        hits, evidence_kind = _legacy_evidence(path, text)
        if hits:
            legacy_rows.append({
                "path": path,
                "active_runtime": path.startswith("model/"),
                "tokens": sorted(set(hits)),
                "evidence_kind": evidence_kind,
                "classification": "PROVENANCE_OR_METADATA" if not path.startswith("model/") else "ACTIVE_RUNTIME_REVIEW",
            })

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "MODEL_FILE_INVENTORY_V1.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    cross_layer_edges = [
        edge
        for edge in edges
        if edge["source_owner"] in MODEL_LAYERS
        and edge["target_owner"] in MODEL_LAYERS
        and edge["source_owner"] != edge["target_owner"]
    ]
    illegal_edges = [
        edge
        for edge in cross_layer_edges
        if edge["status"] in {"ILLEGAL_DIRECTION", "PRIVATE_CROSS_LAYER_IMPORT"}
    ]
    (OUT / "MODEL_IMPORT_GRAPH_V1.json").write_text(
        json.dumps(
            {
                "schema_version": "MODEL_IMPORT_GRAPH_V1",
                "roots": ROOTS,
                "nodes": [row["path"] for row in rows],
                "edges": edges,
                "cross_layer_edges": cross_layer_edges,
                "illegal_cross_layer_edges": illegal_edges,
                "edge_status_counts": {
                    status: sum(1 for edge in edges if edge["status"] == status)
                    for status in sorted({edge["status"] for edge in edges})
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with (OUT / "MODEL_SYMBOL_OWNERSHIP_V1.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("symbol", "owners", "owner_count", "status"))
        writer.writeheader()
        for symbol, owners in sorted(symbol_owners.items()):
            writer.writerow({
                "symbol": symbol,
                "owners": ";".join(sorted(owners)),
                "owner_count": len(owners),
                "status": "DUPLICATE" if len(owners) > 1 else "SINGLE_OWNER",
            })

    dup_lines = [
        "# MODEL DUPLICATION AUDIT V1",
        "",
        f"Scanned files: {len(rows)}",
        "",
        "## Symbol definitions",
    ]
    for symbol, owners in sorted(symbol_owners.items()):
        dup_lines.append(f"- `{symbol}`: {len(owners)} definition(s) -> {', '.join(sorted(owners))}")
    dup_lines += ["", "## Concept footprint"]
    for concept, paths in concept_hits.items():
        dup_lines.append(f"- `{concept}`: {len(paths)} file(s)")
        for path in paths[:40]:
            dup_lines.append(f"  - `{path}`")
        if len(paths) > 40:
            dup_lines.append(f"  - ... {len(paths) - 40} more")
    dup_lines += ["", "## Initial interpretation", "", "This is a static audit only. Duplicate textual mentions are not by themselves executable duplicate owners; each candidate requires parity evidence before merge/delete."]
    (OUT / "MODEL_DUPLICATION_AUDIT_V1.md").write_text("\n".join(dup_lines) + "\n", encoding="utf-8")

    legacy_lines = [
        "# MODEL LEGACY RUNTIME AUDIT V1",
        "",
        "Static token scan across model, registry, config, validation, tests, and formal roots.",
        "",
        "## Active model runtime findings",
    ]
    active_legacy = [item for item in legacy_rows if item["active_runtime"]]
    for item in active_legacy:
        legacy_lines.append(
            f"- `{item['path']}` [{item['evidence_kind']}]: "
            f"{', '.join(item['tokens'])}"
        )
    if not active_legacy:
        legacy_lines.append("- NONE")
    legacy_lines += ["", "## Non-runtime provenance/metadata findings"]
    for item in legacy_rows:
        if not item["active_runtime"]:
            legacy_lines.append(
                f"- `{item['path']}` [{item['evidence_kind']}]: "
                f"{', '.join(item['tokens'])}"
            )
    if not any(not item["active_runtime"] for item in legacy_rows):
        legacy_lines.append("- NONE")
    legacy_lines += ["", "## Boundary", "", "Historical provenance and frozen registry names must remain preserved. Active runtime hits require explicit classification during migration; this report does not delete or rename anything."]
    (OUT / "MODEL_LEGACY_RUNTIME_AUDIT_V1.md").write_text("\n".join(legacy_lines) + "\n", encoding="utf-8")

    return {
        "schema_version": "MODEL_ARCHITECTURE_AUDIT_V1",
        "file_count": len(rows),
        "module_count": sum(1 for row in rows if row["path"].startswith("model/") and row["path"].endswith(".py")),
        "duplicate_symbols": {name: sorted(paths) for name, paths in symbol_owners.items() if len(paths) > 1},
        "active_legacy_runtime_files": [item["path"] for item in active_legacy],
        "cross_layer_edge_count": len(cross_layer_edges),
        "illegal_cross_layer_edge_count": len(illegal_edges),
        "illegal_direction_count": sum(
            1 for edge in illegal_edges if edge["status"] == "ILLEGAL_DIRECTION"
        ),
        "private_cross_layer_import_count": sum(
            1
            for edge in illegal_edges
            if edge["status"] == "PRIVATE_CROSS_LAYER_IMPORT"
        ),
        "reports": [
            str(OUT / name)
            for name in (
                "MODEL_FILE_INVENTORY_V1.csv",
                "MODEL_IMPORT_GRAPH_V1.json",
                "MODEL_SYMBOL_OWNERSHIP_V1.csv",
                "MODEL_DUPLICATION_AUDIT_V1.md",
                "MODEL_LEGACY_RUNTIME_AUDIT_V1.md",
            )
        ],
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
