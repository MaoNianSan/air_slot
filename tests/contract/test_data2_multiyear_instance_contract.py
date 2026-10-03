"""M0/M3 contract tests for the Data2 multi-year instance design.

Round-scoped guarantees:

1. ``data2_2019`` stays the fully-enabled legacy reproducibility instance with
   its frozen split rule / fit window / replay lag mirrored exactly.
2. ``data2_2017_2022`` is PROFILING_ONLY in this round: PRE and experiments
   disabled, temporal split and fit window explicitly undefined.
3. The frozen surfaces this round promised not to touch still carry the exact
   byte hashes recorded at round start (paths.py, cohort.py, adapter modules,
   hashed registries + manifest, source adapter registry).

The freeze pin is intentionally strict for this engineering round; when a
frozen-surface change is separately authorized (e.g. the M4 adapter wiring),
the pin constants must be updated deliberately in the same change.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from model.PRE.instances import (
    DATA2_2017_2022,
    INSTANCE_CONTRACTS,
    LEGACY_DATA2_2019,
    get_instance_contract,
)
from model.PRE.instances.contract import (
    DatasetInstanceContract,
    assert_distinct_instances,
)

ROOT = Path(__file__).resolve().parents[2]

FREEZE_SURFACE = {
    # M4a/M4b note: adapters/{registry,base,data2}.py (M4a) and
    # model/PRE/cohort.py (M4b: additive split_for_date_multiyear for the
    # authorized DATA2_TEMPORAL_SPLIT@2.0.0 rule) were deliberately modified
    # in authorized rounds and are therefore no longer byte-pinned here;
    # their legacy behavior is pinned behaviorally by
    # tests/contract/test_data2_multiyear_m4a.py and
    # tests/contract/test_data2_multiyear_m4b.py, and their V1R1 manifest
    # drift is whitelisted in tests/m1/test_model_baseline_fingerprint.py.
    "model/common/paths.py":
        "66be8174be6fbb4f231859dd2baaa92018a58c0424de4880c7e446e7d00a0e69",
    "model/PRE/adapters/readers.py":
        "690fdc44a740920328bc3516629f7e1a4de89971719cacb24fb82e10b4a22308",
    "registries/source_adapter_registry.yaml":
        "83f288e0123ea04ed2e49152efd73e003c5548b37696dad4d186c3733ab96c70",
    "registries/registry_manifest.json":
        "1e1cd2ee8941034b71655778a3865a70f5d4023eb568b653362fe33738b6276a",
    "registries/data_usage_rules.yaml":
        "74f418cb8b1a6011e031ddbde4e5a097f26e621cd0baf123fa7c2a2ee8b873a4",
    "registries/scientific_variables.yaml":
        "b48f20879001775e40ea2f35b2bb868fb26553a254b8308857560895b1c3c5b0",
    "registries/dataset_capabilities.yaml":
        "e1e99045a685215335eff53711cd07ba4e45b92d08649f5cd262d90de74c605b",
    "registries/source_priority.yaml":
        "34468b63c1327ef37a8be4214791c393e60af8d0a884e495fdd07acdd30e4781",
}

PROFILING_REUSE_FORBIDDEN_TOKENS = (
    "split_for_date",
    "DATA2_TEMPORAL_SPLIT",
    "FINAL_TEST_START",
    "FINAL_TEST",
    'startswith("2019-',
    "month_key",
    "== 2019",
    "!= 2019",
)


# --------------------------------------------------------------------- M0 --


def test_legacy_instance_mirrors_current_frozen_constants():
    assert LEGACY_DATA2_2019.instance_id == "data2_2019"
    assert LEGACY_DATA2_2019.status == "LEGACY_REPRODUCIBILITY"
    assert LEGACY_DATA2_2019.raw_root_name == "data2"
    assert LEGACY_DATA2_2019.years == (2019,)
    assert LEGACY_DATA2_2019.split_rule_id == "DATA2_TEMPORAL_SPLIT@1.0.0"
    assert LEGACY_DATA2_2019.fit_window == "2019-H1"
    assert LEGACY_DATA2_2019.replay_lag_minutes == 5
    assert LEGACY_DATA2_2019.raw_ingestion_enabled is True
    assert LEGACY_DATA2_2019.canonicalization_enabled is True
    assert LEGACY_DATA2_2019.cohort_profiling_enabled is True
    assert LEGACY_DATA2_2019.pre_materialization_enabled is True
    assert LEGACY_DATA2_2019.model_training_enabled is True
    assert LEGACY_DATA2_2019.experiment_enabled is True


def test_new_instance_is_cohort_profiling_only():
    assert DATA2_2017_2022.instance_id == "data2_2017_2022"
    assert DATA2_2017_2022.status == "COHORT_PROFILING"
    assert DATA2_2017_2022.years == (2017, 2018, 2019, 2020, 2021, 2022)
    assert DATA2_2017_2022.raw_ingestion_enabled is True
    assert DATA2_2017_2022.canonicalization_enabled is True
    assert DATA2_2017_2022.cohort_profiling_enabled is True
    assert DATA2_2017_2022.pre_materialization_enabled is False
    assert DATA2_2017_2022.model_training_enabled is False
    assert DATA2_2017_2022.experiment_enabled is False
    assert DATA2_2017_2022.split_rule_id is None
    assert DATA2_2017_2022.fit_window is None
    assert DATA2_2017_2022.raw_root_name == "data2"


def test_read_only_instance_cannot_enable_downstream_capabilities():
    for status in ("PROFILING_ONLY", "COHORT_PROFILING"):
        with pytest.raises(ValidationError):
            DatasetInstanceContract(
                instance_id="data2_2017_2022",
                status=status,
                raw_root_name="data2",
                years=(2017, 2018, 2019, 2020, 2021, 2022),
                adapter_id="D2",
                source_families=("bts_ontime",),
                split_rule_id=None,
                fit_window=None,
                pre_materialization_enabled=True,
            )
        with pytest.raises(ValidationError):
            DatasetInstanceContract(
                instance_id="data2_2017_2022",
                status=status,
                raw_root_name="data2",
                years=(2017, 2018, 2019, 2020, 2021, 2022),
                adapter_id="D2",
                source_families=("bts_ontime",),
                split_rule_id="DATA2_TEMPORAL_SPLIT@2.0.0",
                fit_window=None,
            )


def test_read_only_instance_cannot_predefine_a_temporal_split():
    with pytest.raises(ValidationError):
        DatasetInstanceContract(
            instance_id="data2_2017_2022",
            status="COHORT_PROFILING",
            raw_root_name="data2",
            years=(2017, 2018, 2019, 2020, 2021, 2022),
            adapter_id="D2",
            source_families=("bts_ontime",),
            fit_window="2017-2019-H1",
        )


def test_legacy_instance_cannot_be_demoted():
    with pytest.raises(ValidationError):
        DatasetInstanceContract(
            instance_id="data2_2019",
            status="LEGACY_REPRODUCIBILITY",
            raw_root_name="data2",
            years=(2019,),
            adapter_id="D2",
            source_families=("bts_ontime",),
            split_rule_id="DATA2_TEMPORAL_SPLIT@1.0.0",
            fit_window="2019-H1",
            model_training_enabled=False,
        )


def test_pooled_identity_is_rejected():
    with pytest.raises(ValidationError):
        DatasetInstanceContract(
            instance_id="data2_2019+data2_2017_2022",
            status="PROFILING_ONLY",
            raw_root_name="data2",
            years=(2019,),
            adapter_id="D2",
            source_families=("bts_ontime",),
        )


def test_instances_stay_distinct_and_unique():
    assert_distinct_instances()
    ids = [contract.instance_id for contract in INSTANCE_CONTRACTS]
    assert ids == ["data2_2019", "data2_2017_2022"]
    assert get_instance_contract("data2_2019") is LEGACY_DATA2_2019
    assert get_instance_contract("data2_2017_2022") is DATA2_2017_2022
    with pytest.raises(KeyError):
        get_instance_contract("data1_2019")


# ------------------------------------------------- M3: frozen-surface pin --


@pytest.mark.parametrize("relative,expected", sorted(FREEZE_SURFACE.items()))
def test_frozen_surface_unchanged(relative: str, expected: str):
    path = ROOT / relative
    assert path.is_file(), relative
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == expected, (
        f"{relative} changed during the multi-year engineering round; if this "
        "change was authorized (e.g. M4 adapter wiring), update the pin "
        "deliberately in the same commit"
    )


def test_profiling_reuse_chain_is_free_of_legacy_split_machinery():
    """Constraint check: every PRE function the profiler reuses must be free
    of the legacy temporal-split machinery (cohort split / 2019 filters)."""
    script = ROOT / "data2" / "scripts" / "profile_data2_years.py"
    assert script.is_file(), "profiling script missing"
    spec = importlib.util.spec_from_file_location(
        "profile_data2_years", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    audit = module.static_reuse_audit()
    assert audit["status"] == "PASS", audit
    assert audit["clean_functions"], "no reuse functions audited"
