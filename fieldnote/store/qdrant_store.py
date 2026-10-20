"""Qdrant backend.

Three collections (text / image / audio), each with its own vector size and
its own payload index. The modality filter is a Qdrant payload condition.

Requires the optional extra::

    pip install "fieldnote[qdrant]"
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..schema import Chunk
from .base import IndexedRecord


class QdrantSpaceStore:
    def __init__(self, space: str, dim: int, url: str, collection: str):
        from qdrant_client import QdrantClient
        from qdrant_client.http import models

        self.space = space
        self.dim = dim
        self.client = QdrantClient(url=url)
        self.collection = f"{collection}_{space}"
        self._models = models

        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(
                    size=dim, distance=models.Distance.COSINE
                ),
            )
        for field_name in ("modality", "source_kind", "source_id", "doc_title"):
            self.client.create_payload_index(
                collection_name=self.collection,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

    def add(self, records: list[IndexedRecord]) -> None:
        from qdrant_client.http import models

        points = []
        for rec in records:
            payload = rec.chunk.to_dict()
            payload.update(rec.filters)
            points.append(
                models.PointStruct(
                    id=self._stable_id(rec.chunk.chunk_id),
                    vector=np.asarray(rec.vector, dtype=np.float32).tolist(),
                    payload=payload,
                )
            )
        if points:
            self.client.upsert(collection_name=self.collection, points=points)

    def search(
        self, vector: np.ndarray, top_k: int, filters: dict[str, Any] | None = None
    ) -> list[tuple[IndexedRecord, float]]:
        conditions = []
        for key, want in (filters or {}).items():
            if want is None:
                continue
            if isinstance(want, (list, tuple, set)):
                conditions.append(
                    self._models.FieldCondition(
                        key=key, match=self._models.MatchAny(any=list(want))
                    )
                )
            elif isinstance(want, str) and want.startswith("contains:"):
                conditions.append(
                    self._models.FieldCondition(
                        key=key,
                        match=self._models.TextMatch(
                            text=want.split(":", 1)[1],
                        ),
                    )
                )
            else:
                conditions.append(
                    self._models.FieldCondition(key=key, match=self._models.MatchValue(value=want))
                )

        query_filter = self._models.Filter(must=conditions) if conditions else None
        hits = self.client.query_points(
            collection_name=self.collection,
            query=np.asarray(vector, dtype=np.float32).tolist(),
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        ).points

        out: list[tuple[IndexedRecord, float]] = []
        for hit in hits:
            payload = dict(hit.payload or {})
            chunk = Chunk.from_dict(payload)
            out.append((IndexedRecord(chunk=chunk, space=self.space, vector=np.zeros(self.dim)), float(hit.score)))
        return out

    def count(self) -> int:
        return int(self.client.count(collection_name=self.collection).count)

    def save(self) -> None:
        return None

    def load(self) -> None:
        return None

    def close(self) -> None:
        self.client.close()

    @staticmethod
    def _stable_id(chunk_id: str) -> int:
        import hashlib

        return int.from_bytes(hashlib.sha1(chunk_id.encode()).digest()[:8], "big", signed=False)
