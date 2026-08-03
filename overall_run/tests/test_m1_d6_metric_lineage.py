from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.m1_lineage_contract import (
    FAST_ROOT,
    HISTORICAL_FIXTURE_ROOT,
    QUANTILES,
    cohort_hash,
    pinball_loss,
    quantile_crps,
    registered_artifact_snapshot,
    sha256_file,
    twcrps_value,
    verify_frozen_baseline,
)
from src.m1_lineage_dictionary import (
    build_metric_dictionary,
    build_prediction_layer_mapping,
)
from src.m1_lineage_history import (
    build_historical_deprecation_registry,
    scan_formal_materials_for_deprecated_claims,
)
from src.m1_lineage_identity import build_current_identity
from src.m1_lineage_lineage import (
    build_bootstrap_lineage,
    build_cohort_lineage,
    build_metric_version_registry,
)
from src.m1_lineage_reconstruction import reconstruct_current_metrics


@pytest.fixture(scope="module")
def lineage() -> dict:
    context = reconstruct_current_metrics()
    dictionary = build_metric_dictionary()
    return {
        "context": context,
        "dictionary": dictionary,
        "identity": build_current_identity(context, dictionary),
        "cohorts": build_cohort_lineage(context, dictionary),
        "versions": build_metric_version_registry(dictionary),
        "bootstrap": build_bootstrap_lineage(context, dictionary),
    }


def test_d6_current_metric_identity(lineage: dict) -> None:
    reported = lineage["identity"].loc[lambda frame: frame["reported_value"].notna()]
    assert reported["value_match"].all()
    assert reported["absolute_error"].max() <= 1e-12


def test_d6_support_identity(lineage: dict) -> None:
    reported = lineage["identity"].loc[lambda frame: frame["support_reported"].notna()]
    assert reported["support_match"].all()
    assert lineage["context"]["tail_mask"].sum() == 32


def test_d6_cohort_hash_identity(lineage: dict) -> None:
    context = lineage["context"]
    assert context["formal_cohort_hash"] == context["reconstructed_formal_cohort_hash"]
    assert context["tail_cohort_hash"] == context["reconstructed_tail_cohort_hash"]
    assert cohort_hash(context["predictions"]["snapshot_id"]) == context["formal_cohort_hash"]


def test_d6_prediction_layer_mapping(lineage: dict) -> None:
    mapping = build_prediction_layer_mapping().set_index("layer")
    assert {"RAW_MODEL_QUANTILES", "FINAL_PUBLISHED_QUANTILES"}.issubset(mapping.index)
    assert lineage["context"]["prediction_layer_max_abs_delta"] == 0.0
    assert lineage["context"]["predictive_sample_max_abs_delta"] == 0.0


def test_d6_q95_exceedance_coverage_equivalence(lineage: dict) -> None:
    values = lineage["context"]["values"]
    assert values["q95_exceedance"] == pytest.approx(1.0 - values["q95_empirical_cdf"])
    assert values["q95_exceedance"] == pytest.approx(0.0609375)


def test_d6_pinball_formula_identity() -> None:
    y = np.array([0.0, 2.0, 5.0])
    q = np.array([1.0, 1.0, 5.0])
    expected = np.maximum(0.95 * (y - q), -0.05 * (y - q))
    np.testing.assert_allclose(pinball_loss(y, q, 0.95), expected, atol=1e-15, rtol=0.0)


def test_d6_crps_formula_identity(lineage: dict) -> None:
    context = lineage["context"]
    actual = quantile_crps(context["target"], context["qmat"])
    np.testing.assert_array_equal(actual, context["crps_rows"])
    assert actual.mean() == pytest.approx(context["values"]["crps"], abs=1e-12)


def test_d6_twcrps_formula_identity(lineage: dict) -> None:
    context = lineage["context"]
    actual = twcrps_value(context["crps_rows"], context["target"], context["validation_q95"])
    assert actual == pytest.approx(context["values"]["twcrps"], abs=1e-12)


def test_d6_tail_diagnostic_is_not_formal_metric(lineage: dict) -> None:
    row = lineage["dictionary"].set_index("value_key").loc["tail_coverage90"]
    assert row["formal_or_diagnostic"] == "DIAGNOSTIC_ONLY"
    assert bool(row["prohibited_as_primary_gate"])


def test_d6_bootstrap_unit_identity(lineage: dict) -> None:
    active = lineage["bootstrap"].loc[lambda frame: frame["bootstrap_applicable"]]
    assert set(active["bootstrap_unit"]) == {"trigger_event_group_id"}
    assert set(active["support_clusters"]) == {6}


def test_d6_metric_version_uniqueness(lineage: dict) -> None:
    versions = lineage["versions"]
    assert versions["canonical_metric_id"].is_unique
    assert versions["definition_hash"].is_unique


def test_d6_historical_values_are_deprecated() -> None:
    registry = build_historical_deprecation_registry()
    assert len(registry) >= 8
    assert set(registry["reconstructability"]) == {"NOT_RECONSTRUCTABLE"}
    assert set(registry["authority_status"]) == {"NON_AUTHORITATIVE"}
    assert set(registry["manuscript_use_status"]) == {"PROHIBITED"}


def test_d6_deprecated_values_prohibited_from_formal_reports() -> None:
    assert scan_formal_materials_for_deprecated_claims() == []


def test_d6_historical_artifact_not_overwritten() -> None:
    path = HISTORICAL_FIXTURE_ROOT / "audit" / "historical_d6_label_lineage.json"
    before = (sha256_file(path), path.stat().st_size)
    build_historical_deprecation_registry()
    assert (sha256_file(path), path.stat().st_size) == before


def test_d6_audit_does_not_modify_formal_artifacts() -> None:
    before = registered_artifact_snapshot()
    verify_frozen_baseline(deep_inputs=False)
    assert registered_artifact_snapshot() == before


def test_d6_registry_hashes() -> None:
    result = verify_frozen_baseline(deep_inputs=False)
    assert all(result["checks"].values())
    registry = json.loads((FAST_ROOT / "artifact_registry.json").read_text(encoding="utf-8"))
    registered = {str(row["artifact_name"]) for row in registry["artifacts"]}
    assert registered.issuperset(set(registry["required_artifact_ids"]))
    assert result["current_pre_lineage_stale"] is True
