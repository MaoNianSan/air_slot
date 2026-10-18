def fahrenheit_to_celsius(value: float) -> float:
    return (value - 32.0) * 5.0 / 9.0


def knots_to_mps(value: float) -> float:
    return value * 0.514444


def statute_miles_to_m(value: float) -> float:
    return value * 1609.344


def hundreds_feet_to_m(value: float) -> float:
    return value * 100.0 * 0.3048
