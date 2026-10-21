"""Orders and their totals."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from shop.catalog import Catalog

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Order:
    customer: str
    total: Decimal
    created_at: str


def order_total(catalog: Catalog, lines: dict[str, int]) -> Decimal:
    """Sum of price x quantity for each SKU, rounded half-up to cents."""
    total = sum((catalog.get(sku).price * qty for sku, qty in lines.items()), Decimal(0))
    return total.quantize(CENT, rounding=ROUND_HALF_UP)
