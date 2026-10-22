"""Cross-encoder: judges a question and a passage together.

Same model, same behaviour as ``sentence_transformers.CrossEncoder``, written
directly on ``transformers`` so that the runtime does not need scikit-learn
(see ``text.py`` for why that matters).

Two details have to match exactly or the scores shift:

* **The activation.** ``sentence-transformers`` applies ``nn.Sigmoid()`` to a
  single-label model by default - but a model may override that. This
  cross-encoder's config sets
  ``sbert_ce_default_activation_function = torch.nn.modules.linear.Identity``,
  so the score is the **raw logit**. The config is read at load time so the
  right behaviour follows the model rather than a guess.
* **The output shape.** A single-label model returns ``(batch, 1)``; the score
  for a pair is that one logit.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..config import settings


def _activation_kind(model_name: str) -> str:
    """'sigmoid' or 'identity', following the model's own configuration."""
    try:
        from huggingface_hub import try_to_load_from_cache
    except Exception:  # noqa: BLE001
        return "sigmoid"
    try:
        path = try_to_load_from_cache(model_name, "config.json")
    except Exception:  # noqa: BLE001
        return "sigmoid"
    if not path or not Path(path).is_file():
        return "sigmoid"
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return "sigmoid"
    override = config.get("sbert_ce_default_activation_function")
    if isinstance(override, str) and "Identity" in override:
        return "identity"
    return "sigmoid"


class CrossEncoderScorer:
    """Scores (question, passage) pairs. Higher is more relevant."""

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
        max_length: int = 384,
    ):
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.model_name = model_name or settings.cross_encoder_model
        self.device = device or settings.device
        self.max_length = max_length
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = (
            AutoModelForSequenceClassification.from_pretrained(self.model_name)
            .to(self.device)
            .eval()
        )
        self.num_labels = int(self.model.config.num_labels)
        self.activation = _activation_kind(self.model_name)

    # ------------------------------------------------------------------
    def predict(
        self,
        pairs: list[tuple[str, str]],
        batch_size: int = 16,
        show_progress_bar: bool = False,
        **_: object,
    ) -> list[float]:
        """Score (question, passage) pairs. Higher is more relevant.

        The signature mirrors ``sentence_transformers.CrossEncoder.predict`` so
        it is a drop-in replacement.
        """
        import torch

        scores: list[float] = []
        for i in range(0, len(pairs), batch_size):
            batch = pairs[i : i + batch_size]
            encoded = self.tokenizer(
                [p[0] for p in batch],
                [p[1] for p in batch],
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            ).to(self.device)
            with torch.inference_mode():
                logits = self.model(**encoded).logits
            if logits.shape[-1] == 1:
                values = logits[:, 0]
            else:
                values = logits[:, -1]
            if self.activation == "sigmoid":
                values = torch.sigmoid(values)
            scores.extend(values.float().cpu().tolist())
        return scores
