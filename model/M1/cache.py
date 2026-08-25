from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import torch

from model.common.identity import content_id

from .data import M1NormalizationArtifact
from .lifecycle import M1TrainingExample
from .static_features import (
    M1StaticNormalizationArtifact,
    STATIC_FEATURE_COUNT,
    STATIC_FEATURE_NAMES,
)

CACHE_SCHEMA_VERSION = "M1_V2_DEVELOPMENT_BASE_CACHE_V4"
LEGACY_CACHE_SCHEMA_VERSIONS = ("M1_V2_DEVELOPMENT_BASE_CACHE_V3",)
TARGET_NAMES = ("T_IB_REMAINING_HAZARD", "D_OB", "D_TX")
ALLOWED_SPLITS = ("train", "calibration", "development")
REQUIRED_CONTRACT_HASHES = (
    "PRE_contract_hash",
    "episode_contract_hash",
    "episode_construction_hash",
    "feature_contract_hash",
    "split_contract_hash",
    "roll_contract_hash",
    "normalization_contract_hash",
)


def _lineage_json_default(value):
    if isinstance(value, datetime):
        return {"__m1_lineage_type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__m1_lineage_type__": "date", "value": value.isoformat()}
    raise TypeError(f"M1_CACHE_LINEAGE_JSON_UNSUPPORTED:{type(value).__name__}")


def _lineage_json_object_hook(value):
    kind = value.get("__m1_lineage_type__")
    if kind == "datetime":
        return datetime.fromisoformat(value["value"])
    if kind == "date":
        return date.fromisoformat(value["value"])
    return value


def _lineage_dumps(value) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=_lineage_json_default,
    )


def _lineage_loads(value: str):
    return json.loads(value, object_hook=_lineage_json_object_hook)


def _update_hash(hasher, value) -> None:
    if isinstance(value, torch.Tensor):
        array = value.detach().cpu().contiguous().numpy()
        hasher.update(str(array.dtype).encode("ascii"))
        hasher.update(json.dumps(array.shape).encode("ascii"))
        hasher.update(array.tobytes(order="C"))
        return
    encoded = str(value).encode("utf-8")
    hasher.update(len(encoded).to_bytes(8, "big"))
    hasher.update(encoded)


def _stable_store_hash(store: "M1CanonicalRaggedStore") -> str:
    hasher = sha256()
    for value in (
        store.values_flat,
        store.episode_offsets,
        store.episode_ids,
        store.sample_episode_indices,
        store.sample_start_offsets,
        store.sample_end_offsets,
        store.sample_episode_ids,
        store.sample_decision_node_ids,
        store.sample_episode_dates,
        store.sample_splits,
        store.static_values,
    ):
        if isinstance(value, tuple):
            for item in value:
                _update_hash(hasher, item)
        else:
            _update_hash(hasher, value)
    for name in TARGET_NAMES:
        _update_hash(hasher, store.labels[name])
        _update_hash(hasher, store.active[name])
    for lineage in store.static_context_lineages:
        _update_hash(
            hasher,
            "" if lineage is None else _lineage_dumps(lineage),
        )
    return f"sha256:{hasher.hexdigest()}"


@dataclass(frozen=True)
class M1CanonicalRaggedStore:
    values_flat: torch.Tensor
    episode_offsets: torch.Tensor
    episode_ids: tuple[str, ...]
    sample_episode_indices: torch.Tensor
    sample_start_offsets: torch.Tensor
    sample_end_offsets: torch.Tensor
    sample_episode_ids: tuple[str, ...]
    sample_decision_node_ids: tuple[str, ...]
    sample_episode_dates: tuple[str, ...]
    sample_splits: tuple[str, ...]
    static_values: torch.Tensor | None
    static_context_lineages: tuple[dict[str, object] | None, ...]
    labels: Mapping[str, torch.Tensor]
    active: Mapping[str, torch.Tensor]

    @classmethod
    def from_partitions(cls, partitions: Mapping[str, Sequence[M1TrainingExample]]):
        unknown = set(partitions) - set(ALLOWED_SPLITS)
        if unknown:
            raise ValueError(f"M1_CACHE_SPLIT_NOT_ALLOWED:{sorted(unknown)}")
        samples: list[tuple[str, M1TrainingExample]] = []
        canonical: dict[str, torch.Tensor] = {}
        for split in ALLOWED_SPLITS:
            for example in partitions.get(split, ()):
                if example.episode_date >= date(2019, 10, 1):
                    raise ValueError("M1_CACHE_FINAL_TEST_EXAMPLE_REJECTED")
                values = (
                    example.values.detach().cpu().to(dtype=torch.float32).contiguous()
                )
                previous = canonical.get(example.episode_id)
                if previous is None or len(values) > len(previous):
                    if previous is not None and not torch.equal(
                        values[: len(previous)], previous
                    ):
                        raise ValueError("M1_CACHE_NONCANONICAL_EPISODE_PREFIX")
                    canonical[example.episode_id] = values
                elif not torch.equal(previous[: len(values)], values):
                    raise ValueError("M1_CACHE_NONCANONICAL_EPISODE_PREFIX")
                samples.append((split, example))

        episode_ids = tuple(sorted(canonical))
        episode_index = {
            episode_id: index for index, episode_id in enumerate(episode_ids)
        }
        values_parts = [canonical[episode_id] for episode_id in episode_ids]
        feature_count = values_parts[0].shape[1] if values_parts else 0
        values_flat = (
            torch.cat(values_parts, dim=0)
            if values_parts
            else torch.empty((0, feature_count), dtype=torch.float32)
        )
        offsets = [0]
        for values in values_parts:
            offsets.append(offsets[-1] + len(values))

        sample_episode_indices = torch.tensor(
            [episode_index[example.episode_id] for _, example in samples],
            dtype=torch.int32,
        )
        sample_start_offsets = torch.zeros(len(samples), dtype=torch.int32)
        sample_end_offsets = torch.tensor(
            [len(example.values) for _, example in samples], dtype=torch.int32
        )
        labels = {
            name: torch.tensor(
                [
                    (
                        -1.0
                        if example.targets.get(name) is None
                        else float(example.targets[name])
                    )
                    for _, example in samples
                ],
                dtype=torch.float32,
            )
            for name in TARGET_NAMES
        }
        active = {
            name: torch.tensor(
                [example.active[name] for _, example in samples], dtype=torch.bool
            )
            for name in TARGET_NAMES
        }
        static_widths = {
            int(example.static_values.numel())
            for _, example in samples
            if example.static_values is not None
        }
        if len(static_widths) > 1:
            raise ValueError("M1_CACHE_STATIC_FEATURE_WIDTH_MISMATCH")
        static_values = None
        if static_widths:
            if any(example.static_values is None for _, example in samples):
                raise ValueError("M1_CACHE_PARTIAL_STATIC_BLOCK_REJECTED")
            width = static_widths.pop()
            static_values = torch.stack(
                [
                    example.static_values.detach()
                    .cpu()
                    .reshape(-1)
                    .to(dtype=torch.float32)
                    .contiguous()
                    for _, example in samples
                ]
            )
        return cls(
            values_flat=values_flat,
            episode_offsets=torch.tensor(offsets, dtype=torch.int64),
            episode_ids=episode_ids,
            sample_episode_indices=sample_episode_indices,
            sample_start_offsets=sample_start_offsets,
            sample_end_offsets=sample_end_offsets,
            sample_episode_ids=tuple(example.episode_id for _, example in samples),
            sample_decision_node_ids=tuple(
                example.decision_node_id or "" for _, example in samples
            ),
            sample_episode_dates=tuple(
                example.episode_date.isoformat() for _, example in samples
            ),
            sample_splits=tuple(split for split, _ in samples),
            static_values=static_values,
            static_context_lineages=tuple(
                example.static_context_lineage for _, example in samples
            ),
            labels=labels,
            active=active,
        )

    @property
    def canonical_node_count(self) -> int:
        return int(self.values_flat.shape[0])

    @property
    def expanded_prefix_node_count(self) -> int:
        return int((self.sample_end_offsets - self.sample_start_offsets).sum())

    def partition(
        self,
        split: str,
        *,
        representation: str = "ADAPTIVE_HISTORY",
        window_minutes: int | None = None,
    ) -> "M1RaggedDataset":
        if split not in ALLOWED_SPLITS:
            raise ValueError(f"M1_CACHE_SPLIT_NOT_ALLOWED:{split}")
        indices = tuple(
            index for index, value in enumerate(self.sample_splits) if value == split
        )
        return M1RaggedDataset(
            store=self,
            sample_indices=indices,
            representation=representation,
            window_minutes=window_minutes,
        )


@dataclass(frozen=True)
class M1RaggedDataset(Sequence[M1TrainingExample]):
    store: M1CanonicalRaggedStore
    sample_indices: tuple[int, ...]
    representation: str = "ADAPTIVE_HISTORY"
    window_minutes: int | None = None

    def __post_init__(self):
        if self.representation not in {"ADAPTIVE_HISTORY", "FIXED_HISTORY", "CURRENT"}:
            raise ValueError(f"M1_CACHE_UNKNOWN_HISTORY:{self.representation}")
        if self.representation == "FIXED_HISTORY":
            if (
                self.window_minutes is None
                or self.window_minutes <= 0
                or self.window_minutes % 5
            ):
                raise ValueError("M1_CACHE_FIXED_WINDOW_MUST_ALIGN_TO_FIVE_MINUTES")
        elif self.window_minutes is not None:
            raise ValueError("M1_CACHE_WINDOW_ONLY_VALID_FOR_FIXED_HISTORY")

    def __len__(self) -> int:
        return len(self.sample_indices)

    def _example(self, local_index: int) -> M1TrainingExample:
        sample_index = self.sample_indices[local_index]
        episode_index = int(self.store.sample_episode_indices[sample_index])
        episode_start = int(self.store.episode_offsets[episode_index])
        start = int(self.store.sample_start_offsets[sample_index])
        end = int(self.store.sample_end_offsets[sample_index])
        if self.representation == "CURRENT":
            start = end - 1
        elif self.representation == "FIXED_HISTORY":
            width_nodes = self.window_minutes // 5 + 1
            start = max(start, end - width_nodes)
        values = self.store.values_flat[episode_start + start : episode_start + end]
        targets = {}
        for name in TARGET_NAMES:
            stored = float(self.store.labels[name][sample_index])
            targets[name] = None if stored < 0 else stored
        return M1TrainingExample(
            episode_id=self.store.sample_episode_ids[sample_index],
            episode_date=date.fromisoformat(
                self.store.sample_episode_dates[sample_index]
            ),
            values=values,
            targets=targets,
            active={
                name: bool(self.store.active[name][sample_index])
                for name in TARGET_NAMES
            },
            decision_node_id=self.store.sample_decision_node_ids[sample_index] or None,
            static_values=(
                None
                if self.store.static_values is None
                else self.store.static_values[sample_index].clone()
            ),
            static_context_lineage=self.store.static_context_lineages[sample_index],
        )

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self._example(item) for item in range(*index.indices(len(self)))]
        if index < 0:
            index += len(self)
        if index < 0 or index >= len(self):
            raise IndexError(index)
        return self._example(index)


@dataclass(frozen=True)
class M1DevelopmentBaseCache:
    store: M1CanonicalRaggedStore
    normalization: M1NormalizationArtifact
    static_normalization: M1StaticNormalizationArtifact | None
    audit: dict
    manifest: dict

    @classmethod
    def from_partitions(
        cls,
        *,
        partitions,
        normalization,
        audit,
        cache_key: str,
        source_manifest_hash: str,
        contract_hashes: Mapping[str, str],
        static_normalization: M1StaticNormalizationArtifact | None = None,
        feature_names: Sequence[str] | None = None,
        static_feature_names: Sequence[str] | None = None,
        provenance: Mapping[str, object] | None = None,
        feature_schema_hash: str | None = None,
    ):
        missing_contracts = set(REQUIRED_CONTRACT_HASHES) - set(contract_hashes)
        if missing_contracts:
            raise ValueError(
                f"M1_CACHE_CONTRACT_HASH_MISSING:{sorted(missing_contracts)}"
            )
        store = M1CanonicalRaggedStore.from_partitions(partitions)
        return cls.from_store(
            store=store,
            normalization=normalization,
            static_normalization=static_normalization,
            audit=audit,
            cache_key=cache_key,
            source_manifest_hash=source_manifest_hash,
            contract_hashes=contract_hashes,
            feature_names=feature_names,
            static_feature_names=static_feature_names,
            provenance=provenance,
            feature_schema_hash=feature_schema_hash,
        )

    @classmethod
    def from_store(
        cls,
        *,
        store: M1CanonicalRaggedStore,
        normalization,
        static_normalization,
        audit,
        cache_key: str,
        source_manifest_hash: str,
        contract_hashes: Mapping[str, str],
        feature_names: Sequence[str] | None = None,
        static_feature_names: Sequence[str] | None = None,
        provenance: Mapping[str, object] | None = None,
        feature_schema_hash: str | None = None,
    ):
        missing_contracts = set(REQUIRED_CONTRACT_HASHES) - set(contract_hashes)
        if missing_contracts:
            raise ValueError(
                f"M1_CACHE_CONTRACT_HASH_MISSING:{sorted(missing_contracts)}"
            )
        dynamic_width = int(store.values_flat.shape[1])
        static_width = (
            0 if store.static_values is None else int(store.static_values.shape[1])
        )
        if static_width == STATIC_FEATURE_COUNT and not isinstance(
            static_normalization, M1StaticNormalizationArtifact
        ):
            raise ValueError("M1_CACHE_STATIC_NORMALIZATION_REQUIRED")
        dynamic_names = tuple(
            feature_names
            or (f"dynamic_feature_{index}" for index in range(dynamic_width))
        )
        if len(dynamic_names) != dynamic_width:
            raise ValueError("M1_CACHE_DYNAMIC_FEATURE_NAMES_WIDTH_MISMATCH")
        if static_feature_names is None:
            static_names = (
                tuple(STATIC_FEATURE_NAMES)
                if static_width == STATIC_FEATURE_COUNT
                else tuple(f"static_feature_{index}" for index in range(static_width))
            )
        else:
            static_names = tuple(static_feature_names)
        if len(static_names) != static_width:
            raise ValueError("M1_CACHE_STATIC_FEATURE_NAMES_WIDTH_MISMATCH")
        manifest = {
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "cache_key": cache_key,
            "source_manifest_hash": source_manifest_hash,
            "raw_input_manifest_hash": source_manifest_hash,
            "contract_hashes": dict(contract_hashes),
            "feature_schema_hash": feature_schema_hash
            or contract_hashes.get("feature_contract_hash"),
            "cache_build_scope": list(ALLOWED_SPLITS),
            "final_test_included": False,
            "final_test_access_count": 0,
            "normalization": normalization.model_dump(mode="json"),
            "static_normalization": (
                None
                if static_normalization is None
                else static_normalization.model_dump(mode="json")
            ),
            "feature_names": list(dynamic_names),
            "static_feature_names": list(static_names),
            "candidate_status": audit.get("candidate_status"),
            "provenance": dict(provenance or {}),
            "audit": audit,
            "episode_count": len(store.episode_ids),
            "sample_count": len(store.sample_splits),
            "feature_count": int(store.values_flat.shape[1]),
            "static_feature_count": (
                0 if store.static_values is None else int(store.static_values.shape[1])
            ),
            "canonical_node_count": store.canonical_node_count,
            "expanded_prefix_node_count": store.expanded_prefix_node_count,
            "partition_counts": {
                split: store.sample_splits.count(split) for split in ALLOWED_SPLITS
            },
            **{
                f"{split}_episode_count": len(
                    {
                        episode_id
                        for index, episode_id in enumerate(store.sample_episode_ids)
                        if store.sample_splits[index] == split
                    }
                )
                for split in ALLOWED_SPLITS
            },
        }
        return cls(
            store=store,
            normalization=normalization,
            static_normalization=static_normalization,
            audit=audit,
            manifest=manifest,
        )

    def partition(
        self,
        split: str,
        *,
        representation: str = "ADAPTIVE_HISTORY",
        window_minutes: int | None = None,
    ) -> M1RaggedDataset:
        return self.store.partition(
            split, representation=representation, window_minutes=window_minutes
        )

    def save(self, data_path: Path, manifest_path: Path) -> dict:
        data_path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {
            "values_flat": self.store.values_flat.numpy(),
            "episode_offsets": self.store.episode_offsets.numpy(),
            "episode_ids": np.asarray(self.store.episode_ids, dtype=np.str_),
            "sample_episode_indices": self.store.sample_episode_indices.numpy(),
            "sample_start_offsets": self.store.sample_start_offsets.numpy(),
            "sample_end_offsets": self.store.sample_end_offsets.numpy(),
            "sample_episode_ids": np.asarray(
                self.store.sample_episode_ids, dtype=np.str_
            ),
            "sample_decision_node_ids": np.asarray(
                self.store.sample_decision_node_ids, dtype=np.str_
            ),
            "sample_episode_dates": np.asarray(
                self.store.sample_episode_dates, dtype=np.str_
            ),
            "sample_splits": np.asarray(self.store.sample_splits, dtype=np.str_),
            "static_context_lineages": np.asarray(
                [
                    _lineage_dumps(lineage)
                    for lineage in self.store.static_context_lineages
                ],
                dtype=np.str_,
            ),
        }
        if self.store.static_values is not None:
            arrays["static_values"] = self.store.static_values.numpy()
        arrays.update(
            {f"labels_{name}": self.store.labels[name].numpy() for name in TARGET_NAMES}
        )
        arrays.update(
            {f"active_{name}": self.store.active[name].numpy() for name in TARGET_NAMES}
        )
        temporary_data = data_path.with_suffix(data_path.suffix + ".tmp")
        with temporary_data.open("wb") as stream:
            np.savez_compressed(stream, **arrays)
        cache_hash = _stable_store_hash(self.store)
        manifest = {
            **self.manifest,
            "cache_hash": cache_hash,
            "cache_bytes": temporary_data.stat().st_size,
            "array_dtypes": {name: str(value.dtype) for name, value in arrays.items()},
        }
        temporary_manifest = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
        temporary_manifest.write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        temporary_data.replace(data_path)
        temporary_manifest.replace(manifest_path)
        return manifest

    @classmethod
    def load(
        cls,
        data_path: Path,
        manifest_path: Path,
        *,
        expected_cache_key: str,
        allow_legacy_schema: bool = False,
    ):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        schema = manifest.get("cache_schema_version")
        allowed = {CACHE_SCHEMA_VERSION}
        if allow_legacy_schema:
            allowed.update(LEGACY_CACHE_SCHEMA_VERSIONS)
        if schema not in allowed:
            raise ValueError("M1_CACHE_SCHEMA_VERSION_MISMATCH")
        if manifest.get("cache_key") != expected_cache_key:
            raise ValueError("M1_CACHE_KEY_MISMATCH")
        if manifest.get("final_test_included") is not False:
            raise ValueError("M1_CACHE_FINAL_TEST_GUARD_FAILED")
        if manifest.get("final_test_access_count") != 0:
            raise ValueError("M1_CACHE_FINAL_TEST_ACCESS_RECORDED")
        with np.load(data_path, allow_pickle=False) as arrays:
            tensor = lambda name: torch.from_numpy(np.asarray(arrays[name]).copy())
            store = M1CanonicalRaggedStore(
                values_flat=tensor("values_flat").to(dtype=torch.float32),
                episode_offsets=tensor("episode_offsets").to(dtype=torch.int64),
                episode_ids=tuple(str(value) for value in arrays["episode_ids"]),
                sample_episode_indices=tensor("sample_episode_indices").to(
                    dtype=torch.int32
                ),
                sample_start_offsets=tensor("sample_start_offsets").to(
                    dtype=torch.int32
                ),
                sample_end_offsets=tensor("sample_end_offsets").to(dtype=torch.int32),
                sample_episode_ids=tuple(
                    str(value) for value in arrays["sample_episode_ids"]
                ),
                sample_decision_node_ids=tuple(
                    str(value) for value in arrays["sample_decision_node_ids"]
                ),
                sample_episode_dates=tuple(
                    str(value) for value in arrays["sample_episode_dates"]
                ),
                sample_splits=tuple(str(value) for value in arrays["sample_splits"]),
                static_values=(
                    None
                    if "static_values" not in arrays.files
                    else tensor("static_values").to(dtype=torch.float32)
                ),
                static_context_lineages=tuple(
                    _lineage_loads(str(value))
                    for value in arrays["static_context_lineages"]
                ),
                labels={
                    name: tensor(f"labels_{name}").to(dtype=torch.float32)
                    for name in TARGET_NAMES
                },
                active={
                    name: tensor(f"active_{name}").to(dtype=torch.bool)
                    for name in TARGET_NAMES
                },
            )
        normalization = M1NormalizationArtifact.model_validate(
            manifest["normalization"]
        )
        static_normalization = manifest.get("static_normalization")
        if static_normalization is not None:
            static_normalization = M1StaticNormalizationArtifact.model_validate(
                static_normalization
            )
        if schema == CACHE_SCHEMA_VERSION:
            feature_names = manifest.get("feature_names", [])
            static_feature_names = manifest.get("static_feature_names", [])
            if len(feature_names) != int(store.values_flat.shape[1]):
                raise ValueError("M1_CACHE_DYNAMIC_FEATURE_NAMES_WIDTH_MISMATCH")
            static_width = (
                0 if store.static_values is None else int(store.static_values.shape[1])
            )
            if len(static_feature_names) != static_width:
                raise ValueError("M1_CACHE_STATIC_FEATURE_NAMES_WIDTH_MISMATCH")
            if static_width == STATIC_FEATURE_COUNT and not isinstance(
                static_normalization, M1StaticNormalizationArtifact
            ):
                raise ValueError("M1_CACHE_STATIC_NORMALIZATION_REQUIRED")
        if manifest.get("cache_hash") != _stable_store_hash(store):
            raise ValueError("M1_CACHE_CONTENT_HASH_MISMATCH")
        return cls(
            store=store,
            normalization=normalization,
            static_normalization=static_normalization,
            audit=manifest["audit"],
            manifest=manifest,
        )


def cache_key(
    *,
    source_manifest_hash: str,
    contract_hashes: Mapping[str, str],
    cohort_counts: Mapping[str, int],
    cohort_seed: int,
) -> str:
    missing_contracts = set(REQUIRED_CONTRACT_HASHES) - set(contract_hashes)
    if missing_contracts:
        raise ValueError(f"M1_CACHE_CONTRACT_HASH_MISSING:{sorted(missing_contracts)}")
    return content_id(
        {
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "source_manifest_hash": source_manifest_hash,
            "contract_hashes": dict(contract_hashes),
            "cohort_counts": dict(cohort_counts),
            "cohort_seed": cohort_seed,
        }
    )
