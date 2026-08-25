"""Assumption-grounded tail scoring for the frozen explicit overflow class (G-Tail).

Implements the Path B supplement T-A / T-B / T-C contracts:

- T-A  : mixed discrete-continuous predictive representation
         ``F_hat(x) = H(x)`` for ``x < q_max`` (finite-bin histogram CDF) and
         ``F_hat(x) = 1 - p_tail + p_tail * G(x - q_max)`` for ``x >= q_max``,
         with the tail-internal distribution G in two tracks:
         T-BASE  : ``G(y) = 1[y >= 0]`` (point mass at the lower bound q_max)
         T-PARAM : ``G`` = generalized Pareto GP(xi, sigma), sigma from a
                   moment estimate of observed tail excesses (>= 30 tail
                   samples required, otherwise fallback to T-BASE).
- T-B  : threshold-weighted CRPS ``twCRPS(F, y; w)`` with ``w = 1[x >= q_max]``
         (Gneiting & Ranjan 2011) in closed form, and the mixed
         ``CRPS = CRPS_finite + CRPS_tail`` decomposition (Friederichs &
         Thorarinsdottir 2012).  Tail-conditional PIT diagnostics are
         diagnostic-only (Taillardat et al. 2023).
- T-C  : M4 tail loss ``J_tail = c_tail * E[(D_tail - q_max)+]`` with the GP
         excess expectation ``sigma/(1 - xi)`` (Coles 2001) and the actuarial
         limited expected value ``LEV(u) = int_0^u (1 - F(x)) dx`` (Loss
         Models) for the T-BASE lower bound.

All outputs are ASSUMPTION_GROUNDED: they never claim empirical calibration,
never substitute a fabricated scalar for the overflow class, and never
zero-fill.  When T-BASE and T-PARAM disagree, no empirical tail calibration
claim is made.
"""

from __future__ import annotations

from math import exp, isfinite
from statistics import mean
from typing import Any, Mapping, Sequence


Q_MAX_MINUTES: dict[str, float] = {"D_OB": 210.0, "D_TX": 60.0, "T_IB_A00": 360.0}
BIN_WIDTH_MINUTES = 5.0
TAIL_MIN_SAMPLES = 30
XI_SENSITIVITY: tuple[float, ...] = (-0.2, 0.0, 0.2)
SCHEME_T_BASE = "T-BASE"
SCHEME_T_PARAM = "T-PARAM"
SCHEMES = (SCHEME_T_BASE, SCHEME_T_PARAM)

_FINITE_CLASSES = ("ZERO", "FINITE")
_TAIL_CLASS = "OVERFLOW_TAIL"


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def gp_survival(y: float, xi: float, sigma: float) -> float:
    """P(Y > y) for Y ~ GP(xi, sigma) on y >= 0."""
    _require(sigma > 0.0, "TAIL_GP_SIGMA_NONPOSITIVE")
    if abs(xi) < 1e-12:
        return exp(-y / sigma)
    base = 1.0 + xi * y / sigma
    if base <= 0.0:
        return 0.0
    return base ** (-1.0 / xi)


def gp_mean(xi: float, sigma: float) -> float:
    """E[Y] = sigma / (1 - xi), xi < 1 (Coles 2001)."""
    _require(xi < 1.0, "TAIL_GP_XI_GE_ONE_MEAN_UNDEFINED")
    return sigma / (1.0 - xi)


def gp_survival_integral(d: float, xi: float, sigma: float) -> float:
    """int_0^d S(y) dy with S the GP survival function (closed form)."""
    _require(d >= 0.0, "TAIL_GP_INTEGRAL_NEGATIVE_BOUND")
    _require(xi < 1.0, "TAIL_GP_XI_GE_ONE_INTEGRAL_UNDEFINED")
    if abs(xi) < 1e-12:
        return sigma * (1.0 - exp(-d / sigma))
    base = 1.0 + xi * d / sigma
    if base <= 0.0:
        return gp_mean(xi, sigma)
    return gp_mean(xi, sigma) * (1.0 - base ** (1.0 - 1.0 / xi))


def gp_sq_survival_integral(xi: float, sigma: float) -> float:
    """int_0^infty S(y)^2 dy = sigma / (2 - xi), xi < 2."""
    _require(xi < 2.0, "TAIL_GP_XI_GE_TWO_SQUARE_INTEGRAL_UNDEFINED")
    return sigma / (2.0 - xi)


def gp_tail_moment_sigma(excesses: Sequence[float], xi: float) -> float:
    """Method-of-moments sigma for fixed xi: E[Y] = sigma/(1-xi).

    For xi < 0 the GP has finite support [0, -sigma/xi]; the estimate is
    raised so that every observed excess lies inside the support.
    """
    values = tuple(float(value) for value in excesses)
    _require(bool(values), "TAIL_GP_NO_EXCESS_SAMPLES")
    _require(xi in XI_SENSITIVITY, "TAIL_GP_XI_OUTSIDE_SENSITIVITY_GRID")
    estimate = mean(values) * (1.0 - xi)
    if xi < 0.0:
        estimate = max(estimate, max(values) * (-xi))
    return estimate


def twcrps_tail_closed_form(
    *,
    p_tail: float,
    q_max: float,
    observation: float,
    scheme: str,
    xi: float = 0.0,
    sigma: float | None = None,
) -> float:
    """int_{q_max}^inf (F(x) - 1[y <= x])^2 dx with w = 1[x >= q_max].

    T-BASE (G degenerate at 0, i.e. F == 1 on [q_max, inf)):
        y <= q_max -> 0 ; y > q_max -> y - q_max.
    T-PARAM (G = GP(xi, sigma)):
        y <= q_max -> p_tail^2 * sigma/(2 - xi)
        y >  q_max -> (y - q_max) - 2 p_tail I(y - q_max)
                      + p_tail^2 * sigma/(2 - xi),
        I(d) = int_0^d S(y) dy.
    """
    _require(0.0 <= p_tail <= 1.0, "TAIL_P_TAIL_OUT_OF_RANGE")
    _require(scheme in SCHEMES, "TAIL_UNKNOWN_SCHEME")
    if scheme == SCHEME_T_BASE:
        return max(0.0, float(observation) - q_max)
    _require(sigma is not None and sigma > 0.0, "TAIL_GP_SIGMA_REQUIRED")
    sq = gp_sq_survival_integral(xi, sigma)
    if observation <= q_max:
        return (p_tail ** 2) * sq
    d = float(observation) - q_max
    return d - 2.0 * p_tail * gp_survival_integral(d, xi, sigma) + (p_tail ** 2) * sq


def _bin_polynomial_integrals(cdf_start: float, slope: float, width: float):
    """int (h + s t)^2 dt and int (h + s t - 1)^2 dt over [0, width]."""
    square = (
        (cdf_start ** 2) * width
        + cdf_start * slope * (width ** 2)
        + (slope ** 2) * (width ** 3) / 3.0
    )
    shifted = (
        square
        - 2.0 * (cdf_start * width + slope * (width ** 2) / 2.0)
        + width
    )
    return square, shifted


def crps_finite_closed_form(
    *,
    histogram_counts: Sequence[int],
    bin_width: float,
    q_max: float,
    observation: float,
    total_mass: float = 1.0,
) -> float:
    """int_0^{q_max} (F(x) - 1[y <= x])^2 dx over the finite bins.

    ``F(x) = total_mass * H(x)`` with ``H`` the finite-conditional histogram
    CDF, so that ``F(q_max-) = 1 - p_tail`` matches the T-A mixed
    representation.  ``histogram_counts`` cover the finite bins
    ``[0, q_max)`` (left-closed, right-open, uniform width); the observation
    ``y`` may be finite or in the overflow class (``y >= q_max``).
    """
    counts = tuple(int(value) for value in histogram_counts)
    total = sum(counts)
    _require(total > 0, "TAIL_FINITE_HISTOGRAM_EMPTY")
    _require(bin_width > 0.0 and q_max > 0.0, "TAIL_HISTOGRAM_BAD_GEOMETRY")
    _require(abs(q_max - bin_width * len(counts)) <= 1e-9, "TAIL_HISTOGRAM_Q_MAX_MISMATCH")
    _require(0.0 <= total_mass <= 1.0, "TAIL_FINITE_TOTAL_MASS_OUT_OF_RANGE")
    y = float(observation)
    cdf = 0.0
    integral = 0.0
    for index, count in enumerate(counts):
        mass = total_mass * count / total
        slope = mass / bin_width
        start = index * bin_width
        end = start + bin_width
        if y >= end:
            square, _ = _bin_polynomial_integrals(cdf, slope, bin_width)
            integral += square
        elif y <= start:
            _, shifted = _bin_polynomial_integrals(cdf, slope, bin_width)
            integral += shifted
        else:
            width = y - start
            square, _ = _bin_polynomial_integrals(cdf, slope, width)
            integral += square
            _, shifted = _bin_polynomial_integrals(cdf + slope * width, slope, bin_width - width)
            integral += shifted
        cdf += mass
    _require(abs(cdf - total_mass) <= 1e-9, "TAIL_HISTOGRAM_CDF_NONUNIT")
    return integral


def limited_expected_value(
    *,
    histogram_counts: Sequence[int],
    bin_width: float,
    q_max: float,
    total_mass: float = 1.0,
) -> float:
    """LEV(q_max) = int_0^{q_max} (1 - F(x)) dx, actuarial finite expectation."""
    counts = tuple(int(value) for value in histogram_counts)
    total = sum(counts)
    _require(total > 0, "TAIL_FINITE_HISTOGRAM_EMPTY")
    _require(0.0 <= total_mass <= 1.0, "TAIL_FINITE_TOTAL_MASS_OUT_OF_RANGE")
    cdf = 0.0
    value = 0.0
    for index, count in enumerate(counts):
        mass = total_mass * count / total
        slope = mass / bin_width
        value += (1.0 - cdf) * bin_width - 0.5 * slope * (bin_width ** 2)
        cdf += mass
    return value


def mixed_crps(
    *,
    p_tail: float,
    histogram_counts: Sequence[int],
    bin_width: float,
    q_max: float,
    observation: float,
    scheme: str,
    xi: float = 0.0,
    sigma: float | None = None,
) -> dict[str, float]:
    """CRPS = CRPS_finite + CRPS_tail over the T-A mixed representation."""
    finite = 0.0 if sum(histogram_counts) == 0 else crps_finite_closed_form(
        histogram_counts=histogram_counts, bin_width=bin_width,
        q_max=q_max, observation=observation, total_mass=1.0 - p_tail,
    )
    tail = twcrps_tail_closed_form(
        p_tail=p_tail, q_max=q_max, observation=observation,
        scheme=scheme, xi=xi, sigma=sigma,
    )
    return {"crps_finite": finite, "crps_tail": tail,
            "crps_total": finite + tail}


def j_tail_expectation(
    *,
    p_tail: float,
    scheme: str,
    xi: float = 0.0,
    sigma: float | None = None,
    c_tail: float = 1.0,
) -> dict[str, float]:
    """E[(D_tail - q_max)+] and J_tail = c_tail * that expectation (T-C).

    T-BASE: the tail mass sits at the lower bound -> excess expectation 0.
    T-PARAM: E[(X - q_max)+] = p_tail * sigma/(1 - xi) (Coles 2001).
    """
    _require(c_tail >= 0.0, "TAIL_C_TAIL_NEGATIVE")
    if scheme == SCHEME_T_BASE:
        excess_expectation = 0.0
    else:
        _require(sigma is not None and sigma > 0.0, "TAIL_GP_SIGMA_REQUIRED")
        excess_expectation = p_tail * gp_mean(xi, sigma)
    return {"excess_expectation": excess_expectation,
            "j_tail": c_tail * excess_expectation}


def tail_pit_value(
    *,
    observation: float,
    q_max: float,
    scheme: str,
    xi: float = 0.0,
    sigma: float | None = None,
) -> float | None:
    """Tail-conditional PIT G(observation - q_max) for observed tail values.

    Diagnostic only (Taillardat et al. 2023); never a gate.  T-BASE is the
    degenerate limit -> PIT 1.0 at the lower bound.
    """
    y = float(observation)
    if y < q_max:
        return None
    if scheme == SCHEME_T_BASE:
        return 1.0
    _require(sigma is not None and sigma > 0.0, "TAIL_GP_SIGMA_REQUIRED")
    return 1.0 - gp_survival(y - q_max, xi, sigma)


def pooled_tail_sigma(
    excesses: Sequence[float],
) -> dict[str, Any]:
    """Pooled moment estimate of the GP scale for every xi sensitivity level.

    Enabled only when >= TAIL_MIN_SAMPLES observed tail excesses exist;
    otherwise the T-PARAM track falls back to T-BASE.
    """
    values = tuple(float(value) for value in excesses)
    enabled = len(values) >= TAIL_MIN_SAMPLES
    return {
        "n_tail_samples": len(values),
        "enabled": enabled,
        "fallback_reason": (None if enabled else "TAIL_SAMPLES_BELOW_MINIMUM_30"),
        "sigma_by_xi": {
            str(xi): (gp_tail_moment_sigma(values, xi) if enabled else None)
            for xi in XI_SENSITIVITY
        },
    }


def build_node_target_distribution(
    envelopes: Sequence[Mapping[str, Any]],
    *,
    target: str,
    q_max: float,
    bin_width: float = BIN_WIDTH_MINUTES,
) -> dict[str, Any]:
    """Histogram over finite scalars + explicit tail mass from scenario draws."""
    _require(target in Q_MAX_MINUTES, "TAIL_UNKNOWN_TARGET")
    _require(abs(q_max - Q_MAX_MINUTES[target]) <= 1e-9, "TAIL_Q_MAX_DRIFT")
    bin_count = int(round(q_max / bin_width))
    counts = [0] * bin_count
    tail = 0
    supported = 0
    for envelope in envelopes:
        class_id = envelope.get("class_id")
        scalar = envelope.get("scalar_minutes")
        if class_id == _TAIL_CLASS or scalar is None:
            tail += 1
            continue
        if class_id not in _FINITE_CLASSES or scalar < 0.0:
            continue
        supported += 1
        index = min(bin_count - 1, int(float(scalar) // bin_width))
        counts[index] += 1
    total = len(envelopes)
    _require(total > 0, "TAIL_NODE_NO_SCENARIO_DRAWS")
    return {
        "histogram_counts": counts,
        "p_tail": tail / total,
        "n_tail_draws": tail,
        "n_finite_supported": supported,
        "n_draws": total,
        "q_max": q_max,
        "bin_width": bin_width,
    }


def node_scalar_tail_scores(
    distribution: Mapping[str, Any],
    *,
    observation: float | None,
    pooled: Mapping[str, Any],
    c_tail: float = 1.0,
) -> dict[str, Any] | None:
    """Dual-scheme scalar CRPS / twCRPS_tail / J_tail for one node target.

    Returns None when the observation is unavailable (ABSTAIN, no zero-fill).
    T-PARAM falls back to T-BASE when the pooled tail sample is too small.
    """
    if observation is None:
        return None
    if distribution["n_tail_draws"] + distribution["n_finite_supported"] == 0:
        return None
    q_max = float(distribution["q_max"])
    p_tail = float(distribution["p_tail"])
    schemes: dict[str, Any] = {}
    sigma = pooled["sigma_by_xi"]["0.0"] if pooled["enabled"] else None
    for scheme in SCHEMES:
        active = scheme if (scheme == SCHEME_T_BASE or sigma is not None) else SCHEME_T_BASE
        crps = mixed_crps(
            p_tail=p_tail, histogram_counts=distribution["histogram_counts"],
            bin_width=float(distribution["bin_width"]), q_max=q_max,
            observation=float(observation), scheme=active, xi=0.0, sigma=sigma,
        )
        j_tail = j_tail_expectation(
            p_tail=p_tail, scheme=active, xi=0.0, sigma=sigma, c_tail=c_tail,
        )
        schemes[active] = {
            "crps": crps["crps_total"],
            "crps_finite": crps["crps_finite"],
            "crps_tail": crps["crps_tail"],
            "twcrps_tail": crps["crps_tail"],
            "j_tail": j_tail["j_tail"],
            "excess_expectation": j_tail["excess_expectation"],
            "xi": 0.0,
            "sigma": sigma,
        }
    pit = tail_pit_value(
        observation=float(observation), q_max=q_max,
        scheme=SCHEME_T_PARAM if pooled["enabled"] else SCHEME_T_BASE,
        xi=0.0, sigma=sigma,
    )
    return {
        "schemes": schemes,
        "p_tail": p_tail,
        "n_tail_draws": distribution["n_tail_draws"],
        "n_finite_supported": distribution["n_finite_supported"],
        "observed_in_tail": float(observation) >= q_max,
        "tail_pit": pit,
        "tail_pooled_n": pooled["n_tail_samples"],
        "tail_pooled_enabled": pooled["enabled"],
        "sensitivity_xi": list(XI_SENSITIVITY),
    }