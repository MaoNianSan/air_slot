from __future__ import annotations

from copy import deepcopy
from itertools import permutations
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import ConfigError, load_config
from src.m2 import fit_m2
from src.m3 import generate_m3_library, load_actions
from src.m4 import evaluate_m4, fit_m4, screen_physical_actions


def _frame(n: int = 240) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    return pd.DataFrame(
        {
            "episode_id": [f"e{i}" for i in range(n)],
            "flight_id": [f"f{i}" for i in range(n)],
            "snapshot_id": [f"s{i}" for i in range(n)],
            "airport": ["EHAM"] * n,
            "snapshot_stage": ["t1"] * n,
            "turnaround_margin": rng.uniform(0, 30, n),
            "continuity_exposure": rng.uniform(0, 1, n),
            "execution_window_margin": rng.uniform(5, 40, n),
            "estimated_passenger_load": rng.uniform(80, 220, n),
            "connection_pressure_proxy": rng.uniform(0, 1, n),
            "rebooking_scarcity_proxy": rng.uniform(0, 1, n),
            "airport_flow_pressure": rng.uniform(10, 100, n),
            "infrastructure_flexibility": rng.uniform(0, 1, n),
            "resource_available_r": rng.uniform(0.3, 1.0, n),
        }
    )


def _samples(n: int, s: int = 128) -> np.ndarray:
    rng = np.random.default_rng(11)
    return rng.normal(40, 20, (n, s)).clip(-20, 120)


def _rules(frame: pd.DataFrame, action_ids: list[str]) -> pd.DataFrame:
    rows = []
    for record in frame.itertuples(index=False):
        for action_id in action_ids:
            rows.append(
                {
                    "episode_id": record.episode_id,
                    "snapshot_id": record.snapshot_id,
                    "action_id": action_id,
                    "airport_flow_pressure": 20.0,
                    "capacity_threshold": 100.0,
                    "capacity_reference_p05": 10.0,
                    "capacity_reference_p95": 80.0,
                    "action_window_margin": 60.0,
                    "action_window_open": True,
                    "resource_profile_id": "normal",
                    "authority_profile_id": "public_rule_v1",
                    "authority_allowed": True,
                    "lead_time_margin": 100.0,
                }
            )
    return pd.DataFrame(rows)


def _artifacts(sample_count: int = 128):
    cfg = load_config(ROOT, mode="fast")
    train = _frame()
    train_samples = _samples(len(train), sample_count)
    m2 = fit_m2(train, cfg.scientific)
    m2.fit_unit_scales(train, train_samples)
    actions = load_actions(cfg.scientific)
    m3 = generate_m3_library(
        actions,
        sample_count,
        int(cfg.compute["random_seed"]),
        cfg.scientific,
    )
    m4 = fit_m4(cfg.scientific)
    return cfg, train, train_samples, m2, actions, m3, m4


def test_graph_edges_exclude_r_to_f_and_order_is_invariant() -> None:
    cfg, train, samples, m2, *_ = _artifacts()
    assert "R_to_F" not in m2.graph_edges
    baseline = m2.exposures(train)
    edge_value_pairs = list(m2.graph_edges.items())

    for ordering in permutations(edge_value_pairs):
        scientific = deepcopy(cfg.scientific)
        scientific["m2"]["graph_edges"] = dict(ordering)
        alternative = fit_m2(train, scientific).exposures(train)
        for channel in ("F", "P", "R"):
            assert np.allclose(
                baseline["base"][channel], alternative["base"][channel], equal_nan=True
            )
            assert np.allclose(
                baseline["final"][channel], alternative["final"][channel], equal_nan=True
            )
        for edge in m2.graph_edges:
            assert np.allclose(
                baseline["edge_contributions"][edge],
                alternative["edge_contributions"][edge],
                equal_nan=True,
            )


def test_graph_edge_coefficient_change_is_not_order_change() -> None:
    cfg, train, _, m2, *_ = _artifacts()
    baseline = m2.exposures(train)
    changed_cfg = deepcopy(cfg.scientific)
    changed_cfg["m2"]["graph_edges"]["F_to_P"] += 0.01
    changed = fit_m2(train, changed_cfg).exposures(train)
    for channel in ("F", "P", "R"):
        assert np.allclose(baseline["base"][channel], changed["base"][channel])
    assert not np.allclose(
        baseline["edge_contributions"]["F_to_P"],
        changed["edge_contributions"]["F_to_P"],
    )
    assert not np.allclose(baseline["final"]["P"], changed["final"]["P"])


def test_synchronous_base_semantics_differs_from_sequential_accumulation() -> None:
    _, train, _, m2, *_ = _artifacts()
    exposure = m2.exposures(train)
    sequential = {channel: values.copy() for channel, values in exposure["base"].items()}
    for edge in ("F_to_P", "P_to_R", "F_to_R"):
        source, target = edge.split("_to_")
        sequential[target] += m2.graph_edges[edge] * sequential[source]
    sequential = {channel: np.clip(values, 0.0, 1.0) for channel, values in sequential.items()}
    assert not np.allclose(exposure["final"]["R"], sequential["R"])


def test_m2_quantity_unit_and_rmb_identity() -> None:
    _, train, samples, m2, *_ = _artifacts()
    result = m2.reconstruct(train, samples)
    for channel in ("F", "P", "R"):
        unit = result["quantities_unit"][channel]
        cost = result["costs_rmb"][channel]
        assert np.allclose(
            cost,
            unit * result["unit_costs_rmb"][channel],
            equal_nan=True,
        )
    expected = sum(result["costs_rmb"][channel] for channel in ("F", "P", "R"))
    assert np.allclose(result["total_cost_rmb"], expected, equal_nan=True)


def test_m3_is_reproducible_and_episode_independent() -> None:
    cfg = load_config(ROOT, mode="fast")
    actions = load_actions(cfg.scientific)
    first = generate_m3_library(actions, 128, 20260718, cfg.scientific)
    second = generate_m3_library(actions, 128, 20260718, cfg.scientific)
    assert first.sample_hash == second.sample_hash
    assert first.parameter_hash == second.parameter_hash
    for action_id in actions:
        assert np.array_equal(first.recovery_rates[action_id], second.recovery_rates[action_id])
        assert np.array_equal(
            first.implementation_costs_rmb[action_id],
            second.implementation_costs_rmb[action_id],
        )
    assert np.all(first.recovery_rates["A00"] == 0)
    assert np.all(first.implementation_costs_rmb["A00"] == 0)


def test_m4_a00_score_decomposition_and_unsupported_rows_are_retained() -> None:
    cfg, train, _, m2, actions, m3, m4 = _artifacts()
    evaluation = train.iloc[:2].copy().reset_index(drop=True)
    evaluation.loc[0, "estimated_passenger_load"] = np.nan
    samples = _samples(len(evaluation), m3.n_samples)
    result = m2.reconstruct(evaluation, samples)
    physical = screen_physical_actions(
        _rules(evaluation, list(actions)),
        evaluation,
        actions,
        np.ones(len(evaluation), dtype=bool),
        cfg.scientific["m3"]["resource_profiles"],
    )
    scores, rankings, candidates = evaluate_m4(
        evaluation,
        result["costs_rmb"],
        physical.audit,
        actions,
        m3,
        m4,
    )
    unsupported = candidates[candidates["snapshot_id"].eq("s0")]
    assert len(unsupported) == len(actions)
    assert unsupported["evaluation_status"].eq("M2_COST_UNAVAILABLE").all()
    assert not rankings["snapshot_id"].eq("s0").any()

    supported_scores = scores[scores["snapshot_id"].eq("s1")]
    contribution_sum = supported_scores[
        ["channel_contribution_F", "channel_contribution_P", "channel_contribution_R"]
    ].sum(axis=1)
    assert np.allclose(contribution_sum, supported_scores["score"])
    a00 = supported_scores[supported_scores["action_id"].eq("A00")].iloc[0]
    pre_total = sum(result["costs_rmb"][channel][1] for channel in ("F", "P", "R"))
    expected = float(pre_total.mean())
    threshold = float(np.quantile(pre_total, m4.cvar_alpha))
    cvar = float(pre_total[pre_total >= threshold].mean())
    formal_score = (1 - m4.risk_aversion) * expected + m4.risk_aversion * cvar
    assert np.isclose(a00["score"], formal_score)
    assert physical.audit[physical.audit["action_id"].eq("A00")]["physical_feasible"].all()


def test_missing_capacity_span_rejects_non_null_capacity_action() -> None:
    cfg = load_config(ROOT, mode="fast")
    actions = load_actions(cfg.scientific)
    frame = _frame(1)
    rules = _rules(frame, list(actions))
    rules.loc[rules["action_id"].eq("A11"), "capacity_reference_p95"] = np.nan
    result = screen_physical_actions(
        rules,
        frame,
        actions,
        np.ones(1, dtype=bool),
        cfg.scientific["m3"]["resource_profiles"],
    )
    row = result.audit[result.audit["action_id"].eq("A11")].iloc[0]
    assert not row["physical_feasible"]
    assert "CAPACITY_INPUT_OR_SPAN_MISSING" in row["failure_codes"]
