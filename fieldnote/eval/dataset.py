"""The eval set.

The set is generated from the same spec that generated the corpus, so a
question can never point at evidence that is not there.

Two groups:

``text_answerable`` (25)
    The answer is in the manual prose or in a call transcript.

``picture_only`` (15)
    The answer exists **only** inside a picture - a chart, a wiring diagram, a
    spec table or a job-site photo. These are the questions the caption-only
    baseline structurally cannot answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..fixtures.spec import AUDIO_FACTS, FIGURE_FACTS, MANUALS, TEXT_FACTS
from ..schema import Chunk, Modality
from .metrics import contains_answer


@dataclass
class EvalQuestion:
    qid: str
    question: str
    answer: str
    kind: str                     # text_answerable | picture_only
    modality_hint: str
    evidence: dict[str, Any] = field(default_factory=dict)
    expected_source_id: str | None = None
    expected_page: int | None = None
    expected_modality: Modality | None = None

    def to_dict(self) -> dict:
        return {
            "qid": self.qid,
            "question": self.question,
            "answer": self.answer,
            "kind": self.kind,
            "modality_hint": self.modality_hint,
            "evidence": self.evidence,
            "expected_source_id": self.expected_source_id,
            "expected_page": self.expected_page,
            "expected_modality": self.expected_modality.value if self.expected_modality else None,
        }


def _manual_layout() -> dict[str, tuple[str, int]]:
    """Map qid -> (source_id, page) using the same layout the renderer uses."""
    layout: dict[str, tuple[str, int]] = {}
    for spec in MANUALS:
        source_id = f"pdf:{spec.filename[:-4]}"
        # page 1 = cover, page 2 = table of contents, page 3+ = spec.pages
        for index, page_spec in enumerate(spec.pages):
            page = 3 + index
            for qid in page_spec["text_facts"]:
                layout[qid] = (source_id, page)
            for qid in page_spec["figures"]:
                layout[qid] = (source_id, page)
    return layout


def build_eval_set() -> list[EvalQuestion]:
    layout = _manual_layout()
    questions: list[EvalQuestion] = []

    for fact in TEXT_FACTS:
        source_id, page = layout.get(fact.qid, (None, None))
        questions.append(
            EvalQuestion(
                qid=fact.qid,
                question=fact.question,
                answer=fact.answer,
                kind="text_answerable",
                modality_hint="text",
                evidence={"doc": fact.doc, "section": fact.section},
                expected_source_id=source_id,
                expected_page=page,
                expected_modality=Modality.TEXT,
            )
        )

    for fact in AUDIO_FACTS:
        questions.append(
            EvalQuestion(
                qid=fact.qid,
                question=fact.question,
                answer=fact.answer,
                kind="text_answerable",
                modality_hint="audio",
                evidence={"call": fact.call},
                expected_source_id=f"aud:{fact.call}",
                expected_page=None,
                expected_modality=Modality.AUDIO,
            )
        )

    for fig in FIGURE_FACTS:
        source_id, page = layout.get(fig.qid, (None, None))
        questions.append(
            EvalQuestion(
                qid=fig.qid,
                question=fig.question,
                answer=fig.answer,
                kind="picture_only",
                modality_hint="image",
                evidence={"doc": fig.doc, "section": fig.section, "renderer": fig.renderer},
                expected_source_id=source_id,
                expected_page=page,
                expected_modality=Modality.IMAGE,
            )
        )

    return questions


def picture_only(questions: list[EvalQuestion]) -> list[EvalQuestion]:
    return [q for q in questions if q.kind == "picture_only"]


def text_only(questions: list[EvalQuestion]) -> list[EvalQuestion]:
    return [q for q in questions if q.kind == "text_answerable"]


# ---------------------------------------------------------------------------
# Unanswerability verification
# ---------------------------------------------------------------------------


def text_corpus(chunks: list[Chunk], captions: dict[str, str] | None = None) -> str:
    """Everything a caption-only text pipeline could possibly have.

    Page prose, call transcripts, and BLIP captions of every image.
    """
    parts: list[str] = []
    for chunk in chunks:
        if chunk.modality in (Modality.TEXT, Modality.AUDIO):
            parts.append(chunk.text or "")
    if captions:
        parts.extend(captions.values())
    return "\n".join(parts)


@dataclass
class Leak:
    qid: str
    answer: str
    where: str


def verify_unanswerable(
    questions: list[EvalQuestion],
    chunks: list[Chunk],
    captions: dict[str, str] | None = None,
) -> list[Leak]:
    """Prove the picture-only answers are absent from the text-only corpus."""
    corpus = text_corpus(chunks, captions)
    leaks: list[Leak] = []
    for q in picture_only(questions):
        if contains_answer(q.answer, corpus):
            leaks.append(Leak(q.qid, q.answer, "text corpus (prose/transcript/caption)"))
    return leaks
