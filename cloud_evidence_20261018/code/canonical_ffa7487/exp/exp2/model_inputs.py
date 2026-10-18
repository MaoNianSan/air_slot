"""Thin M1/M2 boundary for Exp2 Development materialization."""

from __future__ import annotations

import json
from math import isclose, isfinite
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd

from model.M2 import M2Service
from model.M2.context import build_m2_seven_component_scope
from model.M2.contracts import M2ScenarioInput, ScenarioConsequence
from model.M2.cu.registry import FrozenData2CUNormalizationRegistry
from model.M2.scientific_registry import load_active_m2_cu_registry
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from .common_support import (
    conditional_node_summary,
    identify_common_supported_scenarios,
)
from .protocol import COMPONENTS


def active_model_contract() -> (
    tuple[object, FrozenData2CUNormalizationRegistry, object]
):
    frozen = load_active_m2_cu_registry()
    if frozen.registry_id != "M2_DATA2_FORMAL_CU_V4":
        raise RuntimeError("M2_ACTIVE_REGISTRY_NOT_V4")
    if frozen.scientific_status != "FROZEN" or frozen.implementation_status != "MATCH":
        raise RuntimeError("M2_ACTIVE_REGISTRY_STATUS_INVALID")
    if frozen.final_test_access_count != 0:
        raise RuntimeError("M2_REGISTRY_FINAL_TEST_ACCESS_VIOLATION")
    if tuple(frozen.formal_scope) != tuple(CONSEQUENCE_COMPONENTS):
        raise RuntimeError("M2_V4_FORMAL_SCOPE_MISMATCH")
    if frozen.support_rule != "UNAVAILABLE_ABSTAIN_NO_DROP_RENORM_ZERO_PROXY":
        raise RuntimeError("M2_SUPPORT_RULE_MISMATCH")
    for component in COMPONENTS:
        if not isfinite(frozen.scale(component)) or frozen.scale(component) <= 0:
            raise RuntimeError(f"M2_TRAIN_SCALE_NOT_POSITIVE:{component}")
    registry = FrozenData2CUNormalizationRegistry(frozen)
    scope = build_m2_seven_component_scope()
    return frozen, registry, scope


def typed_m1_inputs(
    scenarios: Iterable[object],
    *,
    pre_lineage: tuple[str, ...],
    reference_lineage: tuple[str, ...],
) -> tuple[M2ScenarioInput, ...]:
    return tuple(
        M2ScenarioInput.from_m1(
            scenario, pre_lineage=pre_lineage, reference_lineage=reference_lineage
        )
        for scenario in scenarios
    )


def map_model_outputs(
    typed: Iterable[M2ScenarioInput], context: object
) -> tuple[ScenarioConsequence, ...]:
    _, registry, scope = active_model_contract()
    return M2Service(registry=registry, consequence_scope=scope).map_scenarios(
        tuple(typed), context
    )


def flatten_node(
    typed: Iterable[M2ScenarioInput],
    mapped: Iterable[ScenarioConsequence],
    *,
    metadata: Mapping[str, object],
) -> dict[str, object]:
    inputs = tuple(typed)
    outputs = tuple(mapped)
    frozen, registry, _ = active_model_contract()
    support_records = identify_common_supported_scenarios(inputs, outputs, registry)
    summary = conditional_node_summary(support_records)
    row: dict[str, object] = {
        **metadata,
        "episode_id": inputs[0].episode_id,
        "decision_node_id": inputs[0].decision_node_id,
        **summary,
        "delay_to_mean": summary["delay_to_mean_cs"],
    }
    for reason in ("D_TO", *COMPONENTS):
        row[f"unsupported_scenario_count_{reason}"] = sum(
            reason in support_record["unsupported_reasons"]
            for support_record in support_records
        )
    for component in COMPONENTS:
        native = summary[f"{component}_native_cs"]
        cu = summary[f"Z_{component}_cs"]
        if native is not None and not isclose(
            float(cu),
            float(native) / frozen.scale(component),
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise ValueError(f"EXP2_MODEL_CU_VALIDATION_FAILED:{component}")
        row[f"{component}_native"] = native
        row[f"Z_{component}"] = cu
        row[f"{component}_status"] = (
            "SUPPORTED_CONDITIONAL" if native is not None else "UNSUPPORTED"
        )
    row["m2_registry_id"] = frozen.registry_id
    row["m2_registry_hash"] = frozen.registry_hash
    return row


def load_explicit_node_inputs(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise RuntimeError("BLOCK_EXP2_DEVELOPMENT_INPUT_MISSING")
    if path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(path)
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        frame = pd.DataFrame(payload["rows"] if isinstance(payload, dict) else payload)
    required = {
        "episode_id",
        "decision_node_id",
        "decision_time",
        "information_cutoff",
        "operational_stage",
        "common_support_mass",
        "support_primary",
        "support_sensitivity",
        "support_full",
        "conditional_aggregate_complete",
        "formal_full_support",
        "scenario_count_total",
        "common_support_scenario_count",
        "delay_to_mean",
        *(f"{component}_native" for component in COMPONENTS),
        *(f"Z_{component}" for component in COMPONENTS),
        *(f"{component}_status" for component in COMPONENTS),
    }
    if not required <= set(frame.columns):
        missing = sorted(required - set(frame.columns))
        raise RuntimeError(f"BLOCK_EXP2_DEVELOPMENT_INPUT_COLUMNS_MISSING:{missing}")
    decision_time = pd.to_datetime(frame["decision_time"], utc=True, errors="coerce")
    information_cutoff = pd.to_datetime(
        frame["information_cutoff"], utc=True, errors="coerce"
    )
    if decision_time.isna().any() or information_cutoff.isna().any():
        raise RuntimeError("BLOCK_EXP2_DEVELOPMENT_TIMESTAMP_INVALID")
    if (information_cutoff > decision_time).any():
        raise RuntimeError("BLOCK_EXP2_INFORMATION_CUTOFF_AFTER_DECISION")
    start = pd.Timestamp("2019-08-01", tz="UTC")
    end = pd.Timestamp("2019-10-01", tz="UTC")
    if ((decision_time < start) | (decision_time >= end)).any():
        raise RuntimeError("BLOCK_EXP2_DEVELOPMENT_TEST_SEPARATION_FAILED")
    if "final_test_access_count" in frame and not frame[
        "final_test_access_count"
    ].fillna(0).eq(0).all():
        raise RuntimeError("BLOCK_EXP2_FINAL_TEST_ACCESS_VIOLATION")
    return frame
