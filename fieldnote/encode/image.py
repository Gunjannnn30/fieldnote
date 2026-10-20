"""Image encoder: CLIP (or SigLIP) image tower, plus its paired text tower.

Two things matter here:

1. The image tower embeds **pixels**, never a caption. A caption is a lossy
   summary of a picture; a chart's axis values only exist in the pixels.
2. The paired text tower embeds the *query* into the same joint space, which is
   the only reason a typed question can retrieve an image at all.
"""

from __future__ import annotations

import numpy as np
import torch
from PIL import Image

from ..config import settings


def _load_image(path: str) -> Image.Image:
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


class ImageEncoder:
    """CLIP/SigLIP joint space: 512-d for ViT-B/32, 768-d for SigLIP-base."""

    name = "clip"
    modality = "image"

    def __init__(self, model_name: str | None = None, device: str | None = None):
        self.model_name = model_name or settings.image_model
        self.device = device or settings.device
        self.is_siglip = "siglip" in self.model_name.lower()
        self.dim = 768 if self.is_siglip else 512

        if self.is_siglip:
            from transformers import AutoProcessor, SiglipModel

            self.processor = AutoProcessor.from_pretrained(self.model_name)
            self.model = SiglipModel.from_pretrained(self.model_name)
        else:
            from transformers import CLIPModel, CLIPProcessor

            self.processor = CLIPProcessor.from_pretrained(self.model_name)
            self.model = CLIPModel.from_pretrained(self.model_name)

        self.model.to(self.device).eval()
        self.model.eval()

    # --- images -----------------------------------------------------------
    def encode(self, paths: list[str]) -> np.ndarray:
        if not paths:
            return np.zeros((0, self.dim), dtype=np.float32)
        out: list[np.ndarray] = []
        for i in range(0, len(paths), 8):
            batch = [_load_image(p) for p in paths[i : i + 8]]
            inputs = self.processor(images=batch, return_tensors="pt").to(self.device)
            with torch.inference_mode():
                feats = self.model.get_image_features(**inputs)
            out.append(self._norm(_as_tensor(feats)))
        return np.concatenate(out, axis=0)

    # --- query side -------------------------------------------------------
    def encode_query(self, query: str) -> np.ndarray:
        """Embed a text query into the CLIP joint space.

        CLIP's text tower is trained on alt-text, not on technical manuals, so
        a long question dilutes the signal badly. We therefore hand the tower a
        keyword-stripped version of the query.
        """
        text = _strip_question_to_keywords(query)
        return self.encode_texts([text])[0]

    def encode_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        if self.is_siglip:
            inputs = self.processor(
                text=texts,
                padding="max_length",
                max_length=64,
                truncation=True,
                return_tensors="pt",
            ).to(self.device)
        else:
            inputs = self.processor(
                text=texts, padding=True, truncation=True, max_length=77, return_tensors="pt"
            ).to(self.device)
        with torch.inference_mode():
            feats = self.model.get_text_features(**inputs)
        return self._norm(_as_tensor(feats))

    @staticmethod
    def _norm(feats: torch.Tensor) -> np.ndarray:
        feats = feats / feats.norm(p=2, dim=-1, keepdim=True).clamp_min(1e-8)
        return feats.detach().cpu().numpy().astype(np.float32)


def _as_tensor(out) -> torch.Tensor:
    """transformers >=5 returns a ModelOutput from get_*_features, not a tensor."""
    if isinstance(out, torch.Tensor):
        return out
    for attr in ("image_embeds", "text_embeds", "pooler_output", "last_hidden_state"):
        value = getattr(out, attr, None)
        if isinstance(value, torch.Tensor):
            return value
    if isinstance(out, dict):
        for attr in ("image_embeds", "text_embeds", "pooler_output", "last_hidden_state"):
            value = out.get(attr)
            if isinstance(value, torch.Tensor):
                return value
    if isinstance(out, (tuple, list)):
        return out[0]
    raise TypeError(f"cannot pull a tensor out of {type(out)!r}")


_QUESTION_PREFIXES = (
    "why does",
    "why is",
    "why do",
    "why are",
    "what is",
    "what's",
    "what are",
    "how do",
    "how does",
    "how much",
    "when should",
    "when does",
    "which",
    "can you tell me",
    "tell me",
    "please",
)


def _strip_question_to_keywords(query: str) -> str:
    """Turn a conversational question into a CLIP-friendly keyword phrase.

    CLIP was trained on captions. Feeding it "why does unit 7 keep tripping on
    high pressure" wastes most of the 77-token budget on interrogative
    scaffolding. This keeps the domain nouns.
    """
    q = " ".join(query.lower().split())
    for prefix in _QUESTION_PREFIXES:
        if q.startswith(prefix):
            q = q[len(prefix) :].strip()
            break
    q = q.rstrip("?.! ")
    return q or query.lower()
