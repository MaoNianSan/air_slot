"""Typed, lineage-preserving representation adapters for Exp2.

This module transforms frozen M1/M2 outputs only.  It contains no model
training, M2 consequence reconstruction, action response, monetary mapping,
or risk evaluation logic.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.errors import ContractError
from model.common.identity import content_id

from .variants import (
    EXP2A_POINT,
    EXP2A_JOINT,
    EXP2A_MARGINAL,
    EXP2A_VARIANTS,
    EXP2B_3CHANNEL,
    EXP2B_7COMP,
    EXP2B_SCALAR,
    EXP2B_VARIANTS,
)


SCENARIO_FIELDS = ("D_OB", "D_TX", "D_TO")
CHANNELS = ("Flight", "Passenger", "Resource")


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    raise TypeError("EXP2_TYPED_OR_SERIALIZED_ARTIFACT_REQUIRED")


def _tuple_lineage(value: Any) -> tuple[str, ...]:
    if isinstance(value, str) and value.strip():
        return (value,)
    if isinstance(value, (tuple, list)) and value and all(str(item).strip() for item in value):
        return tuple(str(item) for item in value)
    return ()


class ScenarioSample(BaseModel):
    """The exact Exp2A scenario surface, independent of M1 implementation details."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_id: int | str
    scenario_weight: float = Field(gt=0, le=1)
    D_OB: float | None
    D_TX: float | None
    D_TO: float | None
    lineage: tuple[str, ...] = Field(min_length=1)
    field_source_scenario_ids: dict[str, int | str]

    @model_validator(mode="after")
    def valid_sample(self):
        if any(value is not None and value < 0 for value in (self.D_OB, self.D_TX, self.D_TO)):
            raise ValueError("EXP2_SCENARIO_DELAY_NEGATIVE")
        if set(self.field_source_scenario_ids) != set(SCENARIO_FIELDS):
            raise ValueError("EXP2_SCENARIO_FIELD_LINEAGE_INCOMPLETE")
        return self


class ScenarioRepresentation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    variant_id: Literal[
        "EXP2A_POINT", "EXP2A_MARGINAL", "EXP2A_JOINT"
    ]
    artifact_version: str = Field(min_length=1)
    source_scenario_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_sample_count: int = Field(gt=0)
    samples: tuple[ScenarioSample, ...] = Field(min_length=1)
    transform_rule: str = Field(min_length=1)
    transform_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_distribution(self):
        if abs(sum(item.scenario_weight for item in self.samples) - 1.0) > 1e-6:
            raise ValueError("EXP2_SCENARIO_WEIGHTS_MUST_SUM_TO_ONE")
        ids = tuple(item.scenario_id for item in self.samples)
        if len(ids) != len(set(ids)):
            raise ValueError("EXP2_SCENARIO_ID_DUPLICATE")
        if self.variant_id == EXP2A_POINT and len(self.samples) != 1:
            raise ValueError("EXP2_POINT_REQUIRES_ONE_SCENARIO")
        if self.variant_id != EXP2A_POINT and len(self.samples) != self.source_sample_count:
            raise ValueError("EXP2_SCENARIO_COUNT_NOT_PRESERVED")
        return self

    @property
    def representation_hash(self) -> str:
        return content_id(self.model_dump(mode="json"))


class ScenarioRepresentationAdapter:
    """Build POINT/MARGINAL/JOINT views of one immutable M1 artifact."""

    def __init__(
        self,
        scenarios: Iterable[Any],
        *,
        artifact_version: str,
        scenario_hash: str | None = None,
    ):
        if not str(artifact_version).strip():
            raise ValueError("EXP2_M1_ARTIFACT_VERSION_REQUIRED")
        rows = tuple(self._normalize(item) for item in scenarios)
        if not rows:
            raise ContractError("EXP2_SCENARIO_ARTIFACT_EMPTY")
        if len({item.scenario_id for item in rows}) != len(rows):
            raise ContractError("EXP2_SCENARIO_ID_DUPLICATE")
        if abs(sum(item.scenario_weight for item in rows) - 1.0) > 1e-6:
            raise ContractError("EXP2_SCENARIO_WEIGHTS_MUST_SUM_TO_ONE")
        self._rows = rows
        self.artifact_version = artifact_version
        self.source_content_hash = content_id(
            tuple(item.model_dump(mode="json") for item in rows)
        )
        self.scenario_hash = scenario_hash or self.source_content_hash
        if not self.scenario_hash.startswith("sha256:") or len(self.scenario_hash) != 71:
            raise ValueError("EXP2_SCENARIO_HASH_INVALID")

    @staticmethod
    def _normalize(value: Any) -> ScenarioSample:
        row = _mapping(value)
        scenario_id = row.get("scenario_id")
        if scenario_id is None:
            raise ValueError("EXP2_SCENARIO_ID_REQUIRED")
        weight = row.get("scenario_weight")
        if weight is None:
            raise ValueError("EXP2_SCENARIO_WEIGHT_REQUIRED")
        d_ob = row.get("D_OB", row.get("d_ob_minutes"))
        d_tx = row.get("D_TX", row.get("d_tx_minutes"))
        d_to = row.get("D_TO", row.get("d_to_minutes"))
        if d_to is None and d_ob is not None and d_tx is not None:
            d_to = float(d_ob) + float(d_tx)
        if d_to is not None and (
            d_ob is None
            or d_tx is None
            or abs(float(d_to) - (float(d_ob) + float(d_tx))) > 1e-6
        ):
            raise ValueError("EXP2_SOURCE_D_TO_IDENTITY_VIOLATION")

        lineage = _tuple_lineage(row.get("lineage"))
        if not lineage:
            seed_key = row.get("scenario_seed_key")
            if seed_key:
                lineage = (f"M1_SCENARIO_SEED:{seed_key}",)
        if not lineage:
            raise ValueError("EXP2_SCENARIO_LINEAGE_REQUIRED")
        return ScenarioSample(
            scenario_id=scenario_id,
            scenario_weight=float(weight),
            D_OB=None if d_ob is None else float(d_ob),
            D_TX=None if d_tx is None else float(d_tx),
            D_TO=None if d_to is None else float(d_to),
            lineage=lineage,
            field_source_scenario_ids={field: scenario_id for field in SCENARIO_FIELDS},
        )

    @property
    def source_samples(self) -> tuple[ScenarioSample, ...]:
        return self._rows

    def transform(self, variant_id: str) -> ScenarioRepresentation:
        if variant_id not in EXP2A_VARIANTS:
            raise KeyError(f"EXP2A_VARIANT_UNKNOWN:{variant_id}")
        before = self.source_content_hash
        if variant_id == EXP2A_JOINT:
            samples = tuple(item.model_copy(deep=True) for item in self._rows)
            rule = "IDENTITY_PRESERVE_FROZEN_JOINT_SAMPLES"
            metadata = {"joint_dependency_preserved": True, "marginals_preserved": True}
        elif variant_id == EXP2A_MARGINAL:
            samples, metadata = self._marginal_samples()
            rule = "DETERMINISTIC_WITHIN_WEIGHT_STRATUM_INDEPENDENT_FIELD_PERMUTATION"
        else:
            samples = (self._point_sample(),)
            rule = "WEIGHTED_JOINT_SCENARIO_MEDOID"
            metadata = {
                "joint_dependency_preserved": False,
                "marginals_preserved": False,
                "coherent_joint_scenario": True,
            }
        if content_id(tuple(item.model_dump(mode="json") for item in self._rows)) != before:
            raise ContractError("EXP2_MUTATED_M1_ARTIFACT")
        return ScenarioRepresentation(
            variant_id=variant_id,
            artifact_version=self.artifact_version,
            source_scenario_hash=self.scenario_hash,
            source_sample_count=len(self._rows),
            samples=samples,
            transform_rule=rule,
            transform_metadata=metadata,
        )

    def _point_sample(self) -> ScenarioSample:
        """Select a real weighted joint medoid instead of component-wise means."""
        def distance(candidate: ScenarioSample) -> float:
            total = 0.0
            for row in self._rows:
                squared = 0.0
                for field in SCENARIO_FIELDS:
                    left, right = getattr(candidate, field), getattr(row, field)
                    if left is not None and right is not None:
                        squared += (float(left) - float(right)) ** 2
                total += row.scenario_weight * squared
            return total

        selected = min(enumerate(self._rows), key=lambda item: (distance(item[1]), item[0]))[1]
        return ScenarioSample(
            scenario_id=f"POINT:{selected.scenario_id}",
            scenario_weight=1.0,
            D_OB=selected.D_OB,
            D_TX=selected.D_TX,
            D_TO=selected.D_TO,
            lineage=selected.lineage,
            field_source_scenario_ids={field: selected.scenario_id for field in SCENARIO_FIELDS},
        )

    def _marginal_samples(self) -> tuple[tuple[ScenarioSample, ...], dict[str, Any]]:
        weights = {item.scenario_weight for item in self._rows}
        if len(weights) != 1:
            raise ContractError("BLOCKED_WEIGHTED_TRANSFORM_NOT_IMPLEMENTED")
        groups: dict[float, list[int]] = defaultdict(list)
        for index, item in enumerate(self._rows):
            groups[item.scenario_weight].append(index)

        sources = {field: list(range(len(self._rows))) for field in ("D_OB", "D_TX")}
        offsets = {"D_OB": 0, "D_TX": 1}
        for field in ("D_OB", "D_TX"):
            for indices in groups.values():
                if len(indices) <= 1:
                    continue
                shift = offsets[field] % len(indices)
                rotated = indices[shift:] + indices[:shift]
                for target, source in zip(indices, rotated, strict=True):
                    sources[field][target] = source

        output = []
        for target, original in enumerate(self._rows):
            source_rows = {field: self._rows[sources[field][target]] for field in ("D_OB", "D_TX")}
            lineage = tuple(dict.fromkeys(
                entry
                for field in ("D_OB", "D_TX")
                for entry in source_rows[field].lineage
            ))
            d_ob = source_rows["D_OB"].D_OB
            d_tx = source_rows["D_TX"].D_TX
            output.append(ScenarioSample(
                scenario_id=original.scenario_id,
                scenario_weight=original.scenario_weight,
                D_OB=d_ob,
                D_TX=d_tx,
                D_TO=None if d_ob is None or d_tx is None else d_ob + d_tx,
                lineage=lineage,
                field_source_scenario_ids={
                    "D_OB": source_rows["D_OB"].scenario_id,
                    "D_TX": source_rows["D_TX"].scenario_id,
                    "D_TO": "DERIVED_FROM_D_OB_PLUS_D_TX",
                },
            ))

        def weighted_marginal(rows: tuple[ScenarioSample, ...] | list[ScenarioSample], field: str):
            return sorted(
                ((getattr(item, field), item.scenario_weight) for item in rows),
                key=lambda pair: (pair[0] is None, pair[0], pair[1]),
            )

        preserved = all(
            weighted_marginal(self._rows, field) == weighted_marginal(output, field)
            for field in ("D_OB", "D_TX")
        )
        if not preserved:
            raise ContractError("EXP2_MARGINAL_DISTRIBUTION_NOT_PRESERVED")
        return tuple(output), {
            "joint_dependency_preserved": False,
            "marginals_preserved": True,
            "field_source_scenario_ids": {
                field: tuple(self._rows[index].scenario_id for index in indices)
                for field, indices in sources.items()
            },
            "D_TO": "RECOMPUTED_SAMPLEWISE_FROM_D_OB_PLUS_D_TX",
        }


class ConsequenceValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value_id: str = Field(min_length=1)
    channel: Literal["Flight", "Passenger", "Resource", "ALL"]
    value_cu: float | None
    support_status: str = Field(min_length=1)
    source_component_ids: tuple[str, ...] = Field(min_length=1)
    lineage: tuple[str, ...] = Field(min_length=1)


class ScenarioConsequenceRepresentation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_id: int | str
    scenario_weight: float = Field(gt=0, le=1)
    values: tuple[ConsequenceValue, ...] = Field(min_length=1)


class ConsequenceRepresentation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    variant_id: Literal["EXP2B_SCALAR", "EXP2B_3CHANNEL", "EXP2B_7COMP"]
    artifact_version: str = Field(min_length=1)
    source_artifact_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    scenarios: tuple[ScenarioConsequenceRepresentation, ...] = Field(min_length=1)
    aggregation_rule: str = Field(min_length=1)

    @model_validator(mode="after")
    def normalized_weights(self):
        if abs(sum(item.scenario_weight for item in self.scenarios) - 1.0) > 1e-6:
            raise ValueError("EXP2_CONSEQUENCE_WEIGHTS_MUST_SUM_TO_ONE")
        return self

    @property
    def representation_hash(self) -> str:
        return content_id(self.model_dump(mode="json"))


class ConsequenceRepresentationAdapter:
    """Aggregate M2-emitted CU values without recomputing M2 quantities."""

    def __init__(self, consequences: Any, *, artifact_version: str):
        if hasattr(consequences, "consequences"):
            consequences = consequences.consequences
        rows = tuple(self._normalize_scenario(item) for item in consequences)
        if not rows:
            raise ContractError("EXP2_M2_CONSEQUENCE_ARTIFACT_EMPTY")
        if abs(sum(item[1] for item in rows) - 1.0) > 1e-6:
            raise ContractError("EXP2_CONSEQUENCE_WEIGHTS_MUST_SUM_TO_ONE")
        self._rows = rows
        self.artifact_version = artifact_version
        self.source_artifact_hash = content_id(rows)

    @staticmethod
    def _normalize_scenario(value: Any):
        raw = _mapping(value)
        scenario_id = raw.get("scenario_id")
        weight = raw.get("scenario_weight")
        if scenario_id is None or weight is None:
            raise ValueError("EXP2_M2_SCENARIO_ID_WEIGHT_REQUIRED")
        vector = raw.get("component_vector")
        if isinstance(vector, Mapping):
            components = vector.get("rows")
        else:
            components = getattr(vector, "rows", None)
        components = components or raw.get("components")
        if not components:
            raise ValueError("EXP2_M2_SEVEN_COMPONENT_VECTOR_REQUIRED")
        normalized = []
        for component in components:
            item = _mapping(component)
            component_id = str(item.get("component_id", ""))
            support = item.get("support_state", "ABSTAIN")
            support = support.value if hasattr(support, "value") else str(support)
            lineage = _tuple_lineage(item.get("reference_lineage"))
            if not lineage and item.get("reference_lineage_hash"):
                lineage = (str(item["reference_lineage_hash"]),)
            if not lineage:
                raise ValueError("EXP2_M2_COMPONENT_LINEAGE_REQUIRED")
            normalized.append({
                "component_id": component_id,
                "channel": str(item.get("aspect", "")),
                "value_cu": item.get("constructed_value_cu", item.get("value_cu")),
                "support_status": support,
                "lineage": lineage,
            })
        if tuple(item["component_id"] for item in normalized) != CONSEQUENCE_COMPONENTS:
            raise ValueError("EXP2_M2_EXACT_SEVEN_COMPONENTS_REQUIRED")
        if set(item["channel"] for item in normalized) - set(CHANNELS):
            raise ValueError("EXP2_M2_OPERATIONAL_CHANNEL_UNKNOWN")
        return scenario_id, float(weight), tuple(normalized)

    def transform(self, variant_id: str) -> ConsequenceRepresentation:
        if variant_id not in EXP2B_VARIANTS:
            raise KeyError(f"EXP2B_VARIANT_UNKNOWN:{variant_id}")
        before = self.source_artifact_hash
        scenarios = []
        for scenario_id, weight, components in deepcopy(self._rows):
            if variant_id == EXP2B_7COMP:
                values = tuple(
                    ConsequenceValue(
                        value_id=item["component_id"],
                        channel=item["channel"],
                        value_cu=item["value_cu"],
                        support_status=item["support_status"],
                        source_component_ids=(item["component_id"],),
                        lineage=item["lineage"],
                    )
                    for item in components
                )
                rule = "IDENTITY_PRESERVE_SEVEN_M2_COMPONENTS"
            elif variant_id == EXP2B_3CHANNEL:
                values = tuple(
                    self._aggregate(
                        value_id=channel,
                        channel=channel,
                        components=tuple(item for item in components if item["channel"] == channel),
                    )
                    for channel in CHANNELS
                )
                rule = "SUM_M2_EMITTED_CU_WITH_COMPLETE_CHANNEL_SUPPORT"
            else:
                values = (self._aggregate(
                    value_id="ALL_CONSEQUENCE",
                    channel="ALL",
                    components=components,
                ),)
                rule = "SUM_M2_EMITTED_CU_WITH_COMPLETE_SEVEN_COMPONENT_SUPPORT"
            scenarios.append(ScenarioConsequenceRepresentation(
                scenario_id=scenario_id,
                scenario_weight=weight,
                values=values,
            ))
        if content_id(self._rows) != before:
            raise ContractError("EXP2_MUTATED_M2_ARTIFACT")
        return ConsequenceRepresentation(
            variant_id=variant_id,
            artifact_version=self.artifact_version,
            source_artifact_hash=self.source_artifact_hash,
            scenarios=tuple(scenarios),
            aggregation_rule=rule,
        )

    @staticmethod
    def _aggregate(*, value_id: str, channel: str, components: tuple[dict, ...]) -> ConsequenceValue:
        if not components:
            raise ValueError("EXP2_AGGREGATION_COMPONENT_SET_EMPTY")
        supported = all(
            item["value_cu"] is not None and item["support_status"] != "ABSTAIN"
            for item in components
        )
        value = sum(float(item["value_cu"]) for item in components) if supported else None
        status = "SUPPORTED" if supported else "ABSTAINED"
        lineage = tuple(dict.fromkeys(
            entry for item in components for entry in item["lineage"]
        ))
        return ConsequenceValue(
            value_id=value_id,
            channel=channel,
            value_cu=value,
            support_status=status,
            source_component_ids=tuple(item["component_id"] for item in components),
            lineage=lineage,
        )


__all__ = [
    "CHANNELS",
    "ConsequenceRepresentation",
    "ConsequenceRepresentationAdapter",
    "ConsequenceValue",
    "SCENARIO_FIELDS",
    "ScenarioConsequenceRepresentation",
    "ScenarioRepresentation",
    "ScenarioRepresentationAdapter",
    "ScenarioSample",
]
