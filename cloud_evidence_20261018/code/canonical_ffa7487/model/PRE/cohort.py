from __future__ import annotations

from datetime import date
from typing import Literal

from model.common.errors import ContractError
from model.PRE.transformation import (
    TransformationStatus,
    current_transformation_registry,
)

RULE_ID = "DATA2_TEMPORAL_SPLIT"
RULE_VERSION = "1.0.0"
MULTIYEAR_RULE_VERSION = "2.0.0"

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


def split_for_date_multiyear(service_date: date) -> SplitName:
    """Within-year replication of the 2019 month window (rule @2.0.0).

    Y = year(service_date): train <= Y-06-30, calibration Y-07-01..07-31,
    development Y-08-01..09-30, test >= Y-10-01. The legacy @1.0.0 rule and
    its ``split_for_date`` are untouched; the multi-year instance resolves
    through this function so every year repeats the JATM Table 8 structure.
    """
    rule = current_transformation_registry().get(
        RULE_ID, MULTIYEAR_RULE_VERSION)
    if rule.status is not TransformationStatus.FROZEN:
        raise ContractError("CONSTRUCTION_RULE_NOT_FROZEN")
    year = service_date.year
    if service_date <= date(year, 6, 30):
        return "train"
    if service_date <= date(year, 7, 31):
        return "calibration"
    if service_date <= date(year, 9, 30):
        return "development"
    return "test"
