"""Text encoder: sentence-transformers MiniLM. Owns the `text` modality space."""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer

from ..config import settings


class TextEncoder:
    """384-d MiniLM space used for manual text, transcripts and OCR strings."""

    name = "minilm"
    modality = "text"

    def __init__(self, model_name: str | None = None, device: str | None = None):
        self.model_name = model_name or settings.text_model
        self.device = device or settings.device
        self.model = SentenceTransformer(self.model_name, device=self.device)
        self.dim = int(
            self.model.get_embedding_dimension()
            if hasattr(self.model, "get_embedding_dimension")
            else self.model.get_sentence_embedding_dimension()
        )

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vecs = self.model.encode(
            texts,
            batch_size=32,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vecs, dtype=np.float32)

    def encode_query(self, query: str) -> np.ndarray:
        return self.encode([query])[0]
