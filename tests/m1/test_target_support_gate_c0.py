from validation.m1_v2_target_support_gate_c0 import run


def test_c0_is_read_only_and_emits_three_decisions(tmp_path):
    report = run(tmp_path)

    assert report["TARGET_SUPPORT_C0_STATUS"] == "TARGET_SUPPORT_C0_DATA_ANOMALY"
    assert report["b2_baseline"]["feature_contract_unchanged"] is True
    assert report["overflow_forensic"]["row_count"] == 90
    assert report["overflow_counts"]["T_IB_REMAINING_HAZARD"]["train"] == 2
    assert report["overflow_counts"]["D_OB"]["train"] == 34
    assert report["overflow_counts"]["D_TX"]["development"] == 28
    assert [item["recommendation"] for item in report["human_decisions"]] == [
        "KEEP_360", "EXPAND_TO_210", "KEEP_60"
    ]
    assert report["train_value_loss_truncation"]["TRAIN_VALUE_LOSS_TRUNCATION"] is False
    assert report["conditioning_consequences"]["D_TX_PARENT_CONDITIONING_ROLE"] == "NONE"
    assert report["safety"] == {
        "M1_TRAINING_RUNS": 0,
        "TUNING_RUNS": 0,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "GATE_B2_FEATURE_FREEZE": True,
        "M1_TARGET_SUPPORT_FROZEN": False,
        "HYPERPARAMETER_TUNING_AUTHORIZED": False,
    }
    assert (tmp_path / "AIR_SLOT_M1_V2_TARGET_SUPPORT_GATE_C0.json").is_file()
    assert (tmp_path / "M1_V2_TARGET_SUPPORT_GATE_C0_THRESHOLDS.csv").is_file()
    assert (tmp_path / "M1_V2_TARGET_SUPPORT_GATE_C0_OVERFLOW.csv").is_file()
    assert (tmp_path / "M1_V2_TARGET_SUPPORT_GATE_C0_HUMAN_REVIEW_PACKET.md").is_file()


def test_c0_train_profiles_and_tail_bands_are_frozen_cache_values(tmp_path):
    report = run(tmp_path)

    assert report["train_profiles"]["T_IB_REMAINING_HAZARD"]["max"] == 365.0
    assert report["train_profiles"]["D_OB"]["max"] == 343.0
    assert report["train_profiles"]["D_TX"]["max"] == 40.0
    assert report["d_ob_train_tail_bands"] == {
        "180--210": 24,
        "210--240": 0,
        "240--300": 0,
        "300--360": 10,
        ">360": 0,
    }
    assert report["scenario_representation"]["T_IB_REMAINING_HAZARD"]["absolute_error_mean_minutes"] == 2.5
    assert report["scenario_representation"]["D_OB"]["absolute_error_max_minutes"] == 158.0
