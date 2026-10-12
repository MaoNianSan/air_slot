from pathlib import Path

from exp.jatm_s34.readiness import build_readiness, inspect_year


def test_year_readiness_marks_existing_development_manifests_without_test_access():
    root = Path(__file__).resolve().parents[2]
    payload = build_readiness(root)
    assert payload["reads_q4_or_test_rows"] is False
    assert payload["executes_scientific_model"] is False
    assert payload["summary"]["pre_development_ready"] == 6
    assert payload["summary"]["test_runs_ready"] == 0
    assert all(row["test"] == 0 for row in payload["rows"])
    assert all(row["test_execution_status"] == "BLOCKED_TEST_ACCESS" for row in payload["rows"])


def test_missing_year_is_typed():
    row = inspect_year(Path("C:/does/not/exist"), 2017)
    assert row["status"] == "MISSING_PRE_DEVELOPMENT_MANIFEST"
    assert row["test_execution_status"] == "BLOCKED_TEST_ACCESS"
