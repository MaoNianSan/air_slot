"""CU scaling adapter over the active frozen registry."""

from .registry import FrozenData2CUNormalizationRegistry


def scale_native_quantity(registry: FrozenData2CUNormalizationRegistry, quantity):
    """Scale a typed native quantity without changing support semantics."""
    return registry.value(quantity)


__all__ = ["scale_native_quantity"]
