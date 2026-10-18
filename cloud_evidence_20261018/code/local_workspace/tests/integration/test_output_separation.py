from pathlib import Path
from tests.fixtures.pre.foundation_cases import build_data1_case


def test_fixture_metadata_and_output_namespaces_are_separate():
    result = build_data1_case().model_dump(mode="json")
    assert {key for key in result if key != "pre_state"} == {"FIXTURE_ONLY", "paper_result", "evaluation_scope"}
    assert result["FIXTURE_ONLY"] is True and result["paper_result"] is False
    assert result["evaluation_scope"] == "FOUNDATION_ONLY"
    for namespace in ("evaluation", "paper_candidate", "manuscript_values"):
        files = [p for p in (Path("outputs") / namespace).rglob("*") if p.is_file() and p.name != "README.md"]
        assert files == []
