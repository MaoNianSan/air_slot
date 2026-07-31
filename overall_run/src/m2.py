from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

CHANNELS = ("F", "P", "R")
ALLOWED_GRAPH_EDGES = {"F_to_P", "F_to_R", "P_to_R"}

ANCHOR_ALIASES = {
    "turnaround_margin": ["turnaround_margin"],
    "continuity": ["continuity_exposure"],
    "window_margin": ["execution_window_margin"],
    "passenger_load": ["estimated_passenger_load"],
    "connection": ["connection_pressure_proxy"],
    "rebooking": ["rebooking_scarcity_proxy"],
    "flow": ["airport_flow_pressure"],
    "infrastructure": ["infrastructure_flexibility"],
    "resource_available": ["resource_available_r", "resource_availability_r"],
}


def _pick(df: pd.DataFrame, aliases: list[str]) -> np.ndarray:
    for col in aliases:
        if col in df:
            return pd.to_numeric(df[col], errors="coerce").to_numpy(float)
    return np.full(len(df), np.nan, dtype=float)


@dataclass
class RobustNormalizer:
    q05: float
    q95: float
    reverse: bool = False
    supported: bool = True
    preserve_missing: bool = False

    def transform(self, x: np.ndarray) -> np.ndarray:
        values = np.asarray(x, dtype=float)
        if not self.supported:
            return np.full(values.shape, np.nan, dtype=float)
        z = np.clip(
            (values - self.q05) / max(self.q95 - self.q05, 1e-9),
            0.0,
            1.0,
        )
        # Non-passenger anchors may use a frozen training-median proxy.  The
        # imputation is surfaced separately by M2Artifact.anchor_statuses().
        z = np.where(np.isfinite(z), z, 0.5)
        if self.preserve_missing:
            z = np.where(np.isfinite(values), z, np.nan)
        return 1.0 - z if self.reverse else z


@dataclass
class M2Artifact:
    normalizers: dict[str, RobustNormalizer]
    graph_edges: dict[str, float]
    params: dict[str, Any]
    anchor_support: dict[str, int]
    resource_reference_scale: float
    unit_scales: dict[str, float] = field(default_factory=dict)
    unit_scale_support: dict[str, int] = field(default_factory=dict)
    unit_costs_rmb: dict[str, float] = field(default_factory=lambda: {g: 1.0 for g in CHANNELS})
    contract_version: str = "overall-run-m2-rmb-v2"

    @property
    def passenger_proxy_supported(self) -> bool:
        return all(
            self.anchor_support.get(name, 0) > 0
            for name in ("passenger_load", "connection", "rebooking")
        )

    @property
    def unit_scales_fitted(self) -> bool:
        return set(self.unit_scales) == set(CHANNELS) and all(
            np.isfinite(self.unit_scales[g]) and self.unit_scales[g] > 0
            for g in CHANNELS
        )

    def _normalized_anchors(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        return {
            name: normalizer.transform(_pick(df, ANCHOR_ALIASES[name]))
            for name, normalizer in self.normalizers.items()
        }

    def anchor_statuses(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        statuses: dict[str, np.ndarray] = {}
        passenger_names = {"passenger_load", "connection", "rebooking"}
        for name, normalizer in self.normalizers.items():
            raw = _pick(df, ANCHOR_ALIASES[name])
            if not normalizer.supported:
                statuses[name] = np.full(len(df), "UNSUPPORTED_INPUT", dtype=object)
            elif name in passenger_names:
                statuses[name] = np.where(
                    np.isfinite(raw), "AVAILABLE", "UNSUPPORTED_INPUT"
                ).astype(object)
            else:
                statuses[name] = np.where(
                    np.isfinite(raw), "AVAILABLE", "CALIBRATION_IMPUTED"
                ).astype(object)
        return statuses

    def exposures(self, df: pd.DataFrame) -> dict[str, Any]:
        n = self._normalized_anchors(df)
        base = {
            "F": np.nanmean(
                np.column_stack(
                    [n["turnaround_margin"], n["continuity"], n["window_margin"]]
                ),
                axis=1,
            ),
            "P": np.clip(
                0.45 * n["passenger_load"]
                + 0.25 * n["connection"]
                + 0.30 * n["rebooking"],
                0.0,
                1.0,
            ),
            "R": np.clip(
                self.params["resource_stress"]["alpha_flow"] * n["flow"]
                + self.params["resource_stress"]["alpha_infra"] * n["infrastructure"]
                + self.params["resource_stress"]["alpha_scarcity"] * n["resource_available"],
                0.0,
                1.0,
            ),
        }
        final = {channel: values.copy() for channel, values in base.items()}
        contributions: dict[str, np.ndarray] = {}
        # Every edge is computed from the unchanged base exposure.  Results are
        # therefore invariant to YAML ordering and contain no implicit cycles.
        for edge, coefficient in self.graph_edges.items():
            source, target = edge.split("_to_")
            contribution = float(coefficient) * base[source]
            contributions[edge] = contribution
            final[target] = final[target] + contribution
        for channel in CHANNELS:
            final[channel] = np.clip(final[channel], 0.0, 1.0)
        return {
            "base": base,
            "final": final,
            "edge_contributions": contributions,
            "normalized_anchors": n,
            "anchor_statuses": self.anchor_statuses(df),
        }

    def raw_quantities(
        self,
        df: pd.DataFrame,
        execution_samples: np.ndarray,
    ) -> dict[str, Any]:
        samples = np.asarray(execution_samples, dtype=float)
        if samples.ndim != 2 or samples.shape[0] != len(df):
            raise ValueError(
                f"M2_SAMPLE_SHAPE_MISMATCH:{samples.shape}!={(len(df), 'S')}"
            )
        exposure = self.exposures(df)
        x = exposure["final"]
        anchors = exposure["normalized_anchors"]
        raw_anchor_values = {
            name: _pick(df, aliases) for name, aliases in ANCHOR_ALIASES.items()
        }

        quantities: dict[str, np.ndarray] = {}
        thresholds: dict[str, np.ndarray] = {}

        flight_cfg = self.params["flight"]
        threshold_f = np.clip(
            float(flight_cfg["threshold_base"])
            + float(flight_cfg["threshold_exposure_slope"]) * (0.5 - x["F"]),
            float(flight_cfg["threshold_min"]),
            float(flight_cfg["threshold_max"]),
        )
        # Equivalent flight-operation disruption minutes.
        quantities["F"] = (
            (1.0 + x["F"][:, None])
            * np.maximum(samples - threshold_f[:, None], 0.0)
        ).astype(np.float32)
        thresholds["F"] = threshold_f

        passenger_cfg = self.params["passenger"]
        passenger_excess = np.maximum(
            samples - float(passenger_cfg["threshold"]), 0.0
        )
        passenger_response = passenger_excess / (
            float(passenger_cfg["saturation"]) + passenger_excess
        )
        passenger_load = raw_anchor_values["passenger_load"]
        passenger_supported = (
            np.isfinite(passenger_load)
            & np.isfinite(anchors["connection"])
            & np.isfinite(anchors["rebooking"])
            & np.isfinite(x["P"])
        )
        # Flight-level passenger exposure remains in its original magnitude;
        # normalized pressure and F->P coupling act only as bounded multipliers.
        passenger_multiplier = (
            1.0
            + 0.50 * x["P"]
            + 0.25 * anchors["connection"]
            + 0.25 * anchors["rebooking"]
        )
        q_p = (
            passenger_load[:, None]
            * passenger_multiplier[:, None]
            * passenger_response
        )
        q_p[~passenger_supported, :] = np.nan
        quantities["P"] = q_p.astype(np.float32)
        thresholds["P"] = np.full(len(df), float(passenger_cfg["threshold"]))

        resource_cfg = self.params["resource"]
        resource_excess = np.maximum(
            samples - float(resource_cfg["threshold"]), 0.0
        )
        resource_response = resource_excess / (
            float(resource_cfg["saturation"]) + resource_excess
        )
        quantities["R"] = (
            self.resource_reference_scale
            * (0.25 + x["R"][:, None])
            * resource_response
        ).astype(np.float32)
        thresholds["R"] = np.full(len(df), float(resource_cfg["threshold"]))

        return {
            "raw_quantities": quantities,
            "exposures": x,
            "base_exposures": exposure["base"],
            "edge_contributions": exposure["edge_contributions"],
            "thresholds": thresholds,
            "normalized_anchors": anchors,
            "anchor_statuses": exposure["anchor_statuses"],
            "passenger_proxy_used": passenger_supported,
            "passenger_proxy_missing_reason": np.where(
                passenger_supported, "", "UNSUPPORTED_INPUT"
            ),
            "passenger_cost_fallback_used": np.zeros(len(df), dtype=bool),
        }

    def fit_unit_scales(
        self,
        df: pd.DataFrame,
        execution_samples: np.ndarray,
    ) -> "M2Artifact":
        raw = self.raw_quantities(df, execution_samples)["raw_quantities"]
        minimum_support = int(self.params.get("channel_scale_min_positive", 200))
        scales: dict[str, float] = {}
        support: dict[str, int] = {}
        for channel in CHANNELS:
            values = np.asarray(raw[channel], dtype=float)
            finite_counts = np.isfinite(values).sum(axis=1)
            episode_means = np.divide(
                np.where(np.isfinite(values), values, 0.0).sum(axis=1),
                finite_counts,
                out=np.full(len(values), np.nan),
                where=finite_counts > 0,
            )
            positive = episode_means[np.isfinite(episode_means) & (episode_means > 0)]
            support[channel] = int(len(positive))
            if len(positive) < minimum_support:
                raise RuntimeError(
                    f"M2_UNIT_SCALE_SUPPORT_INSUFFICIENT:{channel}:"
                    f"{len(positive)}<{minimum_support}"
                )
            scale = float(np.median(positive))
            if not np.isfinite(scale) or scale <= 0:
                raise RuntimeError(f"M2_UNIT_SCALE_INVALID:{channel}:{scale}")
            scales[channel] = scale
        self.unit_scales = scales
        self.unit_scale_support = support
        return self

    def reconstruct(
        self,
        df: pd.DataFrame,
        execution_samples: np.ndarray,
        scenario: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        del scenario  # Retained only for backward API compatibility.
        if not self.unit_scales_fitted:
            raise RuntimeError("M2_UNIT_SCALES_NOT_FITTED")
        result = self.raw_quantities(df, execution_samples)
        unit_quantities: dict[str, np.ndarray] = {}
        costs_rmb: dict[str, np.ndarray] = {}
        for channel in CHANNELS:
            unit = (
                np.asarray(result["raw_quantities"][channel], dtype=float)
                / float(self.unit_scales[channel])
            ).astype(np.float32)
            cost = (unit * float(self.unit_costs_rmb[channel])).astype(np.float32)
            unit_quantities[channel] = unit
            costs_rmb[channel] = cost
            finite = np.isfinite(unit) & np.isfinite(cost)
            if not np.allclose(
                cost[finite],
                unit[finite] * float(self.unit_costs_rmb[channel]),
                atol=1e-7,
                rtol=1e-7,
            ):
                raise RuntimeError(f"M2_RMB_IDENTITY_FAILURE:{channel}")
        total = np.zeros_like(costs_rmb["F"], dtype=np.float32)
        any_missing = np.zeros_like(total, dtype=bool)
        for channel in CHANNELS:
            any_missing |= ~np.isfinite(costs_rmb[channel])
            total += np.nan_to_num(costs_rmb[channel], nan=0.0)
        total[any_missing] = np.nan
        result.update(
            {
                "quantities_unit": unit_quantities,
                "unit_scales": dict(self.unit_scales),
                "unit_scale_support": dict(self.unit_scale_support),
                "unit_costs_rmb": dict(self.unit_costs_rmb),
                "costs_rmb": costs_rmb,
                "losses": costs_rmb,  # Transitional downstream alias.
                "total_cost_rmb": total,
            }
        )
        return result


def fit_m2(train: pd.DataFrame, scientific: dict[str, Any]) -> M2Artifact:
    missing = [
        name
        for name, aliases in ANCHOR_ALIASES.items()
        if not any(column in train for column in aliases)
    ]
    if missing:
        raise RuntimeError("M2_ANCHOR_SCHEMA_MISSING:" + ",".join(missing))

    graph_edges = {
        str(key): float(value)
        for key, value in scientific["m2"].get("graph_edges", {}).items()
    }
    invalid_edges = set(graph_edges) - ALLOWED_GRAPH_EDGES
    if invalid_edges:
        raise RuntimeError(
            "M2_GRAPH_EDGE_INVALID:" + ",".join(sorted(invalid_edges))
        )
    if "R_to_F" in graph_edges:
        raise RuntimeError("M2_R_TO_F_PROHIBITED")

    normalizers: dict[str, RobustNormalizer] = {}
    support: dict[str, int] = {}
    passenger_names = {"passenger_load", "connection", "rebooking"}
    reverse_names = {
        "turnaround_margin",
        "window_margin",
        "infrastructure",
        "resource_available",
    }
    for name, aliases in ANCHOR_ALIASES.items():
        values = _pick(train, aliases)
        finite = values[np.isfinite(values)]
        support[name] = int(len(finite))
        if not len(finite):
            if name not in passenger_names:
                raise RuntimeError(f"M2_ANCHOR_ALL_MISSING:{name}")
            normalizers[name] = RobustNormalizer(
                0.0,
                1.0,
                supported=False,
                preserve_missing=True,
            )
            continue
        q05, q95 = np.quantile(finite, [0.05, 0.95])
        normalizers[name] = RobustNormalizer(
            q05=float(q05),
            q95=float(max(q95, q05 + 1e-9)),
            reverse=name in reverse_names,
            supported=True,
            preserve_missing=name in passenger_names,
        )

    flow_values = _pick(train, ANCHOR_ALIASES["flow"])
    resource_reference_scale = float(np.nanmedian(flow_values))
    if not np.isfinite(resource_reference_scale) or resource_reference_scale <= 0:
        raise RuntimeError("M2_RESOURCE_REFERENCE_SCALE_UNIDENTIFIED")

    unit_costs = {
        channel: float(value)
        for channel, value in scientific["m2"].get(
            "unit_costs_rmb", {"F": 1.0, "P": 1.0, "R": 1.0}
        ).items()
    }
    if set(unit_costs) != set(CHANNELS) or any(
        not np.isfinite(value) or value < 0 for value in unit_costs.values()
    ):
        raise RuntimeError("M2_UNIT_COST_RMB_INVALID")

    return M2Artifact(
        normalizers=normalizers,
        graph_edges=graph_edges,
        params=scientific["m2"],
        anchor_support=support,
        resource_reference_scale=resource_reference_scale,
        unit_costs_rmb=unit_costs,
    )
