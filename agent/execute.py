"""Run generated SQL against the seeded DuckDB stand-in.

Read-only. Sets a search_path so the agent's *unqualified* refs (the "before"
SQL often writes `FROM order_history`) resolve to the right schema, while its
fully-qualified refs (`order_entry_db.analytics.order_history`) resolve via the
catalog name. Errors are returned, not raised — a failed query is itself a
demo-worthy outcome (the naive SQL sometimes doesn't even run).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import duckdb

DB_PATH = os.environ.get("DUCKDB_PATH", "examples/order_entry_db.duckdb")


@dataclass
class Result:
    columns: list[str]
    rows: list[tuple]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def scalar(self):
        """If the result is a single cell, return it (for wrong-number/right-number)."""
        if self.ok and len(self.rows) == 1 and len(self.columns) == 1:
            return self.rows[0][0]
        return None


def execute_sql(sql: str, db_path: str = DB_PATH, limit: int = 20) -> Result:
    if not os.path.exists(db_path):
        return Result([], [], error=f"no seeded db at {db_path} (run: python -m examples.seed_duckdb)")
    try:
        con = duckdb.connect(db_path, read_only=True)
        con.execute("SET search_path='order_entry_db.analytics,order_entry_db.order_entry'")
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(limit)
        con.close()
        return Result(columns=cols, rows=rows)
    except Exception as e:  # noqa: BLE001 — surfacing the message is the point
        return Result([], [], error=f"{type(e).__name__}: {str(e).splitlines()[0][:160]}")


if __name__ == "__main__":
    for sql in [
        "SELECT SUM(order_total) AS total_revenue FROM order_history",
        "SELECT oh.order_id, SUM(oi.unit_price*oi.quantity) AS revenue "
        "FROM order_entry_db.analytics.order_history oh "
        "JOIN order_entry_db.order_entry.order_items oi ON oh.order_id=oi.order_id "
        "GROUP BY oh.order_id ORDER BY oh.order_id",
    ]:
        r = execute_sql(sql)
        print("SQL:", sql[:60], "...")
        print("  ->", ("ERROR " + r.error) if not r.ok else f"{r.columns} {r.rows}")
