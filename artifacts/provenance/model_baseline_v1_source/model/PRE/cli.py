import argparse
import json
from pathlib import Path
import pyarrow.parquet as pq

from model.common.errors import AirSlotError, ContractError
from model.common.paths import data_root, project_path
from model.PRE.adapters.data1 import Data1Adapter
from model.PRE.adapters.data2 import Data2Adapter
from model.PRE.adapters.readers import source_files
from model.PRE.adapters.registry import RawReadRequest, SourceAdapterRegistry
from model.PRE.canonical.storage import write_canonical_partition
from model.PRE.episode.builder import build_episode_records


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Air Slot production PRE")
    commands = value.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect-source")
    canonical = commands.add_parser("canonicalize")
    for item in (inspect, canonical):
        item.add_argument("--dataset", required=True)
        item.add_argument("--source", required=True)
        item.add_argument("--raw-root", type=Path)
        item.add_argument("--year", type=int, default=2019)
        item.add_argument("--month", type=int)
        item.add_argument("--max-rows", type=int, default=32)
        item.add_argument("--max-files", type=int, default=1)
    canonical.add_argument(
        "--output-root",
        type=Path,
        default=project_path("outputs", "runtime", "canonical"),
    )
    canonical.add_argument("--replay-lag-minutes", type=int, default=0)
    episodes = commands.add_parser("build-episodes")
    episodes.add_argument("--dataset", required=True)
    episodes.add_argument("--canonical-root", type=Path, required=True)
    episodes.add_argument("--max-episodes", type=int, default=32)
    publish = commands.add_parser("publish")
    publish.add_argument("--dataset", required=True)
    publish.add_argument("--canonical-root", type=Path, required=True)
    publish.add_argument("--max-episodes", type=int, default=32)
    smoke = commands.add_parser("smoke-real")
    smoke.add_argument("--data1-root", type=Path, default=data_root("data1_2019"))
    smoke.add_argument("--data2-root", type=Path, default=data_root("data2_2019"))
    smoke.add_argument("--max-rows", type=int, default=32)
    return value


def _request(args, output: Path) -> RawReadRequest:
    return RawReadRequest(
        dataset_instance_id=args.dataset,
        source_family=args.source,
        raw_root=args.raw_root or data_root(args.dataset),
        output_root=output,
        year=args.year,
        month=args.month,
        max_rows=args.max_rows,
        max_files=args.max_files,
    )


def _adapter(dataset: str):
    if dataset == "data1_2019":
        return Data1Adapter()
    if dataset == "data2_2019":
        return Data2Adapter()
    raise ContractError("UNKNOWN_DATASET_INSTANCE")


def execute(args) -> dict:
    registry = SourceAdapterRegistry.load(
        project_path("registries", "source_adapter_registry.yaml")
    )
    if args.command == "inspect-source":
        request = _request(args, project_path("outputs", "runtime", "inspect"))
        definition = registry.get(args.dataset, args.source)
        files = source_files(request, definition)
        return {
            "status": "PASS",
            "dataset": args.dataset,
            "source": args.source,
            "matched_files": len(files),
            "sample_paths": [
                p.relative_to(request.raw_root).as_posix() for p in files[:3]
            ],
        }
    if args.command == "canonicalize":
        request = _request(args, args.output_root)
        kwargs = (
            {"replay_lag_minutes": args.replay_lag_minutes}
            if args.dataset == "data1_2019"
            else {}
        )
        records = list(_adapter(args.dataset).iter_canonical(request, **kwargs))
        manifest = write_canonical_partition(
            records,
            output_root=args.output_root,
            dataset_instance_id=args.dataset,
            source_family=args.source,
            registry_hash="source-adapter-registry:1.0.0",
            config_hash=f"replay-lag:{args.replay_lag_minutes}",
        )
        return {"status": "PASS", "row_count": len(records), "run_id": manifest.run_id}
    if args.command == "build-episodes":
        paths = sorted(args.canonical_root.rglob("*.parquet"))
        flights = []
        for path in paths:
            for row in pq.read_table(path).to_pylist():
                if row.get("canonical_object_type") == "FlightRecord":
                    flights.append(row)
        episodes = build_episode_records(flights)[: args.max_episodes]
        return {
            "status": "PASS",
            "episode_count": len(episodes),
            "episode_ids": [x.episode_id for x in episodes],
        }
    if args.command == "publish":
        # Production publication is episode/node-specific; this entry validates canonical availability.
        paths = sorted(args.canonical_root.rglob("*.parquet"))
        return {
            "status": "PASS" if paths else "BLOCKED",
            "canonical_partitions": len(paths),
            "reason_code": None if paths else "NO_CANONICAL_PARTITIONS",
        }
    if args.command == "smoke-real":
        out = project_path("outputs", "runtime", "production_pre", "smoke")
        d1 = RawReadRequest(
            dataset_instance_id="data1_2019",
            source_family="iem_metar",
            raw_root=args.data1_root,
            output_root=out,
            year=2019,
            max_rows=args.max_rows,
            max_files=1,
        )
        d2 = RawReadRequest(
            dataset_instance_id="data2_2019",
            source_family="bts_ontime",
            raw_root=args.data2_root,
            output_root=out,
            year=2019,
            month=1,
            max_rows=args.max_rows,
            max_files=1,
        )
        rows1 = list(Data1Adapter().iter_canonical(d1, replay_lag_minutes=5))
        rows2 = list(Data2Adapter().iter_canonical(d2))
        return {
            "status": "PASS",
            "data1_rows": len(rows1),
            "data2_rows": len(rows2),
            "limitations": ["REPLAY_LAG_DEVELOPMENT_VALUE", "BOUNDED_SMOKE_ONLY"],
        }
    raise ContractError("UNKNOWN_COMMAND")


def main(argv=None) -> int:
    try:
        result = execute(parser().parse_args(argv))
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    except (AirSlotError, ValueError, OSError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
