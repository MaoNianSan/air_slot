"""M1 V2 common calibration contract and hazard/hurdle calibration routines.

Round 2.2 calibration contract (shared by STATE_AWARE and FAST — the
underlying estimators may differ, the scientific calibration policy does not):

- predecessor: discrete-hazard event-time NLL calibration.  The objective
  goes hazard logits -> temperature -> hazard probabilities -> induced
  event-time PMF / survival tail -> event-time NLL.  Multiclass softmax
  cross-entropy is FORBIDDEN for hazard logits because every logit is a
  conditional hazard on its bin's risk set, not a mutually-exclusive class
  logit (``M1_HAZARD_MULTICLASS_CALIBRATION_FORBIDDEN``).
- successor zero mass: explicit binary-cross-entropy temperature calibration
  discipline on the hurdle zero logits.
- positive quantiles: raw quantile regressors with explicit
  ``QUANTILE_CALIBRATION_NOT_APPLIED`` status and calibration-split coverage
  diagnostics — nothing is silently claimed as calibrated.

Calibration split only; Final Test forbidden
(``M1_CALIBRATION_FINAL_TEST_ACCESS_FORBIDDEN``, ``final_test_access_count``
stays 0).
"""

from __future__ import annotations

import torch

from model.common.errors import ContractError
from model.common.value_objects import FrozenModel

from .loss import hazard_interval_nll


class M1CalibrationContract(FrozenModel):
    """Typed common calibration policy shared by STATE_AWARE and FAST."""

    predecessor_probability_calibration: str = "DISCRETE_HAZARD_EVENT_TIME_NLL"
    predecessor_calibration_method: str = "TEMPERATURE_ON_HAZARD_LOGITS"
    successor_zero_mass_calibration: str = "HURDLE_ZERO_BINARY_CE_TEMPERATURE"
    positive_quantile_calibration: str = "QUANTILE_CALIBRATION_NOT_APPLIED"
    split: str = "calibration"
    version: str = "M1_CALIBRATION_CONTRACT_V1"
    final_test_access_count: int = 0


COMMON_CALIBRATION_POLICY = M1CalibrationContract()


def common_calibration_policy() -> M1CalibrationContract:
    """Single scientific calibration policy for both paths."""
    return COMMON_CALIBRATION_POLICY


def require_calibration_split(split: str) -> None:
    if split != "calibration":
        raise ContractError(f"M1_CALIBRATION_SPLIT_FORBIDDEN:{split}")


def require_no_final_test(final_test_access_count: int) -> None:
    if int(final_test_access_count) != 0:
        raise ContractError("M1_CALIBRATION_FINAL_TEST_ACCESS_FORBIDDEN")


def reject_multiclass_hazard_calibration() -> None:
    """Forbid the legacy multiclass softmax fit for discrete-hazard logits.

    Each hazard logit is the conditional hazard of its finite bin (risk-set
    semantics), never a mutually-exclusive class logit; softmax cross-entropy
    would silently corrupt the discrete-hazard likelihood.
    """
    raise ContractError("M1_HAZARD_MULTICLASS_CALIBRATION_FORBIDDEN")


def fit_hazard_temperature(
    logits: torch.Tensor,
    labels: torch.Tensor,
    active: torch.Tensor,
    contract,
    *,
    steps: int = 50,
    split: str = "calibration",
) -> float:
    """Calibrate hazard logits by event-time NLL on the calibration split.

    ``labels`` are hazard bin indices (finite bins or the overflow tail); the
    objective is the negative log probability of the observed remaining-time
    interval under the induced discrete-hazard PMF / survival tail.
    """
    require_calibration_split(split)
    labels = torch.as_tensor(labels, dtype=torch.long)
    active = torch.as_tensor(active, dtype=torch.bool)
    # Inactive rows (label == -1) are NEVER converted to bin intervals: they
    # must not influence the calibration objective and must not trigger
    # invalid bin access (``contract.bin_start(-1)``).  ``hazard_interval_nll``
    # skips inactive rows entirely; the conversion below only touches active
    # rows.
    lower = torch.full((logits.shape[0],), -1.0, dtype=torch.float32)
    upper = torch.full((logits.shape[0],), -1.0, dtype=torch.float32)
    for index in active.nonzero(as_tuple=False).reshape(-1).tolist():
        bin_index = int(labels[index])
        if bin_index < 0:
            raise ContractError("M1_HAZARD_ACTIVE_LABEL_INVALID")
        lower[index] = contract.bin_start(bin_index)
        upper[index] = contract.bin_end(bin_index)
    log_temperature = torch.zeros((), requires_grad=True)
    optimizer = torch.optim.LBFGS([log_temperature], max_iter=int(steps))

    def closure():
        optimizer.zero_grad()
        temperature = log_temperature.exp().clamp(0.05, 20.0)
        loss = hazard_interval_nll(
            logits / temperature,
            contract,
            lower=lower,
            upper=upper,
            active=active,
        )
        loss.backward()
        return loss

    if bool(active.any()):
        optimizer.step(closure)
    return float(log_temperature.exp().detach().clamp(0.05, 20.0))


def fit_zero_mass_temperature(
    logits: torch.Tensor,
    labels: torch.Tensor,
    active: torch.Tensor,
    *,
    steps: int = 50,
    split: str = "calibration",
) -> float:
    """Calibrate hurdle zero-mass logits by binary CE on the calibration split."""
    require_calibration_split(split)
    logits = torch.as_tensor(logits, dtype=torch.float32).reshape(-1)
    labels = torch.as_tensor(labels, dtype=torch.float32).reshape(-1)
    active = torch.as_tensor(active, dtype=torch.bool).reshape(-1)
    log_temperature = torch.zeros((), requires_grad=True)
    optimizer = torch.optim.LBFGS([log_temperature], max_iter=int(steps))

    def closure():
        optimizer.zero_grad()
        temperature = log_temperature.exp().clamp(0.05, 20.0)
        loss = torch.nn.functional.binary_cross_entropy_with_logits(
            logits[active] / temperature, labels[active]
        )
        loss.backward()
        return loss

    if bool(active.any()):
        optimizer.step(closure)
    return float(log_temperature.exp().detach().clamp(0.05, 20.0))


def quantile_coverage_diagnostic(
    predicted_quantiles: torch.Tensor,
    actual: torch.Tensor,
    levels: tuple[float, ...],
    active: torch.Tensor,
    *,
    split: str = "calibration",
) -> dict[str, float | None]:
    """Calibration-split coverage diagnostic for raw positive quantiles.

    Diagnostic only: the policy stays ``QUANTILE_CALIBRATION_NOT_APPLIED``
    until the manuscript freezes a positive-quantile calibration method.
    """
    require_calibration_split(split)
    predicted = torch.as_tensor(predicted_quantiles, dtype=torch.float32)
    actual = torch.as_tensor(actual, dtype=torch.float32).reshape(-1)
    active = torch.as_tensor(active, dtype=torch.bool).reshape(-1)
    coverage: dict[str, float | None] = {}
    for level_index, level in enumerate(levels):
        if not bool(active.any()):
            coverage[str(level)] = None
            continue
        covered = actual[active] <= predicted[active, level_index]
        coverage[str(level)] = float(covered.float().mean())
    return coverage
