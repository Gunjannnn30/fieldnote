"""The retrieval pipeline.

The cascade is:

1. **Parallel per-modality search.** Three spaces, three query encoders, run
   concurrently.
2. **Late fusion.** The ranked lists are merged with Reciprocal Rank Fusion.
3. **Chunk-level rerank.** A cross-encoder judges the shortlist. The
   shortlist is short on purpose - the cross-encoder is the expensive part
   and it cannot be precomputed.
4. **Expansion.** The best chunks are opened up into *evidence units* - the
   sentence, the phrase read off the chart, the transcript segment.
5. **Unit-level rerank.** The cross-encoder judges (question, unit) pairs.

Steps 3 and 5 both use a cross-encoder because that is what a cross-encoder
is for: judging a question and a passage together. Step 4 exists because the
unit that answers a question is rarely the whole 900-character chunk.

This is the "late fusion" the project is about, and the distinction from
"early fusion" is worth stating plainly:

*Early fusion* mixes the raw signals before the model sees them - typically by
concatenating a caption onto the document text and embedding one combined
vector. The retrieval decision is then made in a single space that never
contained the picture. Whatever the caption lost is lost forever.

*Late fusion* keeps the modalities separate all the way to the point where the
model has to commit to an answer. Each modality is searched in the space where
its signal is strongest, the ranked lists are merged, and a cross-encoder
makes the final call over the merged set - with the picture still available as
pixels.

The cost of late fusion is that you need more than one index and a fusion
step. The benefit is that a chart's axis values are still there when the
question needs them.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np

from ..config import settings
from ..schema import Modality, ScoredChunk
from ..store.base import IndexedRecord, MultiSpaceStore


@dataclass
class RetrievalResult:
    question: str
    candidates: list[ScoredChunk]
    per_space: dict[str, list[tuple[IndexedRecord, float]]] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)
    units: list = field(default_factory=list)
    shortlist_size: int = 0

    @property
    def top(self) -> ScoredChunk | None:
        return self.candidates[0] if self.candidates else None

    def by_modality(self, modality: Modality) -> list[ScoredChunk]:
        return [c for c in self.candidates if c.chunk.modality is modality]

    def space_counts(self) -> dict[str, int]:
        return {space: len(hits) for space, hits in self.per_space.items()}


class Retriever:
    """Parallel multi-space search with late fusion and cross-encoder reranking."""

    def __init__(
        self,
        store: MultiSpaceStore,
        *,
        use_cross_encoder: bool | None = None,
        use_vlm_rerank: bool = False,
        spaces: list[str] | None = None,
        shortlist_per_space: int = 8,
        fused_shortlist: int = 12,
        expand_chunks: int = 6,
    ):
        self.store = store
        self.use_cross_encoder = (
            settings.use_cross_encoder if use_cross_encoder is None else use_cross_encoder
        )
        self.use_vlm_rerank = use_vlm_rerank
        self.spaces = spaces or ["text", "image", "audio"]
        self.shortlist_per_space = shortlist_per_space
        self.fused_shortlist = fused_shortlist
        self.expand_chunks = expand_chunks

    # ------------------------------------------------------------------
    def encode_query(self, question: str) -> dict[str, np.ndarray]:
        """Encode one question into every modality space it can reach.

        A question is text, so the only way it reaches the image index is
        through the joint space that CLIP's text tower shares with its image
        tower. Same story for CLAP and audio. This is the single most
        important detail in the whole design.
        """
        from ..encode.registry import get_audio_encoder, get_image_encoder, get_text_encoder

        out: dict[str, np.ndarray] = {}
        if "text" in self.spaces:
            out["text"] = get_text_encoder().encode_query(question)
        if "image" in self.spaces:
            out["image"] = get_image_encoder().encode_query(question)
        if "audio" in self.spaces:
            out["audio"] = get_audio_encoder().encode_query(question)
        return out

    # ------------------------------------------------------------------
    def search(
        self,
        question: str,
        *,
        k: int | None = None,
        modalities: list[str] | None = None,
        filters: dict | None = None,
        candidate_k: int | None = None,
        rerank: bool = True,
    ) -> RetrievalResult:
        k = k or settings.final_k
        candidate_k = candidate_k or settings.candidate_k
        timings: dict[str, float] = {}

        t0 = time.perf_counter()
        query_vectors = self.encode_query(question)
        timings["encode_query_ms"] = (time.perf_counter() - t0) * 1000

        spaces = modalities or list(self.spaces)
        available = set(self.store.spaces.keys())
        spaces = [s for s in spaces if s in query_vectors and s in available]

        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=len(spaces)) as pool:
            futures = {
                space: pool.submit(
                    self.store.search_space, space, query_vectors[space], candidate_k, filters
                )
                for space in spaces
            }
            per_space = {space: fut.result() for space, fut in futures.items()}
        timings["search_ms"] = (time.perf_counter() - t0) * 1000

        from .fuse import fuse

        t0 = time.perf_counter()
        fused = fuse(per_space, strategy=settings.fusion, rrf_k=settings.rrf_k)
        timings["fuse_ms"] = (time.perf_counter() - t0) * 1000

        candidates = fused.candidates
        units: list = []
        shortlist_size = 0

        if rerank and candidates:
            from .rerank import rerank as rerank_candidates

            # Reuse the vectors already in the index. Re-encoding every
            # candidate picture on every question costs seconds on a CPU.
            stored_vectors: dict[str, dict[str, np.ndarray]] = {}
            for space, hits in per_space.items():
                stored_vectors[space] = {rec.chunk.chunk_id: rec.vector for rec, _s in hits}

            # Keep the shortlist short: the cross-encoder cannot be
            # precomputed, so every pair it judges is paid for on every query.
            shortlist = self._shortlist(candidates, per_space)

            t0 = time.perf_counter()
            reranked = rerank_candidates(
                question,
                shortlist,
                top_k=k,
                use_cross_encoder=self.use_cross_encoder,
                use_joint=settings.use_clip_rerank,
                use_vlm=self.use_vlm_rerank,
                query_vectors=query_vectors,
                stored_vectors=stored_vectors,
            )
            timings["rerank_ms"] = (time.perf_counter() - t0) * 1000
            shortlist_size = len(shortlist)

            # Fill the remaining slots with the best of the rest, so the
            # caller still gets k candidates.
            seen = {c.chunk.chunk_id for c in reranked}
            for cand in candidates:
                if len(reranked) >= k:
                    break
                if cand.chunk.chunk_id in seen:
                    continue
                seen.add(cand.chunk.chunk_id)
                cand.rerank_score = cand.rerank_score if cand.rerank_score is not None else cand.fused_score
                reranked.append(cand)
            candidates = reranked

            # --- expand the best chunks into evidence units --------------
            t0 = time.perf_counter()
            units = self._expand(question, candidates[: self.expand_chunks])
            timings["expand_ms"] = (time.perf_counter() - t0) * 1000

        return RetrievalResult(
            question=question,
            candidates=candidates,
            per_space=per_space,
            timings=timings,
            units=units,
            shortlist_size=shortlist_size,
        )

    # ------------------------------------------------------------------
    def _shortlist(
        self,
        candidates: list[ScoredChunk],
        per_space: dict[str, list[tuple[IndexedRecord, float]]],
    ) -> list[ScoredChunk]:
        """The shortlist the cross-encoder gets to judge.

        Two sources, because either one alone misses things. The best few
        from *each* space guarantee that every modality is represented - a
        question about a chart must not be answered from prose. The best few
        by *fused* rank guarantee that a chunk which the space's own encoder
        ranked poorly but the other spaces liked is not dropped: an audio
        segment is ranked acoustically by CLAP, and acoustic similarity says
        nothing about which segment mentions roof B.
        """
        keep: dict[str, ScoredChunk] = {}

        for _space, hits in per_space.items():
            for record, _score in hits[: self.shortlist_per_space]:
                chunk_id = record.chunk.chunk_id
                if chunk_id not in keep:
                    keep[chunk_id] = ScoredChunk(
                        chunk=record.chunk,
                        fused_score=0.0,
                        retrieval_score=0.0,
                    )

        for cand in candidates[: self.fused_shortlist]:
            keep.setdefault(
                cand.chunk.chunk_id,
                ScoredChunk(chunk=cand.chunk, fused_score=0.0, retrieval_score=0.0),
            )

        # Preserve the fused ranking among the shortlist.
        for cand in candidates:
            if cand.chunk.chunk_id in keep:
                entry = keep[cand.chunk.chunk_id]
                entry.fused_score = cand.fused_score
                entry.retrieval_score = cand.retrieval_score
                entry.per_modality_rank = cand.per_modality_rank
                entry.traces = dict(cand.traces)
        return sorted(keep.values(), key=lambda c: -c.fused_score)

    # ------------------------------------------------------------------
    def _expand(self, question: str, chunks: list[ScoredChunk]) -> list:
        """Open the best chunks into answerable units and score them."""
        from ..answer.units import build_units, chunk_relevance_map, score_units

        units = build_units(chunks)
        if not units:
            return []

        cross_encoder = None
        if self.use_cross_encoder:
            from ..encode.registry import get_cross_encoder

            cross_encoder = get_cross_encoder()

        return score_units(
            question,
            units,
            cross_encoder=cross_encoder,
            chunk_scores=chunk_relevance_map(chunks),
        )
