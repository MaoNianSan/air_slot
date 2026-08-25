"""Unit tests for the assumption-grounded tail scoring module (G-Tail).

Validates the T-A / T-B / T-C closed forms against brute-force numeric
integration and Monte Carlo energy-form checks, the T-PARAM -> T-BASE
consistency limit, the tail-sample fallback, and the frozen q_max contract
from the M1 target-support manifest.
"""

import json
from math import exp
from pathlib import Path
import random

import pytest

from exp.exp2.tail_scores import (
    BIN_WIDTH_MINUTES,
    Q_MAX_MINUTES,
    SCHEME_T_BASE,
    SCHEME_T_PARAM,
    TAIL_MIN_SAMPLES,
    XI_SENSITIVITY,
    build_node_target_distribution,
    crps_finite_closed_form,
    gp_mean,
    gp_tail_moment_sigma,
    j_tail_expectation,
    limited_expected_value,
    mixed_crps,
    node_scalar_tail_scores,
    pooled_tail_sigma,
    tail_pit_value,
    twcrps_tail_closed_form,
)

ROOT = Path(__file__).resolve().parents[2]
SUPPORT_MANIFEST = ROOT / "artifacts/diagnostics/m1_v2_positive_tail_policy_freeze_v2/M1_V2_TARGET_SUPPORT_MANIFEST.json"


def _numeric_integral(fn, lower, upper, step=0.002):
    total = 0.0
    x = lower
    while x < upper:
        total += (fn(x) + fn(x + step)) * 0.5 * step
        x += step
    return total


def _histogram_cdf(counts, bin_width):
    total = sum(counts)
    points = []
    cdf = 0.0
    for index, count in enumerate(counts):
        mass = count / total
        start = index * bin_width
        points.append((start, cdf))
        cdf += mass
    points.append((len(counts) * bin_width, cdf))

    def evaluate(x):
        for index in range(len(points) - 1):
            start, value = points[index]
            end = points[index + 1][0]
            if start <= x < end:
                slope = (points[index + 1][1] - value) / bin_width
                return value + slope * (x - start)
        return points[-1][1]

    return evaluate




def _full_counts(prefix_counts, bin_count):
    """Pad a short bin list to the full finite-bin count for q_max."""
    assert len(prefix_counts) <= bin_count
    return list(prefix_counts) + [0] * (bin_count - len(prefix_counts))


def test_q_max_contract_matches_frozen_support_manifest():
    manifest = json.loads(SUPPORT_MANIFEST.read_text(encoding="utf-8"))
    for target, q_max in Q_MAX_MINUTES.items():
        assert float(manifest["target_contracts"][target]["q_max_minutes"]) == q_max
    assert manifest["representation"] == "FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS"
    assert manifest["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0


@pytest.mark.parametrize("observation", [50.0, 210.0, 300.0])
@pytest.mark.parametrize("p_tail", [0.02, 0.3])
def test_twcrps_t_base_matches_numeric_integral(observation, p_tail):
    q_max = 210.0
    # Mixed predictive: histogram over [0, q) plus p_tail point mass at q.
    counts = _full_counts([10, 20, 15, 8, 4, 2, 1], 42)
    cdf = _histogram_cdf(counts, BIN_WIDTH_MINUTES)

    def mixed_cdf(x):
        if x < q_max:
            return (1.0 - p_tail) * cdf(x)
        return 1.0

    def integrand(x):
        indicator = 1.0 if observation <= x else 0.0
        return (mixed_cdf(x) - indicator) ** 2

    expected = _numeric_integral(integrand, q_max, q_max + 200.0)
    actual = twcrps_tail_closed_form(
        p_tail=p_tail, q_max=q_max, observation=observation, scheme=SCHEME_T_BASE,
    )
    assert actual == pytest.approx(expected, abs=2e-3)


@pytest.mark.parametrize("xi", list(XI_SENSITIVITY))
@pytest.mark.parametrize("observation", [100.0, 210.0, 260.0])
def test_twcrps_t_param_matches_numeric_integral(xi, observation):
    q_max, sigma, p_tail = 210.0, 25.0, 0.05
    counts = [10, 20, 15, 8, 4, 2, 1]
    cdf = _histogram_cdf(counts, BIN_WIDTH_MINUTES)

    def gp_cdf(y):
        if abs(xi) < 1e-12:
            return 1.0 - exp(-y / sigma)
        base = 1.0 + xi * y / sigma
        if base <= 0.0:
            return 1.0
        return 1.0 - base ** (-1.0 / xi)

    def mixed_cdf(x):
        if x < q_max:
            return (1.0 - p_tail) * cdf(x)
        return 1.0 - p_tail + p_tail * gp_cdf(x - q_max)

    def integrand(x):
        indicator = 1.0 if observation <= x else 0.0
        return (mixed_cdf(x) - indicator) ** 2

    expected = _numeric_integral(integrand, q_max, q_max + 400.0)
    actual = twcrps_tail_closed_form(
        p_tail=p_tail, q_max=q_max, observation=observation,
        scheme=SCHEME_T_PARAM, xi=xi, sigma=sigma,
    )
    assert actual == pytest.approx(expected, abs=2e-3)


@pytest.mark.parametrize("observation", [30.0, 90.0, 140.0, 210.0, 300.0])
def test_crps_finite_matches_numeric_integral(observation):
    q_max, bin_width, p_tail = 210.0, 5.0, 0.05
    counts = _full_counts([10, 0, 20, 15, 8, 4, 2, 1, 0, 0, 3, 5, 0, 1, 2], 42)
    cdf = _histogram_cdf(counts, bin_width)

    def integrand(x):
        indicator = 1.0 if observation <= x else 0.0
        return ((1.0 - p_tail) * cdf(x) - indicator) ** 2

    expected = _numeric_integral(integrand, 0.0, q_max)
    actual = crps_finite_closed_form(
        histogram_counts=counts, bin_width=bin_width, q_max=q_max,
        observation=observation, total_mass=1.0 - p_tail,
    )
    assert actual == pytest.approx(expected, abs=2e-3)


def test_mixed_crps_matches_energy_form_monte_carlo():
    random.seed(7)
    q_max, sigma, p_tail = 210.0, 20.0, 0.06
    counts = _full_counts([30, 40, 25, 18, 10, 6, 3, 2, 1], 42)
    weights = [count / sum(counts) for count in counts]
    n = 200_000

    def draw():
        if random.random() < p_tail:
            return q_max + random.expovariate(1.0 / sigma)
        bin_index = random.choices(range(len(weights)), weights=weights)[0]
        return bin_index * BIN_WIDTH_MINUTES + random.random() * BIN_WIDTH_MINUTES

    for observation in (80.0, 220.0, 260.0):
        xs = [draw() for _ in range(n)]
        first = sum(abs(x - observation) for x in xs) / n
        second = sum(abs(xs[i] - xs[i - 1]) for i in range(1, n)) / n
        energy = first - 0.5 * second
        closed = mixed_crps(
            p_tail=p_tail, histogram_counts=counts, bin_width=BIN_WIDTH_MINUTES,
            q_max=q_max, observation=observation, scheme=SCHEME_T_PARAM,
            xi=0.0, sigma=sigma,
        )["crps_total"]
        assert closed == pytest.approx(energy, abs=1.0)


def test_t_param_limit_matches_t_base():
    q_max, p_tail = 210.0, 0.05
    for observation in (100.0, 260.0):
        base = twcrps_tail_closed_form(
            p_tail=p_tail, q_max=q_max, observation=observation, scheme=SCHEME_T_BASE,
        )
        param = twcrps_tail_closed_form(
            p_tail=p_tail, q_max=q_max, observation=observation,
            scheme=SCHEME_T_PARAM, xi=0.0, sigma=1e-6,
        )
        assert param == pytest.approx(base, abs=1e-6)


def test_tail_sample_fallback_below_minimum():
    pooled = pooled_tail_sigma([230.0, 240.0, 250.0, 260.0, 270.0, 280.0, 290.0, 300.0, 310.0, 320.0])
    assert pooled["n_tail_samples"] == 10
    assert pooled["enabled"] is False
    assert pooled["fallback_reason"] == "TAIL_SAMPLES_BELOW_MINIMUM_30"
    distribution = build_node_target_distribution(
        [{"class_id": "FINITE", "scalar_minutes": 30.0},
         {"class_id": "OVERFLOW_TAIL", "scalar_minutes": None}] * 50,
        target="D_OB", q_max=210.0,
    )
    scores = node_scalar_tail_scores(distribution, observation=300.0, pooled=pooled)
    assert set(scores["schemes"]) == {SCHEME_T_BASE}
    assert scores["tail_pooled_enabled"] is False


def test_pooled_sigma_enabled_at_threshold():
    excesses = [5.0 + 10.0 * (index % 5) for index in range(TAIL_MIN_SAMPLES)]
    pooled = pooled_tail_sigma(excesses)
    assert pooled["enabled"] is True
    for xi in XI_SENSITIVITY:
        assert pooled["sigma_by_xi"][str(xi)] > 0.0
    assert pooled["sigma_by_xi"]["0.0"] == pytest.approx(sum(excesses) / len(excesses))


def test_gp_moment_sigma_negative_xi_support_bound():
    excesses = [10.0, 20.0, 30.0]
    xi = -0.2
    estimate = gp_tail_moment_sigma(excesses, xi)
    assert estimate >= max(excesses) * 0.2
    assert estimate >= (sum(excesses) / len(excesses)) * 1.2


def test_j_tail_schemes_and_scale():
    p_tail, sigma = 0.05, 20.0
    base = j_tail_expectation(p_tail=p_tail, scheme=SCHEME_T_BASE)
    assert base["excess_expectation"] == 0.0
    assert base["j_tail"] == 0.0
    param = j_tail_expectation(p_tail=p_tail, scheme=SCHEME_T_PARAM, xi=0.0, sigma=sigma)
    assert param["excess_expectation"] == pytest.approx(p_tail * gp_mean(0.0, sigma))
    assert param["j_tail"] == pytest.approx(p_tail * sigma)
    scaled = j_tail_expectation(p_tail=p_tail, scheme=SCHEME_T_PARAM, xi=0.0, sigma=sigma, c_tail=2.5)
    assert scaled["j_tail"] == pytest.approx(2.5 * p_tail * sigma)


def test_limited_expected_value():
    counts = [10, 10]
    bin_width, q_max = 5.0, 10.0
    lev = limited_expected_value(histogram_counts=counts, bin_width=bin_width, q_max=q_max)
    # Uniform density over [0, 10): LEV = int_0^10 (1 - x/10) dx = 5.
    assert lev == pytest.approx(5.0, abs=1e-9)


def test_tail_pit_diagnostics():
    assert tail_pit_value(observation=100.0, q_max=210.0, scheme=SCHEME_T_BASE) is None
    assert tail_pit_value(observation=300.0, q_max=210.0, scheme=SCHEME_T_BASE) == 1.0
    pit = tail_pit_value(observation=220.0, q_max=210.0, scheme=SCHEME_T_PARAM, xi=0.0, sigma=20.0)
    assert 0.0 < pit < 1.0
    assert pit == pytest.approx(1.0 - exp(-10.0 / 20.0))


def test_node_distribution_build():
    envelopes = []
    for index in range(250):
        if index < 240:
            envelopes.append({"class_id": "FINITE", "scalar_minutes": float(index % 40)})
        else:
            envelopes.append({"class_id": "OVERFLOW_TAIL", "scalar_minutes": None})
    distribution = build_node_target_distribution(envelopes, target="D_TX", q_max=60.0)
    assert distribution["n_draws"] == 250
    assert distribution["n_tail_draws"] == 10
    assert distribution["p_tail"] == pytest.approx(10 / 250)
    assert sum(distribution["histogram_counts"]) == 240
    assert len(distribution["histogram_counts"]) == 12
    with pytest.raises(RuntimeError):
        build_node_target_distribution(envelopes, target="D_OB", q_max=60.0)