from __future__ import annotations

import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from action_contract import v3_pre_action_contract  # noqa: E402,F401
from strict_config import StrictConfigError, strict_deep_merge  # noqa: E402,F401


__all__ = ["StrictConfigError", "strict_deep_merge", "v3_pre_action_contract"]
