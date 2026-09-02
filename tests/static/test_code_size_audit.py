from pathlib import Path

from validation.code_size import audit_python_sizes, logical_lines


def test_code_size_audit_covers_repository_and_has_no_required_refactor():
    records = audit_python_sizes(Path("."))
    assert records
    assert {record["path"].split("/", 1)[0] for record in records} == {
        "model", "validation"}
    assert not [record for record in records if record["status"] == "REFACTOR_REQUIRED"]
    this_file = Path(__file__)
    assert logical_lines(this_file) > 0
