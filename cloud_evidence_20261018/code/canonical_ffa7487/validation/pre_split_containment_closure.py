from __future__ import annotations

import argparse
import json
from pathlib import Path

from model.PRE.streaming.containment import audit_v5_split_containment


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Audit and close V5 episode split containment"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "artifacts/diagnostics/v5_development_freeze/PRE_SPLIT_CONTAINMENT_AUDIT.json"
        ),
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    result = audit_v5_split_containment(root)
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
