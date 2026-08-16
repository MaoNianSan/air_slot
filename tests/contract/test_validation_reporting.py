import pytest
from pydantic import ValidationError
from validation.reporting import ValidationFinding, ValidationRun, exit_code


def test_validation_schema_has_allowlisted_fixture_metadata_and_exit_codes():
    run = ValidationRun(run_id="r", command="all", findings=(
        ValidationFinding(check_id="c", status="PASS", message="ok"),))
    assert run.FIXTURE_ONLY is True and run.paper_result is False
    assert run.evaluation_scope == "FOUNDATION_ONLY" and exit_code(run) == 0
    with pytest.raises(ValidationError):
        ValidationRun.model_validate({**run.model_dump(), "scientific_" + "status": "PASS"})
