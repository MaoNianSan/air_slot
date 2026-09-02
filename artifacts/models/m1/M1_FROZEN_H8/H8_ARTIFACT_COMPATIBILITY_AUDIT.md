# H8 Artifact Compatibility Audit

- Old checkpoint: `D:\research\air_slot\code\explore\artifacts\diagnostics\model\m1_v2_tuning_stage1_fast\GRU_H8\M1_V2_FAST_TRAIN_MODE.pt`
- Old checkpoint hash: `sha256:302a5a7d363576bf3d3948ddc836605321748d74848ced0921ea011fd5da2659`
- Conclusion: **STRUCTURAL_ARTIFACT_MISMATCH**

## Findings

- Frozen support: `{'T_IB_REMAINING_HAZARD': 360, 'D_OB': 180, 'D_TX': 60}`
- Checkpoint support: `{'T_IB_REMAINING_HAZARD': 360, 'D_OB': 210, 'D_TX': 60}`
- D_OB embedding rows: `43`; expected for 180 support: `37`
- The D_OB embedding index is the finite-bin plus overflow decoder basis, so 210 versus 180 changes target encoding and decoder semantics.
- Calibration is not transferable because calibration labels and hazard/target bin intervals are support-bound.
- Tensor dimensions are not all compatible: the D_OB conditioning embedding is structurally different.
- The checkpoint is not modified. A new frozen-contract artifact is required.

## Machine-readable evidence

```json
{
  "actual_support": {
    "D_OB": 210,
    "D_TX": 60,
    "T_IB_REMAINING_HAZARD": 360
  },
  "calibration_contract": {
    "final_test_access_count": 0,
    "positive_quantile_calibration": "QUANTILE_CALIBRATION_NOT_APPLIED",
    "predecessor_calibration_method": "TEMPERATURE_ON_HAZARD_LOGITS",
    "predecessor_probability_calibration": "DISCRETE_HAZARD_EVENT_TIME_NLL",
    "split": "calibration",
    "successor_zero_mass_calibration": "HURDLE_ZERO_BINARY_CE_TEMPERATURE",
    "version": "M1_CALIBRATION_CONTRACT_V1"
  },
  "calibration_diagnostics": {},
  "calibration_support_compatible": false,
  "conclusion": "STRUCTURAL_ARTIFACT_MISMATCH",
  "d_ob_embedding_rows_expected_for_180": 37,
  "d_ob_embedding_rows_in_checkpoint": 43,
  "expected": {
    "causal": true,
    "hidden_size": 8,
    "layers": 1,
    "support": {
      "D_OB": 180,
      "D_TX": 60,
      "T_IB_REMAINING_HAZARD": 360
    }
  },
  "loader_behavior": "M1Pipeline.load deserializes the checkpoint; frozen compatibility is rejected by the explicit contract gate, not by metadata rewriting.",
  "old_checkpoint": "D:\\research\\air_slot\\code\\explore\\artifacts\\diagnostics\\model\\m1_v2_tuning_stage1_fast\\GRU_H8\\M1_V2_FAST_TRAIN_MODE.pt",
  "old_checkpoint_hash": "sha256:302a5a7d363576bf3d3948ddc836605321748d74848ced0921ea011fd5da2659",
  "old_contracts": {
    "D_OB": {
      "bin_width_minutes": 5,
      "max_finite_minutes": 210,
      "quantile_levels": [
        0.1,
        0.3,
        0.5,
        0.7,
        0.9
      ],
      "target_name": "D_OB",
      "upper_tail_policy": "UNRESOLVED",
      "upper_tail_policy_reference": null
    },
    "D_TX": {
      "bin_width_minutes": 5,
      "max_finite_minutes": 60,
      "quantile_levels": [
        0.1,
        0.3,
        0.5,
        0.7,
        0.9
      ],
      "target_name": "D_TX",
      "upper_tail_policy": "UNRESOLVED",
      "upper_tail_policy_reference": null
    },
    "T_IB_REMAINING_HAZARD": {
      "bin_width_minutes": 5,
      "max_finite_minutes": 360,
      "target_name": "T_IB_REMAINING_HAZARD"
    }
  },
  "target_encoder_decoder_support_compatible": false,
  "tensor_shapes": {
    "d_ob_embedding.weight": [
      43,
      8
    ],
    "d_ob_quantile_head.bias": [
      5
    ],
    "d_ob_quantile_head.weight": [
      5,
      32
    ],
    "d_ob_zero_head.bias": [
      1
    ],
    "d_ob_zero_head.weight": [
      1,
      32
    ],
    "d_tx_quantile_head.bias": [
      5
    ],
    "d_tx_quantile_head.weight": [
      5,
      40
    ],
    "d_tx_zero_head.bias": [
      1
    ],
    "d_tx_zero_head.weight": [
      1,
      40
    ],
    "fast_encoder.projection.bias": [
      8
    ],
    "fast_encoder.projection.weight": [
      8,
      39
    ],
    "gru.bias_hh_l0": [
      24
    ],
    "gru.bias_ih_l0": [
      24
    ],
    "gru.weight_hh_l0": [
      24,
      8
    ],
    "gru.weight_ih_l0": [
      24,
      39
    ],
    "hazard_head.bias": [
      72
    ],
    "hazard_head.weight": [
      72,
      24
    ],
    "ib_embedding.weight": [
      73,
      8
    ],
    "static_encoder.projection.bias": [
      8
    ],
    "static_encoder.projection.weight": [
      8,
      4
    ]
  }
}
```
