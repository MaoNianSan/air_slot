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
from validation.v2_phase5.common import load_authorities, load_tail_continuations


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
    authorities = load_authorities()
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
        "tails": load_tail_continuations(),
        "year": year,
        "n": n,
        "history_checkpoint": PROJECT_ROOT / "artifacts" / "models" / "m1" / f"YEAR_{year}" / "M1_HISTORY_PRIMARY.pt",
        "current_checkpoint": PROJECT_ROOT / "artifacts" / "models" / "m1" / f"YEAR_{year}" / "M1_CURRENT_COMPARATOR.pt",
    }


__all__ = ["load_annual_bridge"]
