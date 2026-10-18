import pytest
from pydantic import ValidationError
from model.M1.contracts import TargetBinContract, TargetLabel

def test_bins_include_overflow_and_require_explicit_maximum():
    bins = TargetBinContract(target_name="R_IB", bin_width_minutes=5, max_finite_minutes=20)
    assert bins.class_count == 6 and bins.encode(24) == 4 and bins.encode(25) == 5
    with pytest.raises(ValidationError): TargetBinContract(target_name="R_IB", bin_width_minutes=5)


def test_signed_delta_bins_distinguish_underflow_finite_and_overflow():
    bins = TargetBinContract(target_name="DELTA_OB", bin_width_minutes=5,
                             min_finite_minutes=-20, max_finite_minutes=20, signed=True)
    assert bins.encode(-25) == bins.underflow_index
    assert bins.encode(-20) == 1
    assert bins.encode(20) == bins.overflow_index - 1
    assert bins.encode(25) == bins.overflow_index
    assert bins.representative(bins.underflow_index)[1:] == (True, False)
    assert bins.representative(bins.overflow_index)[1:] == (False, True)


def test_signed_target_label_allows_negative_exact_value_only_for_delta_ob():
    assert TargetLabel(target_name="DELTA_OB", exact_minutes=-15, active=True).exact_minutes == -15
    with pytest.raises(ValidationError):
        TargetLabel(target_name="R_IB", exact_minutes=-15, active=True)

def test_interval_label_preserves_bounds():
    label = TargetLabel(target_name="R_IB", lower_minutes=7, upper_minutes=13, active=True)
    assert label.lower_minutes == 7 and label.exact_minutes is None
