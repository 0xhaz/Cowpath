"""G2 gate — local retrieval round-trip.

Write a few proven patterns, embed a paraphrased question, confirm the *right*
pattern comes back by similarity (not keyword match). Fully local; no DataHub.
"""

import tempfile
import os

from retrieval.store import Pattern, PatternStore


def main() -> int:
    tmp = os.path.join(tempfile.mkdtemp(), "g2.db")
    store = PatternStore(path=tmp)

    patterns = [
        Pattern(
            urn="urn:li:query:aov-repeat-buyers",
            intent="average order value by customer segment for repeat buyers",
            templated_sql=(
                "SELECT c.segment, AVG(o.total) FROM orders o "
                "JOIN customers c ON o.customer_id = c.id "
                "WHERE o.customer_id IN (SELECT customer_id FROM orders "
                "GROUP BY customer_id HAVING COUNT(*) > ?) GROUP BY c.segment"
            ),
            metadata={"join_keys": ["customer_id"], "frequency": 42},
        ),
        Pattern(
            urn="urn:li:query:monthly-revenue-region",
            intent="monthly revenue per region",
            templated_sql=(
                "SELECT region, DATE_TRUNC('month', ordered_at) m, SUM(total) "
                "FROM orders GROUP BY region, m"
            ),
            metadata={"frequency": 30},
        ),
        Pattern(
            urn="urn:li:query:top-products",
            intent="best selling products by units",
            templated_sql=(
                "SELECT product_id, SUM(qty) q FROM order_items "
                "GROUP BY product_id ORDER BY q DESC LIMIT ?"
            ),
            metadata={"frequency": 18},
        ),
    ]
    for p in patterns:
        store.add(p)

    # Paraphrase — no lexical overlap with "average order value / repeat buyers".
    question = "how much do returning shoppers spend per order across each tier?"
    hits = store.search(question, k=3)

    print(f"stored {store.count()} patterns")
    print(f"query: {question!r}\n")
    for i, h in enumerate(hits, 1):
        print(f"  {i}. dist={h.score:.4f}  {h.intent}")

    top = hits[0]
    ok = top.urn == "urn:li:query:aov-repeat-buyers"
    print()
    print("G2 PASS - semantic retrieval returned the right pattern"
          if ok else
          f"G2 FAIL - top hit was {top.urn}, expected aov-repeat-buyers")
    store.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
