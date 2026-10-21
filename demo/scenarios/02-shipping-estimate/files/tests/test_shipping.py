from decimal import Decimal

import pytest

from shop.shipping import shipping_cost


@pytest.mark.req("AC1")
@pytest.mark.parametrize("total", [Decimal("50.00"), Decimal("120.00")])
def test_free_shipping_from_fifty(total: Decimal) -> None:
    assert shipping_cost(total, items=3) == Decimal("0.00")


@pytest.mark.req("AC2")
@pytest.mark.parametrize(("items", "expected"), [(0, Decimal("4.99")), (1, Decimal("4.99")), (3, Decimal("5.99"))])
def test_standard_fee_per_item(items: int, expected: Decimal) -> None:
    assert shipping_cost(Decimal("49.99"), items=items) == expected
