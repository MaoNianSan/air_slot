from pathlib import Path

import pytest

from model.PRE.adapters.data1 import Data1Adapter
from model.PRE.adapters.data2 import Data2Adapter
from model.PRE.adapters.registry import RawReadRequest
from model.common.paths import data_root

DATA1=data_root("data1_2019")
DATA2=data_root("data2_2019")


@pytest.mark.parametrize("source",["eurostat","ourairports"])
def test_data1_registered_reference_sources_have_bounded_reader(source,tmp_path):
    if not DATA1.exists(): pytest.skip("configured data1 root unavailable")
    request=RawReadRequest(dataset_instance_id="data1_2019",source_family=source,raw_root=DATA1,
        output_root=tmp_path,year=2019,max_rows=1,max_files=1)
    rows=list(Data1Adapter().iter_canonical(request))
    assert len(rows)==1 and rows[0].canonical_object_type in {"AggregateReference","AirportReference"}


def test_data2_timezone_reference_has_bounded_reader(tmp_path):
    if not DATA2.exists(): pytest.skip("configured data2 root unavailable")
    request=RawReadRequest(dataset_instance_id="data2_2019",source_family="timezone_reference",raw_root=DATA2,
        output_root=tmp_path,year=2019,max_rows=1,max_files=1)
    rows=list(Data2Adapter().iter_canonical(request))
    assert len(rows)==1 and rows[0].timezone
