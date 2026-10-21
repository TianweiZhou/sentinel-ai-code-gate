# Support percentage discount codes

Customers should be able to enter a discount code at checkout.

## Acceptance criteria
- [ ] AC1: `apply_discount(total, code)` applies the percentage for known codes (`SAVE10` = 10%, `SAVE25` = 25%), ignoring case and surrounding spaces.
- [ ] AC2: Unknown codes raise `InvalidDiscountCode`.
- [ ] AC3: Discounted totals are rounded half-up to cents and are never negative.
