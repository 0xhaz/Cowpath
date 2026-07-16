"""Intent labeling — a short natural-language name for each pattern.

One cheap LLM call per canonical query ("monthly revenue per region"). This is a
*label*, not reasoning — keep it terse. The label is what an analyst's question
gets matched against at retrieval time, so it matters that it reads like how a
human would ask, not like the SQL.
"""

from __future__ import annotations

from agent.llm import get_llm
from indexer.extract import extract_pattern

_PROMPT = """You label a SQL query with the business question it answers.
Give ONE short phrase (max 12 words), lowercase, no punctuation, no "this query".
Write it the way an analyst would ask it in plain English. Describe ONLY what the
SQL actually does — do not invent columns, filters, or entities not present.

Facts extracted from the SQL (rely on these, do not guess beyond them):
  tables: {tables}
  aggregations: {aggs}
  group by: {group_by}
  filters on: {filters}

SQL:
{sql}

Intent phrase:"""


def label_intent(sql: str, llm=None) -> str:
    llm = llm or get_llm(temperature=0.0)
    p = extract_pattern(sql)
    prompt = _PROMPT.format(
        sql=sql,
        tables=", ".join(t.split(".")[-1] for t in p.tables) or "—",
        aggs=", ".join(p.aggregations) or "—",
        group_by=", ".join(p.group_by) or "—",
        filters=", ".join(p.filter_columns) or "—",
    )
    resp = llm.invoke(prompt)
    text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
    # take first line, strip stray quotes/trailing period
    line = text.splitlines()[0].strip().strip('"\'').rstrip(".")
    return line[:120]


if __name__ == "__main__":
    demo = (
        "SELECT oh.order_status, AVG(oh.order_total) AS avg_order_value "
        "FROM order_entry_db.analytics.order_history oh "
        "JOIN order_entry_db.order_entry.order_items oi ON oh.order_id = oi.order_id "
        "WHERE oi.return_date IS NOT NULL GROUP BY oh.order_status"
    )
    print(label_intent(demo))
