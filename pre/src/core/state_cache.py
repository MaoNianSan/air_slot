from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..input import object_hash, sha256_file
from ..state import StateStore, extract_state_data
from .observation_requests import observation_request_hashes


def prepare_state_cache(
    cfg: dict[str, Any],
    requests: pd.DataFrame,
    airports: pd.DataFrame,
    coverage: pd.DataFrame,
) -> tuple[StateStore, pd.DataFrame, dict[str, Any]]:
    """Build or reuse only the current V2 state/flow cache."""
    state_requests = requests[requests["source"].eq("state")].copy()
    hashes = observation_request_hashes(requests)
    store, extraction, base_manifest = extract_state_data(
        cfg,
        state_requests,
        airports,
        coverage,
        Path(cfg["cache_root"]),
    )
    all_hit = bool(
        not extraction.empty
        and extraction["cache_status"].eq("HIT").all()
    )
    manifest = {
        **hashes,
        "cache_status": "V2_HIT" if all_hit else "V2_MISS_OR_PARTIAL",
        "cache_root": str(store.candidate_root.parent),
        "source_hash": object_hash(cfg.get("raw_hashes", {})),
        "extraction_code_hash": sha256_file(
            Path(__file__).resolve().parents[1] / "state.py"
        ),
        "base_cache_key": base_manifest.get("cache_key"),
    }
    return store, extraction, manifest
