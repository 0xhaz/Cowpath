"""Seed a tiny DuckDB that mirrors the showcase-ecommerce snowflake schema.

showcase-ecommerce ships *metadata*, not data — there's no warehouse to run
against. This builds a small stand-in so both the naive and the pattern-grounded
SQL actually execute, and Beat 3 shows a wrong number vs a right number.

The trap is baked into the data: `order_history.order_total` is INFLATED /
stale relative to the real line-item revenue (`unit_price * quantity`). So:
    SUM(order_total)            = 765   (naive "before" — WRONG)
    SUM(unit_price * quantity)  = 600   (proven "after" — RIGHT)
A believable data-quality drift: a denormalized total that no longer matches the
lines it was supposed to summarize.

    python -m examples.seed_duckdb   ->  examples/warehouse.duckdb
"""

from __future__ import annotations

import os

import duckdb

# File stem == catalog name, so the agent's fully-qualified refs
# `order_entry_db.analytics.order_history` resolve directly.
DB_PATH = os.environ.get("DUCKDB_PATH", "examples/order_entry_db.duckdb")

# order_id -> (status, order_total[inflated/stale], [(product, unit_price, qty, return_date)])
ORDERS = {
    1: ("SHIPPED",   250.0, [("P1", 20.0, 5, None), ("P2", 25.0, 4, None)]),          # true 200
    2: ("DELIVERED", 180.0, [("P1", 30.0, 5, "2025-01-10")]),                         # true 150, returned
    3: ("DELIVERED", 130.0, [("P3", 10.0, 10, None)]),                                # true 100
    4: ("SHIPPED",   160.0, [("P2", 40.0, 3, "2025-02-01")]),                         # true 120, returned
    5: ("CANCELLED",  45.0, [("P1", 15.0, 2, None)]),                                 # true 30
}

PROMOS = [
    (1, "Spring Sale",   1500.0),
    (2, "Clearance",      800.0),
    (3, "VIP Event",     2200.0),
]


def build(db_path: str = DB_PATH) -> None:
    if os.path.exists(db_path):
        os.remove(db_path)
    con = duckdb.connect(db_path)
    # Default catalog for a file db is the file stem (order_entry_db); create the
    # two snowflake schemas inside it so 3-part names resolve.
    con.execute("CREATE SCHEMA IF NOT EXISTS analytics")
    con.execute("CREATE SCHEMA IF NOT EXISTS order_entry")

    con.execute("""
        CREATE TABLE analytics.order_history (
            order_id INTEGER, customer_id INTEGER, order_status VARCHAR,
            order_total DOUBLE, as_of_date DATE
        )""")
    con.execute("""
        CREATE TABLE order_entry.order_items (
            order_id INTEGER, line_item_id INTEGER, product_id VARCHAR,
            unit_price DOUBLE, quantity INTEGER, return_date DATE
        )""")
    con.execute("""
        CREATE TABLE order_entry.promotions (
            promotion_id INTEGER, promotion_name VARCHAR, promotion_cost DOUBLE
        )""")

    line_id = 1
    for oid, (status, total, items) in ORDERS.items():
        con.execute(
            "INSERT INTO analytics.order_history VALUES (?, ?, ?, ?, DATE '2025-01-01')",
            [oid, 100 + oid, status, total],
        )
        for (prod, price, qty, ret) in items:
            con.execute(
                "INSERT INTO order_entry.order_items VALUES (?, ?, ?, ?, ?, ?)",
                [oid, line_id, prod, price, qty, ret],
            )
            line_id += 1
    con.executemany("INSERT INTO order_entry.promotions VALUES (?, ?, ?)", PROMOS)

    naive = con.execute("SELECT SUM(order_total) FROM analytics.order_history").fetchone()[0]
    true = con.execute("SELECT SUM(unit_price*quantity) FROM order_entry.order_items").fetchone()[0]
    con.close()
    print(f"seeded {db_path}")
    print(f"  naive SUM(order_total)           = {naive:.0f}  (the trap)")
    print(f"  true  SUM(unit_price * quantity)  = {true:.0f}  (what the pattern computes)")


if __name__ == "__main__":
    build()
