from __future__ import annotations

import sys
from pathlib import Path

import pytest


OVERALL = Path(__file__).resolve().parents[2]
if str(OVERALL) not in sys.path:
    sys.path.insert(0, str(OVERALL))

from src.config import load_config
from src.m3 import generate_test_fixture_library, load_m3_contract


@pytest.fixture(scope="session")
def cfg():
    return load_config(OVERALL, "fast")


@pytest.fixture(scope="session")
def m3_contract(cfg):
    return load_m3_contract(cfg.scientific)


@pytest.fixture(scope="session")
def fixture_artifact(cfg, m3_contract):
    return generate_test_fixture_library(
        m3_contract,
        n_draws=256,
        base_seed=20260806,
        m2_contract=cfg.scientific["m2"],
    )
