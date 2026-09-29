from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def cents(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def aud(value: Decimal | int | float) -> str:
    """$12,345.60 — the format AP staff read all day."""
    v = cents(value)
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.2f}"


def price(value: Decimal) -> str:
    """Unit prices keep a third decimal when they have one ($1.425/L)."""
    v = Decimal(value)
    if v == v.quantize(CENT):
        return f"${v:,.2f}"
    return f"${v.normalize():,}"


def qty(value: Decimal) -> str:
    v = Decimal(value)
    return f"{v.normalize():,f}" if v != v.to_integral() else f"{int(v):,}"


def pct(value: Decimal) -> str:
    return f"{Decimal(value) * 100:+.1f}%"
