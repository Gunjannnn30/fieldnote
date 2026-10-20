"""Encoder interfaces.

Every modality gets its own encoder pair. That is the whole point of the
project, so the abstractions here are deliberately *not* collapsed into one
"embed(text) -> vector" function.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class Encoder(Protocol):
    """Embeds a modality into its own vector space."""

    name: str
    dim: int

    def encode(self, items: list) -> np.ndarray:  # pragma: no cover - protocol
        ...


@runtime_checkable
class QueryEncoder(Protocol):
    """A modality encoder that can also embed a *text query* into the same space.

    This is what lets a typed question reach an image index at all. CLIP's text
    tower shares a space with its image tower; CLAP's text tower shares a space
    with its audio tower. Without this, the query never reaches half the index.
    """

    name: str
    dim: int

    def encode_query(self, query: str) -> np.ndarray:  # pragma: no cover - protocol
        ...
