from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.m4_pnb_audit import (
    AUDIT_SEED_NAMESPACE,
    _write_parquet,
    capture_registered_hashes,
    generate_audit_m3_library,
    manual_pnb_reconstruction,
    nonnull_triggered_rows,
    validate_sample_ids,
)
from src.utils import stable_seed


def _inputs() -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, np.ndarray]]:
    pre = {
        "F": np.array([10.0, 4.0, 1.0]),
        "P": np.array([2.0, 5.0, 1.0]),
        "R": np.array([1.0, 1.0, 2.0]),
    }
    recovery = {
        "F": np.array([0.5, 0.1, 0.0]),
        "P": np.array([0.2, 0.4, 0.0]),
        "R": np.array([0.1, 0.5, 0.0]),
    }
    implementation = {
        "F": np.array([0.5, 0.5, 0.2]),
        "P": np.array([0.2, 0.2, 0.1]),
        "R": np.array([0.1, 0.1, 0.1]),
    }
    return pre, recovery, implementation


def test_pnb_formula_matches_manual_reconstruction() -> None:
    pre, recovery, implementation = _inputs()
    result = manual_pnb_reconstruction(pre, recovery, implementation)
    recovered = sum(recovery[channel] * pre[channel] for channel in ("F", "P", "R"))
    cost = sum(implementation.values())
    assert result["positive_net_benefit_probability"] == np.mean(recovered > cost)


def test_pnb_uses_total_recovered_rmb() -> None:
    pre, recovery, implementation = _inputs()
    result = manual_pnb_reconstruction(pre, recovery, implementation)
    expected = sum(recovery[channel] * pre[channel] for channel in ("F", "P", "R"))
    assert np.array_equal(result["recovered_total"], expected)


def test_pnb_uses_total_implementation_rmb() -> None:
    pre, recovery, implementation = _inputs()
    result = manual_pnb_reconstruction(pre, recovery, implementation)
    assert np.array_equal(result["implementation_total"], sum(implementation.values()))


def test_pnb_strict_greater_than() -> None:
    pre = {channel: np.array([1.0, 1.0]) for channel in ("F", "P", "R")}
    recovery = {
        "F": np.array([1.0, 1.0]),
        "P": np.zeros(2),
        "R": np.zeros(2),
    }
    implementation = {
        "F": np.array([1.0, 0.9]),
        "P": np.zeros(2),
        "R": np.zeros(2),
    }
    result = manual_pnb_reconstruction(pre, recovery, implementation)
    assert result["positive_net_benefit_probability"] == 0.5
    assert result["nonnegative_net_benefit_probability"] == 1.0
    assert result["strict_vs_nonstrict_equal_draws"] == 1


def test_pnb_cost_counted_once() -> None:
    pre, recovery, implementation = _inputs()
    result = manual_pnb_reconstruction(pre, recovery, implementation)
    expected_post = result["pre_total"] - result["recovered_total"] + result["implementation_total"]
    assert np.array_equal(result["post_action_total"], expected_post)
    assert np.array_equal(
        result["net_benefit"],
        result["recovered_total"] - result["implementation_total"],
    )


def test_pnb_sample_alignment() -> None:
    assert np.array_equal(validate_sample_ids([0, 1, 2], 3), np.arange(3))
    with pytest.raises(RuntimeError, match="SAMPLE_ID_ALIGNMENT"):
        validate_sample_ids([0, 2, 1], 3)


def test_pnb_action_order_invariance() -> None:
    pre, recovery, implementation = _inputs()
    actions = {
        "A11": (recovery, implementation),
        "A22": (
            {channel: values * 0.8 for channel, values in recovery.items()},
            implementation,
        ),
    }
    first = {
        action: manual_pnb_reconstruction(pre, *values)["positive_net_benefit_probability"]
        for action, values in actions.items()
    }
    second = {
        action: manual_pnb_reconstruction(pre, *actions[action])["positive_net_benefit_probability"]
        for action in reversed(actions)
    }
    assert first == second


def test_pnb_channel_order_invariance() -> None:
    pre, recovery, implementation = _inputs()
    expected = manual_pnb_reconstruction(pre, recovery, implementation)
    reverse = lambda values: dict(reversed(list(values.items())))
    actual = manual_pnb_reconstruction(
        reverse(pre), reverse(recovery), reverse(implementation)
    )
    assert np.array_equal(actual["net_benefit"], expected["net_benefit"])


def test_pnb_failure_keeps_cost() -> None:
    parameters = pd.DataFrame(
        [
            {
                "action_id": "A11",
                "mu_F": 0.4,
                "mu_P": 0.2,
                "mu_R": 0.1,
                "kbar_rmb_F": 0.1,
                "kbar_rmb_P": 0.1,
                "kbar_rmb_R": 0.1,
                "recovery_concentration": 18.0,
                "cost_cv": 0.1,
                "failure_probability": 0.5,
            }
        ]
    )
    recovery, cost, success = generate_audit_m3_library(parameters, 512, 7)
    failure = ~success["A11"]
    assert failure.any()
    assert np.all(recovery["A11"][failure] == 0.0)
    assert np.all(cost["A11"][failure].sum(axis=1) > 0.0)


def test_pnb_excludes_a00_from_non_null_rates() -> None:
    frame = pd.DataFrame(
        {
            "action_id": ["A00", "A11", "A22", "A11"],
            "trigger": [True, True, False, True],
        }
    )
    result = nonnull_triggered_rows(frame)
    assert result["action_id"].tolist() == ["A11", "A11"]


def test_pnb_audit_does_not_modify_formal_artifacts(tmp_path: Path) -> None:
    formal = tmp_path / "formal.bin"
    formal.write_bytes(b"formal-baseline")
    digest = hashlib.sha256(formal.read_bytes()).hexdigest()
    registry = {
        "artifacts": [
            {"artifact_name": "formal.bin", "sha256": digest}
        ]
    }
    (tmp_path / "artifact_registry.json").write_text(json.dumps(registry), encoding="utf-8")
    before = capture_registered_hashes(tmp_path)
    _write_parquet(pd.DataFrame({"value": [1]}), tmp_path / "audits" / "m4_test.parquet")
    after = capture_registered_hashes(tmp_path)
    assert before == after
    assert formal.read_bytes() == b"formal-baseline"


def test_pnb_mc_audit_uses_independent_seed_namespace() -> None:
    formal_seed = stable_seed(20260718, "M3_RESPONSE", "A11", "success")
    audit_seed = stable_seed(20260718, AUDIT_SEED_NAMESPACE, 0, "A11", "success")
    second_audit_seed = stable_seed(20260718, AUDIT_SEED_NAMESPACE, 1, "A11", "success")
    assert formal_seed != audit_seed
    assert audit_seed != second_audit_seed
