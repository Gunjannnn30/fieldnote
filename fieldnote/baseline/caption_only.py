"""The caption-only baseline.

This is the trap the project exists to avoid, implemented properly so the
comparison is fair:

* every image is captioned by a vision-language model (BLIP);
* the caption is embedded with the ordinary text encoder;
* the caption is indexed as if it were a document paragraph;
* retrieval is a single search in the single text space.

Everything else - the cross-encoder reranker, the synthesizer, the grader, the
latency measurement - is identical to the real system. The only difference is
that the pixels are gone by the time the question is asked.

The consequence is worth stating plainly: a caption of a pressure-temperature
curve does not contain 385. It contains something like "a graph with a line
going up from left to right". The axis values the technician needs are
destroyed at caption time and no amount of clever retrieval brings them back.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..config import settings
from ..schema import Chunk, Modality, SourceKind


def build_caption_baseline(
    chunks: list[Chunk],
    *,
    cache_path: str | Path | None = None,
    caption_prompt: str | None = None,
) -> list[Chunk]:
    """Turn a multimodal chunk list into a text-only, caption-only chunk list."""
    cache: dict[str, str] = {}
    cache_path = Path(cache_path) if cache_path else (settings.artifacts_dir / "captions.json")
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            cache = {}

    from ..encode.registry import get_captioner

    captioner = None
    out: list[Chunk] = []

    for chunk in chunks:
        if chunk.modality is not Modality.IMAGE:
            # Text stays text. Audio keeps its transcript - a transcript is
            # language, not a lossy summary of a picture.
            out.append(chunk)
            continue

        path = chunk.crop_path or chunk.page_image_path
        if not path:
            out.append(chunk)
            continue

        caption = cache.get(chunk.chunk_id)
        if caption is None:
            if captioner is None:
                captioner = get_captioner()
            caption = captioner.caption(path, caption_prompt)
            cache[chunk.chunk_id] = caption

        out.append(
            Chunk(
                # A distinct id. The caption is a *different* artefact from the
                # picture it replaces; sharing the id would let the two collide
                # in the fusion step.
                chunk_id=f"caption::{chunk.chunk_id}",
                modality=Modality.TEXT,
                source_id=chunk.source_id,
                source_kind=SourceKind.MANUAL_PAGE if chunk.source_kind is not SourceKind.JOB_PHOTO else chunk.source_kind,
                doc_title=chunk.doc_title,
                text=caption,
                page=chunk.page,
                bbox=chunk.bbox,
                crop_path=None,          # the pixels are not available downstream
                page_image_path=None,
                audio_path=chunk.audio_path,
                start_sec=chunk.start_sec,
                end_sec=chunk.end_sec,
                region_label="caption",
                metadata={
                    "caption": caption,
                    "captioned_from": chunk.chunk_id,
                    "original_modality": chunk.modality.value,
                    "original_source_kind": chunk.source_kind.value,
                    "page": chunk.page,
                },
            )
        )

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    return out


def caption_report(chunks: list[Chunk]) -> list[dict]:
    """The captions the baseline produced, for the write-up."""
    out = []
    for chunk in chunks:
        if chunk.modality is Modality.TEXT and chunk.region_label == "caption":
            out.append({
                "chunk_id": chunk.chunk_id,
                "doc": chunk.doc_title,
                "page": chunk.page,
                "caption": chunk.text,
            })
    return out
