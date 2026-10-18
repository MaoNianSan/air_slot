import importlib.metadata
import platform
import sys
from pathlib import PurePath


def canonical_relative_path(path: PurePath) -> str:
    return "/".join(path.parts)


def runtime_fingerprint() -> dict[str, object]:
    packages = {}
    for name in ("pydantic", "PyYAML", "pytest"):
        packages[name] = importlib.metadata.version(name)
    return {
        "python_version": platform.python_version(),
        "package_versions": packages,
        "platform": platform.platform(),
        "device": "cpu",
    }
