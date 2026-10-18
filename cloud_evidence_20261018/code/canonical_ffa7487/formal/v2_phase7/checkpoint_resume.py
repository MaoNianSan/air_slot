"""Release fingerprinting and access-epoch checkpoint identity."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .materialization import _sha256_bytes


def _release_fingerprint(release: Mapping[str, Any]) -> str:
    body = json.dumps(release, sort_keys=True, separators=(",", ":"), default=str)
    return _sha256_bytes(body.encode("utf-8"))


def _access_epoch_id(release: Mapping[str, Any]) -> str:
    return _release_fingerprint(release)


__all__ = ["_access_epoch_id", "_release_fingerprint"]
