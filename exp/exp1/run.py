"""Exp1 entrypoint placeholder for a future authorized materialized run."""

from __future__ import annotations

from .protocol import Exp1Protocol
from .formal import run


def validate_fast_contract(*, hidden_size: int = 16) -> None:
    """Validate frozen protocol constants without reading raw data or running models."""
    protocol = Exp1Protocol(primary_hidden_size=hidden_size)
    protocol.validate()


if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("contract", "fast", "development"), required=True)
    args = parser.parse_args()
    if args.mode == "contract":
        validate_fast_contract()
        print(json.dumps({"status": "PASS", "experiment_id": "EXP1", "final_test_access_count": 0, "paper_result": False}))
    else:
        print(json.dumps(run(args.mode), indent=2))
