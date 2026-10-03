"""Dataset-instance contracts for Data2 multi-year engineering (M0).

Declares the two Data2 dataset instances side by side:

- ``data2_2019``      - the legacy reproducibility instance. Its fields mirror
  the constants currently hard-wired across the production pipeline
  (cohort.py split table @1.0.0, 2019-H1 M2 fit window, NOAA replay lag 5).
- ``data2_2017_2022`` - the future primary-experiment instance. This round it
  is declared PROFILING_ONLY: no adapter/registry wiring, no PRE enablement,
  no experiments, and no temporal split definition (the split rule id stays
  undefined until per-year profiling numbers exist and a human approves a
  ``DATA2_TEMPORAL_SPLIT`` sibling version).

This module is ADDITIVE: no existing module imports it, so legacy
``data2_2019`` behavior is untouched. The runtime contract guards make it
impossible to silently promote the profiling-only instance into a runnable
one - that requires an explicit code change here plus the separately
authorized frozen-surface work (adapter Literals, instance registry, V1R1
manifest refresh).
"""
from __future__ import annotations

from typing import Literal, Tuple

from pydantic import Field, model_validator

from model.common.value_objects import FrozenModel

InstanceStatus = Literal[
    "LEGACY_REPRODUCIBILITY",
    "PROFILING_ONLY",
    "COHORT_PROFILING",
    "ACTIVE",
]
PROFILING_ONLY = "PROFILING_ONLY"
COHORT_PROFILING = "COHORT_PROFILING"
LEGACY_REPRODUCIBILITY = "LEGACY_REPRODUCIBILITY"
# Read-only statuses: raw ingestion / canonicalization / cohort-eligibility
# auditing are allowed, but PRE materialization, model training, experiments,
# and any temporal-split definition stay disabled.
READ_ONLY_STATUSES = (PROFILING_ONLY, COHORT_PROFILING)


class DatasetInstanceContract(FrozenModel):
    """One dataset instance's declared scope and explicit capability bits."""

    instance_id: str
    status: InstanceStatus
    raw_root_name: Literal["data1", "data2"]
    years: Tuple[int, ...]
    adapter_id: str
    source_families: Tuple[str, ...]
    split_rule_id: str | None = None
    fit_window: str | None = None
    replay_lag_minutes: int | None = None
    raw_ingestion_enabled: bool = False
    canonicalization_enabled: bool = False
    cohort_profiling_enabled: bool = False
    pre_materialization_enabled: bool = False
    model_training_enabled: bool = False
    experiment_enabled: bool = False

    @model_validator(mode="after")
    def enforce_instance_discipline(self):
        if "+" in self.instance_id:
            raise ValueError("pooled dataset identity is rejected")
        if len(self.years) == 0 or self.years != tuple(sorted(set(self.years))):
            raise ValueError("years must be a non-empty, sorted, duplicate-free tuple")
        read_only = self.status in READ_ONLY_STATUSES
        if read_only:
            if (self.pre_materialization_enabled or self.model_training_enabled
                    or self.experiment_enabled):
                raise ValueError(
                    f"{self.status} instance cannot enable PRE materialization, "
                    "model training, or experiments")
            if self.split_rule_id is not None or self.fit_window is not None:
                raise ValueError(
                    f"{self.status} instance must leave the temporal split and "
                    "fit window undefined pending profiling and a human decision")
            if not (self.raw_ingestion_enabled and self.canonicalization_enabled
                    and self.cohort_profiling_enabled):
                raise ValueError(
                    f"{self.status} instance must enable raw ingestion, "
                    "canonicalization, and cohort profiling")
        if self.status == LEGACY_REPRODUCIBILITY:
            if not (self.raw_ingestion_enabled and self.canonicalization_enabled
                    and self.cohort_profiling_enabled
                    and self.pre_materialization_enabled
                    and self.model_training_enabled and self.experiment_enabled):
                raise ValueError("legacy instance must remain fully enabled")
            if self.split_rule_id is None or self.fit_window is None:
                raise ValueError(
                    "legacy instance must pin its frozen split rule and fit window")
        return self


LEGACY_DATA2_2019 = DatasetInstanceContract(
    instance_id="data2_2019",
    status=LEGACY_REPRODUCIBILITY,
    raw_root_name="data2",
    years=(2019,),
    adapter_id="D2",
    source_families=(
        "bts_ontime",
        "bts_db1b",
        "bts_t100",
        "timezone_reference",
        "airport_reference",
        "noaa_isd",
    ),
    split_rule_id="DATA2_TEMPORAL_SPLIT@1.0.0",
    fit_window="2019-H1",
    replay_lag_minutes=5,
    raw_ingestion_enabled=True,
    canonicalization_enabled=True,
    cohort_profiling_enabled=True,
    pre_materialization_enabled=True,
    model_training_enabled=True,
    experiment_enabled=True,
)

DATA2_2017_2022 = DatasetInstanceContract(
    instance_id="data2_2017_2022",
    status=COHORT_PROFILING,
    raw_root_name="data2",
    years=(2017, 2018, 2019, 2020, 2021, 2022),
    adapter_id="D2",
    source_families=(
        "bts_ontime",
        "bts_db1b",
        "bts_t100",
        "timezone_reference",
        "airport_reference",
        "noaa_isd",
    ),
    split_rule_id=None,
    fit_window=None,
    replay_lag_minutes=5,
    raw_ingestion_enabled=True,
    canonicalization_enabled=True,
    cohort_profiling_enabled=True,
    pre_materialization_enabled=False,
    model_training_enabled=False,
    experiment_enabled=False,
)

INSTANCE_CONTRACTS: Tuple[DatasetInstanceContract, ...] = (
    LEGACY_DATA2_2019,
    DATA2_2017_2022,
)


def get_instance_contract(instance_id: str) -> DatasetInstanceContract:
    for contract in INSTANCE_CONTRACTS:
        if contract.instance_id == instance_id:
            return contract
    raise KeyError(f"unknown dataset instance contract: {instance_id}")


def assert_distinct_instances() -> None:
    """Guard: the two instances never share a status or enablement profile."""
    if LEGACY_DATA2_2019.status == DATA2_2017_2022.status:
        raise ValueError("instance statuses must differ")
    if LEGACY_DATA2_2019.years == DATA2_2017_2022.years:
        raise ValueError("instance year scopes must differ")
    ids = [contract.instance_id for contract in INSTANCE_CONTRACTS]
    if len(ids) != len(set(ids)):
        raise ValueError("instance ids must be unique")


assert_distinct_instances()
