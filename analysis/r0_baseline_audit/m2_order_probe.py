from __future__ import annotations

import itertools
import json
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OVERALL_RUN_ROOT = PROJECT_ROOT / "overall_run"
if str(OVERALL_RUN_ROOT) not in sys.path:
    sys.path.insert(0, str(OVERALL_RUN_ROOT))

from src.config import load_config  # noqa: E402
from src.m2 import fit_m2  # noqa: E402


def frame(rows: int = 240) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    return pd.DataFrame(
        {
            "episode_id": [f"e{i}" for i in range(rows)],
            "flight_id": [f"f{i}" for i in range(rows)],
            "snapshot_id": [f"s{i}" for i in range(rows)],
            "airport": ["EHAM"] * rows,
            "snapshot_stage": ["t1"] * rows,
            "turnaround_margin": rng.uniform(0, 30, rows),
            "continuity_exposure": rng.uniform(0, 1, rows),
            "execution_window_margin": rng.uniform(5, 40, rows),
            "estimated_passenger_load": rng.uniform(80, 220, rows),
            "connection_pressure_proxy": rng.uniform(0, 1, rows),
            "rebooking_scarcity_proxy": rng.uniform(0, 1, rows),
            "airport_flow_pressure": rng.uniform(10, 100, rows),
            "infrastructure_flexibility": rng.uniform(0, 1, rows),
            "resource_available_r": rng.uniform(0.3, 1.0, rows),
        }
    )


def max_delta(left: dict[str, np.ndarray], right: dict[str, np.ndarray]) -> dict[str, float]:
    return {
        channel: float(np.nanmax(np.abs(left[channel] - right[channel])))
        for channel in ("F", "P", "R")
    }


def propagate(
    base: dict[str, np.ndarray],
    ordered_edges: list[tuple[str, float]],
    semantics: str,
) -> dict[str, np.ndarray]:
    final = {channel: values.copy() for channel, values in base.items()}
    for edge, coefficient in ordered_edges:
        source, target = edge.split("_to_")
        source_values = base[source] if semantics == "synchronous_base" else final[source]
        final[target] = final[target] + coefficient * source_values
    return {channel: np.clip(values, 0.0, 1.0) for channel, values in final.items()}


def main() -> int:
    cfg = load_config(OVERALL_RUN_ROOT, mode="fast")
    source = frame()
    fitted = fit_m2(source, cfg.scientific)
    reference = fitted.exposures(source)
    current_edges = list(fitted.graph_edges.items())

    permutations = []
    for order in itertools.permutations(current_edges):
        scientific = deepcopy(cfg.scientific)
        scientific["m2"]["graph_edges"] = dict(order)
        candidate = fit_m2(source, scientific).exposures(source)
        permutations.append(
            {
                "order": [edge for edge, _ in order],
                "current_code_final_max_abs_delta": max_delta(reference["final"], candidate["final"]),
                "synchronous_formula_max_abs_delta": max_delta(
                    reference["final"],
                    propagate(reference["base"], list(order), "synchronous_base"),
                ),
                "sequential_formula_max_abs_delta": max_delta(
                    reference["final"],
                    propagate(reference["base"], list(order), "sequential_current"),
                ),
            }
        )

    historical_edges = {"P_to_R": 0.05, "F_to_R": 0.08, "F_to_P": 0.10}
    historical_cfg = deepcopy(cfg.scientific)
    historical_cfg["m2"]["graph_edges"] = historical_edges
    historical = fit_m2(source, historical_cfg).exposures(source)
    historical_deltas = {
        "base": max_delta(reference["base"], historical["base"]),
        "edge_contributions": {
            edge: float(
                np.nanmax(
                    np.abs(
                        reference["edge_contributions"][edge]
                        - historical["edge_contributions"][edge]
                    )
                )
            )
            for edge in sorted(reference["edge_contributions"])
        },
        "final": max_delta(reference["final"], historical["final"]),
    }

    payload = {
        "current_edges": dict(current_edges),
        "historical_test_edges": historical_edges,
        "propagation_semantics_in_current_code": "synchronous_base",
        "permutations": permutations,
        "historical_coefficient_change_deltas": historical_deltas,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
