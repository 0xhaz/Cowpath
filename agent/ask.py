"""The before/after — Cowpath's whole thesis in one function.

`answer(question, use_patterns=False)` → schema-only SQL (the agent guesses the
join). `answer(question, use_patterns=True)` → the same agent, now handed the
top proven pattern retrieved from history, grounds its SQL in it.

The money-shot is the diff between the two.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from datahub.sdk import DataHubClient

from agent.llm import get_llm
from agent.schema import get_schema_context
from retrieval.store import PatternStore, Pattern

_BASE = """You are a senior analytics engineer writing Snowflake SQL.
Answer the question with ONE SQL query. Output ONLY the SQL — no prose, no
markdown fences, no explanation.

Available tables:
{schema}
"""

_PATTERN_BLOCK = """
Proven query patterns from this warehouse's history (these joins and filters
have answered similar questions correctly before — prefer them):
{patterns}
"""

_QUESTION = "\nQuestion: {question}\nSQL:"


@dataclass
class Answer:
    question: str
    sql: str
    used_patterns: bool
    patterns: list[Pattern] = field(default_factory=list)


def _format_patterns(patterns: list[Pattern]) -> str:
    out = []
    for p in patterns:
        joins = ", ".join(p.metadata.get("join_keys") or []) or "none"
        out.append(
            f"- intent: {p.intent}\n"
            f"  join keys: {joins}\n"
            f"  SQL template:\n    {p.templated_sql}"
        )
    return "\n".join(out)


def _clean_sql(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if "```" in t[3:] else t.strip("`")
        if t.lower().startswith("sql"):
            t = t[3:]
    return t.strip().strip("`").strip()


def answer(
    question: str,
    use_patterns: bool = False,
    *,
    client: DataHubClient | None = None,
    store: PatternStore | None = None,
    llm=None,
    k: int = 2,
) -> Answer:
    client = client or DataHubClient.from_env()
    llm = llm or get_llm(temperature=0.0)
    schema = get_schema_context(client)

    prompt = _BASE.format(schema=schema)
    hits: list[Pattern] = []
    if use_patterns:
        store = store or PatternStore()
        hits = store.search(question, k=k)
        if hits:
            prompt += _PATTERN_BLOCK.format(patterns=_format_patterns(hits))
    prompt += _QUESTION.format(question=question)

    resp = llm.invoke(prompt)
    sql = _clean_sql(resp.content if hasattr(resp, "content") else str(resp))
    return Answer(question=question, sql=sql, used_patterns=use_patterns, patterns=hits)


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else (
        "What is the average order value for orders that contain a returned item?"
    )
    client = DataHubClient.from_env()
    store = PatternStore()
    llm = get_llm(temperature=0.0)
    print("=== BEFORE (schema only) ===")
    print(answer(q, use_patterns=False, client=client, store=store, llm=llm).sql)
    print("\n=== AFTER (with proven patterns) ===")
    a = answer(q, use_patterns=True, client=client, store=store, llm=llm)
    print(a.sql)
    print("\nretrieved:", [f"{p.intent} (d={p.score:.3f})" for p in a.patterns])
