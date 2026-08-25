from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

from validation.code_size import audit_python_sizes
from validation.dependency_rules import scan_dependency_boundaries

RAW_SCHEMA_TOKENS = (
    "FlightDate",
    "Reporting_Airline",
    "Tail_Number",
    "CRSDepTime",
    "DepTime",
    "ArrTime",
    "WheelsOff",
    "WheelsOn",
    "STATION",
    "WND",
    "TMP",
    "CIG",
    "VIS",
)

RAW_MODULE_PREFIXES = (
    "model.PRE.adapters",
    "model.PRE.canonical.normalization",
    "model.PRE.canonical.timezone",
    "model.PRE.episode.builder",
)

PRE_IMPLEMENTATION_CALLS = {
    "RawReadRequest",
    "canonicalize_ontime_row",
    "canonicalize_isd_row",
    "build_data2_episode_records",
    "build_data2_episode_chain",
    "build_rolling_decision_nodes",
    "ProductionPRERequest",
    "publish_production_pre",
}

MODEL_IMPLEMENTATION_NAMES = {
    "_active_rows",
    "_examples",
    "active_rows",
    "adaptive_history",
    "build_training_examples",
    "current_history",
    "fixed_history",
    "normalization_rows",
    "represent_history",
}

EXPERIMENT_IMPLEMENTATION_NAMES = {
    "_run_candidate",
    "recommend_window",
    "_write_h_decision",
    "_write_w_evidence",
}

THIN_VALIDATION_TARGETS = {
    "validation/data2_v5_hstar_development.py",
    "validation/data2_v5_wstar_development.py",
}

# C0A is a closed, read-only source-clock audit. It invokes the official PRE
# canonicalizer to verify selected source records and does not own or duplicate
# PRE construction semantics.
READ_ONLY_PRE_AUDIT_CONSUMERS = {
    "validation/m1_v2_target_support_c0a_source.py",
}


def _module_names(tree: ast.AST) -> tuple[str, ...]:
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.append(node.module)
    return tuple(result)


def _call_names(node: ast.AST) -> set[str]:
    result = set()
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        if isinstance(item.func, ast.Name):
            result.add(item.func.id)
        elif isinstance(item.func, ast.Attribute):
            result.add(item.func.attr)
    return result


def _raw_tokens(text: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in RAW_SCHEMA_TOKENS
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", text)
    )


def _finding(path: str, code: str, detail: str) -> dict[str, str]:
    return {"path": path, "code": code, "detail": detail, "status": "FAIL"}


def scan_pre_ownership(root: Path) -> list[dict[str, str]]:
    findings = []
    for top in ("model", "exp", "validation"):
        for path in sorted((root / top).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8-sig")
            tree = ast.parse(text)
            modules = _module_names(tree)
            is_downstream = rel.startswith(
                ("model/M1/", "model/M2/", "model/M3/", "model/M4/", "exp/")
            )
            if is_downstream:
                tokens = _raw_tokens(text)
                if tokens:
                    findings.append(
                        _finding(rel, "RAW_SCHEMA_TOKEN_OUTSIDE_PRE", ",".join(tokens))
                    )
                raw_imports = [
                    module
                    for module in modules
                    if module.startswith(RAW_MODULE_PREFIXES)
                ]
                if raw_imports:
                    findings.append(
                        _finding(
                            rel,
                            "RAW_PREPROCESSING_IMPORT_OUTSIDE_PRE",
                            ",".join(raw_imports),
                        )
                    )
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                calls = _call_names(node)
                if (
                    rel.startswith(("validation/", "exp/"))
                    and rel not in READ_ONLY_PRE_AUDIT_CONSUMERS
                ):
                    owned_calls = sorted(calls & PRE_IMPLEMENTATION_CALLS)
                    if owned_calls:
                        findings.append(
                            _finding(
                                rel,
                                "PRE_DATA_CONSTRUCTION_OUTSIDE_PRE",
                                f"{node.name}:{','.join(owned_calls)}",
                            )
                        )
                if (
                    rel.startswith(("validation/", "exp/"))
                    and node.name in MODEL_IMPLEMENTATION_NAMES
                ):
                    findings.append(
                        _finding(rel, "MODEL_HISTORY_LOGIC_OUTSIDE_M1", node.name)
                    )
                if (
                    rel.startswith("validation/")
                    and node.name in EXPERIMENT_IMPLEMENTATION_NAMES
                ):
                    findings.append(
                        _finding(rel, "EXPERIMENT_LOGIC_OUTSIDE_EXP", node.name)
                    )
            if rel in THIN_VALIDATION_TARGETS:
                functions = [
                    node.name
                    for node in tree.body
                    if isinstance(
                        node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                    )
                ]
                if set(functions) - {"main"}:
                    findings.append(
                        _finding(
                            rel, "VALIDATION_WRAPPER_NOT_THIN", ",".join(functions)
                        )
                    )
    dependency_failures = [
        item for item in scan_dependency_boundaries(root) if item["status"] == "FAIL"
    ]
    findings.extend(
        _finding(item["path"], "DEPENDENCY_BOUNDARY", item["message"])
        for item in dependency_failures
    )
    return findings


def build_gate_result(root: Path) -> dict:
    findings = scan_pre_ownership(root)
    size_records = audit_python_sizes(root)
    volume_failures = [
        item for item in size_records if item["status"] == "REFACTOR_REQUIRED"
    ]
    return {
        "schema_version": "AIR_SLOT_PRE_OWNERSHIP_GATE_V2",
        "PRE_OWNERSHIP_GATE": "PASS" if not findings else "FAIL",
        "STATIC_VOLUME_GATE": "PASS" if not volume_failures else "FAIL",
        "PRE_DATA_CONSTRUCTION_OUTSIDE_PRE": sum(
            item["code"] == "PRE_DATA_CONSTRUCTION_OUTSIDE_PRE" for item in findings
        ),
        "MODEL_LOGIC_OUTSIDE_MODEL": sum(
            item["code"] == "MODEL_HISTORY_LOGIC_OUTSIDE_M1" for item in findings
        ),
        "EXP_LOGIC_OUTSIDE_EXP": sum(
            item["code"] == "EXPERIMENT_LOGIC_OUTSIDE_EXP" for item in findings
        ),
        "findings": findings,
        "volume_failures": volume_failures,
        "review_volume_files": [
            item for item in size_records if item["status"] == "REVIEW"
        ],
        "final_test_access_count": 0,
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "artifacts/diagnostics/v5_development_freeze/PRE_OWNERSHIP_GATE_V2.json"
        ),
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    result = build_gate_result(root)
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if result["PRE_OWNERSHIP_GATE"] != "PASS" or result["STATIC_VOLUME_GATE"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
