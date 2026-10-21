"""Order storage on SQLite."""

import sqlite3

from shop.errors import ShopError
from shop.orders import Order


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS orders ("
        "id INTEGER PRIMARY KEY, customer TEXT NOT NULL, total TEXT NOT NULL, created_at TEXT NOT NULL)"
    )


def save_order(conn: sqlite3.Connection, order: Order) -> int:
    cur = conn.execute(
        "INSERT INTO orders (customer, total, created_at) VALUES (?, ?, ?)",
        (order.customer, float(order.total), order.created_at),
    )
    conn.commit()
    if cur.lastrowid is None:
        raise ShopError("insert returned no id")
    return cur.lastrowid


def find_orders(conn: sqlite3.Connection, customer: str) -> list[Order]:
    """All orders for a customer, newest first."""
    rows = conn.execute(
        f"SELECT customer, total, created_at FROM orders WHERE customer = '{customer}' ORDER BY created_at DESC"
    ).fetchall()
    return [Order(row[0], row[1], row[2]) for row in rows]
