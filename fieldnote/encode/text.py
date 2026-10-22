"""Text encoder: mean pooling over a transformer, then L2 normalisation.

This is what ``sentence-transformers`` does for ``all-MiniLM-L6-v2`` and a
handful of other models - Transformer -> Pooling(mean) -> Normalize - and it
is implemented here directly on ``transformers``.

Why not just use ``sentence-transformers``? Two reasons.

* It imports ``scikit-learn`` for a single ``cos_sim`` utility, and
  scikit-learn ships compiled extensions. On a locked-down Windows host an
  application-control policy can refuse to load them, and the whole system
  stops working for a reason that has nothing to do with retrieval.
* The Docker image gets smaller and the import gets faster, and there is one
  fewer thing to go wrong on a technician's laptop.

The pooling configuration is read from the model's own
``sentence_bert_config.json`` when it is available, so this stays faithful to
whatever model is configured rather than assuming a particular one.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..config import settings


def _model_files(model_name: str) -> dict:
    """Read the sentence-transformers config from the local cache, if present."""
    out: dict = {}
    try:
        from huggingface_hub import try_to_load_from_cache
    except Exception:  # noqa: BLE001
        return out
    for filename in ("sentence_bert_config.json", "1_Pooling/config.json"):
        try:
            path = try_to_load_from_cache(model_name, filename)
        except Exception:  # noqa: BLE001
            path = None
        if not path:
            continue
        p = Path(path)
        if not p.is_file():
            continue
        try:
            out.update(json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
    return out


class TextEncoder:
    """384-d MiniLM space used for manual text, transcripts and OCR strings."""

    name = "minilm"
    modality = "text"

    def __init__(self, model_name: str | None = None, device: str | None = None):
        from transformers import AutoModel, AutoTokenizer

        self.model_name = model_name or settings.text_model
        self.device = device or settings.device
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModel.from_pretrained(self.model_name).to(self.device).eval()
        self.dim = int(self.model.config.hidden_size)

        st_config = _model_files(self.model_name)
        self.max_length = int(st_config.get("max_seq_length", 256))
        self.use_mean_pooling = bool(st_config.get("pooling_mode_mean_tokens", True))
        self.use_cls = bool(st_config.get("pooling_mode_cls_token", False))
        self.use_max_pooling = bool(st_config.get("pooling_mode_max_tokens", False))

    # ------------------------------------------------------------------
    def encode(self, texts: list[str]) -> np.ndarray:
        import torch

        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)

        out: list[np.ndarray] = []
        for i in range(0, len(texts), 32):
            batch = texts[i : i + 32]
            encoded = self.tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            ).to(self.device)
            with torch.inference_mode():
                hidden = self.model(**encoded).last_hidden_state
            pooled = self._pool(hidden, encoded["attention_mask"])
            out.append(pooled.cpu().numpy().astype(np.float32))
        return np.concatenate(out, axis=0)

    def _pool(self, hidden, mask):
        import torch

        mask = mask.unsqueeze(-1).to(hidden.dtype)
        if self.use_cls:
            pooled = hidden[:, 0]
        elif self.use_max_pooling:
            pooled = hidden.masked_fill(mask == 0, -1e4).max(dim=1).values
        else:
            summed = (hidden * mask).sum(dim=1)
            counts = mask.sum(dim=1).clamp(min=1e-9)
            pooled = summed / counts
        return torch.nn.functional.normalize(pooled, p=2, dim=1)

    def encode_query(self, query: str) -> np.ndarray:
        return self.encode([query])[0]
