"""PostgreSQL + pgvector backend.

One table per vector space, with the modality enforced by the column type and
an HNSW index per space. Filters become ordinary SQL predicates, so the
"modality filter" guarantee is enforced by the database.

Requires the optional extra::

    pip install "fieldnote[pgvector]"
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from ..schema import Chunk
from .base import IndexedRecord


class PgVectorSpaceStore:
    def __init__(self, space: str, dim: int, dsn: str):
        import psycopg
        from pgvector.psycopg import register_vector

        self.space = space
        self.dim = dim
        self.conn = psycopg.connect(dsn)
        register_vector(self.conn)
        self.table = f"space_{space}"
        self._init_schema()

    def _init_schema(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
                    chunk_id    TEXT PRIMARY KEY,
                    modality    TEXT NOT NULL,
                    source_id   TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    doc_title   TEXT NOT NULL,
                    page        INTEGER,
                    vector      vector({self.dim}) NOT NULL,
                    payload     JSONB NOT NULL
                )
                """
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.table}_hnsw "
                f"ON {self.table} USING hnsw (vector vector_cosine_ops)"
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.table}_modality ON {self.table}(modality)"
            )
            self.conn.commit()

    def add(self, records: list[IndexedRecord]) -> None:
        rows = []
        for rec in records:
            rows.append(
                (
                    rec.chunk.chunk_id,
                    rec.chunk.modality.value,
                    rec.chunk.source_id,
                    rec.chunk.source_kind.value,
                    rec.chunk.doc_title,
                    rec.chunk.page,
                    np.asarray(rec.vector, dtype=np.float32),
                    json.dumps(rec.chunk.to_dict(), ensure_ascii=False),
                )
            )
        if not rows:
            return
        with self.conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO {self.table} "
                "(chunk_id, modality, source_id, source_kind, doc_title, page, vector, payload) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (chunk_id) DO UPDATE SET vector = EXCLUDED.vector, payload = EXCLUDED.payload",
                rows,
            )
            self.conn.commit()

    def search(
        self, vector: np.ndarray, top_k: int, filters: dict[str, Any] | None = None
    ) -> list[tuple[IndexedRecord, float]]:
        clauses = ["TRUE"]
        clause_params: list[Any] = []
        for key, want in (filters or {}).items():
            if want is None:
                continue
            if isinstance(want, (list, tuple, set)):
                clauses.append(f"payload ->> %s = ANY(%s)")
                clause_params.extend([key, list(want)])
            elif isinstance(want, str) and want.startswith("contains:"):
                clauses.append("payload ->> %s ILIKE %s")
                clause_params.extend([key, f"%{want.split(':', 1)[1]}%"])
            else:
                clauses.append(f"payload ->> %s = %s")
                clause_params.extend([key, want])

        query_vec = np.asarray(vector, dtype=np.float32)
        # placeholder order in the SQL: distance, filters..., distance, limit
        sql = (
            f"SELECT payload, 1 - (vector <=> %s) AS score FROM {self.table} "
            f"WHERE {' AND '.join(clauses)} ORDER BY vector <=> %s LIMIT %s"
        )
        params: list[Any] = [query_vec, *clause_params, query_vec, top_k]
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        out: list[tuple[IndexedRecord, float]] = []
        for payload, score in rows:
            chunk = Chunk.from_dict(payload)
            out.append((IndexedRecord(chunk=chunk, space=self.space, vector=np.zeros(self.dim)), float(score)))
        return out

    def count(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {self.table}")
            return int(cur.fetchone()[0])

    def save(self) -> None:
        self.conn.commit()

    def load(self) -> None:
        self._init_schema()

    def close(self) -> None:
        self.conn.close()
