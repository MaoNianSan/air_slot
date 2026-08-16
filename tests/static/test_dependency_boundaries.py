from pathlib import Path
from validation.dependency_rules import scan_dependency_boundaries


def test_static_boundaries_clean():
    findings = scan_dependency_boundaries(Path("."))
    assert [f for f in findings if f["status"] == "FAIL"] == []
