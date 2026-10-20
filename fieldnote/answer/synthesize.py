"""Answer synthesis.

Two implementations:

``extractive`` (default)
    Deterministic. Picks the best-supported candidate value out of the
    retrieved evidence and states it with its context. On a CPU-only field
    laptop this is what you actually want, and it is fast enough to hit the
    6-second p95 gate.

``vlm``
    Hands the retrieved crops to a vision-language model and asks it to write
    the answer. Slower and less deterministic, and the honest way to read a
    chart that has no labels.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import settings
from ..schema import Answer, Citation, Modality, ScoredChunk
from .citations import build_citations
from .units import EvidenceUnit, build_units, chunk_relevance_map, pick_answer_value, score_units

UNANSWERABLE_THRESHOLD = -6.0

_VISUAL_HINTS = ("chart", "graph", "curve", "diagram", "schematic", "photo", "image",
                  "picture", "label", "plate", "figure", "shown", "display")
_AUDIO_HINTS = ("call", "said", "spoke", "talked", "recorded", "conversation", "phone")


def _modality_bonus(question: str) -> dict[str, float]:
    q = question.lower()
    bonus = {"text": 0.0, "image": 0.0, "audio": 0.0}
    if any(h in q for h in _VISUAL_HINTS):
        bonus["image"] = 0.35
    if any(h in q for h in _AUDIO_HINTS):
        bonus["audio"] = 0.35
    return bonus


class Synthesizer:
    name = "base"

    def synthesize(
        self,
        question: str,
        scored: list[ScoredChunk],
        *,
        latency: dict[str, float] | None = None,
    ) -> Answer:
        raise NotImplementedError


class ExtractiveSynthesizer(Synthesizer):
    """Deterministic answer assembled from the retrieved evidence."""

    name = "extractive"

    def __init__(self, threshold: float = UNANSWERABLE_THRESHOLD, citation_limit: int = 3):
        self.threshold = threshold
        self.citation_limit = citation_limit

    def synthesize(
        self,
        question: str,
        scored: list[ScoredChunk],
        *,
        latency: dict[str, float] | None = None,
        units: list | None = None,
    ) -> Answer:
        latency = latency or {}
        focus = None
        if units:
            focus = units[0].chunk_id
        citations = build_citations(scored, limit=self.citation_limit, focus_chunk_id=focus)
        hits = {m: 0 for m in ("text", "image", "audio")}
        for c in scored:
            hits[c.chunk.modality.value] = hits.get(c.chunk.modality.value, 0) + 1

        if not scored:
            return Answer(
                question=question,
                answer="No supporting evidence was found in the corpus for this question.",
                citations=[],
                modality_hits=hits,
                latency_ms=latency,
                answerable=False,
                unanswerable_reason="empty candidate set",
            )

        if units is None:
            units = self._score_units(question, scored)
        best = units[0] if units else None

        if best is None or best.score < self.threshold:
            return Answer(
                question=question,
                answer=(
                    "I could not find evidence in the corpus that answers this question. "
                    "The retrieved material does not contain a supporting page, figure or call segment."
                ),
                citations=citations,
                modality_hits=hits,
                latency_ms=latency,
                answerable=False,
                unanswerable_reason=f"best evidence score {best.score:.3f} < {self.threshold:.3f}"
                if best
                else "no candidates",
            )

        answer = _format_answer(best)
        return Answer(
            question=question,
            answer=answer,
            citations=citations,
            modality_hits=hits,
            latency_ms=latency,
            answerable=True,
        )

    @staticmethod
    def _score_units(question: str, scored: list[ScoredChunk]) -> list:
        from ..encode.registry import get_cross_encoder
        from .units import build_units, chunk_relevance_map, score_units

        units = build_units(scored)
        return score_units(
            question,
            units,
            cross_encoder=get_cross_encoder(),
            chunk_scores=chunk_relevance_map(scored),
            modality_bonus=_modality_bonus(question),
        )


def _format_answer(unit: EvidenceUnit) -> str:
    text = re.sub(r"\s+", " ", unit.text).strip()
    if unit.kind == "image":
        # Prefer the bare value when the picture states exactly one, but keep
        # the label that goes with it so a technician can find it on the page.
        value = pick_answer_value(unit)
        if value != text and len(value) < len(text):
            return f"{value} ({text})"
    return text


class VLMSynthesizer(Synthesizer):
    """Vision-language synthesis over the retrieved crops."""

    name = "vlm"

    def __init__(self, max_images: int = 3, citation_limit: int = 3):
        self.max_images = max_images
        self.citation_limit = citation_limit

    def synthesize(
        self,
        question: str,
        scored: list[ScoredChunk],
        *,
        latency: dict[str, float] | None = None,
        units: list | None = None,
    ) -> Answer:
        latency = dict(latency or {})
        from .vlm import VLMEngine

        focus = units[0].chunk_id if units else None
        citations = build_citations(scored, limit=self.citation_limit, focus_chunk_id=focus)
        hits = {m: 0 for m in ("text", "image", "audio")}
        for c in scored:
            hits[c.chunk.modality.value] = hits.get(c.chunk.modality.value, 0) + 1

        image_paths: list[str] = []
        for cand in scored:
            if cand.chunk.modality is Modality.IMAGE and cand.chunk.crop_path:
                if cand.chunk.crop_path not in image_paths:
                    image_paths.append(cand.chunk.crop_path)
            if len(image_paths) >= self.max_images:
                break

        texts: list[str] = []
        for cand in scored:
            if cand.chunk.modality in (Modality.TEXT, Modality.AUDIO) and cand.chunk.text:
                texts.append(f"[{cand.chunk.doc_title}] {cand.chunk.text[:500]}")

        engine = VLMEngine()
        raw = engine.answer(question, image_paths, texts)
        answer = _clean(raw)
        return Answer(
            question=question,
            answer=answer or "No answer could be synthesised.",
            citations=citations,
            modality_hits=hits,
            latency_ms=latency,
            answerable=bool(answer),
        )


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def build_synthesizer(kind: str | None = None, **kwargs) -> Synthesizer:
    kind = (kind or settings.synthesis).lower()
    if kind == "extractive":
        return ExtractiveSynthesizer(**kwargs)
    if kind == "vlm":
        return VLMSynthesizer(**kwargs)
    raise ValueError(f"unknown synthesizer: {kind}")
