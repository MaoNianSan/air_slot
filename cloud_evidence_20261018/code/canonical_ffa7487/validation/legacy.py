from __future__ import annotations

import json


def deprecated_main(entry_point: str, replacement: str) -> None:
    payload = {
        "status": "DEPRECATED_ARCHITECTURE_ENTRY_POINT",
        "entry_point": entry_point,
        "replacement": replacement,
        "reason": "PRE construction and model orchestration must use owned APIs",
        "final_test_access_count": 0,
    }
    print(json.dumps(payload, sort_keys=True))
    raise SystemExit(2)
