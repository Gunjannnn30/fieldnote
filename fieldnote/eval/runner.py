"""Eval runner.

Runs the same 40 questions through two systems that differ in exactly one
way - whether the pictures stay pictures or get flattened into captions - and
reports the difference as a table.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..answer.synthesize import Synthesizer, build_synthesizer
from ..baseline.caption_only import build_caption_baseline
from ..config import settings
from ..retrieve.pipeline import Retriever
from ..schema import Chunk
from ..store import build_store, encode_chunks
from .dataset import EvalQuestion, build_eval_set, picture_only, text_only, verify_unanswerable
from .metrics import Grade, grade, latency_stats


@dataclass
class QuestionResult:
    qid: str
    question: str
    expected: str
    produced: str
    grade: Grade
    kind: str
    latency_ms: float
    top_source_id: str | None = None
    top_page: int | None = None
    top_modality: str | None = None
    citation_count: int = 0
    citation_has_page: bool = False
    citation_has_crop: bool = False
    citation_page_correct: bool = False
    citation_modality: str | None = None
    answerable: bool = True
    stage_ms: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "qid": self.qid,
            "question": self.question,
            "expected": self.expected,
            "produced": self.produced,
            "grade": self.grade.to_dict(),
            "kind": self.kind,
            "latency_ms": round(self.latency_ms, 1),
            "top_source_id": self.top_source_id,
            "top_page": self.top_page,
            "top_modality": self.top_modality,
            "citation_count": self.citation_count,
            "citation_has_page": self.citation_has_page,
            "citation_has_crop": self.citation_has_crop,
            "citation_page_correct": self.citation_page_correct,
            "citation_modality": self.citation_modality,
            "answerable": self.answerable,
        }


@dataclass
class SystemResult:
    name: str
    results: list[QuestionResult] = field(default_factory=list)

    # --- aggregates -----------------------------------------------------
    def _subset(self, kind: str) -> list[QuestionResult]:
        return [r for r in self.results if r.kind == kind]

    def accuracy(self, kind: str | None = None) -> float:
        rows = self.results if kind is None else self._subset(kind)
        if not rows:
            return 0.0
        return sum(1 for r in rows if r.grade.correct) / len(rows)

    def latency(self) -> dict[str, float]:
        return latency_stats([r.latency_ms for r in self.results]).to_dict()

    def citation_stats(self) -> dict[str, Any]:
        rows = self.results
        n = len(rows) or 1
        return {
            "answers": len(rows),
            "with_page": sum(1 for r in rows if r.citation_has_page),
            "with_crop": sum(1 for r in rows if r.citation_has_crop),
            "page_rate": sum(1 for r in rows if r.citation_has_page) / n,
            "crop_rate": sum(1 for r in rows if r.citation_has_crop) / n,
            "page_correct_rate": sum(1 for r in rows if r.citation_page_correct) / n,
        }

    def modality_mix(self) -> dict[str, int]:
        mix: dict[str, int] = {}
        for r in self.results:
            key = r.top_modality or "none"
            mix[key] = mix.get(key, 0) + 1
        return mix

    def summary(self) -> dict[str, Any]:
        return {
            "system": self.name,
            "accuracy_all": self.accuracy(),
            "accuracy_picture_only": self.accuracy("picture_only"),
            "accuracy_text": self.accuracy("text_answerable"),
            "n_picture_only": len(self._subset("picture_only")),
            "n_text": len(self._subset("text_answerable")),
            "latency": self.latency(),
            "citations": self.citation_stats(),
            "winning_modality": self.modality_mix(),
        }


# ---------------------------------------------------------------------------
# Systems
# ---------------------------------------------------------------------------


@dataclass
class System:
    name: str
    retriever: Retriever
    synthesizer: Synthesizer


def build_fieldnote_system(
    chunks: list[Chunk],
    *,
    backend: str = "sqlite",
    db_path: str | None = None,
    synthesis: str | None = None,
) -> System:
    _warm_models()
    store = build_store(backend, db_path or str(settings.index_dir / "fieldnote.db"))
    store.add(encode_chunks(chunks))
    store.save()
    return System(
        name="fieldnote",
        retriever=Retriever(store, spaces=["text", "image", "audio"]),
        synthesizer=build_synthesizer(synthesis),
    )


def _warm_models() -> None:
    """Load the models before the clock starts.

    A cold model load is ten seconds. That belongs to start-up, not to the
    first technician's question.
    """
    from ..encode.registry import (
        get_audio_encoder,
        get_cross_encoder,
        get_image_encoder,
        get_text_encoder,
    )

    get_text_encoder()
    get_image_encoder()
    get_audio_encoder()
    get_cross_encoder()


def build_baseline_system(
    chunks: list[Chunk],
    *,
    backend: str = "sqlite",
    db_path: str | None = None,
    synthesis: str | None = None,
) -> tuple[System, list[Chunk]]:
    """The caption-only system.

    Identical in every respect except that images are captioned and the pixels
    are thrown away. It gets its own index: sharing a database would let the
    two systems' chunks mix inside the same vector space.
    """
    baseline_chunks = build_caption_baseline(chunks)
    _warm_models()
    store = build_store(backend, db_path or str(settings.index_dir / "caption_baseline.db"))
    store.add(encode_chunks(baseline_chunks))
    store.save()
    return (
        System(
            name="caption-only baseline",
            retriever=Retriever(store, spaces=["text"], use_cross_encoder=True),
            synthesizer=build_synthesizer(synthesis),
        ),
        baseline_chunks,
    )


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def run_system(
    system: System,
    questions: list[EvalQuestion],
    *,
    k: int = 20,
    warmup: bool = True,
) -> SystemResult:
    result = SystemResult(name=system.name)

    if warmup and questions:
        # The first query pays for lazy model initialisation. That belongs to
        # start-up, not to a technician's question, so it is paid before the
        # clock starts.
        system.retriever.search(questions[0].question, k=k)

    for q in questions:
        t0 = time.perf_counter()
        retrieval = system.retriever.search(q.question, k=k)
        answer = system.synthesizer.synthesize(
            q.question, retrieval.candidates, latency=retrieval.timings, units=retrieval.units
        )
        latency_ms = (time.perf_counter() - t0) * 1000

        top = retrieval.candidates[0] if retrieval.candidates else None
        citations = answer.citations

        # The *effective* source modality. A caption chunk is a text chunk, but
        # it is a caption of a picture - and the whole point of the comparison
        # is that the baseline gets its image-derived answers through text.
        top_modality = None
        if top is not None:
            top_modality = top.chunk.metadata.get(
                "original_modality", top.chunk.modality.value
            )

        page_correct = False
        for cit in citations:
            if q.expected_source_id and cit.source_id == q.expected_source_id:
                if q.expected_page is None or cit.page == q.expected_page:
                    page_correct = True
                    break

        result.results.append(
            QuestionResult(
                qid=q.qid,
                question=q.question,
                expected=q.answer,
                produced=answer.answer,
                grade=grade(q.answer, answer.answer),
                kind=q.kind,
                latency_ms=latency_ms,
                top_source_id=top.chunk.source_id if top else None,
                top_page=top.chunk.page if top else None,
                top_modality=top_modality,
                citation_count=len(citations),
                citation_has_page=any(c.page is not None for c in citations),
                citation_has_crop=any(c.crop_path for c in citations),
                citation_page_correct=page_correct,
                citation_modality=citations[0].modality.value if citations else None,
                answerable=answer.answerable,
                stage_ms={k2: round(v, 1) for k2, v in retrieval.timings.items()},
            )
        )
    return result


# ---------------------------------------------------------------------------
# Full evaluation
# ---------------------------------------------------------------------------


@dataclass
class EvalReport:
    fieldnote: SystemResult
    baseline: SystemResult
    questions: list[EvalQuestion]
    leaks: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fieldnote": self.fieldnote.summary(),
            "baseline": self.baseline.summary(),
            "unanswerable_violations": [
                {"qid": leak.qid, "answer": leak.answer, "where": leak.where} for leak in self.leaks
            ],
            "per_question": {
                "fieldnote": [r.to_dict() for r in self.fieldnote.results],
                "baseline": [r.to_dict() for r in self.baseline.results],
            },
        }


def run_full_eval(
    chunks: list[Chunk],
    *,
    backend: str = "sqlite",
    db_path: str | None = None,
    synthesis: str | None = None,
    k: int = 20,
    baseline_chunks: list[Chunk] | None = None,
) -> EvalReport:
    questions = build_eval_set()

    fieldnote = build_fieldnote_system(chunks, backend=backend, db_path=db_path, synthesis=synthesis)

    # The baseline gets its own index. Sharing a database would let the
    # baseline's caption chunks land inside Fieldnote's text space, and the
    # comparison would stop meaning anything.
    baseline_db = None
    if db_path:
        path = Path(db_path)
        baseline_db = str(path.with_name(path.stem + "_baseline" + path.suffix))
    baseline_system, baseline_chunk_list = build_baseline_system(
        chunks, backend=backend, db_path=baseline_db, synthesis=synthesis
    )

    fieldnote_result = run_system(fieldnote, questions, k=k)
    baseline_result = run_system(baseline_system, questions, k=k)

    captions = {
        c.chunk_id: c.text
        for c in (baseline_chunk_list or [])
        if c.region_label == "caption"
    }
    leaks = verify_unanswerable(questions, chunks, captions)

    return EvalReport(
        fieldnote=fieldnote_result,
        baseline=baseline_result,
        questions=questions,
        leaks=leaks,
    )


__all__ = [
    "EvalReport",
    "QuestionResult",
    "System",
    "SystemResult",
    "build_baseline_system",
    "build_fieldnote_system",
    "build_eval_set",
    "picture_only",
    "run_full_eval",
    "run_system",
    "text_only",
]
