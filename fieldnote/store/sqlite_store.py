"""SQLite-backed vector store.

Zero infrastructure, works anywhere, and brute-force cosine search over numpy
is genuinely faster than an ANN index at this scale (thousands of vectors).
It is the default backend so that `fieldnote eval` works on a fresh clone with
nothing but `pip install`.

Filters are applied in Python after the inner product, which keeps the schema
simple and the behaviour identical to what pgvector/Qdrant do with a WHERE
clause.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

import numpy as np

from ..schema import Chunk
from .base import IndexedRecord


class SqliteSpaceStore:
    """One table per vector space."""

    def __init__(self, space: str, dim: int, db_path: str | Path = "fieldnote.db"):
        self.space = space
        self.dim = dim
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Each space has its own connection and each space is searched by one
        # thread at a time, but the search runs in a pool, so the connection
        # must not be pinned to the thread that created it.
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.lock = threading.Lock()
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS space_{self.space} (
                chunk_id   TEXT PRIMARY KEY,
                modality   TEXT NOT NULL,
                source_id  TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                doc_title  TEXT NOT NULL,
                page       INTEGER,
                vector     BLOB NOT NULL,
                payload    TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self.space}_modality ON space_{self.space}(modality)"
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self.space}_source ON space_{self.space}(source_id)"
        )
        self.conn.commit()

    # --- writes -----------------------------------------------------------
    def add(self, records: list[IndexedRecord]) -> None:
        rows = []
        for rec in records:
            payload = rec.chunk.to_dict()
            rows.append(
                (
                    rec.chunk.chunk_id,
                    rec.chunk.modality.value,
                    rec.chunk.source_id,
                    rec.chunk.source_kind.value,
                    rec.chunk.doc_title,
                    rec.chunk.page,
                    np.asarray(rec.vector, dtype=np.float32).tobytes(),
                    json.dumps(payload, ensure_ascii=False),
                )
            )
        if not rows:
            return
        with self.lock:
            self.conn.executemany(
                f"INSERT OR REPLACE INTO space_{self.space} "
                "(chunk_id, modality, source_id, source_kind, doc_title, page, vector, payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            self.conn.commit()

    # --- reads ------------------------------------------------------------
    def _all(self) -> tuple[list[str], np.ndarray, list[dict[str, Any]]]:
        with self.lock:
            cur = self.conn.execute(
                f"SELECT chunk_id, vector, payload FROM space_{self.space}"
            )
            rows = cur.fetchall()
        ids: list[str] = []
        vectors: list[np.ndarray] = []
        payloads: list[dict[str, Any]] = []
        for chunk_id, blob, payload in rows:
            ids.append(chunk_id)
            vectors.append(np.frombuffer(blob, dtype=np.float32))
            payloads.append(json.loads(payload))
        if not vectors:
            return [], np.zeros((0, self.dim), dtype=np.float32), []
        mat = np.vstack(vectors)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        mat = mat / np.clip(norms, 1e-8, None)
        return ids, mat.astype(np.float32), payloads

    def search(
        self, vector: np.ndarray, top_k: int, filters: dict[str, Any] | None = None
    ) -> list[tuple[IndexedRecord, float]]:
        ids, mat, payloads = self._all()
        if not ids:
            return []
        query = np.asarray(vector, dtype=np.float32)
        qn = np.linalg.norm(query)
        if qn > 1e-8:
            query = query / qn
        scores = mat @ query

        order = np.argsort(-scores)[: max(top_k * 4, top_k)]
        results: list[tuple[IndexedRecord, float]] = []
        for idx in order:
            payload = payloads[idx]
            if filters and not _matches(payload, filters):
                continue
            chunk = Chunk.from_dict(payload)
            results.append((IndexedRecord(chunk=chunk, space=self.space, vector=mat[idx]), float(scores[idx])))
            if len(results) >= top_k:
                break
        return results

    def count(self) -> int:
        with self.lock:
            cur = self.conn.execute(f"SELECT COUNT(*) FROM space_{self.space}")
            return int(cur.fetchone()[0])

    def save(self) -> None:
        with self.lock:
            self.conn.commit()

    def load(self) -> None:
        self._init_schema()

    def close(self) -> None:
        with self.lock:
            self.conn.close()


def _matches(payload: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, want in filters.items():
        if want is None:
            continue
        got = payload.get(key)
        if isinstance(want, (list, tuple, set)):
            if got not in want:
                return False
        elif isinstance(want, str) and want.startswith("contains:"):
            needle = want.split(":", 1)[1].lower()
            if needle not in str(got or "").lower():
                return False
        elif got != want:
            return False
    return True
