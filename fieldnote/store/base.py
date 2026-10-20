"""Vector store interfaces.

The key structural decision: **each modality lives in its own vector space**.

MiniLM (384-d), CLIP (512-d) and CLAP (512-d) are not comparable to one
another, so they get separate collections. A search over the image collection
is therefore implicitly modality-filtered - the filter is enforced by the
schema, not by a WHERE clause someone might forget.

Above them sits a thin `MultiSpaceStore` that owns one sub-store per space and
knows which encoder query vector belongs in which space.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from ..schema import Chunk, Modality

SPACE_FOR_MODALITY = {
    Modality.TEXT: "text",
    Modality.IMAGE: "image",
    Modality.AUDIO: "audio",
}


@dataclass
class IndexedRecord:
    """A chunk plus its vector, and the metadata needed to filter it."""

    chunk: Chunk
    space: str
    vector: np.ndarray
    filters: dict[str, Any] = field(default_factory=dict)

    @property
    def modality(self) -> Modality:
        return self.chunk.modality


class SpaceStore(Protocol):
    """One vector space's worth of records."""

    space: str
    dim: int

    def add(self, records: list[IndexedRecord]) -> None: ...
    def search(
        self, vector: np.ndarray, top_k: int, filters: dict[str, Any] | None = None
    ) -> list[tuple[IndexedRecord, float]]: ...
    def save(self) -> None: ...
    def load(self) -> None: ...
    def count(self) -> int: ...


class MultiSpaceStore:
    """Fan-out across per-modality spaces with one shared chunk registry."""

    def __init__(self, spaces: dict[str, SpaceStore]):
        self.spaces = spaces

    def add(self, records: list[IndexedRecord]) -> None:
        by_space: dict[str, list[IndexedRecord]] = {}
        for rec in records:
            by_space.setdefault(rec.space, []).append(rec)
        for space, recs in by_space.items():
            if space not in self.spaces:
                raise KeyError(f"no store for space '{space}'")
            self.spaces[space].add(recs)

    def search_space(
        self, space: str, vector: np.ndarray, top_k: int, filters: dict[str, Any] | None = None
    ) -> list[tuple[IndexedRecord, float]]:
        return self.spaces[space].search(vector, top_k, filters)

    def save(self) -> None:
        for store in self.spaces.values():
            store.save()

    def load(self) -> None:
        for store in self.spaces.values():
            store.load()

    def count(self) -> dict[str, int]:
        return {name: store.count() for name, store in self.spaces.items()}
