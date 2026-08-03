"""Middle CURRENT_DATA_MIDDLE_23D_V1 contract tests."""
from __future__ import annotations

import hashlib, json
from pathlib import Path

import pandas as pd
import pytest

PROJECT = Path(__file__).resolve().parents[1]
MIDDLE_CSV = PROJECT / "data" / "manifests" / "middle_current_data_manifest.csv"
MIDDLE_JSON = PROJECT / "data" / "manifests" / "middle_current_data_manifest.json"
LEGACY_CSV = PROJECT / "data" / "manifests" / "current_data_adapt_full_manifest.csv"


@pytest.fixture(scope="module")
def middle_df() -> pd.DataFrame:
    return pd.read_csv(MIDDLE_CSV, parse_dates=["anchor_date"])


@pytest.fixture(scope="module")
def middle_meta() -> dict:
    return json.loads(MIDDLE_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def legacy_df() -> pd.DataFrame:
    return pd.read_csv(LEGACY_CSV, parse_dates=["anchor_date"])


# --- Identity ---
def test_middle_manifest_version(middle_meta: dict) -> None:
    assert middle_meta["manifest_version"] == "CURRENT_DATA_MIDDLE_23D_V1"


def test_middle_is_23_days(middle_df: pd.DataFrame) -> None:
    assert len(middle_df) == 23


def test_middle_split_is_14_5_4(middle_df: pd.DataFrame) -> None:
    counts = middle_df["split"].value_counts()
    assert counts.get("train") == 14
    assert counts.get("validation") == 5
    assert counts.get("test") == 4


def test_middle_expected_hours_is_552(middle_meta: dict) -> None:
    assert middle_meta["expected_hours"] == 552


# --- Data completeness ---
def test_middle_all_days_24h(middle_df: pd.DataFrame) -> None:
    assert (middle_df["raw_hours"] == 24).all()
    assert (middle_df["cache_complete_hours"] == 24).all()


def test_middle_excludes_2022_02_14_partial_day(middle_df: pd.DataFrame) -> None:
    dates = set(middle_df["anchor_date"].dt.strftime("%Y-%m-%d"))
    assert "2022-02-14" not in dates


def test_middle_retains_2022_05_30(middle_df: pd.DataFrame) -> None:
    dates = set(middle_df["anchor_date"].dt.strftime("%Y-%m-%d"))
    assert "2022-05-30" in dates


# --- Manifest match with legacy ---
def test_middle_manifest_matches_legacy_current_data_source(
    middle_df: pd.DataFrame, legacy_df: pd.DataFrame
) -> None:
    assert len(middle_df) == len(legacy_df)
    assert set(middle_df["anchor_date"]) == set(legacy_df["anchor_date"])
    assert middle_df["split"].value_counts().to_dict() == legacy_df["split"].value_counts().to_dict()


def test_middle_selection_is_outcome_independent(middle_df: pd.DataFrame) -> None:
    assert (middle_df["selection_uses_outcomes"] == False).all()


# --- Hour contract ---
def test_middle_does_not_use_formal72_42_hour_contract(middle_meta: dict) -> None:
    assert middle_meta["hour_contract"] == "24_PER_ANCHOR_DAY"


def test_middle_does_not_use_36_day_coverage_manifest(middle_meta: dict) -> None:
    assert middle_meta["contract_id"] == "CURRENT_DATA_MIDDLE_23D_V1"


# --- Migration contract ---
def test_middle_migration_contract(middle_meta: dict) -> None:
    assert middle_meta["migration_contract_id"] == "ADAPT_FULL_TO_MIDDLE_V1"
    assert middle_meta["legacy_profile"] == "adapt_full"
    assert middle_meta["numeric_content_unchanged"] is True


# --- SHA256 ---
def test_middle_manifest_sha256(middle_meta: dict) -> None:
    actual = hashlib.sha256(MIDDLE_CSV.read_bytes()).hexdigest()
    assert actual == middle_meta["canonical_csv_sha256"]


# --- Result scope ---
def test_middle_result_scope(middle_meta: dict) -> None:
    assert middle_meta["result_scope"] == "CURRENT_DATA_SOURCE_BOUNDED"
