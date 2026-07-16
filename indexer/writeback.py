"""Write-back — the visible graph enrichment (the scoring lever).

The `sql-queries` ingestion already created raw Query entities linked to their
datasets (QuerySubjects). Cowpath *enriches* each one into a canonical, reusable
pattern in DataHub:
  - name         = the intent label (how an analyst asks it)
  - description   = intent + the templated SQL
  - customProperties = templated_sql, join_keys, aggregations, frequency, intent
  - a `cowpath-proven-pattern` tag so Beat 2 visibly reads "these are proven"

DataHub stays the canonical home of the pattern; the local vector store (indexed
separately in build_index) only holds the embedding for nearest-neighbor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import requests
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.metadata.schema_classes import QueryPropertiesClass

from indexer.extract import QueryPattern


@dataclass
class RawQuery:
    urn: str
    statement: str
    datasets: list[str]          # dataset URNs from QuerySubjects
    properties: dict             # raw queryProperties value (to preserve on re-emit)
    subjects: dict               # raw querySubjects value (to preserve)


def pull_queries(gms_url: str) -> list[RawQuery]:
    """Fetch all Query entities with their properties + subjects via OpenAPI v3.

    Uses the entity scroll (not search) so it works right after ingest, modulo
    async index lag — callers should retry if this returns fewer than expected.
    """
    url = (f"{gms_url}/openapi/v3/entity/query"
           "?count=100&aspects=queryProperties&aspects=querySubjects")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    out = []
    for e in resp.json().get("entities", []):
        qp = (e.get("queryProperties") or {}).get("value") or {}
        qs = (e.get("querySubjects") or {}).get("value") or {}
        stmt = (qp.get("statement") or {}).get("value", "")
        subs = [s.get("entity", "") for s in qs.get("subjects", [])]
        ds = [s for s in subs if s.startswith("urn:li:dataset")]
        if stmt:
            out.append(RawQuery(urn=e["urn"], statement=stmt, datasets=ds,
                                properties=qp, subjects=qs))
    return out


def enrich_query(
    graph,
    raw: RawQuery,
    intent: str,
    pattern: QueryPattern,
    frequency: int,
) -> None:
    """Re-emit QueryProperties enriched with intent + pattern metadata, and tag it."""
    custom = dict(raw.properties.get("customProperties") or {})
    custom.update(
        {
            "cowpath_intent": intent,
            "cowpath_templated_sql": pattern.templated_sql,
            "cowpath_join_keys": json.dumps(pattern.join_keys),
            "cowpath_aggregations": json.dumps(pattern.aggregations),
            "cowpath_frequency": str(frequency),
        }
    )
    description = (
        f"**Proven pattern (Cowpath):** {intent}\n\n"
        f"Run {frequency}× in query history. "
        f"Join keys: {', '.join(pattern.join_keys) or 'none'}.\n\n"
        f"```sql\n{pattern.templated_sql}\n```"
    )
    props = QueryPropertiesClass(
        statement=_statement_from_raw(raw),
        source=raw.properties.get("source", "SYSTEM"),
        created=_audit_from_raw(raw, "created"),
        lastModified=_audit_from_raw(raw, "lastModified"),
        name=intent,
        description=description,
        customProperties=custom,
        origin=raw.properties.get("origin"),
    )
    graph.emit(MetadataChangeProposalWrapper(entityUrn=raw.urn, aspect=props))
    # Note: the `query` entity does not support the globalTags aspect, so the
    # "proven pattern" marker lives in the enriched name/description/customProperties
    # (visible on the dataset's Queries tab) rather than a tag.


def _statement_from_raw(raw: RawQuery):
    from datahub.metadata.schema_classes import QueryStatementClass
    st = raw.properties.get("statement") or {}
    return QueryStatementClass(
        value=st.get("value", raw.statement),
        language=st.get("language", "SQL"),
    )


def _audit_from_raw(raw: RawQuery, key: str):
    from datahub.metadata.schema_classes import AuditStampClass
    a = raw.properties.get(key) or {}
    if not a:
        return None
    return AuditStampClass(time=a.get("time", 0), actor=a.get("actor", "urn:li:corpuser:__datahub_system"))
