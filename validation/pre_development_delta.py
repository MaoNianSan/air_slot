from __future__ import annotations

import json
from pathlib import Path

from model.PRE.streaming.development_delta import build_development_delta_manifest


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    base = root / "artifacts" / "diagnostics" / "v5_development_freeze"
    manifest = build_development_delta_manifest(
        root=root,
        old_manifest_path=base / "PRE_DEVELOPMENT_STREAM_MANIFEST.json",
        audit_path=base / "PRE_SPLIT_CONTAINMENT_AUDIT.json",
        output_path=base / "PRE_DEVELOPMENT_STREAM_MANIFEST_V2.json",
    )
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
