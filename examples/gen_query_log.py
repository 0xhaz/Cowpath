"""Synthesize a realistic warehouse query log (NDJSON) for showcase-ecommerce.

The sample datapacks are *metadata*, not query history — but Cowpath needs
history. This emits a newline-delimited JSON log in the shape DataHub's
`sql-queries` source expects, referencing the real snowflake tables loaded by
`datahub datapack load showcase-ecommerce` so `QuerySubjects` links to datasets
that actually exist (and the Queries tab lights up).

Tables (snowflake, instance b2fd91, db order_entry_db) — fully qualified in SQL
so the parser resolves each ref regardless of default schema:
  order_entry_db.analytics.order_history   (order_id, customer_id, order_status, order_total, as_of_date)
  order_entry_db.order_entry.order_items   (order_id, product_id, unit_price, quantity, return_date, ...)
  order_entry_db.order_entry.promotions    (promotion_id, promotion_name, promotion_cost, ...)

Frequency is expressed by repetition: the sql-queries source dedups by
normalized text and counts runs, so a query written N times reads as "run N
times" — which is exactly the frequency signal Cowpath ranks patterns by.
"""

from __future__ import annotations

import json
import sys

# Base timestamp (epoch seconds). Fixed so runs are reproducible — Date.now()
# is intentionally avoided.
BASE_TS = 1_752_000_000  # ~2025-07

OH = "order_entry_db.analytics.order_history"
OI = "order_entry_db.order_entry.order_items"
PROMO = "order_entry_db.order_entry.promotions"

# (sql, run_count) — run_count drives the frequency ranking.
QUERIES: list[tuple[str, int]] = [
    # 1. The non-obvious join: order value for orders that contain a RETURNED
    #    item. Key insight an agent must get right: join order_history to
    #    order_items on order_id, and returns live on the *line item*
    #    (return_date), not the order. Most frequent → the "proven pattern".
    (
        f"SELECT oh.order_status, AVG(oh.order_total) AS avg_order_value "
        f"FROM {OH} oh "
        f"JOIN {OI} oi ON oh.order_id = oi.order_id "
        f"WHERE oi.return_date IS NOT NULL "
        f"GROUP BY oh.order_status",
        6,
    ),
    # 2. Units sold per product.
    (
        f"SELECT product_id, SUM(quantity) AS units_sold "
        f"FROM {OI} "
        f"GROUP BY product_id "
        f"ORDER BY units_sold DESC",
        4,
    ),
    # 3. Overall average order value by status.
    (
        f"SELECT order_status, AVG(order_total) AS aov "
        f"FROM {OH} "
        f"GROUP BY order_status",
        3,
    ),
    # 4. Revenue per order from line items (unit_price * quantity), joined back
    #    to the order for its status.
    (
        f"SELECT oh.order_id, oh.order_status, "
        f"SUM(oi.unit_price * oi.quantity) AS line_revenue "
        f"FROM {OH} oh "
        f"JOIN {OI} oi ON oh.order_id = oi.order_id "
        f"GROUP BY oh.order_id, oh.order_status",
        2,
    ),
    # 5. Promotions by cost (single-table, different table — variety).
    (
        f"SELECT promotion_name, promotion_cost "
        f"FROM {PROMO} "
        f"WHERE promotion_cost > 1000 "
        f"ORDER BY promotion_cost DESC",
        1,
    ),
]


def main() -> int:
    lines = []
    ts = BASE_TS
    for sql, runs in QUERIES:
        for _ in range(runs):
            ts += 3600  # space them an hour apart
            lines.append(
                json.dumps(
                    {
                        "query": sql,
                        "timestamp": ts,
                        "user": "analyst@showcase.example",
                        "default_db": "order_entry_db",
                        "default_schema": "order_entry",
                    }
                )
            )
    out = "examples/query_log.json"
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {len(lines)} query events "
          f"({len(QUERIES)} distinct patterns) to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
