"""Lazy, cached access to the encoders.

Models are heavy; the CLI may run ingest-only or query-only, so nothing is
loaded until it is asked for.
"""

from __future__ import annotations

import functools

from ..config import settings
from ..schema import Modality
from .audio import AudioEncoder
from .cross_encoder import CrossEncoderScorer
from .image import ImageEncoder
from .text import TextEncoder


@functools.lru_cache(maxsize=1)
def get_text_encoder() -> TextEncoder:
    return TextEncoder()


@functools.lru_cache(maxsize=1)
def get_image_encoder() -> ImageEncoder:
    return ImageEncoder()


@functools.lru_cache(maxsize=1)
def get_audio_encoder() -> AudioEncoder:
    return AudioEncoder()


@functools.lru_cache(maxsize=1)
def get_cross_encoder() -> CrossEncoderScorer:
    from .cross_encoder import CrossEncoderScorer

    return CrossEncoderScorer()


@functools.lru_cache(maxsize=1)
def get_captioner():
    """Blip captioner - used *only* to build the caption-only baseline."""
    import torch
    from transformers import BlipForConditionalGeneration, BlipProcessor

    proc = BlipProcessor.from_pretrained(settings.caption_model)
    model = BlipForConditionalGeneration.from_pretrained(settings.caption_model).to(settings.device).eval()
    del torch
    return _BlipCaptioner(proc, model, settings.device)


class _BlipCaptioner:
    def __init__(self, processor, model, device):
        self.processor = processor
        self.model = model
        self.device = device

    def caption(self, image_path: str, prompt: str | None = None) -> str:
        import torch
        from PIL import Image

        img = Image.open(image_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        kwargs: dict = {"images": img, "return_tensors": "pt"}
        if prompt:
            kwargs["text"] = prompt
        inputs = self.processor(**kwargs).to(self.device)
        with torch.inference_mode():
            out = self.model.generate(**inputs, max_new_tokens=40, num_beams=1)
        return self.processor.decode(out[0], skip_special_tokens=True).strip()


def get_encoder_for(modality: Modality):
    return {
        Modality.TEXT: get_text_encoder,
        Modality.IMAGE: get_image_encoder,
        Modality.AUDIO: get_audio_encoder,
    }[modality]()
