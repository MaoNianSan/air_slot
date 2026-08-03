from __future__ import annotations

import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from action_contract import load_action_contract  # noqa: E402,F401


__all__ = ["load_action_contract"]
