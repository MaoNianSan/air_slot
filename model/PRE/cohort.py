from __future__ import annotations

from datetime import date
from typing import Literal

from model.common.errors import ContractError
from model.PRE.transformation import TransformationStatus, current_transformation_registry


RULE_ID = "DATA2_TEMPORAL_SPLIT"
RULE_VERSION = "1.0.0"

TRAIN_END = date(2019, 6, 30)
CALIBRATION_END = date(2019, 7, 31)
DEVELOPMENT_END = date(2019, 9, 30)

SplitName = Literal["train", "calibration", "development", "test"]
ALL_SPLITS: tuple[SplitName, ...] = (
    "train",
    "calibration",
    "development",
    "test",
)


def split_for_date(service_date: date) -> SplitName:
    """Assign the frozen temporal cohort from the canonical service date."""
    rule = current_transformation_registry().get(RULE_ID, RULE_VERSION)
    if rule.status is not TransformationStatus.FROZEN:
        raise ContractError("CONSTRUCTION_RULE_NOT_FROZEN")
    if service_date <= TRAIN_END:
        return "train"
    if service_date <= CALIBRATION_END:
        return "calibration"
    if service_date <= DEVELOPMENT_END:
        return "development"
    return "test"
