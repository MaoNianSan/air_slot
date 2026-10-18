from dataclasses import dataclass
from pathlib import Path

from .loader import RegistryBundle, load_registry_bundle


@dataclass(frozen=True)
class LineageChain:
    rule_id: str
    source_family: str
    canonical_variable: str
    consumers: tuple[str, ...]


class RegistryInspector:
    """Read-only registry inspection; it never opens a raw-data root."""

    def __init__(self, bundle: RegistryBundle):
        self._bundle = bundle

    @classmethod
    def from_path(cls, path: Path) -> "RegistryInspector":
        return cls(load_registry_bundle(path))

    def chains(self, *, dataset_id: str | None = None) -> tuple[LineageChain, ...]:
        rules = self._bundle.data_usage_rules
        if dataset_id is not None:
            rules = tuple(rule for rule in rules if rule.dataset_id == dataset_id)
        return tuple(LineageChain(
            rule_id=rule.rule_id,
            source_family=rule.logical_source,
            canonical_variable=rule.canonical_variable,
            consumers=rule.downstream_consumers,
        ) for rule in rules)
