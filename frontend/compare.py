"""Cowpath comparison harness — the filmable before/after (terminal first).

Fires one question into the agent twice: schema-only vs. schema + proven
patterns retrieved from history. Shows the two SQLs side by side and the
provenance of the pattern that rescued the "after" (URN links back to the
enriched Query entity in DataHub — Beat 2).

    python -m frontend.compare
    python -m frontend.compare "your question here"

`[DECIDED per architecture §7]` Terminal first; only wrap in a web page if the
recording reads cramped.
"""

from __future__ import annotations

import re
import sys

from rich.console import Console
from rich.panel import Panel
from rich.columns import Columns
from rich.syntax import Syntax
from rich.table import Table

from datahub.sdk import DataHubClient

from agent.ask import answer
from agent.execute import execute_sql, Result
from agent.llm import get_llm, provider_label
from retrieval.store import PatternStore

console = Console()

# Each question optionally carries a `reconcile` note: shown ONLY when the two
# results are directly comparable on an ADDITIVE total (SUM/COUNT). Summing
# averages or top-N lists would be meaningless, so those questions omit it.
DEFAULT_QUESTIONS = [
    {
        "q": "What is the total revenue for each order?",
        "reconcile": "the schema-only query trusts the stale `order_total` column; "
                     "the proven pattern sums the line items (`unit_price * quantity`).",
    },
    {"q": "What is the average order value for orders that contain a returned item?"},
    {"q": "Which products sold the most units?"},
]


def _sql_panel(title: str, sql: str, style: str) -> Panel:
    body = Syntax(sql, "sql", theme="ansi_dark", word_wrap=True)
    return Panel(body, title=title, border_style=style, padding=(1, 1))


def _fmt_cell(v) -> str:
    if isinstance(v, float):
        return f"{v:,.0f}" if v == int(v) else f"{v:,.2f}"
    return "∅" if v is None else str(v)


def _result_panel(title: str, res: Result, style: str) -> Panel:
    if not res.ok:
        return Panel(f"[red]query failed:[/]\n{res.error}", title=title,
                    border_style=style)
    if not res.rows:
        return Panel("[dim](no rows)", title=title, border_style=style)
    t = Table(show_header=True, header_style=f"bold {style}", box=None, pad_edge=False)
    for c in res.columns:
        t.add_column(c, overflow="fold")
    for row in res.rows[:8]:
        t.add_row(*[_fmt_cell(v) for v in row])
    return Panel(t, title=title, border_style=style, padding=(1, 1))


def _grand_total(res: Result):
    """Sum the last numeric column — lets a scalar 'before' and a grouped 'after'
    be compared on one reconciled number."""
    if not res.ok or not res.rows:
        return None
    for ci in range(len(res.columns) - 1, -1, -1):
        vals = [r[ci] for r in res.rows]
        if all(isinstance(v, (int, float)) for v in vals):
            return sum(vals)
    return None


# Reconciliation is only valid on ADDITIVE aggregates — summing rows of an AVG /
# MIN / MAX / MEDIAN is meaningless, so skip it for those.
_NON_ADDITIVE = re.compile(r"\b(AVG|MEAN|MIN|MAX|MEDIAN|STDDEV|VARIANCE|PERCENTILE)\b", re.I)


def _is_additive(sql: str) -> bool:
    return not _NON_ADDITIVE.search(sql or "")


def run(spec, client, store, llm) -> None:
    if isinstance(spec, str):
        spec = {"q": spec}
    question = spec["q"]
    console.rule(f"[bold]Q:[/] {question}")

    before = answer(question, use_patterns=False, client=client, store=store, llm=llm)
    after = answer(question, use_patterns=True, client=client, store=store, llm=llm)
    before_res = execute_sql(before.sql)
    after_res = execute_sql(after.sql)

    console.print(
        Columns(
            [
                _sql_panel("BEFORE — schema only", before.sql, "red"),
                _sql_panel("AFTER — Cowpath patterns", after.sql, "green"),
            ],
            equal=True, expand=True,
        )
    )
    console.print(
        Columns(
            [
                _result_panel("BEFORE — result", before_res, "red"),
                _result_panel("AFTER — result", after_res, "green"),
            ],
            equal=True, expand=True,
        )
    )

    # Reconciliation headline — show when the comparison is on an ADDITIVE total
    # (summing rows is valid) and the two numbers actually diverge. Works whether
    # the question came from the curated list or the CLI.
    if _is_additive(before.sql) and _is_additive(after.sql):
        b_tot, a_tot = _grand_total(before_res), _grand_total(after_res)
        if b_tot is not None and a_tot is not None and abs(b_tot - a_tot) > 1e-6:
            diff = b_tot - a_tot
            note = spec.get("reconcile") or (
                "the schema-only query disagrees with how this metric was actually "
                "computed in query history; the proven pattern reflects the real convention."
            )
            console.print(Panel(
                f"naive total [red]{b_tot:,.0f}[/]  vs  proven total [green]{a_tot:,.0f}[/]"
                f"   →  off by [bold red]{diff:+,.0f}[/].  {note}",
                border_style="yellow", title="Why the pattern matters"))

    if after.patterns:
        prov = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False)
        prov.add_column("proven pattern retrieved", overflow="fold")
        prov.add_column("similarity", justify="right")
        prov.add_column("runs", justify="right")
        prov.add_column("DataHub Query URN", overflow="fold", style="dim")
        for p in after.patterns:
            # cosine distance -> similarity in [0,1] (clamped)
            sim = max(0.0, 1 - (p.score or 0))
            prov.add_row(
                p.intent,
                f"{sim:.0%}" if p.score is not None else "—",
                str(p.metadata.get("frequency", "—")),
                p.urn,
            )
        console.print(Panel(prov, title="Grounding provenance (write-back → retrieval)",
                            border_style="cyan"))
    console.print()


def main() -> int:
    console.rule("[bold magenta]Cowpath — proven query patterns for agents")
    console.print(f"LLM: [cyan]{provider_label()}[/]  ·  patterns from DataHub-enriched "
                  f"Query entities + local vector store\n")
    questions = sys.argv[1:] or DEFAULT_QUESTIONS
    client = DataHubClient.from_env()
    store = PatternStore()
    llm = get_llm(temperature=0.0)
    for q in questions:
        run(q, client, store, llm)
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
