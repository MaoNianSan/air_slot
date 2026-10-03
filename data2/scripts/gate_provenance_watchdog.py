# -*- coding: utf-8 -*-
"""Watchdog: record M5-b gate provenance as gates complete (read-mostly).

Polls the AUTORUN state file and, for every gate whose declared outputs are all
present and not yet recorded with the same content signature, appends one
record via record_gate_provenance.record().  It never writes the state file,
never touches gate artifacts, and never interferes with the running wrapper.

    python data2/scripts/gate_provenance_watchdog.py [--interval 60]
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "data2" / "scripts"))

import record_gate_provenance as recorder  # noqa: E402

TERMINAL_PREFIXES = ("BLOCKED_", "FAIL_", "N_GRID_", "BLOCK_M5B")


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def state_status() -> tuple[str, str]:
    if not recorder.STATE_FILE.is_file():
        return "UNKNOWN", "UNKNOWN"
    import json
    payload = json.loads(recorder.STATE_FILE.read_text(encoding="utf-8"))
    return str(payload.get("status")), str(payload.get("current_state"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--max-hours", type=float, default=30.0)
    args = parser.parse_args()
    deadline = time.time() + args.max_hours * 3600.0
    print(f"[{stamp()}] watchdog start (interval={args.interval}s)")
    while time.time() < deadline:
        status, current = state_status()
        for gate in recorder.GATES:
            try:
                recorder.record(gate)
            except Exception as error:
                print(f"[{stamp()}] record {gate} failed: {error!r}")
        if status.startswith(TERMINAL_PREFIXES):
            print(f"[{stamp()}] terminal status {status}; final sweep")
            for gate in recorder.GATES:
                try:
                    recorder.record(gate, force=True)
                except Exception:
                    pass
            return 0
        if status == "M5B_PILOT_COMPLETE_HARD_STOP":
            print(f"[{stamp()}] pilot complete; final sweep")
            for gate in recorder.GATES:
                try:
                    recorder.record(gate, force=True)
                except Exception:
                    pass
            return 0
        time.sleep(max(15, args.interval))
    print(f"[{stamp()}] watchdog deadline reached")
    return 0


if __name__ == "__main__":
    sys.exit(main())
