from datetime import datetime, timezone

from model.common.identity import content_id
from model.common.serialization import canonical_json_bytes


def test_canonical_json_and_hash_are_order_independent():
    a = {"z": 1, "t": datetime(2026, 8, 12, tzinfo=timezone.utc), "a": [2, 1]}
    b = {"a": [2, 1], "t": datetime(2026, 8, 12, tzinfo=timezone.utc), "z": 1}
    assert canonical_json_bytes(a) == canonical_json_bytes(b)
    assert content_id(a) == content_id(b)
    assert content_id(a).startswith("sha256:")
