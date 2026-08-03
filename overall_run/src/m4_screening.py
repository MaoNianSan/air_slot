from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .m3 import Action, M3Artifact

CHANNELS = ("F", "P", "R")


@dataclass
class PhysicalScreenResult:
    audit: pd.DataFrame
    feasible_by_snapshot: dict[tuple[str, str], list[str]]


@dataclass
class M4Artifact:
    cvar_alpha: float
    risk_aversion: float
    near_abs_rmb: float
    near_rel: float
    burden_ratio_max: float
    positive_net_benefit_probability_min: float
    zero_cost_epsilon: float
    contract_version: str = "overall-run-m4-rmb-v2"
    available: bool = True


@dataclass
class M4UnavailableArtifact:
    available: bool
    reason: str
    contract_version: str
    channel_scale_support: dict[str, int]


def fit_m4(scientific: dict[str, Any]) -> M4Artifact:
    cfg = scientific["m4"]
    decision = cfg.get("decision_value", {})
    artifact = M4Artifact(
        cvar_alpha=float(cfg["cvar_alpha"]),
        risk_aversion=float(cfg["risk_aversion"]),
        near_abs_rmb=float(cfg.get("near_equivalent_absolute_rmb", 0.0)),
        near_rel=float(cfg.get("near_equivalent_relative", 0.02)),
        burden_ratio_max=float(decision.get("burden_ratio_max", 1.00)),
        positive_net_benefit_probability_min=float(
            decision.get("positive_net_benefit_probability_min", 0.60)
        ),
        zero_cost_epsilon=float(decision.get("zero_cost_epsilon", 1e-9)),
    )
    if not 0.0 < artifact.cvar_alpha < 1.0:
        raise RuntimeError("M4_CVAR_ALPHA_INVALID")
    if not 0.0 <= artifact.risk_aversion <= 1.0:
        raise RuntimeError("M4_RISK_AVERSION_INVALID")
    return artifact


def _value(row: pd.Series, names: list[str]) -> Any:
    for name in names:
        if name in row and pd.notna(row[name]):
            return row[name]
    return None


def _status(pass_: bool | None, applicable: bool, missing: bool = False) -> str:
    if not applicable:
        return "NOT_APPLICABLE"
    if missing:
        return "MISSING"
    return "PASS" if bool(pass_) else "FAIL"


def _strict_bool(value: Any, field: str) -> bool:
    if not isinstance(value, (bool, np.bool_)):
        raise RuntimeError(f"M3_BOOLEAN_FIELD_INVALID:{field}")
    return bool(value)


def screen_physical_actions(
    rules: pd.DataFrame,
    snapshots: pd.DataFrame,
    actions: dict[str, Action],
    trigger: np.ndarray,
    resource_profiles: dict[str, dict[str, float]] | None = None,
) -> PhysicalScreenResult:
    profiles = resource_profiles or {}
    trigger_values = np.asarray(trigger)
    if trigger_values.ndim != 1 or len(trigger_values) != len(snapshots):
        raise RuntimeError("M4_TRIGGER_SHAPE_INVALID")
    if any(not isinstance(value, (bool, np.bool_)) for value in trigger_values):
        raise RuntimeError("M3_BOOLEAN_FIELD_INVALID:trigger")
    trigger_map = {
        (str(row.episode_id), str(row.snapshot_id)): _strict_bool(row.trigger, "trigger")
        for row in snapshots[["episode_id", "snapshot_id"]]
        .assign(trigger=trigger_values)
        .itertuples(index=False)
    }
    rows: list[dict[str, Any]] = []
    feasible: dict[tuple[str, str], list[str]] = {}

    for key_raw, group in rules.groupby(["episode_id", "snapshot_id"], sort=False):
        key = (str(key_raw[0]), str(key_raw[1]))
        by_action = {str(row.action_id): row for row in group.itertuples(index=False)}
        if set(by_action) != set(actions):
            raise RuntimeError(f"ACTION_AUDIT_SCHEMA_MISMATCH:{key}")
        if key not in trigger_map:
            raise RuntimeError(f"M4_TRIGGER_KEY_MISSING:{key}")
        feasible[key] = []

        for action_id, action in actions.items():
            is_triggered = trigger_map[key]
            if action_id == "A00":
                gates = {
                    "capacity": True,
                    "window": True,
                    "resource": True,
                    "authority": True,
                    "lead": True,
                    "typed": True,
                }
                statuses = {gate: "NOT_APPLICABLE" for gate in gates}
                failures = ["PASS"]
                feasible_now = True
            else:
                rule = pd.Series(by_action[action_id]._asdict())
                failures: list[str] = []

                flow = _value(rule, ["airport_flow_pressure"])
                threshold = _value(rule, ["capacity_threshold"])
                p05 = _value(rule, ["capacity_reference_p05"])
                p95 = _value(rule, ["capacity_reference_p95"])
                if not action.capacity_required:
                    capacity_ok = True
                    capacity_status = "NOT_APPLICABLE"
                elif any(value is None for value in (flow, threshold, p05, p95)):
                    capacity_ok = False
                    capacity_status = "MISSING"
                    failures.append("CAPACITY_INPUT_OR_SPAN_MISSING")
                else:
                    span = float(p95) - float(p05)
                    if not np.isfinite(span) or span < 0.0:
                        capacity_ok = False
                        capacity_status = "MISSING"
                        failures.append("CAPACITY_SPAN_INVALID")
                    else:
                        capacity_ok = (
                            float(flow) + action.cap * span <= float(threshold)
                        )
                        capacity_status = _status(capacity_ok, True)
                        if not capacity_ok:
                            failures.append("CAPACITY_EXCEEDED")

                margin = _value(rule, ["action_window_margin"])
                opened = _value(rule, ["action_window_open"])
                if opened is not None:
                    opened = _strict_bool(opened, f"{key}:{action_id}:action_window_open")
                window_applicable = (
                    action.window_type in {"flight_timing", "combined"}
                    and action.window > 0
                )
                if not window_applicable:
                    window_ok = True
                    window_status = "NOT_APPLICABLE"
                elif opened is None or margin is None:
                    window_ok = False
                    window_status = "MISSING"
                    failures.append("WINDOW_INPUT_MISSING")
                elif not opened:
                    window_ok = False
                    window_status = "FAIL"
                    failures.append("WINDOW_CLOSED")
                else:
                    window_ok = action.window <= float(margin)
                    window_status = _status(window_ok, True)
                    if not window_ok:
                        failures.append("SHIFT_EXCEEDS_WINDOW")

                explicit = [
                    _value(rule, [f"resource_available_{channel.lower()}"])
                    for channel in CHANNELS
                ]
                profile_id = _value(rule, ["resource_profile_id"])
                if all(value is not None for value in explicit):
                    availability = {
                        channel: float(value)
                        for channel, value in zip(CHANNELS, explicit)
                    }
                elif profile_id is not None and str(profile_id) in profiles:
                    availability = {
                        channel: float(value)
                        for channel, value in profiles[str(profile_id)].items()
                    }
                else:
                    availability = {}
                required = {
                    "F": action.req_f,
                    "P": action.req_p,
                    "R": action.req_r,
                }
                if set(availability) != set(CHANNELS):
                    resource_ok = False
                    resource_status = "MISSING"
                    failures.append("RESOURCE_STATE_MISSING")
                else:
                    shortages = [
                        channel
                        for channel in CHANNELS
                        if required[channel] > availability[channel]
                    ]
                    resource_ok = not shortages
                    resource_status = _status(resource_ok, True)
                    failures.extend(
                        [f"RESOURCE_{channel}_SHORTAGE" for channel in shortages]
                    )

                authority = _value(rule, ["authority_allowed"])
                if authority is not None:
                    authority = _strict_bool(authority, f"{key}:{action_id}:authority_allowed")
                authority_profile = str(
                    _value(rule, ["authority_profile_id"]) or ""
                ).lower()
                authority_active = authority_profile not in {
                    "unrestricted",
                    "unrestricted_primary",
                    "public_rule_v1",
                }
                if not authority_active:
                    authority_ok = True
                    authority_status = "NOT_ACTIVE_UNDER_PRIMARY_PROFILE"
                elif authority is None:
                    authority_ok = False
                    authority_status = "MISSING"
                    failures.append("AUTHORITY_RULE_MISSING")
                else:
                    authority_ok = authority
                    authority_status = _status(authority_ok, True)
                    if not authority_ok:
                        failures.append("AUTHORITY_DENIED")

                lead = _value(rule, ["lead_time_margin"])
                if lead is None:
                    lead_ok = False
                    lead_status = "MISSING"
                    failures.append("LEAD_TIME_MARGIN_MISSING")
                else:
                    lead_ok = action.lead <= float(lead)
                    lead_status = _status(lead_ok, True)
                    if not lead_ok:
                        failures.append("INSUFFICIENT_LEAD_TIME")

                typed_failures: list[str] = []
                typed_missing = False
                for gate_name in action.typed_gates:
                    gate_value = _value(rule, [gate_name])
                    evidence = _value(rule, [f"{gate_name}_evidence_status"])
                    if gate_value is not None:
                        gate_value = _strict_bool(
                            gate_value,
                            f"{key}:{action_id}:{gate_name}",
                        )
                    if gate_value is None or evidence is None:
                        typed_missing = True
                        typed_failures.append(f"TYPED_GATE_MISSING:{gate_name}")
                    elif str(evidence) == "UNSUPPORTED":
                        typed_failures.append(f"TYPED_GATE_UNSUPPORTED:{gate_name}")
                    elif not gate_value:
                        typed_failures.append(f"TYPED_GATE_UNAVAILABLE:{gate_name}")
                typed_ok = not typed_failures
                if not action.typed_gates:
                    typed_status = "NOT_APPLICABLE"
                elif typed_missing:
                    typed_status = "MISSING"
                else:
                    typed_status = "PASS" if typed_ok else "FAIL_CLOSED"
                failures.extend(typed_failures)

                gates = {
                    "capacity": capacity_ok,
                    "window": window_ok,
                    "resource": resource_ok,
                    "authority": authority_ok,
                    "lead": lead_ok,
                    "typed": typed_ok,
                }
                statuses = {
                    "capacity": capacity_status,
                    "window": window_status,
                    "resource": resource_status,
                    "authority": authority_status,
                    "lead": lead_status,
                    "typed": typed_status,
                }
                feasible_now = all(gates.values())
                if not failures:
                    failures = ["PASS"]

            if feasible_now:
                feasible[key].append(action_id)
            primary = next((code for code in failures if code != "PASS"), "PASS")
            rows.append({
                "episode_id": key[0],
                "snapshot_id": key[1],
                "action_id": action_id,
                "action_family": action.family,
                "intensity": action.priority,
                **{f"gate_{gate}": bool(value) for gate, value in gates.items()},
                **{
                    f"gate_{gate}_status": statuses[gate]
                    for gate in ("capacity", "window", "resource", "authority", "lead", "typed")
                },
                "typed_gate_required": "|".join(action.typed_gates),
                "failed_gate_count": int(sum(not value for value in gates.values())),
                "failure_codes": "|".join(failures),
                "primary_failure_code": primary,
                "all_failure_codes": "|".join(failures),
                "physical_feasible": bool(feasible_now),
                "is_feasible": bool(feasible_now),  # Transitional alias.
                "trigger": bool(is_triggered),
                "is_evaluated": bool(
                    feasible_now and (action_id == "A00" or is_triggered)
                ),
            })

    return PhysicalScreenResult(pd.DataFrame(rows), feasible)
