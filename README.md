# Cowpath

> *"We pave the cowpaths your analysts already walk — so the agent takes the road, not the wilderness."*

Cowpath reproduces DataHub Cloud's flagship **Context Intelligence** (query history → validated query patterns) on **open-source DataHub Core**.

An agent with only schema metadata fumbles a non-obvious join. Cowpath indexes your warehouse query history into DataHub as retrievable, proven patterns — so the same agent grounds its SQL in a pattern that already worked, and gets it right. The graph gets smarter with every run (read → act → **write-back**).

Built for **Build with DataHub: The Agent Hackathon** (idea 5A). Apache-2.0.

## The loop

```
query log ──▶ sql-queries ingest ──▶ sqlglot pattern extract ──▶ write-back to DataHub
  (NDJSON)      (Query entities)        (skeleton + intent)         (Query entity + embedding)
                                                                            │
                            agent question ──▶ embed ──▶ vector store ◀─────┘
                                                          (top-k proven patterns)
                                                              │
                                                    grounded SQL ✔
```

## Repo layout

| Dir | Role |
|---|---|
| [indexer/](indexer/) | Phase 1: query log → patterns → write-back into DataHub |
| [retrieval/](retrieval/) | Phase 2: local `sqlite-vec` store + nearest-neighbor |
| [agent/](agent/) | Agent Context Kit + LangChain loop |
| [frontend/](frontend/) | before/after comparison harness (terminal first) |
| [examples/](examples/) | sample query log + sample outputs |
| [skill-or-source/](skill-or-source/) | the OSS contribution (ingestion source / skill) |

## Setup

Requires Docker Desktop (≥8GB to Docker), `uv`, and Ollama for the on-device LLM.

```bash
# 1. Python env (pinned to 3.11)
uv venv --python 3.11 && source .venv/bin/activate
uv pip install -e .

# 2. DataHub Core (Quickstart) + sample data
datahub docker quickstart
datahub datapack load showcase-ecommerce

# 3. Config (Quickstart auth is off by default → no PAT needed)
cp .env.example .env

# 4. LLM — Ollama primary (privacy-first). Use a small tool-calling model;
#    NOT a 20GB+ model if DataHub shares the box (it will OOM). Anthropic swap:
#    set LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY for filming insurance.
ollama pull llama3.2
```

## Run the demo

```bash
# Phase 1 — index query history into DataHub as proven patterns (write-back)
datahub ingest -c indexer/ingest_recipe.yml     # query log -> Query entities + QuerySubjects
python -m indexer.build_index                    # extract + label + enrich in DataHub + local index

# Phase 3/4 — the before/after money-shot (seed a stand-in warehouse so SQL runs)
python -m examples.seed_duckdb
python -m frontend.compare                        # schema-only vs pattern-grounded, wrong # vs right #
```

The `sql-queries` source needs the `acryl-datahub[sql-queries]` extra (pulled by `uv pip install -e .`). MCP server (optional, for agent tool-use): `TOOLS_IS_MUTATION_ENABLED=true uvx mcp-server-datahub@latest`.

## OSS contribution

[skill-or-source/datahub-query-patterns/SKILL.md](skill-or-source/datahub-query-patterns/SKILL.md) — a reusable DataHub Skill packaging the indexing → write-back → retrieval workflow.

## Status

**Core loop closed.** Ingest → sqlglot pattern → intent label → write-back into DataHub → embed → retrieve → grounded SQL → execute. The demo shows the same agent fumble a query cold, then nail it after indexing — a wrong number vs a right number.
