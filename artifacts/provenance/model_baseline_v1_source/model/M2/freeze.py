"""M2 Data2 formal freeze: registry, serialization, orchestration.

HUMAN-APPROVED via AIR_SLOT_POST_EXP1_DEVELOPMENT_FREEZE_RESOLUTION
(DECISION 1, M2_DATA2_FORMAL_CU_V1).  Raw train-row reading, reference
fitting, and train-scale computation live in
model.PRE.reference.data2_m2_train_fit (PRE ownership gate V2); this module
only performs deterministic execution of the approved contract and never
touches Final Test data.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from pydantic import Field, model_validator

from model.M2.valuation import (
    M2CUNormalizationAdapter,
    ValuationRegistry,
    ValuationRule,
    ValuationRuleStatus,
)
from model.common.cu_normalization import CUNormalizationRegistry
from model.PRE.reference.data2_m2_train_fit import (
    build_data2_m2_train_preparation,
    compute_train_scales,
    fit_train_references,
    M2_FORMAL_SCOPE,
    M2_NATIVE_DEFINITIONS,
)
from model.PRE.reference.exposure_data2 import (
    Data2ExposureReference,
    data2_downstream_exposure_from_payload,
)
from model.PRE.reference.passenger_data2 import (
    Data2PassengerReference,
    data2_passenger_reference_from_payload,
)
from model.PRE.reference.taxi_data2 import (
    Data2TaxiReference,
    data2_taxi_reference_from_payload,
)
from model.PRE.reference.turnaround_data2 import (
    Data2TurnaroundReference,
    data2_turnaround_reference_from_payload,
)
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.errors import ContractError
from model.common.identity import content_id
from model.common.value_objects import FrozenModel

REGISTRY_ID = "M2_DATA2_FORMAL_CU_V4"
SCHEMA_VERSION = "M2_DATA2_FORMAL_CU_V4"
FORMAL_SCOPE = CONSEQUENCE_COMPONENTS
LEGACY_FORMAL_SCOPE = ("F_continuity", "F_execution", "F_propagation", "P_time", "R_operating")
AGGREGATION_RULE = "SUM_OVER_SEVEN_ONLY_IF_ALL_SUPPORTED"
SUPPORT_RULE = "UNAVAILABLE_ABSTAIN_NO_DROP_RENORM_ZERO_PROXY"
OUTSIDE_SCOPE = ()
SEVEN_SCOPE = (
    "F_continuity",
    "F_execution",
    "F_propagation",
    "P_time",
    "P_itinerary",
    "P_service",
    "R_operating",
)

_NATIVE_DEFINITIONS = M2_NATIVE_DEFINITIONS


class M2Data2FormalCuRegistry(FrozenModel):
    registry_id: str = REGISTRY_ID
    schema_version: str = SCHEMA_VERSION
    formal_scope: tuple[str, ...] = FORMAL_SCOPE
    outside_principal_scope: tuple[str, ...] = ()
    native_quantity_definitions: dict[str, dict[str, str]] = Field(default_factory=dict)
    semantic_channels: dict[str, dict[str, str]] = Field(default_factory=dict)
    train_scale_artifact: dict[str, dict[str, Any]] = Field(default_factory=dict)
    reference_artifacts: dict[str, dict[str, str]] = Field(default_factory=dict)
    component_weights: dict[str, float] = Field(default_factory=dict)
    aggregation_rule: str = AGGREGATION_RULE
    support_rule: str = SUPPORT_RULE
    final_test_access_count: int = 0
    paper_full_run: bool = False
    assumption_grounded: dict[str, Any] | None = None
    assumption_scale_artifact: dict[str, dict[str, Any]] | None = None
    comparison_scope_contract: dict[str, Any] | None = None
    numeric_scale_adoption: dict[str, Any] | None = None
    fit_year: int | None = None
    fit_months: tuple[int, ...] | None = None
    db1b_quarters: tuple[int, ...] | None = None
    passenger_manifest: str | dict[str, Any] | None = None
    scientific_status: str = "FROZEN"
    implementation_status: str = "MATCH"
    registry_hash: str = ""

    @model_validator(mode="after")
    def strict_freeze_contract(self):
        if self.final_test_access_count != 0:
            raise ContractError("M2_REGISTRY_FINAL_TEST_ACCESS_VIOLATION")
        if self.paper_full_run:
            raise ContractError("M2_REGISTRY_PAPER_FULL_VIOLATION")
        if self.registry_id == "M2_DATA2_FORMAL_CU_V1":
            if tuple(self.formal_scope) != LEGACY_FORMAL_SCOPE:
                raise ContractError("M2_FORMAL_SCOPE_MISMATCH")
        elif self.registry_id == "M2_DATA2_FORMAL_CU_V2":
            if set(self.formal_scope) != set(SEVEN_SCOPE) or len(
                self.formal_scope
            ) != len(set(self.formal_scope)):
                raise ContractError("M2_V2_FORMAL_SCOPE_MISMATCH")
            if not self.assumption_grounded or not self.assumption_scale_artifact:
                raise ContractError("M2_V2_ASSUMPTION_GROUNDED_MISSING")
        elif self.registry_id == "M2_DATA2_FORMAL_CU_V3":
            if tuple(self.formal_scope) != tuple(SEVEN_SCOPE) or len(self.formal_scope) != len(set(self.formal_scope)):
                raise ContractError("M2_V3_FORMAL_SCOPE_MISMATCH")
            if self.assumption_scale_artifact:
                raise ContractError("M2_V3_MUST_NOT_USE_ASSUMPTION_SCALES")
        elif self.registry_id == "M2_DATA2_FORMAL_CU_V4":
            if tuple(self.formal_scope) != tuple(CONSEQUENCE_COMPONENTS) or len(self.formal_scope) != 7 or len(set(self.formal_scope)) != 7:
                raise ContractError("M2_V4_FORMAL_SCOPE_MISMATCH")
            if self.assumption_scale_artifact:
                raise ContractError("M2_V4_MUST_NOT_USE_ASSUMPTION_SCALES")
            required_semantic_channels = {
                "P_service": {
                    "consequence_semantics": "passenger service / care burden",
                    "baseline_empirical_realization": "expected passengers x I[D_TO >= 180]",
                },
                "R_operating": {
                    "consequence_semantics": "operating / recovery-resource burden",
                    "baseline_empirical_realization": "D_TX",
                },
            }
            for component, expected in required_semantic_channels.items():
                if self.semantic_channels.get(component) != expected:
                    raise ContractError(f"M2_V4_SEMANTIC_CHANNEL_METADATA_MISMATCH:{component}")
        else:
            raise ContractError("M2_REGISTRY_IDENTITY_UNKNOWN")
        if set(self.component_weights) != set(self.formal_scope):
            raise ContractError("M2_COMPONENT_WEIGHT_SET_MISMATCH")
        if any(weight != 1.0 for weight in self.component_weights.values()):
            raise ContractError("M2_COMPONENT_WEIGHT_NOT_UNITY")
        assumption_components = set(self.assumption_scale_artifact or {})
        if self.registry_id in {"M2_DATA2_FORMAL_CU_V3", "M2_DATA2_FORMAL_CU_V4"} and set(self.train_scale_artifact) != set(SEVEN_SCOPE):
            raise ContractError("M2_V4_REQUIRES_SEVEN_TRAIN_SCALES" if self.registry_id == "M2_DATA2_FORMAL_CU_V4" else "M2_V3_REQUIRES_SEVEN_TRAIN_SCALES")
        missing = (
            set(self.formal_scope)
            - set(self.train_scale_artifact)
            - assumption_components
        )
        if missing:
            raise ContractError(f"M2_TRAIN_SCALE_ARTIFACT_MISSING:{sorted(missing)}")
        if self.registry_id == "M2_DATA2_FORMAL_CU_V2":
            expected_assumptions = {"P_itinerary", "P_service"}
            if assumption_components != expected_assumptions:
                raise ContractError("M2_V2_ASSUMPTION_NORMALIZATION_SET_MISMATCH")
            for component in expected_assumptions:
                item = self.assumption_scale_artifact[component]
                if item.get("normalization_status") != "ASSUMPTION_EVENT_NORMALIZATION":
                    raise ContractError("M2_V2_ASSUMPTION_NORMALIZATION_STATUS_INVALID")
                if item.get("empirical_train_positive_median") is not False:
                    raise ContractError("M2_V2_ASSUMPTION_SCALE_CANNOT_CLAIM_EMPIRICAL_MEDIAN")
        required = (
            {"turnaround", "taxi", "downstream_exposure", "expected_pax", "connection_share"}
            if self.registry_id in {"M2_DATA2_FORMAL_CU_V3", "M2_DATA2_FORMAL_CU_V4"}
            else {"turnaround", "taxi", "downstream_exposure", "passenger"}
        )
        if set(self.reference_artifacts) != required:
            if self.registry_id == "M2_DATA2_FORMAL_CU_V4":
                raise ContractError("M2_V4_PASSENGER_REFERENCE_ARTIFACT_MISSING")
            raise ContractError("M2_REFERENCE_ARTIFACT_SET_MISMATCH")
        if self.registry_id == "M2_DATA2_FORMAL_CU_V4":
            if self.fit_year != 2019 or tuple(self.fit_months or ()) != (1, 2, 3, 4, 5, 6) or tuple(self.db1b_quarters or ()) != (1, 2):
                raise ContractError("M2_V4_REFERENCE_PERIOD_MISMATCH")
            for component in SEVEN_SCOPE:
                item = self.train_scale_artifact.get(component, {})
                if item.get("fit_period") != "2019-H1":
                    raise ContractError("M2_V4_REFERENCE_PERIOD_MISMATCH")
                if not item.get("artifact_hash") or not item.get("path"):
                    raise ContractError("M2_V4_PASSENGER_REFERENCE_ARTIFACT_MISSING")
            expected_meta = self.reference_artifacts.get("expected_pax", {})
            connection_meta = self.reference_artifacts.get("connection_share", {})
            for meta in (expected_meta, connection_meta):
                if not meta.get("path") or not meta.get("artifact_hash"):
                    raise ContractError("M2_V4_PASSENGER_REFERENCE_ARTIFACT_MISSING")
        if self.registry_hash and self.registry_hash != self.digest():
            raise ContractError("M2_REGISTRY_HASH_MISMATCH")
        return self

    def registry_payload(self) -> dict:
        payload = self.model_dump(mode="json")
        payload.pop("registry_hash", None)
        if self.registry_id == "M2_DATA2_FORMAL_CU_V2":
            payload.pop("outside_principal_scope", None)
        if payload.get("assumption_grounded") is None:
            payload.pop("assumption_grounded", None)
        if payload.get("assumption_scale_artifact") is None:
            payload.pop("assumption_scale_artifact", None)
        if payload.get("comparison_scope_contract") is None:
            payload.pop("comparison_scope_contract", None)
        if payload.get("numeric_scale_adoption") is None:
            payload.pop("numeric_scale_adoption", None)
        for name in ("fit_year", "fit_months", "db1b_quarters", "passenger_manifest"):
            if payload.get(name) is None:
                payload.pop(name, None)
        return payload

    def digest(self) -> str:
        return content_id(self.registry_payload())

    def scale(self, component: str) -> float:
        assumption = (self.assumption_scale_artifact or {}).get(component)
        if assumption is not None:
            value = float(assumption["scale"])
        else:
            value = float(self.train_scale_artifact[component]["median"])
        if not value > 0:
            raise ContractError(f"M2_TRAIN_SCALE_NOT_POSITIVE:{component}")
        return value

    def component_definition(self, component: str) -> str:
        scale = self.train_scale_artifact.get(component)
        if scale is not None:
            return str(
                scale.get(
                    "active_quantity_definition",
                    scale.get(
                        "definition",
                        self.native_quantity_definitions.get(component, {}).get(
                            "definition", component
                        ),
                    ),
                )
            )
        return self.native_quantity_definitions[component]["definition"]


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _artifact_hash(payload: dict) -> str:
    return content_id(payload)


def reference_to_payload(reference) -> dict:
    """Serialize a frozen Data2 reference dataclass to its payload form.

    Mirrors the exact keys expected by the corresponding
    data2_*_reference_from_payload loaders (round-trip stable).
    """
    if isinstance(reference, Data2TurnaroundReference):
        return {
            "reference_id": reference.reference_id,
            "dataset_instance_id": reference.dataset_instance_id,
            "rule_id": reference.rule_id,
            "rule_version": reference.rule_version,
            "fit_period": reference.fit_period,
            "statistic_id": reference.statistic_id,
            "minimum_support_rule": reference.minimum_support_rule,
            "fallback_hierarchy": list(reference.fallback_hierarchy),
            "applicability_scope": reference.applicability_scope,
            "global_value_minutes": reference.global_value_minutes,
            "global_sample_count": reference.global_sample_count,
            "cells": [
                {
                    "airport_id": cell.airport_id,
                    "value_minutes": cell.value_minutes,
                    "sample_count": cell.sample_count,
                    "fallback_level": cell.fallback_level,
                    "provenance": list(cell.provenance),
                }
                for cell in reference.cells
            ],
            "cells_count": len(reference.cells),
            "manifest_freeze_id": reference.manifest_freeze_id,
            "support_state": reference.support_state.value,
            "reason_code": reference.reason_code,
        }
    if isinstance(reference, Data2TaxiReference):
        return {
            "reference_id": reference.reference_id,
            "dataset_instance_id": reference.dataset_instance_id,
            "rule_id": reference.rule_id,
            "rule_version": reference.rule_version,
            "fit_period": reference.fit_period,
            "statistic_id": reference.statistic_id,
            "minimum_support_rule": reference.minimum_support_rule,
            "fallback_hierarchy": list(reference.fallback_hierarchy),
            "applicability_scope": reference.applicability_scope,
            "global_value_minutes": reference.global_value_minutes,
            "global_sample_count": reference.global_sample_count,
            "cells": [
                {
                    "airport_id": cell.airport_id,
                    "value_minutes": cell.value_minutes,
                    "sample_count": cell.sample_count,
                    "fallback_level": cell.fallback_level,
                    "provenance": list(cell.provenance),
                }
                for cell in reference.cells
            ],
            "cells_count": len(reference.cells),
            "manifest_freeze_id": reference.manifest_freeze_id,
            "support_state": reference.support_state.value,
            "reason_code": reference.reason_code,
        }
    if isinstance(reference, Data2ExposureReference):
        return {
            "reference_id": reference.reference_id,
            "dataset_instance_id": reference.dataset_instance_id,
            "rule_id": reference.rule_id,
            "rule_version": reference.rule_version,
            "fit_period": reference.fit_period,
            "statistic_id": reference.statistic_id,
            "minimum_support_rule": reference.minimum_support_rule,
            "fallback_hierarchy": list(reference.fallback_hierarchy),
            "applicability_scope": reference.applicability_scope,
            "horizon_minutes": reference.horizon_minutes,
            "global_value_legs": reference.global_value_legs,
            "global_sample_count": reference.global_sample_count,
            "cells": [
                {
                    "airport_id": cell.airport_id,
                    "value_legs": cell.value_legs,
                    "sample_count": cell.sample_count,
                    "fallback_level": cell.fallback_level,
                    "provenance": list(cell.provenance),
                }
                for cell in reference.cells
            ],
            "cells_count": len(reference.cells),
            "manifest_freeze_id": reference.manifest_freeze_id,
            "support_state": reference.support_state.value,
            "reason_code": reference.reason_code,
        }
    if isinstance(reference, Data2PassengerReference):
        return {
            "reference_id": reference.reference_id,
            "dataset_instance_id": reference.dataset_instance_id,
            "rule_id": reference.rule_id,
            "rule_version": reference.rule_version,
            "fit_period": reference.fit_period,
            "statistic_id": reference.statistic_id,
            "scale_factor": reference.scale_factor,
            "minimum_support_rule": reference.minimum_support_rule,
            "fallback_hierarchy": list(reference.fallback_hierarchy),
            "applicability_scope": reference.applicability_scope,
            "total_passengers": reference.total_passengers,
            "total_sample_count": reference.total_sample_count,
            "route_count": reference.route_count,
            "cells": [
                {
                    "origin": cell.origin_airport_id,
                    "destination": cell.destination_airport_id,
                    "value_passengers": cell.value_passengers,
                    "sample_count": cell.sample_count,
                    "provenance": list(cell.provenance),
                }
                for cell in reference.cells
            ],
            "cells_count": len(reference.cells),
            "manifest_freeze_id": reference.manifest_freeze_id,
            "support_state": reference.support_state.value,
            "reason_code": reference.reason_code,
        }
    raise ContractError("M2_REFERENCE_SERIALIZATION_UNSUPPORTED")


def build_m2_data2_formal_registry(
    *,
    root: Path,
    artifact_dir: Path,
    fit_period: str = "2019-H1",
) -> tuple[M2Data2FormalCuRegistry, dict[str, Path]]:
    """Materialize and load the active M2 V4 registry."""
    if REGISTRY_ID == "M2_DATA2_FORMAL_CU_V4":
        registry_path = root / "registries" / "m2_data2_formal_cu_v4.json"
        if not registry_path.is_file():
            raise ContractError("M2_V4_PASSENGER_REFERENCE_ARTIFACT_MISSING")
        return load_m2_registry(registry_path), {"registry": registry_path}
    preparation = build_data2_m2_train_preparation(
        root=root,
        months=tuple(range(1, 7)),
        fit_period=fit_period,
    )
    rows = preparation.rows
    references = fit_train_references(rows, root=root, fit_period=fit_period)
    turnaround_ref = data2_turnaround_reference_from_payload(references["turnaround"])
    taxi_ref = data2_taxi_reference_from_payload(references["taxi"])
    exposure_ref = data2_downstream_exposure_from_payload(
        references["downstream_exposure"]
    )
    passenger_ref = data2_passenger_reference_from_payload(references["passenger"])

    written: dict[str, Path] = {}
    reference_files = {
        "turnaround": "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json",
        "downstream_exposure": "DATA2_DOWNSTREAM_EXPOSURE_REFERENCE_TRAIN_FROZEN_V1.json",
        "passenger": "DATA2_PASSENGER_REFERENCE_H1_TRAIN_FROZEN_V1.json",
        "taxi": "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json",
    }
    reference_artifacts = {}
    for name, filename in reference_files.items():
        path = artifact_dir / filename
        _write_json_atomic(path, references[name])
        written[name] = path
        reference = (
            turnaround_ref
            if name == "turnaround"
            else (
                taxi_ref
                if name == "taxi"
                else passenger_ref if name == "passenger" else exposure_ref
            )
        )
        reference_artifacts[name] = {
            "path": str(path.relative_to(root)),
            "artifact_hash": references[name]["artifact_hash"],
            "reference_id": reference.reference_id,
            "manifest_freeze_id": reference.manifest_freeze_id,
        }

    scales = compute_train_scales(
        rows,
        references,
        turnaround_ref=turnaround_ref,
        taxi_ref=taxi_ref,
        exposure_ref=exposure_ref,
        passenger_ref=passenger_ref,
    )
    scales_path = artifact_dir / "M2_DATA2_TRAIN_SCALES_V1.json"
    scales_payload = {
        "schema_version": "M2_DATA2_TRAIN_SCALES_V1",
        "registry_id": REGISTRY_ID,
        "fit_period": fit_period,
        "scale_rule": "POSITIVE_TRAIN_PERIOD_MEDIAN",
        "components": scales,
        "final_test_access_count": 0,
        "paper_full_run": False,
    }
    scales_payload["artifact_hash"] = _artifact_hash(scales_payload)
    _write_json_atomic(scales_path, scales_payload)
    written["scales"] = scales_path

    registry = M2Data2FormalCuRegistry(
        train_scale_artifact={
            name: {
                **scales[name],
                "path": str(scales_path.relative_to(root)),
                "artifact_hash": scales_payload["artifact_hash"],
            }
            for name in FORMAL_SCOPE
        },
        reference_artifacts=reference_artifacts,
        component_weights={name: 1.0 for name in FORMAL_SCOPE},
        native_quantity_definitions=dict(M2_NATIVE_DEFINITIONS),
    )
    registry = registry.model_copy(update={"registry_hash": registry.digest()})
    return registry, written


def write_m2_registry(
    registry: M2Data2FormalCuRegistry,
    *,
    registry_path: Path,
    manifest_path: Path,
    root: Path,
) -> tuple[Path, Path]:
    payload = registry.registry_payload()
    payload["registry_hash"] = registry.digest()
    if registry_path.exists():
        raise ContractError("M2_REGISTRY_ALREADY_EXISTS")
    _write_json_atomic(registry_path, payload)
    manifest = {
        "manifest_version": "1.0.0",
        "registry_id": registry.registry_id,
        "registry_path": str(registry_path.relative_to(root)),
        "registry_sha256": content_id(payload),
        "formal_scope": list(registry.formal_scope),
        "aggregation_rule": registry.aggregation_rule,
        "support_rule": registry.support_rule,
        "reference_ids": {
            name: item["reference_id"]
            for name, item in registry.reference_artifacts.items()
        },
        "final_test_access_count": 0,
        "paper_full_run": False,
    }
    _write_json_atomic(manifest_path, manifest)
    return registry_path, manifest_path


class FrozenData2CUNormalizationRegistry(M2CUNormalizationAdapter):
    """Production CU-normalization adapter consuming the frozen M2 scales.

    C_k^CU = q_k / s_k_CU where s_k_CU is the train-frozen median scale.
    Monetary mapping is deliberately separate and lives in M4.
    """

    def __init__(self, registry: M2Data2FormalCuRegistry | Mapping):
        if not isinstance(registry, M2Data2FormalCuRegistry):
            registry = M2Data2FormalCuRegistry.model_validate(registry)
        cu_registry = CUNormalizationRegistry.from_scales(
            registry_id=registry.registry_id,
            version=registry.schema_version,
            freeze_id=registry.registry_id,
            reference_period="2019-H1",
            scales={
                component: registry.scale(component)
                for component in registry.formal_scope
            },
            provenance=tuple(
                f"{component}={registry.component_definition(component)}"
                for component in registry.formal_scope
            ),
        )
        super().__init__(cu_registry)


class FrozenData2ValuationRegistry(FrozenData2CUNormalizationRegistry):
    """Deprecated compatibility alias of FrozenData2CUNormalizationRegistry."""


def load_m2_registry(path: Path) -> M2Data2FormalCuRegistry:
    payload = json.loads(path.read_text(encoding="utf-8"))
    registry = M2Data2FormalCuRegistry.model_validate(payload)
    if registry.registry_hash != registry.digest():
        raise ContractError("M2_REGISTRY_HASH_MISMATCH")
    return registry


__all__ = [
    "AGGREGATION_RULE",
    "FORMAL_SCOPE",
    "FrozenData2ValuationRegistry",
    "M2Data2FormalCuRegistry",
    "REGISTRY_ID",
    "SCHEMA_VERSION",
    "SUPPORT_RULE",
    "build_m2_data2_formal_registry",
    "load_m2_registry",
    "reference_to_payload",
    "write_m2_registry",
]
