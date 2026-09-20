import pytest

from model.M4.common_support import support_flags


@pytest.mark.parametrize(
    ("mass", "primary", "sensitivity", "full"),
    [
        (0.90, True, True, False),
        (0.90 - 5e-10, True, True, False),
        (0.90 - 1e-7, False, True, False),
        (0.50, False, True, False),
        (1.00, True, True, True),
        (0.0, False, False, False),
    ],
)
def test_frozen_common_support_flags(mass, primary, sensitivity, full):
    assert support_flags(mass) == (primary, sensitivity, full)
