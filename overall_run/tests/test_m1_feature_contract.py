from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.m1_feature_contract import M1FeatureContract, M1FeatureContractError


def _contract() -> M1FeatureContract:
    frame = pd.DataFrame({"numeric": [1.0], "category": ["A"]})
    return M1FeatureContract.build(frame, ["numeric", "category"], ["category"])


def test_train_inference_order_mismatch_rejected() -> None:
    contract = _contract()
    swapped = pd.DataFrame({"category": ["A"], "numeric": [1.0]})
    with pytest.raises(M1FeatureContractError, match="M1_INFERENCE_FEATURE_ORDER_MISMATCH"):
        contract.validate_feature_frame(swapped)


def test_authoritative_contract_reorders_full_pipeline_frame_explicitly() -> None:
    contract = _contract()
    full = pd.DataFrame({"extra": [7], "category": ["A"], "numeric": [1.0]})
    selected = contract.select_authoritative(full)
    assert list(selected.columns) == ["numeric", "category"]


def test_feature_contract_dtype_mismatch_rejected() -> None:
    contract = _contract()
    wrong = pd.DataFrame({"numeric": ["1.0"], "category": ["A"]})
    with pytest.raises(M1FeatureContractError, match="M1_INFERENCE_DTYPE_MISMATCH"):
        contract.validate_feature_frame(wrong)
