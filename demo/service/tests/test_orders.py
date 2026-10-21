from decimal import Decimal

import pytest

from shop.catalog import Catalog, Product
from shop.errors import OutOfStock, UnknownProduct
from shop.orders import order_total


@pytest.fixture
def catalog() -> Catalog:
    return Catalog([Product("MUG", "Mug", Decimal("8.50")), Product("TEE", "T-shirt", Decimal("19.99"))],
                   {"MUG": 5, "TEE": 1})


def test_order_total_sums_lines(catalog: Catalog) -> None:
    assert order_total(catalog, {"MUG": 2, "TEE": 1}) == Decimal("36.99")


def test_unknown_product(catalog: Catalog) -> None:
    with pytest.raises(UnknownProduct):
        order_total(catalog, {"HAT": 1})


def test_reserve_checks_stock(catalog: Catalog) -> None:
    catalog.reserve("TEE", 1)
    with pytest.raises(OutOfStock):
        catalog.reserve("TEE", 1)
