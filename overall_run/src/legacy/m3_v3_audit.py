"""Legacy M3 V2/V3 audit implementation.

This module is not part of the active M3 V4 runtime path.
It must not be imported by the formal pipeline.
"""

from __future__ import annotations


LEGACY_AUDIT_ONLY = True

from dataclasses import dataclass
from numbers import Real
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import beta as beta_distribution

from ..action_contract import load_action_contract

from ..utils import stable_hash, stable_seed

CHANNELS = ("F", "P", "R")
_V2_CONTRACT = load_action_contract("V2")
_V3_CONTRACT = load_action_contract("V3")
V2_ACTION_IDS = frozenset(_V2_CONTRACT["action_ids"])
FORMAL_ACTION_IDS = frozenset(_V3_CONTRACT["action_ids"])
STRESS_TEST_ACTION_IDS = frozenset(_V3_CONTRACT["stress_test_action_ids"])
ALLOWED_ACTION_FAMILIES = {
    "null", "hold", "retime", "protect", "support", "combined",
    "cancel", "aircraft", "crew", "execution_coordination",
    "slot_coordination", "passenger", "gate", "ground", "integrated",
    "cancellation",
}
BURDEN_ONLY_TEST_FIXTURE_IDS = {"S01", "S02"}


def burden_only_test_parameters() -> pd.DataFrame:
    """Return non-formal M3 fixtures used only by unit tests and audits."""
    return pd.DataFrame([
        {
            "action_id": "S01", "mu_F": 0.0, "mu_P": 0.0, "mu_R": 0.0,
            "kbar_rmb_F": 0.10, "kbar_rmb_P": 0.15, "kbar_rmb_R": 0.20,
            "recovery_concentration": 18.0, "cost_cv": 0.12,
            "failure_probability": 0.02, "fixture_only": True,
        },
        {
            "action_id": "S02", "mu_F": 0.0, "mu_P": 0.0, "mu_R": 0.0,
            "kbar_rmb_F": 0.10, "kbar_rmb_P": 0.30, "kbar_rmb_R": 0.15,
            "recovery_concentration": 16.0, "cost_cv": 0.18,
            "failure_probability": 0.05, "fixture_only": True,
        },
    ])


@dataclass(frozen=True)
class Action:
    id: str
    name: str
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
    description: str = ""
    typed_gates: tuple[str, ...] = ()
    provisional: bool = False
    parameter_source: str = "scenario-declared"
    resource_requirement: str = "generic"
    authority_requirement: str = "operational"
    lead_time_requirement: float = 0.0
    compatibility_requirement: str = "none"


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
    contract_version: str = "overall-run-m3-response-v3"

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
    version = str(scientific["m3"].get("response_parameter_version", ""))
    contract = _V2_CONTRACT if "V2" in version else _V3_CONTRACT
    normalized: list[dict[str, Any]] = []
    for raw in scientific["m3"]["actions"]:
        item = dict(raw)
        action_id = str(item.get("id", ""))
        if not action_id:
            raise RuntimeError("M3_ACTION_ID_MISSING")
        if item.get("family") is None and action_id == "A00":
            item["family"] = "null"
        item.setdefault("capacity_required", float(item.get("cap", 0.0)) > 0.0)
        item.setdefault(
            "window_type",
            "flight_timing" if float(item.get("window", 0.0)) > 0.0 else "none",
        )
        item.setdefault("name", action_id)
        item.setdefault("description", str(item.get("name", action_id)))
        item.setdefault("typed_gates", ())
        item.setdefault("provisional", False)
        item.setdefault(
            "parameter_source",
            str(scientific["m3"].get("parameter_source", "scenario-declared")),
        )
        item.setdefault("resource_requirement", "none" if action_id == "A00" else "generic")
        item.setdefault("authority_requirement", "none" if action_id == "A00" else "operational")
        item.setdefault("lead_time_requirement", float(item.get("lead", 0.0)))
        item.setdefault("compatibility_requirement", "none")
        if not isinstance(item["capacity_required"], bool):
            raise RuntimeError(f"M3_BOOLEAN_FIELD_INVALID:{action_id}:capacity_required")
        if not isinstance(item["window_type"], str):
            raise RuntimeError(f"M3_WINDOW_TYPE_INVALID:{action_id}")
        numeric_fields = (
            "time", "window", "lead", "nu_f", "nu_p", "nu_r", "cap",
            "req_f", "req_p", "req_r", "burden",
        )
        invalid_numeric = [
            key for key in numeric_fields
            if not isinstance(item.get(key), Real) or isinstance(item.get(key), bool)
        ]
        if invalid_numeric:
            raise RuntimeError(
                f"M3_ACTION_NUMERIC_FIELD_INVALID:{action_id}:"
                + ",".join(invalid_numeric)
            )
        if not isinstance(item.get("priority"), int) or isinstance(item.get("priority"), bool):
            raise RuntimeError(f"M3_PRIORITY_INVALID:{action_id}")
        if str(item.get("family")) not in ALLOWED_ACTION_FAMILIES:
            raise RuntimeError(f"M3_FAMILY_INVALID:{action_id}")
        if not isinstance(item.get("provisional"), bool):
            raise RuntimeError(f"M3_BOOLEAN_FIELD_INVALID:{action_id}:provisional")
        if not isinstance(item.get("parameter_source"), str):
            raise RuntimeError(f"M3_PARAMETER_SOURCE_INVALID:{action_id}")
        if not isinstance(item["typed_gates"], (list, tuple)):
            raise RuntimeError(f"M3_TYPED_GATES_INVALID:{action_id}")
        if any(not isinstance(gate, str) or not gate for gate in item["typed_gates"]):
            raise RuntimeError(f"M3_TYPED_GATES_INVALID:{action_id}")
        item["typed_gates"] = tuple(item.get("typed_gates", ()))
        normalized.append(item)
    ids = [str(item["id"]) for item in normalized]
    if len(ids) != len(set(ids)):
        raise RuntimeError("M3_DUPLICATE_ACTION_ID")
    if ids != list(contract["action_ids"]):
        raise RuntimeError("ACTION_LIBRARY_MISMATCH")
    actions = {item["id"]: Action(**item) for item in normalized}
    if set(actions) & STRESS_TEST_ACTION_IDS:
        raise RuntimeError("STRESS_TEST_ACTION_IN_FORMAL_LIBRARY")
    return actions


def _parameter_rows(
    actions: dict[str, Action],
    scientific: dict[str, Any],
) -> pd.DataFrame:
    response = scientific["m3"].get("response_parameters", {})
    defaults = scientific["m3"].get("response_defaults", {})
    version = str(scientific["m3"].get("response_parameter_version", ""))
    strict_v3 = "V2" not in version
    rows: list[dict[str, Any]] = []
    for action_id in sorted(actions):
        configured = dict(response.get(action_id, {}))
        if strict_v3:
            required = {
                *(f"mu_{channel}" for channel in CHANNELS),
                *(f"K_{channel}" for channel in CHANNELS),
                "kappa_eta", "CV_K", "p_fail", "priority", "family",
                "provisional", "parameter_source",
            }
            missing = sorted(key for key in required if key not in configured or configured[key] is None)
            if missing:
                raise RuntimeError(f"M3_PARAMETER_MISSING:{action_id}:" + ",".join(missing))
        if all(f"mu_{channel}" in configured for channel in CHANNELS):
            mu = [configured[f"mu_{channel}"] for channel in CHANNELS]
        else:
            mu = configured.get("mu", [0.0, 0.0, 0.0])
        if all(f"K_{channel}" in configured for channel in CHANNELS):
            kbar = [configured[f"K_{channel}"] for channel in CHANNELS]
        else:
            kbar = configured.get("kbar_rmb", [0.0, 0.0, 0.0])
        if len(mu) != 3 or len(kbar) != 3:
            raise RuntimeError(f"M3_PARAMETER_VECTOR_LENGTH:{action_id}")
        if strict_v3 and not isinstance(configured.get("provisional"), bool):
            raise RuntimeError(f"M3_BOOLEAN_FIELD_INVALID:{action_id}:provisional")
        if strict_v3 and (
            not isinstance(configured.get("priority"), int)
            or isinstance(configured.get("priority"), bool)
        ):
            raise RuntimeError(f"M3_PRIORITY_INVALID:{action_id}")
        if strict_v3 and str(configured.get("family")) not in ALLOWED_ACTION_FAMILIES:
            raise RuntimeError(f"M3_FAMILY_INVALID:{action_id}")
        if strict_v3:
            numeric_fields = [
                *(f"mu_{channel}" for channel in CHANNELS),
                *(f"K_{channel}" for channel in CHANNELS),
                "kappa_eta", "CV_K", "p_fail", "lead_time_requirement",
            ]
            invalid_numeric = [
                key for key in numeric_fields
                if not isinstance(configured.get(key), Real)
                or isinstance(configured.get(key), bool)
            ]
            if invalid_numeric:
                raise RuntimeError(
                    f"M3_PARAMETER_TYPE_INVALID:{action_id}:"
                    + ",".join(invalid_numeric)
                )
            requirement_fields = (
                "capacity_requirement", "window_requirement",
                "resource_requirement", "authority_requirement",
                "aircraft_requirement", "crew_requirement",
                "passenger_requirement", "airport_requirement",
                "parameter_source", "description",
            )
            invalid_requirements = [
                key for key in requirement_fields
                if not isinstance(configured.get(key), str) or not configured.get(key)
            ]
            if invalid_requirements:
                raise RuntimeError(
                    f"M3_PARAMETER_TYPE_INVALID:{action_id}:"
                    + ",".join(invalid_requirements)
                )
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
                    configured.get(
                        "kappa_eta",
                        defaults.get("recovery_concentration", defaults.get("kappa_eta", 18.0)),
                    ),
                )
            ),
            "cost_cv": float(
                configured.get("cost_cv", configured.get("CV_K", defaults.get("cost_cv", defaults.get("CV_K", 0.10))))
            ),
            "failure_probability": float(
                configured.get(
                    "failure_probability",
                    configured.get(
                        "p_fail",
                        defaults.get("failure_probability", defaults.get("p_fail", 0.02)),
                    ),
                )
            ),
            "parameter_source": str(
                configured.get(
                    "parameter_source",
                    scientific["m3"].get("parameter_source", "scenario-declared"),
                )
            ),
            "parameter_version": str(
                configured.get(
                    "parameter_version",
                    scientific["m3"].get("response_parameter_version", "M3_RESPONSE_V2"),
                )
            ),
            "kappa_eta": float(
                configured.get(
                    "kappa_eta", defaults.get("recovery_concentration", 18.0)
                )
            ),
            "CV_K": float(
                configured.get("CV_K", defaults.get("cost_cv", 0.10))
            ),
            "p_fail": float(
                configured.get(
                    "p_fail", defaults.get("failure_probability", 0.02)
                )
            ),
            **{
                name: configured.get(name)
                for name in (
                    "capacity_requirement", "window_requirement",
                    "resource_requirement", "authority_requirement",
                    "lead_time_requirement", "aircraft_requirement",
                    "crew_requirement", "passenger_requirement",
                    "airport_requirement", "priority", "family",
                    "description", "provisional",
                )
            },
        }
        for index, channel in enumerate(CHANNELS):
            row[f"K_{channel}"] = float(kbar[index])
        if action_id == "A00":
            for channel in CHANNELS:
                row[f"mu_{channel}"] = 0.0
                row[f"kbar_rmb_{channel}"] = 0.0
            row["failure_probability"] = 0.0
        row["kappa_eta"] = row["recovery_concentration"]
        row["CV_K"] = row["cost_cv"]
        row["p_fail"] = row["failure_probability"]
        if any(not 0.0 <= row[f"mu_{channel}"] <= 1.0 for channel in CHANNELS):
            raise RuntimeError(f"M3_RECOVERY_MEAN_OUT_OF_RANGE:{action_id}")
        if any(row[f"kbar_rmb_{channel}"] < 0.0 for channel in CHANNELS):
            raise RuntimeError(f"M3_COST_MEAN_NEGATIVE:{action_id}")
        if row["recovery_concentration"] <= 0.0:
            raise RuntimeError(f"M3_CONCENTRATION_INVALID:{action_id}")
        if row["cost_cv"] < 0.0:
            raise RuntimeError(f"M3_COST_CV_INVALID:{action_id}")
        if not 0.0 <= row["failure_probability"] <= 1.0:
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
        contract_version=(
            "overall-run-m3-response-v2"
            if set(actions) == V2_ACTION_IDS
            else "overall-run-m3-response-v3-provisional"
        ),
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
