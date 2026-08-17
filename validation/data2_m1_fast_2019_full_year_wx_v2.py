"""Deprecated mixed-ownership full-year Data2 M1 entry point."""

from validation.legacy import deprecated_main


def main() -> None:
    deprecated_main(
        "validation.data2_m1_fast_2019_full_year_wx_v2",
        "model.PRE.development + model.M1 owned APIs",
    )


if __name__ == "__main__":
    main()
