from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("artifacts/models/m1")


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_formal_cohort_has_frozen_counts_and_zero_final_test_access():
    cohort = _read(ROOT / "M1_FORMAL_TRAINING_COHORT_V1.json")
    assert cohort["train_episode_count"] == 128
    assert cohort["calibration_episode_count"] == 64
    assert cohort["development_episode_count"] == 128
    assert cohort["final_test_episode_count"] == 0
    assert cohort["final_test_access_count"] == 0
    assert cohort["selection_seed"] == 20260813
    assert cohort["selection_pre_outcome"] is True
    assert len(cohort["train_episode_ids"]) == len(set(cohort["train_episode_ids"])) == 128
    assert len(cohort["calibration_episode_ids"]) == len(set(cohort["calibration_episode_ids"])) == 64
    assert len(cohort["development_episode_ids"]) == len(set(cohort["development_episode_ids"])) == 128


def test_history_and_current_manifests_are_matched_except_history_mode():
    history = _read(ROOT / "M1_H16_HISTORY_PRIMARY/M1_H16_HISTORY_PRIMARY_MANIFEST.json")
    current = _read(ROOT / "M1_H16_CURRENT_COMPARATOR/M1_H16_CURRENT_COMPARATOR_MANIFEST.json")
    cohort = _read(ROOT / "M1_FORMAL_TRAINING_COHORT_V1.json")
    for key in (
        "hidden_size", "training_seed", "epochs", "optimizer", "learning_rate",
        "weight_decay", "batch_size", "training_cohort_hash", "calibration_cohort_hash",
        "target_contract_hash", "support_contract_hash", "feature_contract_hash", "scenario_count",
    ):
        assert history[key] == current[key]
    assert history["training_cohort_hash"] == cohort["cohort_hash"]
    assert history["history_mode"] == "FULL_ADAPTIVE_CAUSAL_PREFIX"
    assert current["history_mode"] == "NO_HISTORY_CURRENT_OBSERVATION"
    assert current["history_contract"]["history_encoder_enabled"] is False
    assert current["history_contract"]["future_information"] == "FORBIDDEN"
    assert current["history_contract"]["full_episode_access"] == "FORBIDDEN"
    assert history["training_seed"] == current["training_seed"] == 20260813
    assert history["epochs"] == current["epochs"] == 8
    assert history["development_used_for_parameter_selection"] is False
    assert current["development_used_for_parameter_selection"] is False
    assert history["final_test_access_count"] == current["final_test_access_count"] == 0


def test_matched_audit_passes_and_records_only_intended_scientific_difference():
    audit = _read(ROOT / "M1_H16_HISTORY_CURRENT_MATCHED_AUDIT.json")
    assert audit["status"] == "PASS"
    assert audit["different_history_mode"] is True
    assert audit["history_mode_history"] == "FULL_ADAPTIVE_CAUSAL_PREFIX"
    assert audit["history_mode_current"] == "NO_HISTORY_CURRENT_OBSERVATION"
    assert audit["development_used_for_parameter_selection"] is False
    assert audit["final_test_access_count"] == 0
    assert audit["final_test_access_check"] is True
    assert all(audit[key] is True for key in audit if key.startswith("same_"))


def test_formal_materializer_contains_no_parameter_averaging_or_fast_training_authority():
    source = Path("validation/model/m1_frozen_h16_artifact_materialization.py").read_text(encoding="utf-8")
    assert "averaged_state" not in source
    assert "seed_states" not in source
    assert "_build_or_load_cache" not in source
    assert "M1_FORMAL_TRAINING_COHORT_V1" in source
    assert "PRIMARY_TRAINING_SEED" in source
