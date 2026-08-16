from hashlib import sha256
from typing import Any

from .serialization import canonical_json_bytes


def content_id(value: Any) -> str:
    return f"sha256:{sha256(canonical_json_bytes(value)).hexdigest()}"
