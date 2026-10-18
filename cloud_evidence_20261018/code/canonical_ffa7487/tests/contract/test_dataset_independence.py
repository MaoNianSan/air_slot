import pytest
from pydantic import ValidationError
from model.PRE.adapters.base import AdapterDescription


def test_pooled_identity_and_implicit_overlay_are_rejected():
    with pytest.raises(ValidationError):
        AdapterDescription(dataset_instance_id="data1+data2", source_families=("x",), cross_dataset_overlay=False)
    with pytest.raises(ValidationError):
        AdapterDescription(dataset_instance_id="data1_2019", source_families=("x",), cross_dataset_overlay=True)
