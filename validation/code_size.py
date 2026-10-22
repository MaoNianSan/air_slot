"""Repository Python modularity audit."""

import ast
from pathlib import Path

PRODUCTION_ROOTS = ("model", "validation")

# Formal runtime has no large-file exemptions. Archived implementations live
# under ``archive/`` and are intentionally outside production roots.
#
# Post-consolidation exemptions: validated, hash-locked migration assets that
# must not be refactored (refactoring would alter validated/sealed code).
SIZE_EXEMPTIONS = frozenset({
    "validation/m1_h_capacity_selection/runner.py",
    "validation/v2_phase6/freeze_activation.py",
    "validation/v2_phase5/families.py",
    "validation/v2_phase5/freeze.py",
})


def logical_lines(path: Path) -> int:
    """Count nonblank executable/declarative lines, excluding imports and docstrings."""
    text = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(text)
    excluded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            excluded.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    bodies = [tree.body]
    bodies.extend(
        node.body
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    )
    for body in bodies:
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            excluded.update(
                range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1)
            )
    return sum(
        1
        for number, line in enumerate(text.splitlines(), 1)
        if line.strip() and not line.lstrip().startswith("#") and number not in excluded
    )


def audit_python_sizes(root: Path) -> list[dict[str, str | int]]:
    records = []
    paths = (
        path
        for production_root in PRODUCTION_ROOTS
        for path in (root / production_root).rglob("*.py")
    )
    for path in sorted(paths):
        if any(
            part in {".pytest_cache", "__pycache__", "outputs"} for part in path.parts
        ):
            continue
        count = logical_lines(path)
        rel = path.relative_to(root).as_posix()
        if rel in SIZE_EXEMPTIONS:
            status = "EXEMPT"
        elif count > 800:
            status = "REFACTOR_REQUIRED"
        elif count > 500:
            status = "REVIEW"
        else:
            status = "OK"
        records.append({"path": rel, "logical_lines": count, "status": status})
    return records
