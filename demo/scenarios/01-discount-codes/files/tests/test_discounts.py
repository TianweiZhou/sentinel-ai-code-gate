from decimal import Decimal

import pytest

from shop.discounts import apply_discount
from shop.errors import InvalidDiscountCode


@pytest.mark.req("AC1")
@pytest.mark.parametrize(
    ("code", "expected"),
    [("SAVE10", Decimal("90.00")), ("SAVE25", Decimal("75.00")), (" save10 ", Decimal("90.00"))],
)
def test_applies_percentage_for_known_codes(code: str, expected: Decimal) -> None:
    assert apply_discount(Decimal("100.00"), code) == expected


@pytest.mark.req("AC2")
@pytest.mark.parametrize("code", ["", "SAVE100", "FREE"])
def test_unknown_codes_are_rejected(code: str) -> None:
    with pytest.raises(InvalidDiscountCode):
        apply_discount(Decimal("10.00"), code)


@pytest.mark.req("AC3")
def test_rounds_half_up_to_cents() -> None:
    assert apply_discount(Decimal("0.05"), "SAVE10") == Decimal("0.05")  # 0.045 -> 0.05 (half-up)
    assert apply_discount(Decimal("19.99"), "SAVE25") == Decimal("14.99")  # 14.9925
    assert apply_discount(Decimal("0.50"), "SAVE10") == Decimal("0.45")


@pytest.mark.req("AC3")
def test_never_negative() -> None:
    assert apply_discount(Decimal("-5.00"), "SAVE10") == Decimal("0.00")
