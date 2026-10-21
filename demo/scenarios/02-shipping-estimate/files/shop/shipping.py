"""Shipping cost estimate."""

from decimal import Decimal

FREE_SHIPPING_FROM = Decimal("50.00")
BASE_FEE = Decimal("4.99")
PER_EXTRA_ITEM = Decimal("0.50")


def shipping_cost(total: Decimal, items: int, express: bool = False) -> Decimal:
    """Standard or express shipping for an order."""
    if total >= FREE_SHIPPING_FROM:
        return Decimal("0.00")
    fee = BASE_FEE + PER_EXTRA_ITEM * max(items - 1, 0)
    if express:
        fee = fee * 2
    return fee
