# Add percentage discount codes

Closes #1

Adds `shop/discounts.py` with `apply_discount()` and an `InvalidDiscountCode` error. Codes are normalised
(case and whitespace), and the result is rounded half-up to cents and floored at zero.

Tests are tagged with the acceptance criteria they prove.

_Generated with a coding agent._
