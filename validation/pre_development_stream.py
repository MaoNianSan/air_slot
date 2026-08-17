from __future__ import annotations

import argparse
import json
from pathlib import Path

from model.common.config import load_config_layers
from model.PRE.streaming.development import run_development_pre_stream


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Verify the PRE-owned Development stream")
    parser.add_argument("--max-episodes", type=int)
    parser.add_argument("--heartbeat-seconds", type=float, default=45.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    official = root / "artifacts" / "diagnostics" / "v5_development_freeze"
    output = args.output or official / "PRE_DEVELOPMENT_STREAM_MANIFEST.json"
    if not output.is_absolute():
        output = root / output
    resume = output.with_name(output.stem + "_RESUME.pt")
    scientific = load_config_layers(root / "configs").scientific
    manifest = run_development_pre_stream(
        scientific,
        root=root,
        manifest_path=output,
        resume_path=resume,
        heartbeat_seconds=args.heartbeat_seconds,
        max_episodes=args.max_episodes,
    )
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
