"""Pattern extraction — the part Cowpath actually builds and contributes back.

Given a raw SQL string, produce a reusable *pattern*: the structural skeleton
(tables, joins + keys, filter columns, aggregations, group-by) with literals
stripped to `?`. This is what makes a query from history reusable as a proven
template instead of a one-off.

Uses `sqlglot` only — no warehouse connection. Dialect defaults to snowflake to
match showcase-ecommerce; override per call.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import sqlglot
from sqlglot import exp


@dataclass
class QueryPattern:
    templated_sql: str                       # literals -> ?, normalized
    tables: list[str] = field(default_factory=list)      # fully-qualified refs
    join_keys: list[str] = field(default_factory=list)   # "a.order_id = b.order_id"
    filter_columns: list[str] = field(default_factory=list)
    aggregations: list[str] = field(default_factory=list)  # e.g. "AVG(order_total)"
    group_by: list[str] = field(default_factory=list)
    dialect: str = "snowflake"

    def to_dict(self) -> dict:
        return asdict(self)

    def fingerprint(self) -> str:
        """Order-independent structural signature for dedup / clustering."""
        parts = [
            "T:" + ",".join(sorted(self.tables)),
            "J:" + ",".join(sorted(self.join_keys)),
            "A:" + ",".join(sorted(self.aggregations)),
            "G:" + ",".join(sorted(self.group_by)),
        ]
        return "|".join(parts)


def _strip_literals(tree: exp.Expression) -> exp.Expression:
    """Replace literal values with a placeholder so `country='MY'` -> `country=?`."""
    tree = tree.copy()
    for lit in tree.find_all(exp.Literal):
        lit.replace(exp.Placeholder())
    # Also collapse IN (...) lists and boolean/NULL-free literals already handled.
    return tree


def _qualified_name(table: exp.Table) -> str:
    return ".".join(
        p.name for p in (table.args.get("catalog"), table.args.get("db"), table.this)
        if p is not None
    )


def extract_pattern(sql: str, dialect: str = "snowflake") -> QueryPattern:
    tree = sqlglot.parse_one(sql, read=dialect)

    tables = sorted({_qualified_name(t) for t in tree.find_all(exp.Table)})

    join_keys: list[str] = []
    for join in tree.find_all(exp.Join):
        on = join.args.get("on")
        if isinstance(on, exp.EQ):
            join_keys.append(on.sql(dialect=dialect))

    filter_columns: list[str] = []
    for where in tree.find_all(exp.Where):
        for col in where.find_all(exp.Column):
            filter_columns.append(col.sql(dialect=dialect))

    aggregations: list[str] = []
    for func in tree.find_all(exp.AggFunc):
        aggregations.append(func.sql(dialect=dialect))

    group_by: list[str] = []
    for g in tree.find_all(exp.Group):
        for e in g.expressions:
            group_by.append(e.sql(dialect=dialect))

    templated = _strip_literals(tree).sql(dialect=dialect, normalize=True)

    return QueryPattern(
        templated_sql=templated,
        tables=tables,
        join_keys=sorted(set(join_keys)),
        filter_columns=sorted(set(filter_columns)),
        aggregations=sorted(set(aggregations)),
        group_by=sorted(set(group_by)),
        dialect=dialect,
    )


if __name__ == "__main__":
    demo = (
        "SELECT oh.order_status, AVG(oh.order_total) AS avg_order_value "
        "FROM order_entry_db.analytics.order_history oh "
        "JOIN order_entry_db.order_entry.order_items oi ON oh.order_id = oi.order_id "
        "WHERE oi.return_date IS NOT NULL AND oh.order_total > 100 "
        "GROUP BY oh.order_status"
    )
    p = extract_pattern(demo)
    import json
    print(json.dumps(p.to_dict(), indent=2))
    print("\nfingerprint:", p.fingerprint())
