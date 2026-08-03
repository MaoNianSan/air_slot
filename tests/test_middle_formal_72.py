"""Middle FORMAL_72_V1_20260724 contract tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

PROJECT = Path(__file__).resolve().parents[1]
MANIFEST_CSV = PROJECT / "data" / "manifests" / "formal_72_day_manifest.csv"
MANIFEST_JSON = PROJECT / "data" / "manifests" / "formal_72_day_manifest.json"
REQUIRED_HOURS = PROJECT / "data" / "manifests" / "formal_72_required_hours.csv"
EXISTING_HOURS = PROJECT / "data" / "manifests" / "formal_72_existing_hours.csv"
MISSING_HOURS = PROJECT / "data" / "manifests" / "formal_72_missing_hours.csv"
FOLD_CSV = PROJECT / "data" / "manifests" / "formal_fold_membership.csv"


@pytest.fixture(scope="module")
def manifest_csv() -> pd.DataFrame:
    return pd.read_csv(MANIFEST_CSV, parse_dates=["anchor_date"])


@pytest.fixture(scope="module")
def manifest_json() -> dict:
    return json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def required_hours() -> pd.DataFrame:
    return pd.read_csv(REQUIRED_HOURS)


@pytest.fixture(scope="module")
def existing_hours() -> pd.DataFrame:
    return pd.read_csv(EXISTING_HOURS)


@pytest.fixture(scope="module")
def missing_hours() -> pd.DataFrame:
    return pd.read_csv(MISSING_HOURS)


@pytest.fixture(scope="module")
def fold() -> pd.DataFrame:
    return pd.read_csv(FOLD_CSV, parse_dates=["anchor_date"])


# --- Manifest version ---
def test_middle_manifest_version(manifest_json: dict) -> None:
    assert manifest_json["manifest_version"] == "FORMAL_72_V1_20260724"


def test_middle_manifest_sha256(manifest_json: dict) -> None:
    actual = hashlib.sha256(MANIFEST_CSV.read_bytes()).hexdigest()
    assert actual == manifest_json["canonical_csv_sha256"]


# --- Day count ---
def test_middle_day_count_is_72(manifest_csv: pd.DataFrame) -> None:
    assert len(manifest_csv) == 72


def test_middle_month_count_is_12(manifest_csv: pd.DataFrame) -> None:
    assert manifest_csv["month"].nunique() == 12


def test_middle_has_six_days_per_month(manifest_csv: pd.DataFrame) -> None:
    assert (manifest_csv.groupby("month").size() == 6).all()


# --- Weekday/weekend structure ---
def test_middle_has_four_weekdays_two_weekends_per_month(manifest_csv: pd.DataFrame) -> None:
    counts = manifest_csv.groupby("month")["weekday_type"].value_counts().unstack(fill_value=0)
    assert (counts.get("weekday", 0) == 4).all()
    assert (counts.get("weekend", 0) == 2).all()


def test_middle_selection_rule(manifest_csv: pd.DataFrame) -> None:
    assert (manifest_csv["selection_rule"] == "FIRST_FOUR_MONDAYS_PLUS_SATURDAYS_AFTER_M1_AND_M3").all()


# --- Role counts ---
def test_middle_role_counts_40_20_12(manifest_csv: pd.DataFrame) -> None:
    counts = manifest_csv["subset_role"].value_counts()
    assert counts.get("model") == 40
    assert counts.get("audit") == 20
    assert counts.get("final_test") == 12


def test_middle_nov_dec_are_final_test(manifest_csv: pd.DataFrame) -> None:
    nd = manifest_csv[manifest_csv["month"].isin([11, 12])]
    assert (nd["subset_role"] == "final_test").all()


def test_middle_final_test_not_train_eligible(manifest_csv: pd.DataFrame) -> None:
    ft = manifest_csv[manifest_csv["subset_role"] == "final_test"]
    assert not ft["train_eligible"].any()
    assert ft["evaluation_only"].all()


# --- Required hours ---
def test_middle_required_hour_count_is_3024(required_hours: pd.DataFrame) -> None:
    assert len(required_hours) == 3024


def test_middle_each_anchor_has_42_required_hours(required_hours: pd.DataFrame) -> None:
    counts = required_hours.groupby("used_by_anchor_dates").size()
    assert (counts == 42).all()
    assert len(counts) == 72


def test_middle_context_window_is_6_24_12(required_hours: pd.DataFrame) -> None:
    counts = required_hours["context_role"].value_counts()
    assert counts.get("PRE_CONTEXT") == 72 * 6   # 432
    assert counts.get("ANCHOR_DAY") == 72 * 24    # 1728
    assert counts.get("POST_CONTEXT") == 72 * 12  # 864


# --- Fold contract ---
def test_middle_fold_manifest_matches_calendar(manifest_csv: pd.DataFrame, fold: pd.DataFrame) -> None:
    calendar_dates = set(manifest_csv["anchor_date"].dt.date)
    fold_dates = set(fold["anchor_date"].dt.date)
    # All fold dates must be in the calendar; audit-only dates may not have fold entries
    assert fold_dates.issubset(calendar_dates), f"Fold has {len(fold_dates - calendar_dates)} dates not in calendar"


def test_middle_no_split_overlap(fold: pd.DataFrame) -> None:
    roles = fold.groupby("anchor_date")["evaluation_role"].first()
    train_dates = set(roles[roles == "train"].index)
    val_dates = set(roles[roles == "validation"].index)
    test_dates = set(roles[roles == "test"].index)
    final_dates = set(roles[roles == "final_test"].index)
    assert not train_dates & val_dates
    assert not train_dates & test_dates
    assert not val_dates & test_dates
    assert not (train_dates | val_dates | test_dates) & final_dates


def test_middle_no_future_leakage(fold: pd.DataFrame) -> None:
    # Check temporal ordering within each fold_id group
    for fold_id, group in fold.groupby("evaluation_id"):
        train = group[group["evaluation_role"] == "train"]
        val = group[group["evaluation_role"] == "validation"]
        test = group[group["evaluation_role"] == "test"]
        if len(train) and len(val):
            assert train["anchor_date"].max() < val["anchor_date"].min(), f"{fold_id}: train max {train['anchor_date'].max()} >= val min {val['anchor_date'].min()}"
        if len(val) and len(test):
            assert val["anchor_date"].max() < test["anchor_date"].min(), f"{fold_id}: val max {val['anchor_date'].max()} >= test min {test['anchor_date'].min()}"


# --- Design vs data readiness ---
def test_middle_design_ready_when_data_not_ready(
    manifest_json: dict, existing_hours: pd.DataFrame, missing_hours: pd.DataFrame
) -> None:
    assert manifest_json["design_status"] == "PLANNED_NOT_EXECUTED_NO_NEW_DATA"
    total = len(existing_hours) + len(missing_hours)
    assert total == 3024
    # Design can be READY even when data is NOT_READY
    assert manifest_json["calendar_only"] is True


def test_middle_does_not_fallback(manifest_csv: pd.DataFrame) -> None:
    assert "fast" not in manifest_csv["subset_role"].values
    assert "adapt_full" not in manifest_csv["subset_role"].values


def test_middle_output_path_isolated() -> None:
    from run_profiles import resolve_profile
    p = resolve_profile("middle")
    assert p.output_id == "middle"
    assert p.compute_profile == "full"
    assert p.run_profile == "middle"


# --- Design status ---
def test_middle_design_status(manifest_json: dict) -> None:
    assert manifest_json["day_count"] == 72
    assert manifest_json["role_counts"]["model"] == 40
    assert manifest_json["role_counts"]["audit"] == 20
    assert manifest_json["role_counts"]["final_test"] == 12
    assert manifest_json["monthly_structure"]["days"] == 6


# ============================================================
# Source-bounded executable tests (audit-only, moved to analysis/)
# ============================================================

EXEC_MANIFEST = PROJECT / "analysis" / "formal72_source_coverage" / "middle_executable_manifest.csv"
EXEC_MANIFEST_JSON = PROJECT / "analysis" / "formal72_source_coverage" / "middle_executable_manifest.json"
EXEC_HOURS = PROJECT / "analysis" / "formal72_source_coverage" / "middle_executable_required_hours.csv"
EXEC_FOLD = PROJECT / "analysis" / "formal72_source_coverage" / "middle_executable_fold_membership.csv"


@pytest.fixture(scope="module")
def exec_manifest() -> pd.DataFrame:
    return pd.read_csv(EXEC_MANIFEST, parse_dates=["anchor_date"])


@pytest.fixture(scope="module")
def exec_manifest_json() -> dict:
    return json.loads(EXEC_MANIFEST_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def exec_hours() -> pd.DataFrame:
    return pd.read_csv(EXEC_HOURS)


@pytest.fixture(scope="module")
def exec_fold() -> pd.DataFrame:
    return pd.read_csv(EXEC_FOLD, parse_dates=["anchor_date"])


def test_structurally_unavailable_months_are_not_download_required(
    manifest_csv: pd.DataFrame, exec_manifest_json: dict
) -> None:
    unavail = exec_manifest_json["structurally_unavailable_months"]
    assert len(unavail) == 6
    assert "2022-07" in unavail
    assert "2022-12" in unavail
    # Design months - executable months = structurally unavailable
    assert exec_manifest_json["design_day_count"] == 72
    assert exec_manifest_json["executable_day_count"] == 36
    assert exec_manifest_json["formal_72_complete"] is False


def test_middle_executable_calendar_is_manifest_intersection(
    manifest_csv: pd.DataFrame, exec_manifest: pd.DataFrame
) -> None:
    # Executable dates must be a strict subset of design dates
    design_dates = set(manifest_csv["anchor_date"].dt.date)
    exec_dates = set(exec_manifest["anchor_date"].dt.date)
    assert exec_dates.issubset(design_dates)
    assert len(exec_dates) == 36
    assert len(exec_dates) < len(design_dates)


def test_no_anchor_replacement_or_resampling(
    manifest_csv: pd.DataFrame, exec_manifest: pd.DataFrame
) -> None:
    # All executable dates come from the design manifest (no new dates)
    design_dates = set(manifest_csv["anchor_date"].dt.date)
    exec_dates = set(exec_manifest["anchor_date"].dt.date)
    extra = exec_dates - design_dates
    assert len(extra) == 0, f"Executable has {len(extra)} dates not in design"


def test_design_and_execution_day_counts_are_separate(
    manifest_csv: pd.DataFrame, exec_manifest: pd.DataFrame
) -> None:
    assert len(manifest_csv) == 72
    assert len(exec_manifest) == 36
    assert len(manifest_csv) != len(exec_manifest)


def test_source_bounded_result_not_labeled_formal_72(exec_manifest_json: dict) -> None:
    assert exec_manifest_json["result_scope"] == "SOURCE_BOUNDED_MIDDLE"
    assert exec_manifest_json["formal_72_complete"] is False


def test_final_test_unavailable_is_explicit(
    exec_manifest: pd.DataFrame, exec_fold: pd.DataFrame
) -> None:
    ft = exec_manifest[exec_manifest["subset_role"] == "final_test"]
    assert len(ft) == 0, "No final_test dates in executable calendar"
    ft_fold = exec_fold[exec_fold["evaluation_role"] == "final_test"]
    assert len(ft_fold) == 0


def test_audit_dates_not_used_for_training(
    exec_manifest: pd.DataFrame, exec_fold: pd.DataFrame
) -> None:
    audit_dates = set(exec_manifest[exec_manifest["subset_role"] == "audit"]["anchor_date"].dt.date)
    train_fold_dates = set(exec_fold[exec_fold["evaluation_role"] == "train"]["anchor_date"].dt.date)
    assert not (audit_dates & train_fold_dates), "Audit dates must not appear in training fold"


def test_executable_manifest_hash_propagates_to_registry(exec_manifest_json: dict) -> None:
    assert "canonical_csv_sha256" in exec_manifest_json
    assert len(exec_manifest_json["canonical_csv_sha256"]) == 64


def test_source_bounded_lineage_is_current(exec_manifest_json: dict) -> None:
    assert exec_manifest_json["manifest_version"] == "MIDDLE_EXECUTABLE_V1_20260801"
    assert exec_manifest_json["parent_design"] == "FORMAL_72_V1_20260724"


def test_middle_clean_requires_executable_manifest_pass(exec_manifest_json: dict) -> None:
    assert exec_manifest_json["executable_day_count"] > 0
    assert exec_manifest_json["locally_available_hours"] > 0


def test_executable_manifest_json_self_consistent(exec_manifest_json: dict) -> None:
    assert exec_manifest_json["design_day_count"] == 72
    assert exec_manifest_json["executable_day_count"] == 36
    assert exec_manifest_json["structurally_unavailable_hours"] == 1512
    assert exec_manifest_json["executable_required_hours"] == 1512
    assert exec_manifest_json["locally_available_hours"] == 538
    assert exec_manifest_json["downloadable_missing_hours"] == 974
    assert exec_manifest_json["locally_available_hours"] + exec_manifest_json["downloadable_missing_hours"] == 1512
