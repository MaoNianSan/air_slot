# G0_LINEAGE_AUDIT

- Status: `FROZEN_BUT_LINEAGE_PARTIAL`
- Blocking state: `BLOCKED_LINEAGE`

```json
{
  "blocking_state": "BLOCKED_LINEAGE",
  "finding": "Final-Test projection and checkpoint hashes are matched, and the 2019 temporal partition/reproduction manifests are present. The table records split and generator evidence separately from hash matching; full claim-level number-to-source reconciliation remains incomplete.",
  "manifest_rows": [
    {
      "authority_lineage": "artifacts/experiment/final_test_v2_stage_matched_canonical_v2",
      "cohort_identity": {
        "stage1": "canonical_v2 eligible candidates; q=0.10"
      },
      "figure_id": "FIGURE3",
      "frozen_flags": {
        "model_retrained": false,
        "new_final_test_access_opened": false,
        "parameter_reselected": false,
        "raw_final_test_data_read": false,
        "recalibration_performed": false,
        "scientific_definition_changed": false
      },
      "input_checks": [
        {
          "declared_sha256": "fbcf25389312ac799e19f83469369eb9fad1df080e5fed411227211248badd92",
          "exists": true,
          "hash_match": true,
          "path": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\checkpoints\\ATTENTION_DECISIONS.json"
        },
        {
          "declared_sha256": "9dfdedecdb0bed80882d2d224240f0454db0204c97ef0decbcf17b93e0652bd9",
          "exists": true,
          "hash_match": true,
          "path": "D:\\research\\air_slot\\code\\explore\\artifacts\\paper_results_v2_final_test_rmb\\stage_q_sensitivity\\STAGE_Q_SCREENING_FIGURE_DATA.csv"
        }
      ],
      "manifest": "D:\\Local_Projects\\airslot\\artifacts\\paper_figures\\before_skill_optimization_20261003\\artifacts\\paper_figures\\figure3_stage1\\FIGURE3_MANIFEST.json",
      "status": "MATCHED"
    },
    {
      "authority_lineage": "artifacts/experiment/final_test_v2_stage_matched_canonical_v2",
      "cohort_identity": {
        "stage2": "fixed HISTORY_JOINT Stage-II cohort"
      },
      "figure_id": "FIGURE4",
      "frozen_flags": {
        "model_retrained": false,
        "new_final_test_access_opened": false,
        "parameter_reselected": false,
        "raw_final_test_data_read": false,
        "recalibration_performed": false,
        "scientific_definition_changed": false
      },
      "input_checks": [
        {
          "declared_sha256": "fbcf25389312ac799e19f83469369eb9fad1df080e5fed411227211248badd92",
          "exists": true,
          "hash_match": true,
          "path": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\checkpoints\\ATTENTION_DECISIONS.json"
        },
        {
          "declared_sha256": "4561d385ae16d211d9489019b6a7f5b05b92e96654f8409970324f5cd6ce0161",
          "exists": true,
          "hash_match": true,
          "path": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\checkpoints\\RECOVERY_DECISIONS.json"
        },
        {
          "declared_sha256": "1f4f35781f760c96b307bac81a069f1b18699a724e180b36a7cdbe7c715e219a",
          "exists": true,
          "hash_match": true,
          "path": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\checkpoints\\REFERENCE_RECOVERY_COHORT.json"
        }
      ],
      "manifest": "D:\\Local_Projects\\airslot\\artifacts\\paper_figures\\before_skill_optimization_20261003\\artifacts\\paper_figures\\figure4_stage2\\FIGURE4_MANIFEST.json",
      "status": "MATCHED"
    },
    {
      "authority_lineage": "artifacts/experiment/final_test_v2_stage_matched_canonical_v2",
      "cohort_identity": {
        "cohort": "fixed 16-case recovery cohort",
        "comparators": [
          "CURRENT_JOINT",
          "HISTORY_POINT",
          "HISTORY_MARGINAL"
        ],
        "reference": "HISTORY_JOINT"
      },
      "figure_id": "FIGURE5",
      "frozen_flags": {
        "model_retrained": false,
        "new_final_test_access_opened": false,
        "parameter_reselected": false,
        "raw_final_test_data_read": false,
        "recalibration_performed": false,
        "scientific_definition_changed": false
      },
      "input_checks": [
        {
          "declared_sha256": "4284d15328226665b47b7c7f38bf3f7b84d84602b0fce7fbd7e9123fef9257f7",
          "exists": true,
          "hash_match": true,
          "path": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\PAPER_FACING_SECTION5_RESULTS.json"
        },
        {
          "declared_sha256": "5dac25bc83d030d0c4f3e37fc641622a8d451595ae57418cd0ebc096fce11974",
          "exists": true,
          "hash_match": true,
          "path": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\checkpoints\\BOOTSTRAP.json"
        },
        {
          "declared_sha256": "a5caeedc0cfadf089bba217bfa8279f25515810e6f57358cc37fb0d8c8cd5a9c",
          "exists": true,
          "hash_match": true,
          "path": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\checkpoints\\M4_COMPARISONS.json"
        }
      ],
      "manifest": "D:\\Local_Projects\\airslot\\artifacts\\paper_figures\\before_skill_optimization_20261003\\artifacts\\paper_figures\\figure5_representation\\FIGURE5_MANIFEST.json",
      "status": "MATCHED"
    },
    {
      "authority_lineage": "artifacts/experiment/final_test_v2_stage_matched_canonical_v2",
      "cohort_identity": {
        "stage1": "canonical_v2 eligible candidates; q=0.10"
      },
      "figure_id": "FIGURE3",
      "frozen_flags": {
        "model_retrained": false,
        "new_final_test_access_opened": false,
        "parameter_reselected": false,
        "raw_final_test_data_read": false,
        "recalibration_performed": false,
        "scientific_definition_changed": false
      },
      "input_checks": [
        {
          "declared_sha256": "fbcf25389312ac799e19f83469369eb9fad1df080e5fed411227211248badd92",
          "exists": true,
          "hash_match": true,
          "path": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\checkpoints\\ATTENTION_DECISIONS.json"
        },
        {
          "declared_sha256": "9dfdedecdb0bed80882d2d224240f0454db0204c97ef0decbcf17b93e0652bd9",
          "exists": true,
          "hash_match": true,
          "path": "D:\\research\\air_slot\\code\\explore\\artifacts\\paper_results_v2_final_test_rmb\\stage_q_sensitivity\\STAGE_Q_SCREENING_FIGURE_DATA.csv"
        }
      ],
      "manifest": "D:\\Local_Projects\\airslot\\artifacts\\paper_figures\\figure3_stage1\\FIGURE3_MANIFEST.json",
      "status": "MATCHED"
    },
    {
      "authority_lineage": "artifacts/experiment/final_test_v2_stage_matched_canonical_v2",
      "cohort_identity": {
        "stage2": "fixed HISTORY_JOINT Stage-II cohort"
      },
      "figure_id": "FIGURE4",
      "frozen_flags": {
        "model_retrained": false,
        "new_final_test_access_opened": false,
        "parameter_reselected": false,
        "raw_final_test_data_read": false,
        "recalibration_performed": false,
        "scientific_definition_changed": false
      },
      "input_checks": [
        {
          "declared_sha256": "fbcf25389312ac799e19f83469369eb9fad1df080e5fed411227211248badd92",
          "exists": true,
          "hash_match": true,
          "path": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\checkpoints\\ATTENTION_DECISIONS.json"
        },
        {
          "declared_sha256": "4561d385ae16d211d9489019b6a7f5b05b92e96654f8409970324f5cd6ce0161",
          "exists": true,
          "hash_match": true,
          "path": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\checkpoints\\RECOVERY_DECISIONS.json"
        },
        {
          "declared_sha256": "1f4f35781f760c96b307bac81a069f1b18699a724e180b36a7cdbe7c715e219a",
          "exists": true,
          "hash_match": true,
          "path": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\checkpoints\\REFERENCE_RECOVERY_COHORT.json"
        }
      ],
      "manifest": "D:\\Local_Projects\\airslot\\artifacts\\paper_figures\\figure4_stage2\\FIGURE4_MANIFEST.json",
      "status": "MATCHED"
    },
    {
      "authority_lineage": "artifacts/experiment/final_test_v2_stage_matched_canonical_v2",
      "cohort_identity": {
        "cohort": "fixed 16-case recovery cohort",
        "comparators": [
          "CURRENT_JOINT",
          "HISTORY_POINT",
          "HISTORY_MARGINAL"
        ],
        "reference": "HISTORY_JOINT"
      },
      "figure_id": "FIGURE5",
      "frozen_flags": {
        "model_retrained": false,
        "new_final_test_access_opened": false,
        "parameter_reselected": false,
        "raw_final_test_data_read": false,
        "recalibration_performed": false,
        "scientific_definition_changed": false
      },
      "input_checks": [
        {
          "declared_sha256": "4284d15328226665b47b7c7f38bf3f7b84d84602b0fce7fbd7e9123fef9257f7",
          "exists": true,
          "hash_match": true,
          "path": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\PAPER_FACING_SECTION5_RESULTS.json"
        },
        {
          "declared_sha256": "5dac25bc83d030d0c4f3e37fc641622a8d451595ae57418cd0ebc096fce11974",
          "exists": true,
          "hash_match": true,
          "path": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\checkpoints\\BOOTSTRAP.json"
        },
        {
          "declared_sha256": "a5caeedc0cfadf089bba217bfa8279f25515810e6f57358cc37fb0d8c8cd5a9c",
          "exists": true,
          "hash_match": true,
          "path": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\checkpoints\\M4_COMPARISONS.json"
        }
      ],
      "manifest": "D:\\Local_Projects\\airslot\\artifacts\\paper_figures\\figure5_representation\\FIGURE5_MANIFEST.json",
      "status": "MATCHED"
    }
  ],
  "paper_surface_rows": [
    {
      "commit_or_hash": "8360dd7d88958ae139322d0ea5c66f1c5fe6455c",
      "frozen": true,
      "generator": "formal/v2_phase7/project_delay_vs_consequence_stage1.py",
      "paper_surface": "FIGURE3",
      "projection_path": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\PAPER_FACING_DELAY_VS_CONSEQUENCE_STAGE1.json",
      "reproducible": true,
      "source_artifact": "jatm-final-test-freeze-20260920",
      "source_checkpoints_present": true,
      "split": "held-out October-December 2019",
      "status": "MATCHED"
    },
    {
      "commit_or_hash": "8360dd7d88958ae139322d0ea5c66f1c5fe6455c",
      "frozen": true,
      "generator": "formal/v2_phase7/project_section5_paper_facing.py",
      "paper_surface": "FIGURE4",
      "projection_path": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\PAPER_FACING_SECTION5_RESULTS.json",
      "reproducible": true,
      "source_artifact": "jatm-final-test-freeze-20260920",
      "source_checkpoints_present": true,
      "split": "held-out October-December 2019",
      "status": "MATCHED"
    },
    {
      "commit_or_hash": "8360dd7d88958ae139322d0ea5c66f1c5fe6455c",
      "frozen": true,
      "generator": "formal/v2_phase7/project_section5_paper_facing.py",
      "paper_surface": "FIGURE5",
      "projection_path": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\PAPER_FACING_SECTION5_RESULTS.json",
      "reproducible": true,
      "source_artifact": "jatm-final-test-freeze-20260920",
      "source_checkpoints_present": true,
      "split": "held-out October-December 2019",
      "status": "MATCHED"
    },
    {
      "artifact_value": 5,
      "claim_value": "5/13",
      "commit_or_hash": "8360dd7d88958ae139322d0ea5c66f1c5fe6455c",
      "generator": "formal/v2_phase7/project_delay_vs_consequence_stage1.py",
      "paper_surface": "Stage-I TURN q=0.10 changed positions",
      "source_artifact": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\PAPER_FACING_DELAY_VS_CONSEQUENCE_STAGE1.json",
      "split": "held-out October-December 2019",
      "status": "MATCHED"
    },
    {
      "artifact_value": "29/3",
      "claim_value": "29/3",
      "generator": "formal/v2_phase7/project_section5_paper_facing.py",
      "paper_surface": "PRE shortlist capacity N/K",
      "source_artifact": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\PAPER_FACING_SECTION5_RESULTS.json",
      "split": "held-out October-December 2019",
      "stage": "PRE",
      "status": "MATCHED"
    },
    {
      "artifact_value": "127/13",
      "claim_value": "127/13",
      "generator": "formal/v2_phase7/project_section5_paper_facing.py",
      "paper_surface": "TURN shortlist capacity N/K",
      "source_artifact": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\PAPER_FACING_SECTION5_RESULTS.json",
      "split": "held-out October-December 2019",
      "stage": "TURN",
      "status": "MATCHED"
    },
    {
      "artifact_value": "3/3",
      "claim_value": "3/3",
      "generator": "formal/v2_phase7/project_section5_paper_facing.py",
      "paper_surface": "Stage-II positive targets",
      "source_artifact": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\PAPER_FACING_SECTION5_RESULTS.json",
      "split": "held-out October-December 2019",
      "stage": "PRE",
      "status": "MATCHED"
    },
    {
      "artifact_value": "10/13",
      "claim_value": "10/13",
      "generator": "formal/v2_phase7/project_section5_paper_facing.py",
      "paper_surface": "Stage-II positive targets",
      "source_artifact": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\PAPER_FACING_SECTION5_RESULTS.json",
      "split": "held-out October-December 2019",
      "stage": "TURN",
      "status": "MATCHED"
    },
    {
      "artifact_value": "13/16",
      "claim_value": "13/16",
      "generator": "formal/v2_phase7/project_section5_paper_facing.py",
      "paper_surface": "Stage-II positive targets",
      "source_artifact": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\PAPER_FACING_SECTION5_RESULTS.json",
      "split": "held-out October-December 2019",
      "stage": "TOTAL",
      "status": "MATCHED"
    },
    {
      "artifact_value": "5 min",
      "claim_value": "5 min",
      "generator": "formal/v2_phase7/project_section5_paper_facing.py",
      "paper_surface": "Median positive u",
      "source_artifact": "D:\\research\\air_slot\\code\\explore\\artifacts\\experiment\\final_test_v2_stage_matched_canonical_v2\\PAPER_FACING_SECTION5_RESULTS.json",
      "split": "held-out October-December 2019",
      "stage": "TOTAL",
      "status": "MATCHED"
    },
    {
      "commit_or_hash": null,
      "frozen": true,
      "generator": "PRE_MULTIYEAR_DEVELOPMENT_V1",
      "paper_surface": "2019 temporal partition",
      "reproducible": true,
      "source_artifact": "D:\\research\\air_slot\\code\\explore\\artifacts\\models\\pre\\PRE_MULTIYEAR_V1\\2019\\PRE_MULTIYEAR_DEVELOPMENT_MANIFEST.json",
      "split": "train/calibration/development/test",
      "status": "MATCHED"
    }
  ],
  "required_columns": [
    "paper claim/table",
    "split",
    "source artifact",
    "generator",
    "commit/hash",
    "frozen",
    "reproducible",
    "status"
  ],
  "schema_version": "AIR_SLOT_G0_LINEAGE_AUDIT_V1",
  "scientific_recomputation": false,
  "status": "FROZEN_BUT_LINEAGE_PARTIAL",
  "status_counts": {
    "MATCHED": 6
  }
}
```
