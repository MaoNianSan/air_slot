from __future__ import annotations

from overall_run.src.m1 import M1Pipeline


def test_random_engineering_pipeline_entry_is_removed() -> None:
    assert not hasattr(M1Pipeline, "engineering")
