# Search orders by customer

Support needs to look up a customer's orders.

## Acceptance criteria
- [ ] AC1: `find_orders(conn, customer)` returns that customer's orders, newest first.
- [ ] AC2: Customer names match case-insensitively (`Alice` finds `alice`).
- [ ] AC3: Totals in the results are `Decimal`, exactly as saved.
