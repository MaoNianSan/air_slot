from __future__ import annotations

from .state_store import StateEntry
from ..contracts import M1InputBundle


def replay_reason(entries: tuple[StateEntry, ...], incoming: M1InputBundle) -> str | None:
    for entry in entries:
        current = entry.input_bundle
        if current.snapshot_id == incoming.snapshot_id and incoming.snapshot_version > current.snapshot_version:
            return "SNAPSHOT_VERSION_INCREASED"
        if incoming.information_cutoff < current.information_cutoff:
            return "EARLIER_EVIDENCE_REVISED"
    return None
