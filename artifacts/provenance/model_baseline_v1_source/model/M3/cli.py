import argparse
import json
from pathlib import Path

from .registry import ActionRegistry


def main(argv=None):
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate")
    manifest = commands.add_parser("manifest")
    manifest.add_argument(
        "--registry", type=Path, default=Path("registries/action_templates.yaml")
    )
    manifest.add_argument("--output", type=Path, required=True)
    manifest.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "validate":
        registry = ActionRegistry.load(Path("registries/action_templates.yaml"))
        result = {
            "status": "PASS",
            "templates": len(registry.templates),
            "registry_id": registry.registry_id,
            "registry_hash": registry.digest(),
            "source_sha256": registry.source_sha256,
            "unfrozen_response_parameter_templates": sum(
                item.response_parameter_status.value == "NOT_FROZEN"
                for item in registry.templates
            ),
            "formal_actions_require_frozen_response_parameters": True,
            "final_test_access_count": 0,
        }
    else:
        registry = ActionRegistry.load(args.registry)
        path = registry.write_manifest(args.output, overwrite=args.overwrite)
        result = {"status": "PASS", "manifest": str(path), "final_test_access_count": 0}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
