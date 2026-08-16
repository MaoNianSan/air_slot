import pytest
from pydantic import ValidationError
from model.M1.contracts import TargetBinContract, TargetLabel

def test_bins_include_overflow_and_require_explicit_maximum():
    bins = TargetBinContract(target_name="R_IB", bin_width_minutes=5, max_finite_minutes=20)
    assert bins.class_count == 6 and bins.encode(24) == 4 and bins.encode(25) == 5
    with pytest.raises(ValidationError): TargetBinContract(target_name="R_IB", bin_width_minutes=5)

def test_interval_label_preserves_bounds():
    label = TargetLabel(target_name="R_IB", lower_minutes=7, upper_minutes=13, active=True)
    assert label.lower_minutes == 7 and label.exact_minutes is None
