"""Retired pre-freeze mixed M1-M4 chain probe."""

from validation.legacy import deprecated_main


def main() -> None:
    deprecated_main(
        "validation.data2_m1_m4_bounded_chain",
        "typed model-owned chain validation after an explicit scientific gate",
    )


if __name__ == "__main__":
    main()
