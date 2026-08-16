# -*- coding: utf-8 -*-
"""D2-10 formal temporal split (train/calibration/development/test) for data2.

Frozen rule DATA2_TEMPORAL_SPLIT@1.0.0 / D2-TEMPORAL-SPLIT@1.0.0
(user-approved 2026-08-14, D2-10 item 2, data2 scope): episodes are
partitioned by the successor (later leg) service_date:

    train        <= 2019-06-30
    calibration  2019-07-01 .. 2019-07-31
    development  2019-08-01 .. 2019-09-30
    test         >= 2019-10-01

Cohorts are sampled per split (fast tier 32/16/16/16); the train-frozen
references fit on the train partition only (fit_period 2019-H1), so no
cross-split leakage.  The split key is the successor leg's official
FlightDate (service date), not a UTC timestamp, so local-day boundaries
follow the official reporting date semantics.
"""
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

TRAIN_END = date(2019, 6, 30)
CALIBRATION_END = date(2019, 7, 31)
DEVELOPMENT_END = date(2019, 9, 30)

SplitName = Literal["train", "calibration", "development", "test"]
ALL_SPLITS: tuple[SplitName, ...] = ("train", "calibration", "development", "test")


def split_for_date(service_date: date) -> SplitName:
    """Assign the formal temporal split for an episode by successor service_date."""
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
