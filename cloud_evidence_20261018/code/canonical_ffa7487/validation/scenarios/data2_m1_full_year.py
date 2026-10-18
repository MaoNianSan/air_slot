"""Retired mixed-ownership full-year scenario helpers."""

from validation.legacy import deprecated_main


def main() -> None:
    deprecated_main(
        "validation.scenarios.data2_m1_full_year",
        "model.PRE.development",
    )


if __name__ == "__main__":
    main()
