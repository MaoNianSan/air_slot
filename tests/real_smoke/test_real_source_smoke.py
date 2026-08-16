from pathlib import Path
import pytest
from model.PRE.adapters.registry import RawReadRequest
from model.PRE.adapters.data1 import Data1Adapter
from model.PRE.adapters.data2 import Data2Adapter
from model.common.paths import data_root

D1 = data_root("data1_2019")
D2 = data_root("data2_2019")


@pytest.mark.skipif(not (D1.exists() and D2.exists()), reason="audited real roots not configured")
def test_bounded_real_data1_data2_read_without_raw_writes(tmp_path: Path):
    before1 = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in D1.rglob("*") if p.is_file()}
    d1 = RawReadRequest(dataset_instance_id="data1_2019", source_family="iem_metar", raw_root=D1,
        output_root=tmp_path, year=2019, max_files=1, max_rows=2)
    d2 = RawReadRequest(dataset_instance_id="data2_2019", source_family="bts_ontime", raw_root=D2,
        output_root=tmp_path, year=2019, month=1, max_files=1, max_rows=2)
    assert len(list(Data1Adapter().iter_canonical(d1, replay_lag_minutes=5))) == 2
    assert len(list(Data2Adapter().iter_canonical(d2))) == 4
    after1 = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in D1.rglob("*") if p.is_file()}
    assert before1 == after1
