import inspect
from model.PRE.adapters.base import DatasetAdapter


def test_adapter_protocol_declares_required_methods():
    assert {"describe", "capabilities", "validate_source", "iter_canonical"} <= set(DatasetAdapter.__dict__)
    assert list(inspect.signature(DatasetAdapter.iter_canonical).parameters) == ["self", "request"]
