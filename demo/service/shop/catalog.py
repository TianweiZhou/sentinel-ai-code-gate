"""Products and stock."""

from dataclasses import dataclass
from decimal import Decimal

from shop.errors import OutOfStock, UnknownProduct


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price: Decimal


class Catalog:
    def __init__(self, products: list[Product], stock: dict[str, int]) -> None:
        self._products = {p.sku: p for p in products}
        self._stock = dict(stock)

    def get(self, sku: str) -> Product:
        try:
            return self._products[sku]
        except KeyError:
            raise UnknownProduct(sku) from None

    def reserve(self, sku: str, quantity: int) -> None:
        available = self._stock.get(sku, 0)
        if quantity > available:
            raise OutOfStock(f"{sku}: wanted {quantity}, have {available}")
        self._stock[sku] = available - quantity
