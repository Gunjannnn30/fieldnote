"""Core data model.

The central invariant of Fieldnote: **every chunk carries a modality tag**, and
every chunk knows how to point back at the pixels or audio it came from so the
final answer can be verified by a human standing on a roof.

Nothing in this file is modality-agnostic. That is deliberate.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Modality(str, Enum):
    """The three channels this system indexes independently."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"

    @property
    def encoder_key(self) -> str:
        """Which encoder owns this modality."""
        return {
            Modality.TEXT: "text",
            Modality.IMAGE: "image",
            Modality.AUDIO: "audio",
        }[self]


class SourceKind(str, Enum):
    """Where a chunk came from, independent of its modality."""

    MANUAL_PAGE = "manual_page"          # a page of an equipment manual PDF
    MANUAL_REGION = "manual_region"      # a chart/diagram/table cut out of a manual page
    JOB_PHOTO = "job_photo"              # a technician photo uploaded from a job site
    CALL_RECORDING = "call_recording"    # an audio recording of a support call


@dataclass(slots=True)
class BBox:
    """Pixel bounding box within a rendered page image (x0, y0, x1, y1)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)

    def to_dict(self) -> dict[str, float]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> BBox:
        return BBox(float(d["x0"]), float(d["y0"]), float(d["x1"]), float(d["y1"]))


@dataclass
class Chunk:
    """One indexable unit.

    A chunk is *always* tagged with a modality. A text chunk has no image
    path; an image chunk has no page text unless we deliberately attached the
    surrounding caption; an audio chunk has a time span.
    """

    chunk_id: str
    modality: Modality
    source_id: str                 # stable id of the originating document/asset
    source_kind: SourceKind
    doc_title: str

    # --- the payload ------------------------------------------------------
    text: str = ""                 # transcript, page text, or OCR'd region text
    page: int | None = None        # 1-based page number within the source document
    bbox: BBox | None = None       # region within the rendered page (image chunks)
    crop_path: str | None = None   # cropped image on disk (image chunks)
    page_image_path: str | None = None  # full rendered page (image chunks)
    audio_path: str | None = None  # source audio file (audio chunks)
    start_sec: float | None = None # audio span start
    end_sec: float | None = None   # audio span end

    # --- provenance -------------------------------------------------------
    region_label: str | None = None  # e.g. "pressure_curve", "wiring_diagram"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["modality"] = self.modality.value
        d["source_kind"] = self.source_kind.value
        d["bbox"] = self.bbox.to_dict() if self.bbox else None
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Chunk:
        d = dict(d)
        d["modality"] = Modality(d["modality"])
        d["source_kind"] = SourceKind(d["source_kind"])
        d["bbox"] = BBox.from_dict(d["bbox"]) if d.get("bbox") else None
        return Chunk(**d)

    @property
    def dedup_key(self) -> str:
        """Content hash used to de-duplicate overlapping chunks."""
        payload = f"{self.source_id}|{self.page}|{self.region_label}|{self.text[:400]}"
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


@dataclass
class ScoredChunk:
    """A chunk plus the score trail that produced it."""

    chunk: Chunk
    fused_score: float = 0.0
    retrieval_score: float = 0.0
    rerank_score: float | None = None
    rank: int | None = None
    per_modality_rank: int | None = None
    traces: dict[str, float] = field(default_factory=dict)

    @property
    def modality(self) -> Modality:
        return self.chunk.modality


@dataclass
class Citation:
    """A human-verifiable pointer back to the source.

    The ship gate demands *every* answer carries a page number and a cropped
    image, so `crop_path` and `page` are first-class, not optional garnish.
    """

    chunk_id: str
    modality: Modality
    source_id: str
    source_kind: SourceKind
    doc_title: str
    page: int | None
    snippet: str
    score: float
    crop_path: str | None = None
    page_image_path: str | None = None
    bbox: BBox | None = None
    audio_path: str | None = None
    start_sec: float | None = None
    end_sec: float | None = None
    region_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["modality"] = self.modality.value
        d["source_kind"] = self.source_kind.value
        d["bbox"] = self.bbox.to_dict() if self.bbox else None
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class Answer:
    """Final synthesised answer with its evidence trail."""

    question: str
    answer: str
    citations: list[Citation]
    modality_hits: dict[str, int]
    latency_ms: dict[str, float]
    answerable: bool = True
    unanswerable_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "modality_hits": self.modality_hits,
            "latency_ms": self.latency_ms,
            "answerable": self.answerable,
            "unanswerable_reason": self.unanswerable_reason,
        }
