"""Versioned JATM contracts introduced after the semantic inheritance audit.

Legacy fields and artifacts remain valid under their original identities.  The
new contracts are opt-in so an old cache cannot be silently reinterpreted.
"""

JATM_F_CONTINUITY_B_V1 = "JATM_F_CONTINUITY_B_V1"
JATM_STAGE2_SIGNED_T_IB_V1 = "JATM_STAGE2_SIGNED_T_IB_V1"
JATM_TIME_COORDINATE_LEGACY_A_V1 = "R_IB_LEGACY_V1"

__all__ = [
    "JATM_F_CONTINUITY_B_V1",
    "JATM_STAGE2_SIGNED_T_IB_V1",
    "JATM_TIME_COORDINATE_LEGACY_A_V1",
]
