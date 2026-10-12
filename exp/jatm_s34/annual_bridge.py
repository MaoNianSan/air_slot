"""Materialize an annual PRE -> M1 bridge for Development experiments."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
import json

from data2.scripts.consequence_stability_battery import (
    active_rows,
    build_training_examples,
    fit_static_normalization_from_rows,
    fit_train_normalization,
    load_hash_cohort,
    normalization_rows,
    prefix_partitions,
    year_references,
)
from model.M1.cache import M1DevelopmentBaseCache
from model.M1.data import FEATURE_NAMES_V2
from model.M1.static_features import STATIC_FEATURE_NAMES
from model.M1.pipeline import M1Pipeline
from model.M2.context import load_data2_reference_bundle
from model.PRE.cohort import split_for_date_multiyear
from model.PRE.development import materialize_preselected_cohorts
from model.common.config import load_config_layers
from model.common.paths import PROJECT_ROOT
from validation.v2_phase5.common import Authorities
from .annual_tail import load_annual_tail


M2_ROOT = PROJECT_ROOT / "artifacts" / "models" / "pre" / "PRE_MULTIYEAR_V1_E4_YEARLOCAL_R1"


def _annual_bundle(year: int):
    root = M2_ROOT / str(year) / "M2_REFERENCES"
    names = {
        "turnaround": f"M2_TURNAROUND_REFERENCE_{year}-H1.json",
        "taxi": f"M2_TAXI_REFERENCE_{year}-H1.json",
        "downstream_exposure": f"M2_DOWNSTREAM_EXPOSURE_REFERENCE_{year}-H1.json",
        "passenger": f"M2_PASSENGER_REFERENCE_{year}-H1.json",
        "expected_passengers": f"M2_EXPECTED_PASSENGERS_REFERENCE_{year}-H1.json",
        "connection_share": f"M2_CONNECTION_SHARE_REFERENCE_{year}-H1.json",
    }
    payloads = {key: json.loads((root / name).read_text(encoding="utf-8")) for key, name in names.items()}
    return load_data2_reference_bundle(payloads)


def load_annual_authorities(year: int, *, continuity_contract: str = 'LEGACY_A_V1'):
    """Reuse the authority contract without loading the legacy 2019 cache.

    Annual training records predate an explicit seed field; the seed is the
    fixed constant in their approved generator, not inferred from a later year.
    """
    from .annual_cu import load_annual_cu
    from .annual_models import TRAIN_SEED
    from .cloud_inputs import model_bindings
    bindings = model_bindings(year)
    taxi, _ = year_references(year)
    return Authorities(cache=None, cohort={},
        h16_manifest=dict(bindings['M1_HISTORY_PRIMARY'], training_seed=TRAIN_SEED),
        current_manifest=dict(bindings['M1_CURRENT_COMPARATOR'], training_seed=TRAIN_SEED),
        registry=load_annual_cu(year, continuity_contract=continuity_contract), reference_bundle=_annual_bundle(year), taxi_reference=taxi,
        audit=dict(year=year, seed_source='exp.jatm_s34.annual_models.TRAIN_SEED',
                   legacy_phase5_cache_loaded=False, final_test_access_count=0))


def load_annual_bridge(*, year: int, n: int = 4096, node_limit: int | None = None) -> dict:
    """Build a bridge with annual Train/Calibration normalization and Dev nodes."""
    year = int(year)
    selected = load_hash_cohort(year)
    partitions = prefix_partitions(selected, n)
    if node_limit is not None:
        partitions = {"train": (), "calibration": (), "development": partitions["development"][: int(node_limit)]}
    scientific = load_config_layers(PROJECT_ROOT / "configs").scientific
    taxi, turnaround = year_references(year)
    cohorts = materialize_preselected_cohorts(
        scientific,
        root=PROJECT_ROOT,
        partitions=partitions,
        year=year,
        dataset_instance_id="data2_2017_2022",
        split_resolver=split_for_date_multiyear,
        taxi_reference=taxi,
        turnaround_reference=turnaround,
    )
    rows = {}
    for split in ("train", "calibration", "development"):
        rows[split], _ = active_rows(getattr(cohorts, split), taxi_reference=taxi)
    prepared_by_id = {
        prepared.episode.episode_id: prepared
        for split in ("train", "calibration", "development")
        for prepared in getattr(cohorts, split)
    }
    if node_limit is None:
        normalization = fit_train_normalization(
            normalization_rows([prefix for _ep, prefix, _labels in rows["train"]]), split="train"
        )
        static_normalization = fit_static_normalization_from_rows(rows["train"])
    else:
        checkpoint = PROJECT_ROOT / "artifacts" / "models" / "m1" / f"YEAR_{year}" / "M1_HISTORY_PRIMARY.pt"
        pipeline = M1Pipeline.load(checkpoint)
        normalization = pipeline.normalization
        static_normalization = pipeline.static_normalization
    examples_by_split = {
        split: build_training_examples(
            rows[split], normalization, None, static_normalization=static_normalization
        )
        for split in rows
    }
    partitions_examples = {split: tuple(examples_by_split[split]) for split in examples_by_split}
    authorities = load_annual_authorities(year)
    bundle = _annual_bundle(year)
    cache = M1DevelopmentBaseCache.from_partitions(
        partitions=partitions_examples,
        normalization=normalization,
        static_normalization=static_normalization,
        audit={"candidate_status": "ANNUAL_DEVELOPMENT_BRIDGE", "year": year},
        cache_key=f"JATM_ANNUAL_{year}_N{n}",
        source_manifest_hash=f"annual-pre-{year}",
        contract_hashes={key: "annual-adapter-v1" for key in (
            "PRE_contract_hash", "episode_contract_hash", "episode_construction_hash",
            "feature_contract_hash", "split_contract_hash", "roll_contract_hash",
            "normalization_contract_hash")},
        feature_names=FEATURE_NAMES_V2,
        static_feature_names=STATIC_FEATURE_NAMES,
        provenance={"year": year, "n": n, "m2_reference_ids": bundle.reference_ids},
        final_test_start=date(year, 10, 1),
    )
    dev_rows = tuple(
        (example, prepared_by_id[episode.episode_id], prefix)
        for example, (episode, prefix, _labels)
        in zip(examples_by_split["development"], rows["development"])
    )
    if node_limit is not None:
        dev_rows = dev_rows[: int(node_limit)]
    return {
        "authorities": replace(authorities, cache=cache, reference_bundle=bundle, taxi_reference=taxi),
        "bridge": {"cache": cache, "rows": dev_rows, "mapping": None, "taxi_reference": taxi,
                   "manifest": {"year": year, "n": n}},
        "tails": load_annual_tail(year),
        "year": year,
        "n": n,
        "history_checkpoint": PROJECT_ROOT / "artifacts" / "models" / "m1" / f"YEAR_{year}" / "M1_HISTORY_PRIMARY.pt",
        "current_checkpoint": PROJECT_ROOT / "artifacts" / "models" / "m1" / f"YEAR_{year}" / "M1_CURRENT_COMPARATOR.pt",
    }


def iter_annual_bridges(*, year: int, n: int = 4096, chunk_size: int = 128,
                        node_limit: int | None = None, start_chunk: int = 0,
                        episode_ids: set[str] | None = None,
                        shared: bool = False, device: str = 'cpu',
                        continuity_contract: str = 'LEGACY_A_V1'):
    """Yield bounded Development bridges for one annual cohort.

    Train and Calibration define the frozen annual normalization already
    embedded in the annual M1 checkpoint; they are therefore never rematerialized
    by this Development bridge.  Development episodes are published one chunk
    at a time.  A yielded bridge owns only that chunk's PRE states, M1 rows and
    cache; callers must finish and release a bridge before requesting the next
    one.  This keeps the scientific cohort and split rules identical to
    :func:`load_annual_bridge` while avoiding a whole-year PRE/M1 object graph.
    """
    year = int(year)
    if int(chunk_size) <= 0:
        raise ValueError("JATM_ANNUAL_CHUNK_SIZE_INVALID")
    if int(start_chunk) < 0:
        raise ValueError("JATM_ANNUAL_START_CHUNK_INVALID")
    selected = load_hash_cohort(year)
    n = int(n)
    scientific = load_config_layers(PROJECT_ROOT / "configs").scientific
    taxi, turnaround = year_references(year)
    checkpoint = PROJECT_ROOT / "artifacts" / "models" / "m1" / f"YEAR_{year}" / "M1_HISTORY_PRIMARY.pt"
    pipeline = M1Pipeline.load(checkpoint)
    current_pipeline = M1Pipeline.load(
        PROJECT_ROOT / "artifacts" / "models" / "m1" / f"YEAR_{year}" / "M1_CURRENT_COMPARATOR.pt"
    )
    if device != 'cpu':
        pipeline.to_device(device)
        current_pipeline.to_device(device)
    from .annual_tail import load_annual_tail
    pipeline.tail_continuations = dict(load_annual_tail(year))
    current_pipeline.tail_continuations = dict(pipeline.tail_continuations)
    normalization, static_normalization = pipeline.normalization, pipeline.static_normalization
    authorities = load_annual_authorities(year, continuity_contract=continuity_contract)
    bundle = _annual_bundle(year)
    if shared:
        from .annual_cu import load_annual_cu
        authorities = replace(authorities, registry=load_annual_cu(year))
    tails = dict(pipeline.tail_continuations)
    dev_items = selected["development"]
    if node_limit is not None:
        dev_items = dev_items[:int(node_limit)]
    first_offset = int(start_chunk) * int(chunk_size)
    for offset in range(first_offset, len(dev_items), int(chunk_size)):
        chunk = tuple(episode for _rank, episode in dev_items[offset:offset + int(chunk_size)])
        if episode_ids is not None:
            chunk = tuple(ep for ep in chunk if ep.episode_id in episode_ids)
            if not chunk:
                continue
        partitions = {"train": (), "calibration": (), "development": chunk}
        cohorts = materialize_preselected_cohorts(
            scientific, root=PROJECT_ROOT, partitions=partitions, year=year,
            dataset_instance_id="data2_2017_2022", split_resolver=split_for_date_multiyear,
            taxi_reference=taxi, turnaround_reference=turnaround,
        )
        dev_rows, _ = active_rows(cohorts.development, taxi_reference=taxi)
        dev_examples = tuple(build_training_examples(
            dev_rows, normalization, None, static_normalization=static_normalization
        ))
        prepared_by_id = {prepared.episode.episode_id: prepared for prepared in cohorts.development}
        # The annual checkpoint already contains Train-frozen normalization.
        # No Train/Calibration rows are needed to build a Development node;
        # keeping them out of this cache is what makes the bridge bounded.
        examples_by_split = {"train": (), "calibration": (), "development": dev_examples}
        partitions_examples = {split: tuple(examples_by_split[split]) for split in examples_by_split}
        cache = M1DevelopmentBaseCache.from_partitions(
            partitions=partitions_examples, normalization=normalization,
            static_normalization=static_normalization,
            audit={"candidate_status": "ANNUAL_DEVELOPMENT_BRIDGE_BOUNDED", "year": year,
                   "chunk_index": offset // int(chunk_size)},
            cache_key=f"JATM_ANNUAL_{year}_N{n}_CHUNK{offset // int(chunk_size)}",
            source_manifest_hash=f"annual-pre-{year}",
            contract_hashes={key: "annual-adapter-v1" for key in (
                "PRE_contract_hash", "episode_contract_hash", "episode_construction_hash",
                "feature_contract_hash", "split_contract_hash", "roll_contract_hash",
                "normalization_contract_hash")},
            feature_names=FEATURE_NAMES_V2, static_feature_names=STATIC_FEATURE_NAMES,
            provenance={"year": year, "n": n, "chunk_offset": offset,
                        "m2_reference_ids": bundle.reference_ids},
            final_test_start=date(year, 10, 1),
        )
        dev_bridge_rows = tuple(
            (example, prepared_by_id[episode.episode_id], prefix)
            for example, (episode, prefix, _labels) in zip(dev_examples, dev_rows)
        )
        yield {
            "authorities": replace(authorities, cache=cache, reference_bundle=bundle, taxi_reference=taxi),
            "bridge": {"cache": cache, "rows": dev_bridge_rows, "mapping": None,
                       "taxi_reference": taxi,
                       "manifest": {"year": year, "n": n, "chunk_index": offset // int(chunk_size),
                                    "chunk_offset": offset, "chunk_episode_count": len(chunk)}},
            "tails": tails, "year": year, "n": n,
            "history_checkpoint": checkpoint,
            "current_checkpoint": PROJECT_ROOT / "artifacts" / "models" / "m1" / f"YEAR_{year}" / "M1_CURRENT_COMPARATOR.pt",
            "history_pipeline": pipeline,
            "current_pipeline": current_pipeline,
        }


__all__ = ["load_annual_bridge", "iter_annual_bridges"]
