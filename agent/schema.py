"""Fetch table schemas from DataHub — the context an agent gets *for free*.

This is the "schema only" baseline: real column lists pulled from the catalog,
formatted as CREATE TABLE-ish text. It's honest — the agent isn't handicapped,
it just lacks the *proven join pattern* that history encodes. That missing
pattern is exactly what Cowpath supplies in the "after" case.
"""

from __future__ import annotations

from datahub.sdk import DataHubClient

# The snowflake order_entry tables loaded by showcase-ecommerce that our demo
# question could plausibly touch. The agent sees all of them and must choose.
DEMO_TABLES = [
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_history,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.order_items,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.promotions,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.warehouses,PROD)",
]


def _table_name(urn: str) -> str:
    # urn:li:dataset:(platform,b2fd91.order_entry_db.analytics.order_history,PROD)
    inner = urn.split(",")[1]           # b2fd91.order_entry_db.analytics.order_history
    return ".".join(inner.split(".")[1:])  # order_entry_db.analytics.order_history


def get_schema_context(client: DataHubClient | None = None,
                       urns: list[str] | None = None) -> str:
    client = client or DataHubClient.from_env()
    urns = urns or DEMO_TABLES
    blocks = []
    for urn in urns:
        try:
            d = client.entities.get(urn)
            fields = d.schema or []
        except Exception:
            continue
        cols = []
        for f in fields:
            fn = getattr(f, "fieldPath", None) or getattr(f, "field_path", None)
            ft = (getattr(f, "nativeDataType", None)
                  or getattr(f, "native_data_type", "") or "")
            cols.append(f"  {fn}{(' ' + ft) if ft else ''}")
        blocks.append(f"CREATE TABLE {_table_name(urn)} (\n"
                      + ",\n".join(cols) + "\n);")
    return "\n\n".join(blocks)


if __name__ == "__main__":
    print(get_schema_context())
