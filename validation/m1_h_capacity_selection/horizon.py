"""Development-side node metadata: operational stage and realized forecast lead.

The frozen M1 Development cache persists no per-node stage or decision time.
They are recovered here by aligning the cache samples with the frozen Exp2 H16
node-input table
(``artifacts/experiment/exp2/development/data/EXP2_H16_M2_V4_NODE_INPUT.parquet``),
which covers exactly the same 128 Development episodes under a different
node-id namespace.  Alignment is validated before use: equal per-episode node
counts, monotonically increasing decision times, and exact equality with the
frozen stage counts recorded in the cache manifest.  Any mismatch fails closed.

The realized-lead definitions reuse the frozen horizon semantics of
``docs/diagnostics/M1_HORIZON_ACCURACY_QUICK_20260818.md`` section 1:

- T_IB:  realized predecessor in-block remaining time (the realized label),
- D_OB:  (scheduled successor off-block - decision time) + realized D_OB,
- D_TX:  (scheduled successor off-block - decision time) + realized D_OB
         + realized D_TX.

Realized leads are assigned to the frozen evaluation-lead grid with the frozen
nearest-allowed-horizon rule; leads outside the capture window are kept out of
the per-lead tables (and reported as such) rather than re-binned.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

ALLOWED_LEADS: tuple[int, ...] = (0, 30, 60, 120, 180, 240, 300, 360, 420, 480)
LEAD_CAPTURE_MIN_MINUTES = -15.0
LEAD_CAPTURE_MAX_MINUTES = 495.0

STAGE_ORDER: tuple[str, ...] = (
    "PRE_IB",
    "POST_IB_PRE_OB",
    "POST_OB_PRE_TO",
    "COMPLETED",
)


def _scheduled_departure(example):
    lineage = example.static_context_lineage
    if isinstance(lineage, str):
        lineage = json.loads(lineage)
    raw = lineage["schedule_reference"]["scheduled_departure_utc"]
    if isinstance(raw, Mapping):
        raw = raw.get("value")
    stamp = pd.Timestamp(raw)
    if stamp.tz is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")


def _nearest_allowed_lead(lead: float) -> int | None:
    if lead < LEAD_CAPTURE_MIN_MINUTES or lead > LEAD_CAPTURE_MAX_MINUTES:
        return None
    return min(ALLOWED_LEADS, key=lambda grid: abs(lead - grid))


def _lead_entries(example, decision_time, realized: Mapping[str, Any]):
    reference = _scheduled_departure(example)
    offset = (reference - decision_time).total_seconds() / 60.0
    values: dict[str, float | None] = {
        "T_IB_REMAINING_HAZARD": realized.get("T_IB_REMAINING_HAZARD"),
        "D_OB": (
            None
            if realized.get("D_OB") is None
            else offset + float(realized["D_OB"])
        ),
        "D_TX": (
            None
            if realized.get("D_TX") is None or realized.get("D_OB") is None
            else offset + float(realized["D_OB"]) + float(realized["D_TX"])
        ),
    }
    entries = {}
    for target, lead in values.items():
        if lead is None:
            entries[target] = {"lead_minutes": None, "lead_bin": None}
            continue
        entries[target] = {
            "lead_minutes": float(lead),
            "lead_bin": _nearest_allowed_lead(float(lead)),
        }
    return entries


def load_development_metadata(
    *,
    node_input_path: Path,
    cache_manifest: Mapping[str, Any],
    examples: Sequence[Any],
) -> list[dict[str, Any]]:
    """Return per-example metadata aligned to ``examples`` (cache order)."""

    frame = pd.read_parquet(
        node_input_path,
        columns=["episode_id", "decision_time", "operational_stage"],
    )
    frame["episode_id"] = frame["episode_id"].astype(str)
    frame["decision_time"] = pd.to_datetime(frame["decision_time"], utc=True)

    by_episode: dict[str, list[tuple[Any, str]]] = {}
    for row in frame.sort_values(["episode_id", "decision_time"]).itertuples(
        index=False
    ):
        by_episode.setdefault(row.episode_id, []).append(
            (row.decision_time, str(row.operational_stage))
        )

    example_order: dict[str, list[int]] = {}
    for index, example in enumerate(examples):
        example_order.setdefault(example.episode_id, []).append(index)

    if set(example_order) != set(by_episode):
        raise ValueError("M1_CAPACITY_STAGE_ALIGNMENT_EPISODE_MISMATCH")

    metadata: list[dict[str, Any] | None] = [None] * len(examples)
    for episode_id, indices in example_order.items():
        nodes = by_episode[episode_id]
        if len(nodes) != len(indices):
            raise ValueError(
                f"M1_CAPACITY_STAGE_ALIGNMENT_NODE_COUNT_MISMATCH:{episode_id}"
            )
        for position, example_index in enumerate(indices):
            decision_time, stage = nodes[position]
            example = examples[example_index]
            metadata[example_index] = {
                "episode_id": episode_id,
                "decision_time": decision_time,
                "operational_stage": stage,
                "leads": _lead_entries(example, decision_time, example.targets),
            }

    if any(item is None for item in metadata):
        raise ValueError("M1_CAPACITY_STAGE_ALIGNMENT_INCOMPLETE")

    observed: dict[str, int] = {}
    for item in metadata:
        stage = item["operational_stage"]
        observed[stage] = observed.get(stage, 0) + 1
    expected = {
        str(name): int(value)
        for name, value in cache_manifest["audit"]["active_stage_counts"][
            "development"
        ].items()
    }
    if observed != expected:
        raise ValueError(
            "M1_CAPACITY_STAGE_ALIGNMENT_STAGE_COUNTS_MISMATCH:"
            f"{sorted(observed.items())}!={sorted(expected.items())}"
        )

    return [item for item in metadata if item is not None]
