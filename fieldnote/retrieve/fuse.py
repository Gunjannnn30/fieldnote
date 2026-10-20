"""Late fusion.

Each modality is searched independently in its own space, producing its own
ranked candidate list. Fusion is the step where those lists are merged into
one candidate set for reranking.

Why Reciprocal Rank Fusion rather than a score sum? Because the three spaces
produce scores on incomparable scales: a CLIP cosine of 0.28 and a MiniLM
cosine of 0.62 mean nothing relative to each other, and normalising them by
hand is fragile and unverifiable. RRF only uses *ranks*, so it is scale-free by
construction and has no tuning parameter that can be quietly fitted to the eval
set.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..schema import ScoredChunk
from ..store.base import IndexedRecord

SPACE_WEIGHTS = {"text": 1.0, "image": 1.0, "audio": 1.0}


@dataclass
class Fused:
    """Result of merging per-space candidate lists."""

    candidates: list[ScoredChunk]

    @property
    def top(self) -> ScoredChunk | None:
        return self.candidates[0] if self.candidates else None


def fuse(
    per_space: dict[str, list[tuple[IndexedRecord, float]]],
    *,
    strategy: str = "rrf",
    rrf_k: int = 60,
    weights: dict[str, float] | None = None,
) -> Fused:
    """Merge per-space ranked lists into a single candidate list.

    Strategies:
      ``rrf``          - reciprocal rank fusion (default, scale free)
      ``max``          - take the best normalised score across spaces
      ``weighted_rrf`` - RRF with a per-space weight
    """
    weights = weights or SPACE_WEIGHTS
    merged: dict[str, ScoredChunk] = {}

    for space, hits in per_space.items():
        if not hits:
            continue
        weight = float(weights.get(space, 1.0))

        raw_scores = [s for _, s in hits]
        lo, hi = min(raw_scores), max(raw_scores)
        span = (hi - lo) or 1.0

        for rank, (record, score) in enumerate(hits, start=1):
            chunk = record.chunk
            entry = merged.get(chunk.chunk_id)
            if entry is None:
                entry = ScoredChunk(chunk=chunk, per_modality_rank=rank)
                merged[chunk.chunk_id] = entry
            entry.per_modality_rank = rank
            entry.retrieval_score = max(entry.retrieval_score, float(score))
            normalised = (float(score) - lo) / span

            if strategy == "rrf":
                contribution = weight * (1.0 / (rrf_k + rank))
            elif strategy == "weighted_rrf":
                contribution = weight * (1.0 / (rrf_k + rank))
            elif strategy == "max":
                contribution = normalised * weight
            else:
                raise ValueError(f"unknown fusion strategy: {strategy}")

            entry.fused_score += contribution
            entry.traces[f"{space}_rank"] = float(rank)
            entry.traces[f"{space}_score"] = float(score)
            entry.traces[f"{space}_norm"] = float(normalised)

    candidates = sorted(merged.values(), key=lambda c: -c.fused_score)
    for i, cand in enumerate(candidates, start=1):
        cand.rank = i
    return Fused(candidates)


def dedupe(candidates: list[ScoredChunk]) -> list[ScoredChunk]:
    """Drop exact duplicates that share content hash."""
    seen: set[str] = set()
    out: list[ScoredChunk] = []
    for cand in candidates:
        key = cand.chunk.dedup_key
        if key in seen:
            continue
        seen.add(key)
        out.append(cand)
    return out
