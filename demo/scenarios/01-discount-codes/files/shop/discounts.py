"""Percentage discount codes."""

from decimal import ROUND_HALF_UP, Decimal

from shop.errors import InvalidDiscountCode

DISCOUNTS: dict[str, Decimal] = {"SAVE10": Decimal("0.10"), "SAVE25": Decimal("0.25")}
CENT = Decimal("0.01")


def apply_discount(total: Decimal, code: str) -> Decimal:
    """Returns `total` reduced by the code's percentage, rounded half-up to cents, never below zero."""
    rate = DISCOUNTS.get(code.strip().upper())
    if rate is None:
        raise InvalidDiscountCode(code)
    discounted = total * (1 - rate)
    return max(discounted, Decimal(0)).quantize(CENT, rounding=ROUND_HALF_UP)
