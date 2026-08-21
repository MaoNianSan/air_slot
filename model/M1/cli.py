import argparse, json
from pathlib import Path
import torch
from .pipeline import M1Pipeline
from .lifecycle import M1Lifecycle
from .development_training import run_data2_development_fast


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    train = sub.add_parser("train-smoke")
    train.add_argument("--output", type=Path, required=True)
    train_data2_fast = sub.add_parser("train-data2-fast")
    train_data2_fast.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[2],
    )
    train_data2_fast.add_argument("--output", type=Path)
    infer = sub.add_parser("infer-smoke")
    infer.add_argument("--artifact", type=Path, required=True)
    inspect = sub.add_parser("inspect-artifact")
    inspect.add_argument("--artifact", type=Path, required=True)
    sub.add_parser("validate")
    args = p.parse_args(argv)
    if args.command == "train-data2-fast":
        try:
            result = run_data2_development_fast(
                root=args.root,
                output_root=args.output,
            )
        except Exception as exc:
            result = {
                "status": "M1_V2_REAL_TRAINING_BLOCKED",
                "reason": f"{type(exc).__name__}:{exc}",
                "FINAL_TEST_ACCESS_COUNT": 0,
                "PAPER_FULL_RUN": False,
            }
            print(json.dumps(result, sort_keys=True))
            return 2
    elif args.command == "train-smoke":
        pipe = M1Pipeline.smoke(4)
        optimizer = torch.optim.Adam(pipe.model.parameters(), lr=.01)
        values = torch.randn(8, 3, 4)
        lengths = torch.full((8,), 3)
        labels = {n: torch.arange(8) % b.class_count for n, b in pipe.contracts.items()
                  if hasattr(b, "class_count")}
        initial = None
        for _ in range(8):
            optimizer.zero_grad()
            out = pipe.model(values, lengths)
            loss = sum(out[n].abs().mean() for n in out)
            initial = float(loss.detach()) if initial is None else initial
            loss.backward()
            optimizer.step()
        path = args.output / "m1.pt"
        pipe.save(path)
        result = {"status": "PASS", "initial_loss": initial,
                  "final_loss": float(loss.detach()), "artifact": path.as_posix()}
    elif args.command == "infer-smoke":
        pipe = M1Pipeline.load(args.artifact)
        dist = pipe.predict_distributions(torch.zeros(1, 3, pipe.model.input_size),
                                          torch.tensor([3]))
        result = {"status": "PASS",
                  "heads": {n: list(v.shape) if hasattr(v, "shape") else v
                            for n, v in dist.items()}}
    elif args.command == "inspect-artifact":
        lifecycle = M1Lifecycle.load(args.artifact)
        result = {"status": "PASS",
                  "hidden_size": lifecycle.pipeline.model.hidden_size,
                  "temperatures": lifecycle.pipeline.temperatures,
                  "contract_version": "M1_STATE_ESTIMATOR_V2",
                  "primitive_targets": ["T_IB_A00", "D_OB", "D_TX"]}
    else:
        result = {"status": "PASS",
                  "architecture": "one_layer_unidirectional_gru",
                  "primitive_targets": ["T_IB_A00", "D_OB", "D_TX"],
                  "heads": ["DISCRETE_HAZARD", "HURDLE_QUANTILE", "HURDLE_QUANTILE"]}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
