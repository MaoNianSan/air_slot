from __future__ import annotations

import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from ranking_contract import (  # noqa: E402,F401
    RANKING_CONTRACT_VERSION,
    RANKING_DEPTHS,
    build_ranking_prefixes,
    compare_ranking_prefixes,
    full_ranking_from_scores,
)
from strict_config import strict_deep_merge  # noqa: E402,F401


__all__ = [
    "RANKING_CONTRACT_VERSION",
    "RANKING_DEPTHS",
    "build_ranking_prefixes",
    "compare_ranking_prefixes",
    "full_ranking_from_scores",
    "strict_deep_merge",
]
