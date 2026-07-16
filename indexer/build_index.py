"""Cowpath indexer — Phase 1 end to end.

Reads the Query entities the `sql-queries` ingestion put in DataHub, turns each
into a canonical pattern (extract → intent label), writes the enrichment BACK
into DataHub (visible graph enrichment), and indexes the embedding into the
local vector store for retrieval.

Run (after `datahub ingest -c indexer/ingest_recipe.yml`):
    python -m indexer.build_index
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter

from dotenv import load_dotenv
from rich.console import Console

from datahub.sdk import DataHubClient

from indexer.extract import extract_pattern
from indexer.intent import label_intent
from indexer.writeback import pull_queries, enrich_query
from retrieval.store import Pattern, PatternStore
from retrieval.embeddings import embed_one
from agent.llm import get_llm, provider_label

console = Console()
QUERY_LOG = os.environ.get("QUERY_LOG", "examples/query_log.json")
GMS = os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080")


def frequency_by_statement(log_path: str) -> Counter:
    """Count how often each exact statement appears in the source log."""
    counts: Counter = Counter()
    if not os.path.exists(log_path):
        return counts
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            counts[json.loads(line)["query"]] += 1
    return counts


def main() -> int:
    load_dotenv()
    console.rule("[bold]Cowpath indexer")
    console.print(f"LLM: [cyan]{provider_label()}[/]   GMS: {GMS}")

    client = DataHubClient.from_env()
    graph = client._graph
    freq = frequency_by_statement(QUERY_LOG)

    # Pull the ingested Query entities (retry for async index lag).
    raws = []
    for attempt in range(12):
        raws = pull_queries(GMS)
        if raws:
            break
        console.print(f"  waiting for Query entities to index... ({attempt})")
        time.sleep(5)
    if not raws:
        console.print("[red]No Query entities found. Run the sql-queries ingest first.")
        return 1
    console.print(f"Found [bold]{len(raws)}[/] query entities to index\n")

    store = PatternStore()
    llm = get_llm(temperature=0.0)   # reuse one client across labels

    for raw in raws:
        pattern = extract_pattern(raw.statement)
        intent = label_intent(raw.statement, llm=llm)
        frequency = freq.get(raw.statement, 1)

        # write-back into DataHub (the visible enrichment)
        enrich_query(graph, raw, intent, pattern, frequency)

        # index the embedding locally for retrieval
        emb = embed_one(f"{intent}\n{pattern.templated_sql}")
        store.add(
            Pattern(
                urn=raw.urn,
                intent=intent,
                templated_sql=pattern.templated_sql,
                metadata={
                    "join_keys": pattern.join_keys,
                    "aggregations": pattern.aggregations,
                    "frequency": frequency,
                    "datasets": raw.datasets,
                },
            ),
            embedding=emb,
        )
        tbls = [d.split(",")[1].split(".")[-1] for d in raw.datasets]
        console.print(f"  [green]✓[/] {intent}")
        console.print(f"      freq={frequency}  tables={tbls}  joins={pattern.join_keys or '—'}")

    console.print(f"\n[bold green]Indexed {store.count()} patterns[/] "
                  f"→ DataHub (enriched Query entities) + local store ({store.path})")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
