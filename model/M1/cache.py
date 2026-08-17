from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import torch

from model.common.identity import content_id

from .data import M1NormalizationArtifact
from .lifecycle import M1TrainingExample


CACHE_SCHEMA_VERSION = "M1_SIGNED_OB_DEVELOPMENT_BASE_CACHE_V1"
TARGET_NAMES = ("R_IB", "DELTA_OB", "T_TX")
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
    ):
        if isinstance(value, tuple):
            for item in value:
                _update_hash(hasher, item)
        else:
            _update_hash(hasher, value)
    for name in TARGET_NAMES:
        _update_hash(hasher, store.labels[name])
        _update_hash(hasher, store.active[name])
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
                values = example.values.detach().cpu().to(dtype=torch.float32).contiguous()
                previous = canonical.get(example.episode_id)
                if previous is None or len(values) > len(previous):
                    if previous is not None and not torch.equal(values[:len(previous)], previous):
                        raise ValueError("M1_CACHE_NONCANONICAL_EPISODE_PREFIX")
                    canonical[example.episode_id] = values
                elif not torch.equal(previous[:len(values)], values):
                    raise ValueError("M1_CACHE_NONCANONICAL_EPISODE_PREFIX")
                samples.append((split, example))

        episode_ids = tuple(sorted(canonical))
        episode_index = {episode_id: index for index, episode_id in enumerate(episode_ids)}
        values_parts = [canonical[episode_id] for episode_id in episode_ids]
        feature_count = values_parts[0].shape[1] if values_parts else 0
        values_flat = (torch.cat(values_parts, dim=0) if values_parts
                       else torch.empty((0, feature_count), dtype=torch.float32))
        offsets = [0]
        for values in values_parts:
            offsets.append(offsets[-1] + len(values))

        sample_episode_indices = torch.tensor(
            [episode_index[example.episode_id] for _, example in samples], dtype=torch.int32)
        sample_start_offsets = torch.zeros(len(samples), dtype=torch.int32)
        sample_end_offsets = torch.tensor(
            [len(example.values) for _, example in samples], dtype=torch.int32)
        labels = {name: torch.tensor(
            [example.labels[name] for _, example in samples], dtype=torch.int32)
            for name in TARGET_NAMES}
        active = {name: torch.tensor(
            [example.active[name] for _, example in samples], dtype=torch.bool)
            for name in TARGET_NAMES}
        return cls(
            values_flat=values_flat,
            episode_offsets=torch.tensor(offsets, dtype=torch.int64),
            episode_ids=episode_ids,
            sample_episode_indices=sample_episode_indices,
            sample_start_offsets=sample_start_offsets,
            sample_end_offsets=sample_end_offsets,
            sample_episode_ids=tuple(example.episode_id for _, example in samples),
            sample_decision_node_ids=tuple(
                example.decision_node_id or "" for _, example in samples),
            sample_episode_dates=tuple(
                example.episode_date.isoformat() for _, example in samples),
            sample_splits=tuple(split for split, _ in samples),
            labels=labels,
            active=active,
        )

    @property
    def canonical_node_count(self) -> int:
        return int(self.values_flat.shape[0])

    @property
    def expanded_prefix_node_count(self) -> int:
        return int((self.sample_end_offsets - self.sample_start_offsets).sum())

    def partition(self, split: str, *, representation: str = "ADAPTIVE_HISTORY",
                  window_minutes: int | None = None) -> "M1RaggedDataset":
        if split not in ALLOWED_SPLITS:
            raise ValueError(f"M1_CACHE_SPLIT_NOT_ALLOWED:{split}")
        indices = tuple(index for index, value in enumerate(self.sample_splits)
                        if value == split)
        return M1RaggedDataset(
            store=self, sample_indices=indices, representation=representation,
            window_minutes=window_minutes)


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
            if self.window_minutes is None or self.window_minutes <= 0 \
                    or self.window_minutes % 5:
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
        values = self.store.values_flat[episode_start + start:episode_start + end]
        return M1TrainingExample(
            episode_id=self.store.sample_episode_ids[sample_index],
            episode_date=date.fromisoformat(self.store.sample_episode_dates[sample_index]),
            values=values,
            labels={name: int(self.store.labels[name][sample_index]) for name in TARGET_NAMES},
            active={name: bool(self.store.active[name][sample_index]) for name in TARGET_NAMES},
            decision_node_id=self.store.sample_decision_node_ids[sample_index] or None,
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
    audit: dict
    manifest: dict

    @classmethod
    def from_partitions(cls, *, partitions, normalization, audit,
                        cache_key: str, source_manifest_hash: str,
                        contract_hashes: Mapping[str, str]):
        missing_contracts = set(REQUIRED_CONTRACT_HASHES) - set(contract_hashes)
        if missing_contracts:
            raise ValueError(f"M1_CACHE_CONTRACT_HASH_MISSING:{sorted(missing_contracts)}")
        store = M1CanonicalRaggedStore.from_partitions(partitions)
        manifest = {
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "cache_key": cache_key,
            "source_manifest_hash": source_manifest_hash,
            "raw_input_manifest_hash": source_manifest_hash,
            "contract_hashes": dict(contract_hashes),
            "cache_build_scope": list(ALLOWED_SPLITS),
            "final_test_included": False,
            "final_test_access_count": 0,
            "normalization": normalization.model_dump(mode="json"),
            "audit": audit,
            "episode_count": len(store.episode_ids),
            "sample_count": len(store.sample_splits),
            "feature_count": int(store.values_flat.shape[1]),
            "canonical_node_count": store.canonical_node_count,
            "expanded_prefix_node_count": store.expanded_prefix_node_count,
            "partition_counts": {
                split: store.sample_splits.count(split) for split in ALLOWED_SPLITS},
            **{
                f"{split}_episode_count": len({
                    episode_id
                    for index, episode_id in enumerate(store.sample_episode_ids)
                    if store.sample_splits[index] == split
                })
                for split in ALLOWED_SPLITS
            },
        }
        return cls(store=store, normalization=normalization, audit=audit, manifest=manifest)

    def partition(self, split: str, *, representation: str = "ADAPTIVE_HISTORY",
                  window_minutes: int | None = None) -> M1RaggedDataset:
        return self.store.partition(
            split, representation=representation, window_minutes=window_minutes)

    def save(self, data_path: Path, manifest_path: Path) -> dict:
        data_path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {
            "values_flat": self.store.values_flat.numpy(),
            "episode_offsets": self.store.episode_offsets.numpy(),
            "episode_ids": np.asarray(self.store.episode_ids, dtype=np.str_),
            "sample_episode_indices": self.store.sample_episode_indices.numpy(),
            "sample_start_offsets": self.store.sample_start_offsets.numpy(),
            "sample_end_offsets": self.store.sample_end_offsets.numpy(),
            "sample_episode_ids": np.asarray(self.store.sample_episode_ids, dtype=np.str_),
            "sample_decision_node_ids": np.asarray(
                self.store.sample_decision_node_ids, dtype=np.str_),
            "sample_episode_dates": np.asarray(self.store.sample_episode_dates, dtype=np.str_),
            "sample_splits": np.asarray(self.store.sample_splits, dtype=np.str_),
        }
        arrays.update({f"labels_{name}": self.store.labels[name].numpy()
                       for name in TARGET_NAMES})
        arrays.update({f"active_{name}": self.store.active[name].numpy()
                       for name in TARGET_NAMES})
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
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        temporary_data.replace(data_path)
        temporary_manifest.replace(manifest_path)
        return manifest

    @classmethod
    def load(cls, data_path: Path, manifest_path: Path, *, expected_cache_key: str):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("cache_schema_version") != CACHE_SCHEMA_VERSION:
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
                sample_episode_indices=tensor("sample_episode_indices").to(dtype=torch.int32),
                sample_start_offsets=tensor("sample_start_offsets").to(dtype=torch.int32),
                sample_end_offsets=tensor("sample_end_offsets").to(dtype=torch.int32),
                sample_episode_ids=tuple(str(value) for value in arrays["sample_episode_ids"]),
                sample_decision_node_ids=tuple(
                    str(value) for value in arrays["sample_decision_node_ids"]),
                sample_episode_dates=tuple(str(value) for value in arrays["sample_episode_dates"]),
                sample_splits=tuple(str(value) for value in arrays["sample_splits"]),
                labels={name: tensor(f"labels_{name}").to(dtype=torch.int32)
                        for name in TARGET_NAMES},
                active={name: tensor(f"active_{name}").to(dtype=torch.bool)
                        for name in TARGET_NAMES},
            )
        normalization = M1NormalizationArtifact.model_validate(manifest["normalization"])
        if manifest.get("cache_hash") != _stable_store_hash(store):
            raise ValueError("M1_CACHE_CONTENT_HASH_MISMATCH")
        return cls(store=store, normalization=normalization,
                   audit=manifest["audit"], manifest=manifest)


def cache_key(*, source_manifest_hash: str, contract_hashes: Mapping[str, str],
              cohort_counts: Mapping[str, int], cohort_seed: int) -> str:
    missing_contracts = set(REQUIRED_CONTRACT_HASHES) - set(contract_hashes)
    if missing_contracts:
        raise ValueError(f"M1_CACHE_CONTRACT_HASH_MISSING:{sorted(missing_contracts)}")
    return content_id({
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "source_manifest_hash": source_manifest_hash,
        "contract_hashes": dict(contract_hashes),
        "cohort_counts": dict(cohort_counts),
        "cohort_seed": cohort_seed,
    })
