import argparse
import json
from pathlib import Path

from model.common.serialization import canonical_json_bytes
from model.common.paths import PROJECT_ROOT
from .foundation import run_foundation
from .reporting import exit_code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Air Slot foundation validation")
    parser.add_argument("command", choices=("contracts", "adapters", "pre", "all"))
    parser.add_argument("--fixtures-only", action="store_true")
    parser.add_argument(
        "--materialize",
        action="store_true",
        help="persist validation outputs under outputs/; default is read-only/in-memory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command in {"adapters", "pre", "all"} and not args.fixtures_only:
        _parser().error("--fixtures-only is required for this command")
    root = PROJECT_ROOT
    run, fixture = run_foundation(args.command, root)
    if args.materialize and fixture is not None:
        fixture_path = (
            root
            / "outputs"
            / "formal"
            / "foundation_fixture"
            / "foundation-data1"
            / "pre_state.json"
        )
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        fixture_path.write_bytes(canonical_json_bytes(fixture) + b"\n")
    if args.materialize and args.command == "all":
        output = (
            root
            / "outputs"
            / "runtime"
            / "foundation_validation"
            / "validation_result.json"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(run.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(run.model_dump(mode="json"), sort_keys=True))
    return exit_code(run)


if __name__ == "__main__":
    raise SystemExit(main())
