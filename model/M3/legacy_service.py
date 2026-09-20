"""Public M3 service boundary."""

from __future__ import annotations

from .action_response import build_a00_identity_envelope, build_conditional_scenario_envelope
from .instantiation_layer.builder import instantiate_action_records
from .readiness import build_action_numerical_readiness


class M3Service:
    """Coordinate action registry, factual state, instantiation, and response envelopes."""

    def instantiate(self, pre_state, registry, *, response_registry=None, sensitivity="BASE"):
        return instantiate_action_records(
            pre_state,
            registry,
            response_registry=response_registry,
            sensitivity=sensitivity,
        )

    def numerical_readiness(self, registry, *, response_registry=None):
        return build_action_numerical_readiness(
            registry,
            response_registry=response_registry,
        )

    def build_a00(self, baselines, *, eligibility, response_rule):
        return build_a00_identity_envelope(
            tuple(baselines), eligibility=eligibility, response_rule=response_rule
        )

    def build_conditional(self, baselines, *, eligibility, response_rule, **kwargs):
        return build_conditional_scenario_envelope(
            tuple(baselines), eligibility=eligibility, response_rule=response_rule, **kwargs
        )


__all__ = ["M3Service"]

