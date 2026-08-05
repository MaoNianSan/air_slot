from __future__ import annotations

from pathlib import Path

import pandas as pd

from .input import AIRCRAFT_COLUMNS
from .input_eurostat import _decode_sdmx_json
from .input_sources import iter_csv_tar


def raw_samples(
    inventory: pd.DataFrame,
) -> dict[str, tuple[pd.DataFrame, str]]:
    samples: dict[str, tuple[pd.DataFrame, str]] = {}
    first = {
        name: Path(group.iloc[0].absolute_path)
        for name, group in inventory.groupby("source")
    }
    samples["raw:flightlist"] = (
        pd.read_csv(first["flightlist"], nrows=50_000, low_memory=False),
        "first_file_sample",
    )
    samples["raw:aircraft"] = (
        pd.read_csv(
            first["aircraft"],
            names=AIRCRAFT_COLUMNS,
            nrows=50_000,
            low_memory=False,
            encoding_errors="replace",
        ),
        "headerless_positional_contract; first_file_sample",
    )
    samples["raw:metar"] = (
        pd.read_csv(first["metar"], nrows=50_000, low_memory=False),
        "first_station_file_sample",
    )
    for path in inventory.loc[
        inventory["source"].eq("ourairports"), "absolute_path"
    ]:
        source = f"raw:ourairports_{Path(path).stem}"
        samples[source] = (
            pd.read_csv(path, nrows=50_000, low_memory=False),
            "snapshot_file_sample",
        )
    samples["raw:state_vectors"] = (
        next(iter_csv_tar(first["state_vectors"], chunksize=50_000)),
        "first_archive_first_chunk_sample",
    )
    for name in ["eurostat_passengers", "eurostat_flights"]:
        samples[f"raw:{name}"] = (
            _decode_sdmx_json(first[name]).head(50_000),
            "first_month_SDMX_decoded_sample",
        )
    return samples
