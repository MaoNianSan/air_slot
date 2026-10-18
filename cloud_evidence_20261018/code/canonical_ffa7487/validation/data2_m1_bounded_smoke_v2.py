"""Deprecated mixed-ownership Data2 M1 smoke entry point."""

from pathlib import Path

from validation.legacy import deprecated_main

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    deprecated_main(
        "validation.data2_m1_bounded_smoke_v2",
        "validation.performance_closure_p0",
    )


if __name__ == "__main__":
    main()
