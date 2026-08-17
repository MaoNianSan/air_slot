# -*- coding: utf-8 -*-
"""Formal temporal split (train/calibration/development/test).

Frozen rule TEMPORAL_EPISODE_SPLIT@1.0.0: episodes are
partitioned by the successor (later leg) service_date:

    train        <= 2019-06-30
    calibration  2019-07-01 .. 2019-07-31
    development  2019-08-01 .. 2019-09-30
    test         >= 2019-10-01

Cohorts and train-frozen references are evaluation concerns; the split key is
the typed episode service date, not a raw dataset column.
"""
from model.PRE.cohort import (
    ALL_SPLITS,
    CALIBRATION_END,
    DEVELOPMENT_END,
    RULE_ID,
    RULE_VERSION,
    TRAIN_END,
    SplitName,
    split_for_date,
)

__all__ = [
    "ALL_SPLITS",
    "CALIBRATION_END",
    "DEVELOPMENT_END",
    "RULE_ID",
    "RULE_VERSION",
    "TRAIN_END",
    "SplitName",
    "split_for_date",
]
