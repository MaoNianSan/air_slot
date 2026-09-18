"""Phase 5 unsupported-reference handling in Development families."""

from __future__ import annotations

import math
from types import SimpleNamespace

from validation.v2_phase5.families import _node_consequence


class _ExplodingService:
    def consequence_scenario(self, *_args, **_kwargs):
        raise AssertionError("unsupported references must not call the M2 service")


def test_unsupported_reference_stays_typed_without_calling_m2():
    layer = SimpleNamespace(service=_ExplodingService(), bindings={})
    state_set = SimpleNamespace(node_id="node-unsupported")

    mass, included, expected, reasons = _node_consequence(layer, state_set)

    assert math.isnan(mass)
    assert included is False
    assert expected is None
    assert reasons == ("PHASE5_REFERENCE_UNSUPPORTED",)
