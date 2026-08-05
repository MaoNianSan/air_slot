from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _pre_main():
    path = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location("pre_v2_main", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_exposes_only_current_commands() -> None:
    parser = _pre_main().build_parser()
    command = next(action for action in parser._actions if action.dest == "command")
    assert set(command.choices) == {
        "build",
        "validate",
        "readiness",
        "report",
        "inspect-config",
    }


@pytest.mark.parametrize(
    "retired",
    ["core-" + "build", "core-" + "validate", "legacy-" + "build"],
)
def test_retired_cli_aliases_are_unknown(retired: str) -> None:
    with pytest.raises(SystemExit):
        _pre_main().build_parser().parse_args([retired, "--mode", "fast"])
