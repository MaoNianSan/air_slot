from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import beta as beta_distribution

from .utils import stable_hash, stable_seed

CHANNELS = ("F", "P", "R")
FORMAL_ACTION_IDS = {
    "A00", "A11", "A12", "A21", "A22", "A31",
    "A32", "A41", "A42", "A51", "A52", "A61", "A62",
}


@dataclass(frozen=True)
class Action:
    id: str
    family: str
    time: float
    window: float
    lead: float
    nu_f: float
    nu_p: float
    nu_r: float
    cap: float
    req_f: float
    req_p: float
    req_r: float
    burden: float
    priority: int
    capacity_required: bool = False
    window_type: str = "none"


@dataclass
class M3Artifact:
    sample_ids: np.ndarray
    recovery_rates: dict[str, np.ndarray]
    implementation_costs_rmb: dict[str, np.ndarray]
    success: dict[str, np.ndarray]
    parameter_table: pd.DataFrame
    response_audit: pd.DataFrame
    action_library_hash: str
    parameter_hash: str
    sample_hash: str
    contract_version: str = "overall-run-m3-response-v2"

    @property
    def n_samples(self) -> int:
        return int(len(self.sample_ids))

    def response_samples_frame(self) -> pd.DataFrame:
        rows: list[pd.DataFrame] = []
        for action_id in sorted(self.recovery_rates):
            recovery = np.asarray(self.recovery_rates[action_id], dtype=float)
            costs = np.asarray(self.implementation_costs_rmb[action_id], dtype=float)
            success = np.asarray(self.success[action_id], dtype=bool)
            frame = pd.DataFrame({
                "action_id": action_id,
                "sample_id": self.sample_ids,
                "implementation_success": success,
            })
            for index, channel in enumerate(CHANNELS):
                frame[f"recovery_rate_{channel}"] = recovery[:, index]
                frame[f"implementation_cost_rmb_{channel}"] = costs[:, index]
            rows.append(frame)
        return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def load_actions(scientific: dict[str, Any]) -> dict[str, Action]:
    normalized: list[dict[str, Any]] = []
    for raw in scientific["m3"]["actions"]:
        item = dict(raw)
        item.setdefault("capacity_required", float(item.get("cap", 0.0)) > 0.0)
        item.setdefault(
            "window_type",
            "flight_timing" if float(item.get("window", 0.0)) > 0.0 else "none",
        )
        normalized.append(item)
    actions = {item["id"]: Action(**item) for item in normalized}
    if set(actions) != FORMAL_ACTION_IDS:
        raise RuntimeError("ACTION_LIBRARY_MISMATCH")
    return actions


def _parameter_rows(
    actions: dict[str, Action],
    scientific: dict[str, Any],
) -> pd.DataFrame:
    response = scientific["m3"].get("response_parameters", {})
    defaults = scientific["m3"].get("response_defaults", {})
    rows: list[dict[str, Any]] = []
    for action_id in sorted(actions):
        configured = dict(response.get(action_id, {}))
        mu = configured.get("mu", [0.0, 0.0, 0.0])
        kbar = configured.get("kbar_rmb", [0.0, 0.0, 0.0])
        if len(mu) != 3 or len(kbar) != 3:
            raise RuntimeError(f"M3_PARAMETER_VECTOR_LENGTH:{action_id}")
        row = {
            "action_id": action_id,
            **{f"mu_{channel}": float(mu[index]) for index, channel in enumerate(CHANNELS)},
            **{
                f"kbar_rmb_{channel}": float(kbar[index])
                for index, channel in enumerate(CHANNELS)
            },
            "recovery_concentration": float(
                configured.get(
                    "recovery_concentration",
                    defaults.get("recovery_concentration", 18.0),
                )
            ),
            "cost_cv": float(configured.get("cost_cv", defaults.get("cost_cv", 0.10))),
            "failure_probability": float(
                configured.get(
                    "failure_probability",
                    defaults.get("failure_probability", 0.02),
                )
            ),
            "parameter_source": str(
                configured.get("parameter_source", "scenario-declared")
            ),
            "parameter_version": str(
                configured.get(
                    "parameter_version",
                    scientific["m3"].get("response_parameter_version", "M3_RESPONSE_V2"),
                )
            ),
        }
        if action_id == "A00":
            for channel in CHANNELS:
                row[f"mu_{channel}"] = 0.0
                row[f"kbar_rmb_{channel}"] = 0.0
            row["failure_probability"] = 0.0
        if any(not 0.0 <= row[f"mu_{channel}"] <= 1.0 for channel in CHANNELS):
            raise RuntimeError(f"M3_RECOVERY_MEAN_OUT_OF_RANGE:{action_id}")
        if any(row[f"kbar_rmb_{channel}"] < 0.0 for channel in CHANNELS):
            raise RuntimeError(f"M3_COST_MEAN_NEGATIVE:{action_id}")
        if row["recovery_concentration"] <= 0.0:
            raise RuntimeError(f"M3_CONCENTRATION_INVALID:{action_id}")
        if row["cost_cv"] < 0.0:
            raise RuntimeError(f"M3_COST_CV_INVALID:{action_id}")
        if not 0.0 <= row["failure_probability"] < 1.0:
            raise RuntimeError(f"M3_FAILURE_PROBABILITY_INVALID:{action_id}")
        rows.append(row)
    return pd.DataFrame(rows)


def generate_m3_library(
    actions: dict[str, Action],
    n_samples: int,
    base_seed: int,
    scientific: dict[str, Any],
) -> M3Artifact:
    if n_samples <= 0:
        raise ValueError("M3_SAMPLE_COUNT_MUST_BE_POSITIVE")
    parameters = _parameter_rows(actions, scientific)
    sample_ids = np.arange(n_samples, dtype=np.int32)
    recovery_rates: dict[str, np.ndarray] = {}
    implementation_costs: dict[str, np.ndarray] = {}
    success_draws: dict[str, np.ndarray] = {}
    audit_rows: list[dict[str, Any]] = []

    for row in parameters.itertuples(index=False):
        action_id = str(row.action_id)
        recovery = np.zeros((n_samples, 3), dtype=np.float32)
        costs = np.zeros((n_samples, 3), dtype=np.float32)
        if action_id == "A00":
            success = np.ones(n_samples, dtype=bool)
        else:
            success_rng = np.random.default_rng(
                stable_seed(base_seed, "M3_RESPONSE", action_id, "success")
            )
            rank_rng = np.random.default_rng(
                stable_seed(base_seed, "M3_RESPONSE", action_id, "recovery_rank")
            )
            cost_rng = np.random.default_rng(
                stable_seed(base_seed, "M3_RESPONSE", action_id, "cost_shock")
            )
            success = success_rng.random(n_samples) >= float(row.failure_probability)
            rank = np.clip(rank_rng.random(n_samples), 1e-12, 1.0 - 1e-12)
            concentration = float(row.recovery_concentration)
            for index, channel in enumerate(CHANNELS):
                mean = float(getattr(row, f"mu_{channel}"))
                if mean <= 0.0:
                    recovery[:, index] = 0.0
                elif mean >= 1.0:
                    recovery[:, index] = success.astype(np.float32)
                else:
                    alpha = mean * concentration
                    beta = (1.0 - mean) * concentration
                    draws = beta_distribution.ppf(rank, alpha, beta)
                    recovery[:, index] = np.where(success, draws, 0.0).astype(np.float32)
            cv = float(row.cost_cv)
            sigma2 = float(np.log1p(cv * cv))
            sigma = float(np.sqrt(sigma2))
            shock = cost_rng.lognormal(mean=-0.5 * sigma2, sigma=sigma, size=n_samples)
            for index, channel in enumerate(CHANNELS):
                mean_cost = float(getattr(row, f"kbar_rmb_{channel}"))
                costs[:, index] = (mean_cost * shock).astype(np.float32)

        recovery_rates[action_id] = recovery
        implementation_costs[action_id] = costs
        success_draws[action_id] = success
        audit_rows.append({
            "action_id": action_id,
            "sample_count": n_samples,
            "empirical_failure_rate": float((~success).mean()) if action_id != "A00" else 0.0,
            "configured_failure_probability": float(row.failure_probability),
            "recovery_min": float(recovery.min()),
            "recovery_max": float(recovery.max()),
            "implementation_cost_min_rmb": float(costs.min()),
            "implementation_cost_max_rmb": float(costs.max()),
            "structural_zero_exact": bool(
                all(
                    np.all(recovery[:, index] == 0.0)
                    for index, channel in enumerate(CHANNELS)
                    if float(getattr(row, f"mu_{channel}")) == 0.0
                )
            ),
            "nonnull_response_non_degenerate": bool(
                action_id == "A00"
                or np.nanstd(recovery) > 0.0
                or np.nanstd(costs) > 0.0
            ),
        })

    action_library_hash = stable_hash(
        [actions[action_id].__dict__ for action_id in sorted(actions)]
    )
    parameter_hash = stable_hash(parameters.to_dict("records"))
    sample_hash = stable_hash({
        action_id: {
            "recovery": np.asarray(recovery_rates[action_id]).round(10).tolist(),
            "cost": np.asarray(implementation_costs[action_id]).round(10).tolist(),
            "success": np.asarray(success_draws[action_id], dtype=int).tolist(),
        }
        for action_id in sorted(actions)
    })
    artifact = M3Artifact(
        sample_ids=sample_ids,
        recovery_rates=recovery_rates,
        implementation_costs_rmb=implementation_costs,
        success=success_draws,
        parameter_table=parameters,
        response_audit=pd.DataFrame(audit_rows),
        action_library_hash=action_library_hash,
        parameter_hash=parameter_hash,
        sample_hash=sample_hash,
    )
    _validate_m3_artifact(artifact, actions)
    return artifact


def _validate_m3_artifact(
    artifact: M3Artifact,
    actions: dict[str, Action],
) -> None:
    if set(artifact.recovery_rates) != set(actions):
        raise RuntimeError("M3_ACTION_COVERAGE_FAILURE")
    for action_id in actions:
        recovery = np.asarray(artifact.recovery_rates[action_id], dtype=float)
        costs = np.asarray(artifact.implementation_costs_rmb[action_id], dtype=float)
        if recovery.shape != (artifact.n_samples, 3) or costs.shape != (artifact.n_samples, 3):
            raise RuntimeError(f"M3_SAMPLE_SHAPE_FAILURE:{action_id}")
        if not np.isfinite(recovery).all() or not np.isfinite(costs).all():
            raise RuntimeError(f"M3_NONFINITE_RESPONSE:{action_id}")
        if np.any((recovery < 0.0) | (recovery > 1.0)):
            raise RuntimeError(f"M3_RECOVERY_BOUND_FAILURE:{action_id}")
        if np.any(costs < 0.0):
            raise RuntimeError(f"M3_COST_BOUND_FAILURE:{action_id}")
    if not np.all(artifact.recovery_rates["A00"] == 0.0):
        raise RuntimeError("M3_A00_RECOVERY_IDENTITY_FAILURE")
    if not np.all(artifact.implementation_costs_rmb["A00"] == 0.0):
        raise RuntimeError("M3_A00_COST_IDENTITY_FAILURE")
