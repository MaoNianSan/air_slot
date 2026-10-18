from model.PRE.adapters.data1 import Data1Adapter
from model.PRE.adapters.data2 import Data2Adapter
from model.PRE.adapters.validation import validate_adapter_interface


def test_adapter_interfaces_load_together_but_remain_independent():
    data1, data2 = Data1Adapter(), Data2Adapter()
    all_families = set(data1.describe().source_families) | set(data2.describe().source_families)
    one = validate_adapter_interface(data1, all_families)
    two = validate_adapter_interface(data2, all_families)
    assert one["dataset_instance_id"] != two["dataset_instance_id"]
    assert set(one["source_families"]).isdisjoint(two["source_families"])
    assert data1.describe().cross_dataset_overlay is data2.describe().cross_dataset_overlay is False
