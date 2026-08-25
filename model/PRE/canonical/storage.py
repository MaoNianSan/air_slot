import json
from hashlib import sha256
from pathlib import Path
from typing import Any
import pyarrow as pa
import pyarrow.parquet as pq

from model.common.identity import content_id
from model.common.serialization import canonical_json_bytes
from model.PRE.cache.manifest import CacheManifest, PartitionIdentity


def _storage_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return json.dumps(
            {k: _storage_value(v) for k, v in value.items()}, sort_keys=True
        )
    if isinstance(value, (tuple, list)):
        return json.dumps([_storage_value(v) for v in value], sort_keys=True)
    return value


def write_canonical_partition(
    records: list[Any],
    *,
    output_root: Path,
    dataset_instance_id: str,
    source_family: str,
    registry_hash: str,
    config_hash: str,
) -> CacheManifest:
    if not records:
        raise ValueError("cannot write empty canonical partition")
    relative = Path(dataset_instance_id) / source_family / "part-00000.parquet"
    target = output_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    dictionaries = [
        record.model_dump(mode="python") if hasattr(record, "model_dump") else record
        for record in records
    ]
    normalized = [
        {key: _storage_value(value) for key, value in record.items()}
        for record in dictionaries
    ]
    table = pa.Table.from_pylist(normalized)
    temporary = target.with_suffix(".parquet.tmp")
    pq.write_table(table, temporary, compression="zstd")
    temporary.replace(target)
    content_hash = f"sha256:{sha256(target.read_bytes()).hexdigest()}"
    schema_hash = content_id(str(table.schema))
    sources = tuple(
        sorted(
            {
                record["source_fingerprint"]
                for record in dictionaries
                if record.get("source_fingerprint")
            }
        )
    )
    partition = PartitionIdentity(
        relative_path=relative.as_posix(),
        row_count=len(records),
        content_hash=content_hash,
        schema_hash=schema_hash,
    )
    manifest = CacheManifest(
        run_id=content_id(
            {
                "dataset": dataset_instance_id,
                "source": source_family,
                "registry": registry_hash,
                "config": config_hash,
                "sources": sources,
                "partition": partition.model_dump(),
            }
        ),
        dataset_instance_id=dataset_instance_id,
        source_family=source_family,
        registry_hash=registry_hash,
        config_hash=config_hash,
        source_fingerprints=sources,
        partitions=(partition,),
    )
    manifest_path = target.parent / "manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    return manifest
