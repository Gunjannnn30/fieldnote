"""Cross-encoder reranking across modalities.

A bi-encoder scores (query, document) independently, which is why it can be
precomputed - and also why it is weak: the query never attends to the
document. A cross-encoder attends over both together and is materially more
accurate, but it cannot be precomputed, so it runs over the fused candidate
set only.

Fieldnote reranks with three complementary scorers:

``text_cross_encoder``
    A true cross-attention encoder (ms-marco-MiniLM) over the candidate's
    *text projection*. Every modality has one: page prose for text chunks,
    the OCR string plus the figure caption for image chunks, the transcript
    for audio chunks.

``joint_space``
    CLIP for image candidates and CLAP for audio candidates, scoring the query
    text against the candidate in the modality's own joint space. This is the
    only signal that actually looks at the pixels/waveform again at answer
    time, and it is what the caption-only baseline structurally lacks.

``vlm_cross_encoder``
    Optional, expensive: asks a vision-language model whether the figure
    answers the question, using the yes/no token probability. This is a real
    cross-attention scorer over (text, image) and is the strongest option when
    it is affordable.

The weights are modality-aware on purpose. A text cross-encoder is the best
judge of text; CLIP is the best judge of a picture. Using one weight for both
means whichever signal is weaker for that modality drags the score down.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..config import settings
from ..schema import Modality, ScoredChunk
from ..textutil import content_tokens, question_tokens

# (cross encoder, joint space, vlm) weights per modality.
#
# For audio the cross-encoder gets most of the weight on purpose. CLAP
# measures whether two recordings *sound* alike, which is useful for finding
# a similar fault but says nothing about which call mentions roof B. The
# transcript is the channel that carries content; the waveform is the channel
# that carries acoustics. The question decides which one matters.
WEIGHTS: dict[str, tuple[float, float, float]] = {
    Modality.TEXT.value: (1.00, 0.00, 0.00),
    Modality.IMAGE.value: (0.40, 0.60, 0.60),
    Modality.AUDIO.value: (0.80, 0.20, 0.00),
}


@dataclass
class RerankSignals:
    ce: dict[str, float] = field(default_factory=dict)
    joint: dict[str, float] = field(default_factory=dict)
    vlm: dict[str, float] = field(default_factory=dict)


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if math.isclose(hi, lo):
        return [0.5 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


MAX_PROXY_CHARS = 320


def question_focus(question: str) -> str:
    """The part of the question that names the thing being asked for.

    Imported lazily to keep this module free of a circular import with the
    answer layer.
    """
    from ..answer.units import question_focus as _focus

    return _focus(question)


def is_which_focus(question: str) -> bool:
    from ..answer.units import is_which_focus as _which

    return _which(question)


def text_proxy(chunk) -> str:
    """The text view of a chunk used by the text cross-encoder.

    For an image chunk this is the OCR string - the literal characters
    rendered in the picture, including axis values - together with the
    figure's printed caption. It is deliberately *not* a caption.
    """
    if chunk.modality is Modality.TEXT:
        return chunk.text[:MAX_PROXY_CHARS]
    if chunk.modality is Modality.AUDIO:
        return chunk.text[:MAX_PROXY_CHARS]
    ocr = chunk.metadata.get("ocr_text", "")
    caption = chunk.metadata.get("figure_caption", "")
    title = f"{chunk.doc_title} page {chunk.page} {chunk.region_label or ''}".strip()
    parts = [p for p in (title, caption, ocr) if p]
    return ". ".join(parts)[:MAX_PROXY_CHARS]


def rerank(
    question: str,
    candidates: list[ScoredChunk],
    *,
    top_k: int | None = None,
    use_cross_encoder: bool = True,
    use_joint: bool = True,
    use_vlm: bool = False,
    query_vectors: dict[str, np.ndarray] | None = None,
    stored_vectors: dict[str, dict[str, np.ndarray]] | None = None,
) -> list[ScoredChunk]:
    """Rerank a fused candidate set and return the top-k, re-scored.

    ``query_vectors`` and ``stored_vectors`` let the joint-space score reuse
    the vectors that are already in the index. Re-encoding every candidate
    picture on every question costs seconds on a CPU; dotting the stored
    vector with the stored query vector costs microseconds.
    """
    if not candidates:
        return []

    signals = RerankSignals()

    # ---------------- text cross-encoder --------------------------------
    if use_cross_encoder and candidates:
        from ..encode.registry import get_cross_encoder

        model = get_cross_encoder()
        pairs = [(question, text_proxy(c.chunk)) for c in candidates]
        raw = model.predict(pairs, batch_size=16, show_progress_bar=False)
        for cand, score in zip(candidates, raw):
            signals.ce[cand.chunk.chunk_id] = float(score)

    # ---------------- joint-space scores --------------------------------
    if use_joint and candidates:
        signals.joint = _joint_scores(
            question, candidates, query_vectors=query_vectors, stored_vectors=stored_vectors
        )

    # ---------------- optional VLM cross-encoder ------------------------
    if use_vlm and candidates:
        signals.vlm = _vlm_scores(question, candidates)

    # ---------------- combine -------------------------------------------
    ce_norm = _minmax([signals.ce.get(c.chunk.chunk_id, 0.0) for c in candidates])
    joint_norm = _minmax([signals.joint.get(c.chunk.chunk_id, 0.0) for c in candidates])
    vlm_norm = _minmax([signals.vlm.get(c.chunk.chunk_id, 0.0) for c in candidates])

    # The part of the question that names the thing being asked for.
    #
    # For a "which <thing>" question the answer *is* that thing, so a chunk
    # that contains the word literally is a strong candidate - the chunk that
    # answers the question often does not repeat the question's context words
    # at all. For a "what <quantity>" question the answer is a value, and the
    # word in the question can easily appear in the wrong chunk, so no bonus
    # is applied there.
    focus_tokens = set(question_tokens(question_focus(question)))
    decisive_focus = is_which_focus(question) and len(focus_tokens) <= 3

    for i, cand in enumerate(candidates):
        cid = cand.chunk.chunk_id
        modality = cand.chunk.modality.value
        ce_w, joint_w, vlm_w = WEIGHTS.get(modality, (0.65, 0.35, 0.6))

        parts: list[tuple[float, float]] = []
        if use_cross_encoder:
            cand.traces["ce"] = signals.ce.get(cid, 0.0)
            parts.append((ce_norm[i], ce_w))
        if use_joint:
            cand.traces["joint"] = signals.joint.get(cid, 0.0)
            parts.append((joint_norm[i], joint_w))
        if use_vlm:
            cand.traces["vlm"] = signals.vlm.get(cid, 0.0)
            parts.append((vlm_norm[i], vlm_w))

        if parts:
            total_w = sum(w for _, w in parts)
            cand.rerank_score = sum(score * w for score, w in parts) / (total_w or 1.0)
        else:
            cand.rerank_score = 0.0

        if decisive_focus and focus_tokens:
            proxy_tokens = set(content_tokens(text_proxy(cand.chunk)))
            if focus_tokens & proxy_tokens:
                cand.rerank_score += 0.80
                cand.traces["focus_literal"] = 1.0

    reranked = sorted(candidates, key=lambda c: (-(c.rerank_score or 0.0), -c.fused_score))
    for i, cand in enumerate(reranked, start=1):
        cand.rank = i
    return reranked[: top_k] if top_k else reranked


def _joint_scores(
    question: str,
    candidates: list[ScoredChunk],
    *,
    query_vectors: dict[str, np.ndarray] | None = None,
    stored_vectors: dict[str, dict[str, np.ndarray]] | None = None,
) -> dict[str, float]:
    """Score query against image/audio candidates in their native joint space."""
    out: dict[str, float] = {}

    for space, modality in (("image", Modality.IMAGE), ("audio", Modality.AUDIO)):
        subset = [
            c for c in candidates
            if c.chunk.modality is modality
        ]
        if not subset:
            continue

        query_vec = (query_vectors or {}).get(space)
        stored = (stored_vectors or {}).get(space, {})
        if query_vec is not None and stored:
            sims = []
            for cand in subset:
                vec = stored.get(cand.chunk.chunk_id)
                if vec is None:
                    sims.append(0.0)
                else:
                    sims.append(float(np.dot(vec, query_vec)))
            for cand, sim in zip(subset, sims):
                out[cand.chunk.chunk_id] = sim
            continue

        # Fall back to encoding the candidates on the fly.
        if space == "image":
            from ..encode.registry import get_image_encoder

            enc = get_image_encoder()
            qv = enc.encode_query(question)
            paths = [c.chunk.crop_path for c in subset]
            valid = [(c, p) for c, p in zip(subset, paths) if p]
            if not valid:
                continue
            vecs = enc.encode([p for _c, p in valid])
            for (cand, _p), sim in zip(valid, vecs @ qv):
                out[cand.chunk.chunk_id] = float(sim)
        else:
            from ..encode.registry import get_audio_encoder

            enc = get_audio_encoder()
            qv = enc.encode_query(question)
            items = [
                (c.chunk.audio_path, c.chunk.start_sec, c.chunk.end_sec) for c in subset
            ]
            vecs = enc.encode(items)
            for cand, sim in zip(subset, vecs @ qv):
                out[cand.chunk.chunk_id] = float(sim)

    return out


def _vlm_scores(query: str, candidates: list[ScoredChunk]) -> dict[str, float]:
    """Cross-attention (query, image) scoring via a VLM's yes/no token logits."""
    out: dict[str, float] = {}
    image_cands = [c for c in candidates if c.chunk.modality is Modality.IMAGE and c.chunk.crop_path]
    if not image_cands:
        return out
    try:
        from ..answer.vlm import VLMEngine

        engine = VLMEngine()
        for cand in image_cands:
            out[cand.chunk.chunk_id] = engine.score_image_against_text(query, cand.chunk.crop_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[fieldnote] VLM rerank unavailable: {exc}")
    return out


def reciprocal_rank_fusion(lists: list[list[str]], k: int = 60) -> dict[str, float]:
    """Plain RRF over id lists - used by tests and the baseline comparison."""
    scores: dict[str, float] = {}
    for ranked in lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
