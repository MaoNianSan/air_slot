from model.common.value_objects import FrozenModel


class PartitionIdentity(FrozenModel):
    relative_path: str
    row_count: int
    content_hash: str
    schema_hash: str


class CacheManifest(FrozenModel):
    manifest_version: str = "1.0.0"
    run_id: str
    dataset_instance_id: str
    source_family: str
    registry_hash: str
    config_hash: str
    source_fingerprints: tuple[str, ...]
    partitions: tuple[PartitionIdentity, ...]
    state: str = "COMMITTED"
