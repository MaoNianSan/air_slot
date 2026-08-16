from __future__ import annotations

from datetime import date, datetime

from model.common.errors import ContractError


V5_SPLIT_BOUNDARIES = {
    "train": (date(2019, 1, 1), date(2019, 6, 30)),
    "calibration": (date(2019, 7, 1), date(2019, 7, 31)),
    "development": (date(2019, 8, 1), date(2019, 9, 30)),
    "final_test": (date(2019, 10, 1), date(2019, 12, 31)),
}


def assign_v5_split(value: date | datetime | str) -> str:
    """Assign the V5 split from the successor service date only."""
    if isinstance(value, datetime):
        value = value.date()
    elif isinstance(value, str):
        value = date.fromisoformat(value[:10])
    for name, (start, end) in V5_SPLIT_BOUNDARIES.items():
        if start <= value <= end:
            return name
    raise ContractError("DATE_OUTSIDE_V5_DATA2_SPLIT")


def validate_episode_split(rows, *, date_key: str = "episode_date") -> dict[str, tuple[dict, ...]]:
    """Validate that every episode is wholly contained in one V5 split."""
    grouped: dict[str, list[dict]] = {name: [] for name in V5_SPLIT_BOUNDARIES}
    membership: dict[str, str] = {}
    for row in rows:
        if "episode_id" not in row or date_key not in row:
            raise ContractError("EPISODE_SPLIT_KEYS_MISSING")
        split = assign_v5_split(row[date_key])
        previous = membership.setdefault(row["episode_id"], split)
        if previous != split:
            raise ContractError("EPISODE_CROSSES_V5_SPLIT")
        grouped[split].append(row)
    return {name: tuple(items) for name, items in grouped.items()}


def chronological_episode_split(rows, train_end, calibration_end):
    """Backward-compatible three-way helper; V5 callers should use ``validate_episode_split``."""
    output = {"train": [], "calibration": [], "test": []}
    episode_membership = {}
    for row in sorted(rows, key=lambda x: (x["episode_date"], x["episode_id"])):
        split = "train" if row["episode_date"] <= train_end else "calibration" if row["episode_date"] <= calibration_end else "test"
        previous = episode_membership.setdefault(row["episode_id"], split)
        if previous != split:
            raise ValueError("episode crosses split")
        output[split].append(row)
    return output


def parameter_grid(parameters):
    keys = tuple(parameters)
    rows = [{}]
    for key in keys:
        rows = [{**row, key: value} for row in rows for value in parameters[key]]
    return tuple(rows)
