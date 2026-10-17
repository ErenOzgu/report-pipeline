"""One place that turns numbers into text, so the report, the facts file and the checker agree."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

NUMBER = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?")


def round_half_up(x: float, decimals: int) -> Decimal:
    q = Decimal(1).scaleb(-decimals)
    return Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP)


def number(x: float, decimals: int = 0) -> str:
    """1234.5 -> '1,234.5'. Rounded half up, never '-0'."""
    d = round_half_up(x, decimals)
    if d == 0:
        d = abs(d)
    return f"{d:,.{decimals}f}"


def value(x: float | None, decimals: int = 0, unit: str = "") -> str:
    if x is None:
        return "n/a"
    s = number(x, decimals)
    if unit == "%":
        return s + "%"
    return f"{s} {unit}" if unit else s


def signed(x: float, decimals: int = 0, unit: str = "") -> str:
    d = round_half_up(x, decimals)
    sign = "+" if d > 0 else ("-" if d < 0 else "")
    s = number(abs(x), decimals)
    if unit == "%":
        return f"{sign}{s}%"
    return f"{sign}{s} {unit}" if unit else f"{sign}{s}"


def normalise(token: str) -> Decimal:
    """'1,234.50' -> Decimal('1234.5'): the form in which numbers are compared."""
    return Decimal(token.replace(",", "")).normalize()


def numbers_in(text: str) -> list[str]:
    return [m.group(0) for m in NUMBER.finditer(text)]
