from pathlib import Path
import pytest
from model.common.errors import ContractError
from model.PRE.cache.manifest import CacheManifest, PartitionIdentity
from model.PRE.cache.resume import validate_resume
from model.PRE.canonical.storage import write_canonical_partition
from datetime import datetime, timezone


def test_resume_requires_exact_identity(tmp_path: Path):
    part = PartitionIdentity(relative_path="x.parquet", row_count=1, content_hash="sha256:a", schema_hash="sha256:b")
    manifest = CacheManifest(run_id="r", dataset_instance_id="data1_2019", source_family="iem_metar",
        registry_hash="sha256:r", config_hash="sha256:c", source_fingerprints=("sha256:s",), partitions=(part,))
    assert validate_resume(manifest, registry_hash="sha256:r", config_hash="sha256:c")
    with pytest.raises(ContractError): validate_resume(manifest, registry_hash="sha256:x", config_hash="sha256:c")


def test_storage_normalizes_nested_datetimes(tmp_path: Path):
    record = {"canonical_object_type":"FlightRecord", "source_fingerprint":"sha256:s",
              "realized_outcome":{"DepTime":datetime(2019, 1, 1, tzinfo=timezone.utc)}}
    manifest = write_canonical_partition([record], output_root=tmp_path,
        dataset_instance_id="data2_2019", source_family="bts_ontime",
        registry_hash="sha256:r", config_hash="sha256:c")
    assert manifest.partitions[0].row_count == 1
