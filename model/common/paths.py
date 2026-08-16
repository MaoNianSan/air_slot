"""Project-relative runtime path resolution."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_path(*parts: str) -> Path:
    """Resolve a path from the configured Air Slot project root."""
    return PROJECT_ROOT.joinpath(*parts)


def data_root(dataset_instance_id: str) -> Path:
    """Return the read-only raw-data root for a registered dataset instance."""
    roots = {"data1_2019": "data1", "data2_2019": "data2"}
    try:
        return project_path(roots[dataset_instance_id])
    except KeyError as exc:
        raise ValueError(f"unknown dataset instance: {dataset_instance_id}") from exc
