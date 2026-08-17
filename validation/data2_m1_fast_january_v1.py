"""Deprecated mixed-ownership January Data2 M1 entry point."""

from validation.legacy import deprecated_main


def main() -> None:
    deprecated_main(
        "validation.data2_m1_fast_january_v1",
        "validation.performance_closure_p0",
    )


if __name__ == "__main__":
    main()
