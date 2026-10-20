"""Citation construction.

The ship gate: *every answer carries a citation with page number and a
cropped image.* So a citation always knows where it came from, and for any
evidence that lives in a picture we carry the crop itself plus the exact
rectangle it came from - the technician can compare our number against the
chart without opening a PDF.
"""

from __future__ import annotations

from ..schema import Citation, Modality, ScoredChunk


def build_citation(cand: ScoredChunk) -> Citation:
    chunk = cand.chunk
    return Citation(
        chunk_id=chunk.chunk_id,
        modality=chunk.modality,
        source_id=chunk.source_id,
        source_kind=chunk.source_kind,
        doc_title=chunk.doc_title,
        page=chunk.page,
        snippet=(chunk.text or "")[:400],
        score=float(cand.rerank_score if cand.rerank_score is not None else cand.fused_score),
        crop_path=chunk.crop_path,
        page_image_path=chunk.page_image_path,
        bbox=chunk.bbox,
        audio_path=chunk.audio_path,
        start_sec=chunk.start_sec,
        end_sec=chunk.end_sec,
        region_label=chunk.region_label,
    )


def build_citations(
    candidates: list[ScoredChunk],
    *,
    limit: int = 3,
    prefer_image: bool = True,
    focus_chunk_id: str | None = None,
) -> list[Citation]:
    """Pick the citations for an answer.

    When picture evidence is in play we make sure at least one citation
    carries a crop, because that is the one the technician can verify. The
    chunk that actually supplied the answer is always cited first.
    """
    if not candidates:
        return []

    ordered = sorted(
        candidates,
        key=lambda c: -(c.rerank_score if c.rerank_score is not None else c.fused_score),
    )

    citations: list[Citation] = []
    seen_sources: set[tuple[str, int | None, str]] = set()

    if focus_chunk_id:
        for cand in ordered:
            if cand.chunk.chunk_id == focus_chunk_id:
                citations.append(build_citation(cand))
                key = (cand.chunk.source_id, cand.chunk.page, cand.chunk.region_label or "")
                seen_sources.add(key)
                break

    for cand in ordered:
        chunk = cand.chunk
        key = (chunk.source_id, chunk.page, chunk.region_label or "")
        if key in seen_sources:
            continue
        seen_sources.add(key)
        citations.append(build_citation(cand))
        if len(citations) >= limit:
            break

    if prefer_image:
        has_image = any(c.modality is Modality.IMAGE and c.crop_path for c in citations)
        if not has_image:
            for cand in ordered:
                if cand.chunk.modality is Modality.IMAGE and cand.chunk.crop_path:
                    citations.insert(0, build_citation(cand))
                    citations = citations[:limit]
                    break

    return citations


def citation_coverage(citations: list[Citation]) -> dict:
    """Diagnostics used by the eval harness to enforce the ship gate."""
    return {
        "n": len(citations),
        "with_page": sum(1 for c in citations if c.page is not None),
        "with_crop": sum(1 for c in citations if c.crop_path),
        "with_audio": sum(1 for c in citations if c.audio_path),
        "modality_mix": sorted({c.modality.value for c in citations}),
    }
