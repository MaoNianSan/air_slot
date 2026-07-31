from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .reference_utils import MOVEMENT_LEVELS, WEATHER_FIELDS


@dataclass
class MovementTimeReference:
    tables: dict[str, pd.DataFrame]

    def resolve(self, row: pd.Series) -> tuple[float, str, int, str]:
        keys = {
            "L1": ["origin", "destination", "firstseen_month", "firstseen_time_bin", "aircraft_group"],
            "L2": ["origin", "destination", "firstseen_month", "firstseen_time_bin"],
            "L3": ["origin", "destination", "firstseen_month"],
            "L4": ["origin", "destination"],
            "L5": ["distance_bin", "region_pair"],
            "L6": ["distance_bin"],
        }
        for level in MOVEMENT_LEVELS:
            table = self.tables.get(level, pd.DataFrame())
            if table.empty:
                continue
            mask = pd.Series(True, index=table.index)
            for key in keys[level]:
                mask &= table[key].astype(str).eq(str(row[key]))
            found = table.loc[mask]
            if not found.empty:
                record = found.iloc[0]
                return (
                    float(record["reference_movement_time"]), level, int(record["cell_size"]),
                    "" if level == "L1" else f"FALLBACK_{level}",
                )
        raise KeyError(f"no T_ref support for {row.get('origin')}->{row.get('destination')}")

    def artifact_frame(self) -> pd.DataFrame:
        frames = []
        for level, table in self.tables.items():
            temp = table.copy()
            temp["reference_level"] = level
            frames.append(temp)
        return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


@dataclass
class WeatherClimatology:
    tables: dict[str, pd.DataFrame]

    def resolve(self, airport: str, region: str, month: int, time_bin: str) -> tuple[dict[str, float], str, int] | None:
        specs = [
            ("L0", {"airport": airport, "month": month, "time_bin": time_bin}),
            ("L1", {"airport": airport, "month": month}),
            ("L2", {"airport": airport}),
            ("L3", {"airport_region": region, "month": month}),
            ("L4", {"month": month}),
            ("L5", {}),
        ]
        for level, query in specs:
            table = self.tables.get(level, pd.DataFrame())
            if table.empty:
                continue
            mask = pd.Series(True, index=table.index)
            for key, value in query.items():
                mask &= table[key].astype(str).eq(str(value))
            found = table.loc[mask]
            if not found.empty:
                row = found.iloc[0]
                values = {field: float(row[field]) if pd.notna(row[field]) else np.nan for field in WEATHER_FIELDS}
                return values, level, int(row["cell_size"])
        return None

    def artifact_frame(self) -> pd.DataFrame:
        frames = []
        for level, table in self.tables.items():
            temp = table.copy()
            temp["fallback_level"] = level
            frames.append(temp)
        return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


@dataclass
class FlowReference:
    table: pd.DataFrame

    def resolve(self, airport: str, time_bin: str, field: str) -> tuple[float, str, int]:
        levels = [
            ("airport_time_bin", (self.table["airport"] == airport) & (self.table["time_bin"] == time_bin)),
            ("airport", self.table["airport"] == airport),
            ("core_time_bin_pooled", self.table["time_bin"] == time_bin),
            ("all_core_airport_pooled", pd.Series(True, index=self.table.index)),
        ]
        for level, mask in levels:
            values = pd.to_numeric(self.table.loc[mask, field], errors="coerce").dropna()
            cells = pd.to_numeric(self.table.loc[mask, "flow_cell_size"], errors="coerce").dropna()
            if not values.empty:
                return float(values.median()), level, int(cells.sum()) if not cells.empty else len(values)
        raise KeyError(f"no flow reference: {airport}/{time_bin}/{field}")


@dataclass
class TurnaroundReference:
    tables: dict[str, pd.DataFrame]

    def resolve(self, airport: str, aircraft_group: str, time_bin: str) -> tuple[float, float, float, float, str, int]:
        specs = [
            ("airport_aircraft_time", {"airport": airport, "aircraft_group": aircraft_group, "firstseen_time_bin": time_bin}),
            ("airport_aircraft", {"airport": airport, "aircraft_group": aircraft_group}),
            ("airport", {"airport": airport}),
            ("global_aircraft", {"aircraft_group": aircraft_group}),
            ("global", {}),
        ]
        for level, query in specs:
            table = self.tables.get(level, pd.DataFrame())
            if table.empty:
                continue
            mask = pd.Series(True, index=table.index)
            for key, value in query.items():
                mask &= table[key].astype(str).eq(str(value))
            found = table.loc[mask]
            if not found.empty:
                row = found.iloc[0]
                typical = float(row["turnaround_typical"])
                minimum = float(row["turnaround_minimum"])
                continuity = float(row["continuity_probability"])
                return typical, minimum, typical - minimum, continuity, level, int(row["cell_size"])
        raise KeyError(f"no turnaround reference: {airport}/{aircraft_group}/{time_bin}")

    def artifact_frame(self) -> pd.DataFrame:
        frames = []
        for level, table in self.tables.items():
            temp = table.copy()
            temp["fallback_level"] = level
            frames.append(temp)
        return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


@dataclass
class AirportReference:
    table: pd.DataFrame

    def resolve(self, airport: str) -> pd.Series:
        found = self.table[self.table["airport"] == airport]
        if found.empty:
            raise KeyError(f"airport reference missing: {airport}")
        return found.iloc[0]


