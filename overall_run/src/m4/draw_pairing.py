from __future__ import annotations

import hashlib

from .contracts import M4ContractError, M4_DRAW_PAIRING_VERSION


def response_draw_index(
    *,
    episode_id: str,
    sample_id: int,
    m3_sample_hash: str,
    n_draws: int,
) -> int:
    if not episode_id or int(sample_id) < 0 or not m3_sample_hash or int(n_draws) <= 0:
        raise M4ContractError("M4_DRAW_PAIRING_INPUT_INVALID")
    payload = "\x1f".join(
        (
            M4_DRAW_PAIRING_VERSION,
            str(episode_id),
            str(int(sample_id)),
            str(m3_sample_hash),
        )
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % int(n_draws)
