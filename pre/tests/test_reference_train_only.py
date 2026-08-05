from __future__ import annotations

import pandas as pd

from src.core.chain_builder import build_chains
from src.core.reference_builder import build_references
from core_fixtures import core_cfg, flight, matched_flights


def _empty_eurostat(value: str) -> pd.DataFrame:
    return pd.DataFrame(columns=["airport", "source_period", value, "source_record_id", "raw_source_file", "raw_source_hash"])


def test_reference_fit_ignores_non_train_chain(tmp_path) -> None:
    cfg = core_cfg()
    train_flights = matched_flights()
    test_flights = pd.DataFrame(
        [
            flight("def456", "EDDF", "EHAM", "2022-05-30 08:00", "2022-05-30 10:00", seed=True, record="testpred"),
            flight("def456", "EHAM", "LEMD", "2022-05-30 20:00", "2022-05-30 22:00", seed=False, record="testsucc"),
        ]
    )
    flights = pd.concat([train_flights, test_flights], ignore_index=True)
    episodes = build_chains(flights, cfg)
    references = build_references(
        episodes,
        flights,
        tmp_path,
        _empty_eurostat("passengers"),
        _empty_eurostat("commercial_flights"),
        cfg,
    )
    turnaround = references[references["reference_type"].eq("minimum_turnaround")]
    assert turnaround["fit_split"].eq("train").all()
    assert turnaround["reference_value"].eq(60.0).all()
