from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.input import write_json
from src.pipeline import (
    _artifact_registry,
    _validate_config,
    _validate_published_target_metadata,
    load_config,
)
from src.target_contract import target_contract_metadata
from src.validate import PreBundle, _validate_target_contract


def _bundle(episodes: pd.DataFrame) -> PreBundle:
    empty = pd.DataFrame()
    return PreBundle(episodes, empty, empty, empty, empty)


def _episodes(rows: int = 20) -> pd.DataFrame:
    raw = pd.Series(np.arange(rows, dtype=float))
    return pd.DataFrame({
        "episode_valid": True,
        "split": ["train"] * (rows // 2) + ["test"] * (rows - rows // 2),
        "observed_movement_time": raw + 100.0,
        "reference_movement_time": 100.0,
        "y_movement_raw": raw,
        "y_movement_model": raw,
        "m1_outcome_label": raw,
    })


class FormalTargetContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = load_config(mode="fast")
        # Use no-op quantiles so identity fixtures remain traceable sensitivity labels.
        self.cfg["labels"]["sensitivity_transform"]["clip_quantiles"] = [0.0, 1.0]

    def test_formal_alias_selects_raw_when_both_labels_exist(self) -> None:
        episodes = _episodes()
        episodes["y_movement_model"] = episodes["y_movement_raw"].clip(0.0, 9.0)
        result = _validate_target_contract(_bundle(episodes), self.cfg)
        self.assertEqual(result["formal_target_column"], "y_movement_raw")
        self.assertEqual(result["label_identity_mismatch_count"], 0)

    def test_missing_raw_blocks_without_model_fallback(self) -> None:
        episodes = _episodes().drop(columns="y_movement_raw")
        with self.assertRaisesRegex(ValueError, "FORMAL_TARGET_CONTRACT_BLOCKED"):
            _validate_target_contract(_bundle(episodes), self.cfg)

    def test_raw_model_differences_do_not_change_formal_alias(self) -> None:
        episodes = _episodes(24)
        episodes["y_movement_model"] = episodes["y_movement_raw"].clip(0.0, 11.0)
        result = _validate_target_contract(_bundle(episodes), self.cfg)
        self.assertEqual(result["raw_model_difference_rows"], 12)
        self.assertEqual(result["label_identity_mismatch_count"], 0)

    def test_target_candidates_are_rejected(self) -> None:
        cfg = copy.deepcopy(self.cfg)
        cfg["labels"]["target_candidates"] = ["y_movement_model", "y_movement_raw"]
        with self.assertRaisesRegex(ValueError, "must not contain target_candidates"):
            _validate_config(cfg)

    def test_registry_publishes_exact_contract_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = _artifact_registry(Path(directory), self.cfg, "fixture")
        self.assertEqual(registry["formal_target_column"], "y_movement_raw")
        self.assertEqual(registry["sensitivity_target_column"], "y_movement_model")
        self.assertTrue(registry["formal_target_definition_hash"])
        self.assertEqual(registry["formal_target_contract"], "PASS")

    def test_published_model_as_formal_is_blocked(self) -> None:
        metadata = {**target_contract_metadata(self.cfg), "formal_target_contract": "PASS"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ["run_summary.json", "acceptance.json", "artifact_registry.json"]:
                write_json(metadata, root / name)
            invalid = dict(metadata)
            invalid["formal_target_column"] = "y_movement_model"
            write_json(invalid, root / "artifact_registry.json")
            with self.assertRaisesRegex(ValueError, "artifact_registry.formal_target_column"):
                _validate_published_target_metadata(root, self.cfg)


if __name__ == "__main__":
    unittest.main()
