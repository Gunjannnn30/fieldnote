"""Vision-language engine (optional, CPU-friendly by default).

Two jobs:

1. **Cross-encoder scoring over (question, image).** We ask the model whether
   the figure answers the question and read the yes/no token probabilities.
   Unlike a joint-space cosine, the image tokens and the question tokens
   attend to each other - this is a real cross-attention reranker.
2. **Answer synthesis.** The model reads the retrieved crops and the text
   evidence and writes the answer a technician can act on.

The model is swappable: set ``FIELDNOTE_VLM_MODEL`` to any local
vision-language model, or point the code at an OpenAI-compatible endpoint.
"""

from __future__ import annotations

import functools
import re

from ..config import settings


@functools.lru_cache(maxsize=1)
def _load():
    import torch
    from transformers import AutoProcessor

    model_id = settings.vlm_model
    processor = AutoProcessor.from_pretrained(model_id)

    model = None
    for attr in ("AutoModelForImageTextToText", "AutoModelForVision2Seq"):
        try:
            import transformers

            cls = getattr(transformers, attr)
            model = cls.from_pretrained(model_id, dtype=torch.float32)
            break
        except Exception:  # noqa: BLE001
            continue
    if model is None:
        raise RuntimeError(f"could not load a vision-language model for {model_id}")

    model.to(settings.device).eval()
    return processor, model


class VLMEngine:
    def __init__(self, model_id: str | None = None):
        self.model_id = model_id or settings.vlm_model
        self._processor = None
        self._model = None

    # ------------------------------------------------------------------
    @property
    def processor(self):
        if self._processor is None:
            self._processor, self._model = _load()
        return self._processor

    @property
    def model(self):
        if self._model is None:
            self._processor, self._model = _load()
        return self._model

    # ------------------------------------------------------------------
    def _chat(self, question: str, image_paths: list[str], texts: list[str]) -> str:
        from PIL import Image

        content: list[dict] = []
        for _path in image_paths:
            content.append({"type": "image"})
        body = "\n".join(texts).strip()
        prompt = question.strip()
        if body:
            prompt = f"{prompt}\n\nContext:\n{body}"
        content.append({"type": "text", "text": prompt})

        messages = [{"role": "user", "content": content}]
        processor = self.processor
        text = processor.apply_chat_template(messages, add_generation_prompt=True)

        images = []
        for path in image_paths:
            img = Image.open(path)
            if img.mode != "RGB":
                img = img.convert("RGB")
            images.append(img)

        inputs = processor(text=text, images=images or None, return_tensors="pt")
        inputs = {k: (v.to(settings.device) if hasattr(v, "to") else v) for k, v in inputs.items()}
        return inputs

    # ------------------------------------------------------------------
    def answer(
        self,
        question: str,
        image_paths: list[str] | None = None,
        texts: list[str] | None = None,
        *,
        max_new_tokens: int | None = None,
    ) -> str:
        import torch

        processor = self.processor
        inputs = self._chat(question, image_paths or [], texts or [])
        with torch.inference_mode():
            out = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens or settings.vlm_max_new_tokens,
                do_sample=False,
            )
        generated = out[0][inputs["input_ids"].shape[1] :]
        return processor.decode(generated, skip_special_tokens=True).strip()

    # ------------------------------------------------------------------
    def score_image_against_text(self, query: str, image_path: str) -> float:
        """Cross-attention relevance of an image to a query, in [0, 1]."""
        import torch

        processor = self.processor
        prompt = (
            "Question: " + query.strip() + "\n"
            "Does this image contain the information needed to answer the question? "
            "Reply with exactly one word: Yes or No."
        )
        content = [{"type": "image"}, {"type": "text", "text": prompt}]
        messages = [{"role": "user", "content": content}]
        chat = processor.apply_chat_template(messages, add_generation_prompt=True)

        from PIL import Image

        img = Image.open(image_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        inputs = processor(text=chat, images=[img], return_tensors="pt")
        inputs = {k: (v.to(settings.device) if hasattr(v, "to") else v) for k, v in inputs.items()}

        tokenizer = processor.tokenizer
        yes_ids = tokenizer.encode("Yes", add_special_tokens=False)
        no_ids = tokenizer.encode("No", add_special_tokens=False)
        if not yes_ids or not no_ids:
            return 0.5

        with torch.inference_mode():
            logits = self.model(**inputs).logits[0, -1]
        yes_logit = float(logits[yes_ids[0]])
        no_logit = float(logits[no_ids[0]])

        import math

        m = max(yes_logit, no_logit)
        ey = math.exp(yes_logit - m)
        en = math.exp(no_logit - m)
        return ey / (ey + en)

    # ------------------------------------------------------------------
    @staticmethod
    def clean(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()
