import sqlite3
from collections.abc import Iterator
from decimal import Decimal

import pytest

from shop.db import init_db, save_order
from shop.orders import Order


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(":memory:")
    init_db(c)
    yield c
    c.close()


def test_save_order_returns_id_and_persists(conn: sqlite3.Connection) -> None:
    order_id = save_order(conn, Order("alice", Decimal("12.50"), "2026-01-01T10:00:00"))
    row = conn.execute("SELECT customer, total FROM orders WHERE id = ?", (order_id,)).fetchone()
    assert order_id == 1
    assert row == ("alice", "12.50")
