---
name: datahub-query-patterns
description: >-
  Turn a warehouse query log into proven, reusable query patterns stored in
  DataHub and retrieved at agent-query time. Reproduces DataHub Cloud's Context
  Intelligence on open-source DataHub Core: ingest query history, extract the
  join/filter/aggregation skeleton per query, write each canonical pattern back
  onto its DataHub Query entity (intent label, templated SQL, join keys,
  frequency), and retrieve the best-matching proven pattern for a new question so
  the agent grounds its SQL instead of guessing a join.
---

# datahub-query-patterns

Use this skill when an agent needs to write SQL against catalogued datasets and
schema alone is not enough — the non-obvious join, the team's real revenue
convention, the correct filter — lives in *how questions were answered before*.
This skill indexes that history into DataHub and serves it back.

## When to use
- The agent is about to generate SQL and you have (or can synthesize) a query log.
- You want DataHub to hold reusable query patterns, not just schema/lineage.
- You want the graph to get richer with each run (read → act → **write back**).

## Prerequisites
- DataHub Core (Quickstart) reachable; `DATAHUB_GMS_URL` set (PAT if auth is on).
- MCP server running: `uvx mcp-server-datahub@latest` with
  `TOOLS_IS_MUTATION_ENABLED=true`.
- `acryl-datahub[sql-queries]`, `sqlglot`, a local embedding model.

## Workflow

### 1. Ingest query history (native DataHub — the free ride)
Feed a newline-delimited JSON query log through the `sql-queries` source. DataHub
parses each statement with `SqlParsingAggregator`, creates a `Query` entity,
links `QuerySubjects` to the touched datasets (column-level where inferable), and
auto-dedups by normalized text.

### 2. Extract the pattern (per Query entity)
Pull each `Query` (MCP `get_dataset_queries`, or OpenAPI `entity/query`). With
`sqlglot`, extract the structural skeleton — tables, join keys, filter columns,
aggregations, group-by — and strip literals to `?` to get a reusable template.

### 3. Label intent
One short LLM call per canonical query for a plain-English intent
("total revenue per order"), grounded on the extracted structure so it describes
what the SQL *actually* does. This label is what a new question matches against.

### 4. Write the pattern back into DataHub (the enrichment)
Re-emit `QueryProperties` on each `Query` entity with `name` = intent,
`description` = intent + templated SQL, and `customProperties` carrying
`templated_sql`, `join_keys`, `aggregations`, `frequency`. The proven pattern now
lives on the dataset's Queries tab, linked to the tables it touches. Optionally
also capture it as a knowledge document via MCP `save_document`.

### 5. Retrieve at query time
Embed the incoming question, nearest-neighbor over the pattern embeddings, return
the top-k proven patterns (+ schema) to the agent. The agent grounds its SQL in
the proven join/convention instead of re-deriving it.

## MCP tools this skill chains
`get_dataset_queries` · `get_entities` / `list_schema_fields` · `search` ·
`get_lineage` · `save_document` · `search_documents` (write-back of
`QueryProperties` is done via the metadata emitter / OpenAPI).

## Reference implementation
Cowpath (this repo): `indexer/` (extract + intent + write-back), `retrieval/`
(local `sqlite-vec` store), `agent/` (schema-only vs pattern-grounded SQL). The
demo shows the same agent fumble a query cold, then nail it after indexing —
a wrong number vs a right number.
