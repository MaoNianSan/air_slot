from pathlib import Path
from tests.fixtures.pre.foundation_cases import build_data1_case


def test_fixture_metadata_and_output_namespaces_are_separate():
    namespaces = ("evaluation", "paper_candidate", "manuscript_values")

    def snapshot(namespace):
        root = Path("outputs") / namespace
        return tuple(
            sorted(
                (path.relative_to(root).as_posix(), path.stat().st_size,
                 path.stat().st_mtime_ns)
                for path in root.rglob("*")
                if path.is_file()
            )
        )

    before = {namespace: snapshot(namespace) for namespace in namespaces}
    result = build_data1_case().model_dump(mode="json")
    assert {key for key in result if key != "pre_state"} == {"FIXTURE_ONLY", "paper_result", "evaluation_scope"}
    assert result["FIXTURE_ONLY"] is True and result["paper_result"] is False
    assert result["evaluation_scope"] == "FOUNDATION_ONLY"
    after = {namespace: snapshot(namespace) for namespace in namespaces}
    assert after == before
