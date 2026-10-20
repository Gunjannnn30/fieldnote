"""Evidence units: the thing an answer is actually made of.

Retrieval returns chunks; an answer is made of *sentences*, of *phrases read
off a chart*, of *transcript segments*. Ranking whole 900-character chunks and
then picking a sentence by word overlap is weak - the sentence that repeats
the most question words is often not the sentence that answers the question.

So the second stage of the reranker scores evidence units with the cross
encoder, which is exactly what a cross encoder is for: the question attends
over the candidate passage and the pair is judged together.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..schema import Chunk, Modality, ScoredChunk
from ..textutil import (
    compress_number,
    content_tokens,
    overlap_score,
    question_tokens,
    sentences,
)

# A number only counts as a bare value when it is not part of an identifier.
_NUM_RE = re.compile(r"(?<![\w-])-?\d+(?:,\d{3})*(?:\.\d+)?(?![\w])")

_UNIT_SUFFIX = r"PSIG|PSI|VAC|CFM|AMPS|DEGF|DEGC|DEG|KW|KVA|HZ|LB|V|A|F"
_EMBEDDED_NUM_RE = re.compile(rf"(?<![.\d])(\d+(?:\.\d+)?)[\s.,]?({_UNIT_SUFFIX})(?!\w)")

# Same visual line, or the stacked line just underneath.
_LINE_DY = 26.0
_NEAR_DX = 260.0
_STACK_DX = 70.0
_STACK_DY = 40.0

CHUNK_RELEVANCE_WEIGHT = 0.25


@dataclass
class EvidenceUnit:
    """One answerable fragment inside a chunk."""

    text: str
    chunk: Chunk
    modality: Modality
    context: str = ""
    phrase: str = ""      # the local phrase, without the document title
    kind: str = "text"        # "text" | "image" | "audio"
    ce_score: float = 0.0
    score: float = 0.0
    chunk_relevance: float = 0.0
    value_quality: float = 0.0

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id

    def to_dict(self) -> dict:
        return {
            "text": self.text[:220],
            "phrase": self.phrase[:220],
            "chunk_id": self.chunk_id,
            "modality": self.modality.value,
            "ce_score": round(self.ce_score, 4),
            "score": round(self.score, 4),
            "value_quality": round(self.value_quality, 4),
        }


# A bare number on an axis is not an answer. A number with a unit is.
_VALUE_WITH_UNIT = re.compile(
    r"(?<![\w-])\d+(?:\.\d+)?\s*(?:PSI|PSIG|VAC|V|A|HZ|CFM|DEGF|DEG|LB|MIN|MINUTES?|HRS?|HOURS?|%|AMPS)\b",
    re.I,
)
_VALUE_IDENTIFIER = re.compile(r"[A-Z]{2,}-?\d")


_CAPTION_RE = re.compile(r"^\s*(figure|fig\.?|table)\s*\d+\s*[.:]", re.I)

# A number that stands on its own: not part of "R-410A", not part of "NP-42".
# A unit letter is allowed - "24V" is a value, not an identifier.
_STANDALONE_NUM_RE = re.compile(
    r"(?<![\w-])-?\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:°?[A-Za-z%]{1,5}))?(?![\w])"
)

# A number that follows one of these is a *reference*, not a measurement:
# "Class 2", "Figure 14", "Section 6". Treating those as values lets a
# sentence that states no measurement look like a sentence that does.
_REFERENCE_LABELS = {
    "class", "figure", "fig", "table", "section", "step", "item", "note",
    "page", "paragraph", "chapter", "appendix", "series", "model", "type",
    "plate", "drawing",
}
_REFERENCE_NUMBER_RE = re.compile(
    r"\b(" + "|".join(sorted(_REFERENCE_LABELS)) + r")\s+\d+\b", re.I
)


def _states_a_value(text: str) -> bool:
    """Does this sentence state a measurement?

    "Class 2" is a reference. "2 scfh" and "0.5 in. w.c." are measurements.
    """
    stripped = _REFERENCE_NUMBER_RE.sub(" ", text)
    return bool(_STANDALONE_NUM_RE.search(stripped))

# "What field supply voltage is printed ON THE YSC072 unit 7 wiring diagram?"
# has two jobs: it says *which* figure to look at, and *what* to read off it.
# The part after the last locator phrase identifies the figure; the part
# before it is what the technician actually wants.
_FOCUS_MARKERS = (
    " on the ", " in the ", " of the ", " for the ", " from the ", " at the ",
    " on unit ", " in figure ", " on figure ",
)


_WHICH_RE = re.compile(r"\s*which\s+([a-z][a-z-]*)")


def is_which_focus(question: str) -> bool:
    """Does the question ask "which <thing>"?

    A "which" question names one thing and the answer is that thing, so a
    chunk that contains the word literally is a strong candidate. A "what"
    question names a *quantity* and the answer is a value, and the word in
    the question may appear in the wrong chunk entirely.
    """
    return bool(_WHICH_RE.match((question or "").lower()))


def question_focus(question: str) -> str:
    """The part of the question that names the value being asked for."""
    q = (question or "").lower()
    cut = -1
    for marker in _FOCUS_MARKERS:
        pos = q.rfind(marker)
        if pos > cut:
            cut = pos
    if cut > 0:
        return (question or "")[:cut]

    # "Which roof was the unit..." - the noun after "which" is what is being
    # asked for; the rest of the sentence is context.
    which = _WHICH_RE.match(q)
    if which:
        return "which " + which.group(1)
    return question or ""


def is_caption(text: str) -> bool:
    """Is this fragment a figure or table caption rather than content?

    "Figure 14. R-410A pressure-temperature curve with safety cutouts." points
    at the evidence. It is not the evidence, and it is not an answer.
    """
    return bool(_CAPTION_RE.match(text or ""))


def value_quality(text: str, kind: str = "text") -> float:
    """How much does this fragment look like a stated value?"""
    t = (text or "").strip()
    if not t:
        return 0.0
    if kind != "image" and is_caption(t):
        return 0.0
    if kind == "image":
        if _VALUE_WITH_UNIT.search(t):
            return 1.0
        if _VALUE_IDENTIFIER.search(t):
            return 0.7
        if re.fullmatch(r"-?\d+(?:\.\d+)?", t):
            return 0.15      # a bare axis label
        return 0.0
    # Prose: a sentence that states a number is a candidate answer. The number
    # has to stand on its own - "R-410A" is a refrigerant, not a measurement,
    # and a sentence full of refrigerant names is not a sentence with a value.
    if _states_a_value(t):
        return 0.6
    return 0.0


# The nouns that make a question a question about a *value*. A question about
# "which roof" is not a question about a value; a question about "what
# pressure" is.
_VALUE_NOUNS = (
    "pressure", "voltage", "temperature", "amperage", "amps", "torque",
    "clearance", "reading", "model", "fault code", "setpoint", "target",
    "peak", "charge", "weight", "minutes", "hours", "inches", "size",
    "rating", "cutout", "superheat", "subcooling", "frequency", "speed",
    "airflow", "capacity", "disconnect", "amp draw", "amp", "number", "code",
    "time", "duration", "length", "difference", "value", "psi", "cfm",
)


def wants_a_value(question: str) -> bool:
    """Is this question asking for a number or a stated value?"""
    q = (question or "").lower()
    if re.search(r"\bhow (much|many|long|often|far)\b", q):
        return True
    for noun in _VALUE_NOUNS:
        if re.search(rf"\bwhat\b[^?]*\b{re.escape(noun)}\b", q):
            return True
    return False


# ---------------------------------------------------------------------------
# Building units
# ---------------------------------------------------------------------------


def extract_values(text: str) -> list[str]:
    """Every number in `text` that is a value rather than part of an identifier."""
    if not text:
        return []
    found: list[str] = []
    for m in _NUM_RE.finditer(text):
        found.append(compress_number(m.group()))
    for m in _EMBEDDED_NUM_RE.finditer(text):
        found.append(compress_number(m.group(1)))
    seen: set[str] = set()
    out: list[str] = []
    for value in found:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _ocr_items(chunk: Chunk) -> list[dict]:
    items = chunk.metadata.get("ocr_items") or []
    out = []
    for it in items:
        box = it.get("box") or [0, 0, 0, 0]
        out.append(
            {
                "text": it.get("text", ""),
                "score": float(it.get("score", 0.0)),
                "box": (float(box[0]), float(box[1]), float(box[2]), float(box[3])),
            }
        )
    return out


def _ocr_phrase(items: list[dict], index: int, with_headers: bool = False) -> str:
    """The text of one OCR item plus whatever belongs with it.

    In a table, a value means nothing on its own: "2400 CFM" is only
    "maximum indoor airflow" because of the column it sits under and the row
    it sits in. The geometry is right there in the OCR boxes, so we use it.
    """
    target = items[index]
    t_box = target["box"]
    t_cx = (t_box[0] + t_box[2]) / 2
    t_cy = (t_box[1] + t_box[3]) / 2

    near: list[tuple[float, str]] = []
    for j, it in enumerate(items):
        if j == index:
            continue
        box = it["box"]
        cx = (box[0] + box[2]) / 2
        cy = (box[1] + box[3]) / 2
        if abs(cy - t_cy) <= _LINE_DY and abs(cx - t_cx) <= _NEAR_DX:
            near.append((abs(cx - t_cx), it["text"]))
        elif 0 < cy - t_cy <= _STACK_DY and abs(cx - t_cx) <= _STACK_DX:
            near.append((abs(cy - t_cy) + 40, it["text"]))

    near.sort(key=lambda t: t[0])
    parts = [target["text"]] + [t[1] for t in near[:5]]

    if with_headers:
        parts.extend(_table_context(items, index, t_box, t_cx, t_cy))

    return " ".join(p for p in parts if p)


def _table_context(
    items: list[dict], index: int, t_box: tuple, t_cx: float, t_cy: float
) -> list[str]:
    """The column header above a cell and the row label beside it."""
    out: list[str] = []

    # Column header: the topmost item in the same column, above the cell.
    best_header: tuple[float, str] | None = None
    best_row: tuple[float, str] | None = None
    for j, it in enumerate(items):
        if j == index:
            continue
        box = it["box"]
        cx = (box[0] + box[2]) / 2
        cy = (box[1] + box[3]) / 2
        if cy < t_box[1] and abs(cx - t_cx) <= 60:
            if best_header is None or cy < best_header[0]:
                best_header = (cy, it["text"])
        if abs(cy - t_cy) <= 34 and cx < t_box[0]:
            # The leftmost cell in the row is the row label - the row the
            # value belongs to. It can be a whole column away.
            if best_row is None or cx < best_row[0]:
                best_row = (cx, it["text"])

    if best_row:
        out.append(best_row[1])
    if best_header:
        out.append(best_header[1])
    return out


def _title_band(items: list[dict]) -> float:
    """The y coordinate below which an OCR item is part of the figure's title.

    A chart's title says what the chart *is*. It never says what the chart
    *says*. Treating the top line as a caption keeps "UNIT 7 FIELD WIRING
    DIAGRAM" from being answered with "7".
    """
    if not items:
        return -1.0
    top = min(item["box"][1] for item in items)
    return top + 0.035 * (max(item["box"][3] for item in items) - top)


def units_from_chunk(chunk: Chunk) -> list[EvidenceUnit]:
    """Split a chunk into the fragments an answer could be built from."""
    title = chunk.doc_title or ""
    out: list[EvidenceUnit] = []

    if chunk.modality is Modality.IMAGE:
        caption = chunk.metadata.get("figure_caption", "")
        items = _ocr_items(chunk)
        title_band = _title_band(items)
        is_table = (chunk.region_label or "").lower() == "table"
        for i, item in enumerate(items):
            phrase = _ocr_phrase(items, i, with_headers=is_table)
            if not phrase.strip():
                continue
            context = f"{title}. {caption}. {phrase}".strip() if caption else f"{title}. {phrase}"
            target = item["text"]
            is_title = item["box"][1] <= title_band
            out.append(
                EvidenceUnit(
                    text=target,
                    chunk=chunk,
                    modality=chunk.modality,
                    context=context,
                    phrase=phrase,
                    kind="image",
                    value_quality=0.0 if is_title else value_quality(target, "image"),
                )
            )
        if not out:
            text = chunk.text or caption or title
            out.append(
                EvidenceUnit(
                    text=text,
                    chunk=chunk,
                    modality=chunk.modality,
                    context=f"{title}. {caption}".strip(),
                    phrase=text,
                    kind="image",
                )
            )
    elif chunk.modality is Modality.AUDIO:
        for sent in sentences(chunk.text or ""):
            out.append(
                EvidenceUnit(
                    text=sent,
                    chunk=chunk,
                    modality=chunk.modality,
                    context=f"{title}. {sent}".strip(),
                    phrase=sent,
                    kind="audio",
                    value_quality=value_quality(sent, "audio"),
                )
            )
    else:
        # A chunk that is entirely a figure caption stays a caption, even
        # though the sentence splitter will have cut the "Table 7." prefix
        # off the first sentence.
        chunk_is_caption = is_caption(chunk.text or "")
        for sent in sentences(chunk.text or ""):
            out.append(
                EvidenceUnit(
                    text=sent,
                    chunk=chunk,
                    modality=chunk.modality,
                    context=f"{title}. {sent}".strip(),
                    phrase=sent,
                    kind="text",
                    value_quality=0.0 if chunk_is_caption else value_quality(sent, "text"),
                )
            )
    return out


def build_units(scored: list[ScoredChunk]) -> list[EvidenceUnit]:
    units: list[EvidenceUnit] = []
    for cand in scored:
        units.extend(units_from_chunk(cand.chunk))
    return units


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def chunk_relevance_map(scored: list[ScoredChunk]) -> dict[str, float]:
    """Normalise each retrieved chunk's score into [0, 1]."""
    if not scored:
        return {}
    raw = []
    for cand in scored:
        score = cand.rerank_score if cand.rerank_score is not None else cand.fused_score
        raw.append(float(score))
    lo, hi = min(raw), max(raw)
    span = (hi - lo) or 1.0
    out: dict[str, float] = {}
    for cand, score in zip(scored, raw):
        out[cand.chunk.chunk_id] = (score - lo) / span
    return out


def score_units(
    question: str,
    units: list[EvidenceUnit],
    *,
    cross_encoder=None,
    chunk_scores: dict[str, float] | None = None,
    modality_bonus: dict[str, float] | None = None,
) -> list[EvidenceUnit]:
    """Score evidence units with the cross encoder, plus light lexical signals.

    The weights are modality-aware. For prose the cross-encoder is the best
    judge of "does this passage answer this question". For a picture the
    cross-encoder is reading OCR of a chart, and the better signal is which
    *label* on the chart the question is pointing at - so the lexical match
    against the label carries more weight there, and a fragment that states a
    value with a unit beats a bare axis label.
    """
    if not units:
        return []
    chunk_scores = chunk_scores or {}
    modality_bonus = modality_bonus or {}

    ce_raw: list[float] = []
    if cross_encoder is not None:
        pairs = [(question, unit.context or unit.phrase or unit.text) for unit in units]
        raw = cross_encoder.predict(pairs, batch_size=32, show_progress_bar=False)
        ce_raw = [float(s) for s in raw]
        for unit, score in zip(units, ce_raw):
            unit.ce_score = score

    # Normalise the cross-encoder inside each modality.
    #
    # ms-marco is trained on long passages and scores a short OCR fragment
    # such as "2400 CFM" at -11 - a correct answer, scored as worthless. If
    # every modality is normalised against every other one, that outlier
    # compresses the whole image group to zero and the fragment can never
    # win. Normalising per modality asks the only question that matters:
    # which of *these* candidates is the best one?
    ce_norm = [0.0] * len(units)
    by_modality: dict[Modality, list[int]] = {}
    for i, unit in enumerate(units):
        by_modality.setdefault(unit.modality, []).append(i)
    for indices in by_modality.values():
        values = [ce_raw[i] for i in indices]
        lo, hi = min(values), max(values)
        for i in indices:
            if abs(hi - lo) < 1e-9:
                ce_norm[i] = 0.5
            else:
                ce_norm[i] = (ce_raw[i] - lo) / (hi - lo)

    question_literal = set(question_tokens(question))
    wants_value = wants_a_value(question)
    focus = question_focus(question)
    focus_literal = set(question_tokens(focus)) or question_literal
    which_focus = is_which_focus(question)
    best_relevance = max(chunk_scores.values(), default=1.0) if chunk_scores else 1.0

    for i, unit in enumerate(units):
        overlap = overlap_score(question, unit.phrase or unit.text)
        focus_overlap = overlap_score(focus, unit.phrase or unit.text)
        relevance = float(chunk_scores.get(unit.chunk_id, 0.0))

        literal = question_literal & set(content_tokens(unit.phrase or unit.text))
        literal_bonus = 0.30 * (len(literal) / len(question_literal)) if question_literal else 0.0
        focus_literal_hit = focus_literal & set(content_tokens(unit.phrase or unit.text))
        focus_bonus = (
            0.35 * (len(focus_literal_hit) / len(focus_literal)) if focus_literal else 0.0
        )
        if which_focus:
            # In a "which <thing>" question the other words are context, and
            # context is exactly what the wrong segment repeats. Only the
            # named thing should count.
            literal_bonus = 0.0
            overlap = 0.0

        if unit.modality is Modality.IMAGE:
            # A cross-encoder trained on long passages is a poor judge of an
            # OCR fragment - it scored "2400 CFM" at -11 for a question it
            # answers perfectly. The lexical match against the label the
            # question is pointing at is the signal that actually works.
            score = (
                0.08 * ce_norm[i]
                + 0.40 * focus_overlap
                + 0.16 * overlap
                + 0.10 * relevance
                + literal_bonus
                + focus_bonus
                + 0.30 * unit.value_quality
            )
        elif unit.modality is Modality.AUDIO:
            score = (
                0.42 * ce_norm[i]
                + 0.22 * relevance
                + 0.16 * overlap
                + 0.16 * focus_overlap
                + literal_bonus
                + focus_bonus
            )
        else:
            score = (
                0.55 * ce_norm[i]
                + 0.18 * relevance
                + 0.12 * overlap
                + 0.16 * focus_overlap
                + literal_bonus
                + focus_bonus
            )

        # A fragment from a figure that is not the one being asked about is
        # not a weaker answer, it is a different answer. The gate is heavy
        # for pictures - a label on the wrong chart is simply wrong - and
        # light for prose, where the sentence-level cross-encoder has already
        # judged the passage on its own merits.
        gap = max(0.0, best_relevance - relevance)
        if unit.modality is Modality.IMAGE:
            score -= 1.5 * gap
        else:
            score -= 0.10 * gap

        # A caption that describes a figure is a pointer to the evidence, not
        # the evidence. If the question asks for a value, a fragment that
        # states no value cannot be the answer.
        if wants_value and unit.value_quality <= 0.0:
            score -= 1.0

        score += modality_bonus.get(unit.modality.value, 0.0)
        unit.chunk_relevance = relevance
        unit.score = score

    return sorted(units, key=lambda u: -u.score)


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if abs(hi - lo) < 1e-9:
        return [0.5 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def pick_answer_value(unit: EvidenceUnit) -> str:
    """The short form of the answer, when the unit clearly contains one value."""
    if unit.kind != "image":
        return unit.text
    values = extract_values(unit.text)
    if len(values) == 1:
        return values[0]
    return unit.text
