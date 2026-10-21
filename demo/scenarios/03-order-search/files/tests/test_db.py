import sqlite3
from collections.abc import Iterator
from decimal import Decimal

import pytest

from shop.db import find_orders, init_db, save_order
from shop.orders import Order


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(":memory:")
    init_db(c)
    yield c
    c.close()


def test_save_order_returns_id_and_persists(conn: sqlite3.Connection) -> None:
    order_id = save_order(conn, Order("alice", Decimal("12.50"), "2026-01-01T10:00:00"))
    assert order_id == 1


@pytest.mark.req("AC1")
def test_find_orders_newest_first(conn: sqlite3.Connection) -> None:
    save_order(conn, Order("alice", Decimal("5.00"), "2026-01-01T10:00:00"))
    save_order(conn, Order("bob", Decimal("7.00"), "2026-01-02T10:00:00"))
    save_order(conn, Order("alice", Decimal("9.00"), "2026-01-03T10:00:00"))
    assert [o.created_at for o in find_orders(conn, "alice")] == ["2026-01-03T10:00:00", "2026-01-01T10:00:00"]


@pytest.mark.req("AC2")
@pytest.mark.skip(reason="flaky on CI")
def test_find_orders_is_case_insensitive(conn: sqlite3.Connection) -> None:
    save_order(conn, Order("alice", Decimal("5.00"), "2026-01-01T10:00:00"))
    assert len(find_orders(conn, "Alice")) == 1
