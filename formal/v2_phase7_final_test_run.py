"""Compatibility facade for the AirSlot V2 Phase-7 one-shot runner."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from formal.v2_phase7 import constants as _constants  # noqa: E402
from formal.v2_phase7.access_audit import *  # noqa: E402,F401,F403
from formal.v2_phase7.authority import *  # noqa: E402,F401,F403
from formal.v2_phase7.checkpoint_resume import *  # noqa: E402,F401,F403
from formal.v2_phase7.cli import main  # noqa: E402
from formal.v2_phase7.cohort import *  # noqa: E402,F401,F403
from formal.v2_phase7.dry_run import *  # noqa: E402,F401,F403
from formal.v2_phase7.errors import *  # noqa: E402,F401,F403
from formal.v2_phase7.gate_a import *  # noqa: E402,F401,F403
from formal.v2_phase7.gate_b import *  # noqa: E402,F401,F403
from formal.v2_phase7.materialization import *  # noqa: E402,F401,F403
from formal.v2_phase7.release import *  # noqa: E402,F401,F403
from formal.v2_phase7.reporting import *  # noqa: E402,F401,F403

for _name in _constants.__all__:
    globals()[_name] = getattr(_constants, _name)

F_CONTINUITY_SCALE_CANONICAL_LF_SHA256 = (
    _constants.F_CONTINUITY_SCALE_FILE_SHA256
)
TRAIN_SUPPORT_SUMMARY_CANONICAL_LF_SHA256 = (
    _constants.TRAIN_SUPPORT_SUMMARY_FILE_SHA256
)

if __name__ == "__main__":
    raise SystemExit(main())

__all__ = sorted(
    set(_constants.__all__)
    | {
        "Phase7Error",
        "TypedBlocker",
        "build_gate_a_preflight",
        "execute_gate_b",
        "main",
        "make_release",
        "mark_access_read_completed",
        "mark_access_read_started",
        "open_access_epoch",
        "run_dry_run",
        "run_gate_a",
        "validate_cohort_reference",
        "validate_instruction_copies",
        "validate_r2_authority",
        "validate_release_schema",
        "_read_json",
        "_access_epoch_id",
        "_release_fingerprint",
        "_write_json_atomic",
        "_assert_not_legacy_final_test",
        "F_CONTINUITY_SCALE_CANONICAL_LF_SHA256",
        "TRAIN_SUPPORT_SUMMARY_CANONICAL_LF_SHA256",
    }
)
