from model.common.errors import ContractError
from .manifest import CacheManifest


def validate_resume(
    manifest: CacheManifest, *, registry_hash: str, config_hash: str
) -> bool:
    if manifest.state != "COMMITTED":
        raise ContractError("CACHE_NOT_COMMITTED")
    if manifest.registry_hash != registry_hash:
        raise ContractError("CACHE_REGISTRY_MISMATCH")
    if manifest.config_hash != config_hash:
        raise ContractError("CACHE_CONFIG_MISMATCH")
    return True
