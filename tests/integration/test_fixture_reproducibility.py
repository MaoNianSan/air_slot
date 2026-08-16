from model.common.serialization import canonical_json_bytes
from tests.fixtures.pre.foundation_cases import build_data1_case


def test_fixture_bytes_are_repeatable():
    first = canonical_json_bytes(build_data1_case())
    second = canonical_json_bytes(build_data1_case())
    assert first == second
