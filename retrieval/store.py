"""Local vector store for proven query patterns.

`[DECIDED per architecture §4]` DataHub holds the *canonical* patterns; this
single-file sqlite-vec index does the nearest-neighbor lookup. ~20 lines of real
logic, runs anywhere, fully understood behavior. Never coupled to DataHub-native
vector search.

Each row: the pattern's DataHub URN + templated SQL + intent label + metadata
JSON, with its embedding in a parallel vec0 virtual table keyed by rowid.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field

import sqlite_vec

from .embeddings import dim, embed_one

DEFAULT_PATH = os.environ.get("VECTOR_STORE_PATH", "retrieval/patterns.db")


@dataclass
class Pattern:
    urn: str                       # DataHub Query entity URN (canonical home)
    intent: str                    # LLM-generated intent label
    templated_sql: str             # literals stripped to ?
    metadata: dict = field(default_factory=dict)  # join keys, frequency, datasets
    score: float | None = None     # cosine distance, populated on search


class PatternStore:
    def __init__(self, path: str = DEFAULT_PATH, embed_dim: int | None = None):
        self.path = path
        self.embed_dim = embed_dim or dim()
        self.db = sqlite3.connect(path)
        self.db.enable_load_extension(True)
        sqlite_vec.load(self.db)
        self.db.enable_load_extension(False)
        self._init_schema()

    def _init_schema(self) -> None:
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS patterns (
                rowid        INTEGER PRIMARY KEY AUTOINCREMENT,
                urn          TEXT UNIQUE,
                intent       TEXT,
                templated_sql TEXT,
                metadata     TEXT
            )
            """
        )
        # Cosine distance so `distance` is 0 (identical) .. 2 (opposite) and
        # similarity = 1 - distance reads naturally.
        self.db.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS pattern_vecs
            USING vec0(embedding float[{self.embed_dim}] distance_metric=cosine)
            """
        )
        self.db.commit()

    def add(self, pattern: Pattern, embedding: list[float] | None = None) -> int:
        """Insert (or replace) a pattern and its embedding. Returns rowid."""
        if embedding is None:
            embedding = embed_one(f"{pattern.intent}\n{pattern.templated_sql}")
        cur = self.db.execute(
            "INSERT INTO patterns (urn, intent, templated_sql, metadata) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(urn) DO UPDATE SET intent=excluded.intent, "
            "templated_sql=excluded.templated_sql, metadata=excluded.metadata "
            "RETURNING rowid",
            (pattern.urn, pattern.intent, pattern.templated_sql,
             json.dumps(pattern.metadata)),
        )
        rowid = cur.fetchone()[0]
        self.db.execute("DELETE FROM pattern_vecs WHERE rowid = ?", (rowid,))
        self.db.execute(
            "INSERT INTO pattern_vecs (rowid, embedding) VALUES (?, ?)",
            (rowid, sqlite_vec.serialize_float32(embedding)),
        )
        self.db.commit()
        return rowid

    def search(self, question: str, k: int = 3) -> list[Pattern]:
        """Embed the question, return the top-k nearest proven patterns."""
        qvec = embed_one(question)
        rows = self.db.execute(
            """
            SELECT p.urn, p.intent, p.templated_sql, p.metadata, v.distance
            FROM pattern_vecs v
            JOIN patterns p ON p.rowid = v.rowid
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
            """,
            (sqlite_vec.serialize_float32(qvec), k),
        ).fetchall()
        return [
            Pattern(
                urn=urn,
                intent=intent,
                templated_sql=sql,
                metadata=json.loads(meta or "{}"),
                score=distance,
            )
            for urn, intent, sql, meta, distance in rows
        ]

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM patterns").fetchone()[0]

    def close(self) -> None:
        self.db.close()
