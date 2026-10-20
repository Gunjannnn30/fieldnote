"""Corpus builder.

Renders the synthetic HVAC corpus described by :mod:`fieldnote.fixtures.spec`
into a directory that looks like the real thing::

    corpus/
      manuals/*.pdf
      photos/*.png
      calls/*.wav

It also runs a **collision check**: for every picture-only question, the
expected answer must not appear anywhere in the prose, in a figure caption or
in a call transcript. If it does, the fixture is wrong and the build fails
loudly rather than quietly producing an eval that proves nothing.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from ..config import settings
from ..textutil import normalize
from .render import render_calls, render_figure, render_manual
from .spec import AUDIO_FACTS, FIGURE_FACTS, MANUALS, TEXT_FACTS


def build_corpus(out_dir: str | Path | None = None, *, force: bool = False) -> dict:
    out_dir = Path(out_dir or settings.corpus_dir)
    if out_dir.exists() and force:
        shutil.rmtree(out_dir)

    manuals_dir = out_dir / "manuals"
    photos_dir = out_dir / "photos"
    calls_dir = out_dir / "calls"
    for d in (manuals_dir, photos_dir, calls_dir):
        d.mkdir(parents=True, exist_ok=True)

    # --- figures ---------------------------------------------------------
    figures_by_qid = {f.qid: render_figure(f) for f in FIGURE_FACTS}

    # --- manuals ---------------------------------------------------------
    manual_paths = []
    for spec in MANUALS:
        path = render_manual(spec, manuals_dir, figures_by_qid)
        manual_paths.append(path)
        print(f"[fieldnote] wrote {path.name}")

    # --- photos ----------------------------------------------------------
    photo_paths = []
    for fig in FIGURE_FACTS:
        if fig.kind != "photo":
            continue
        image = figures_by_qid[fig.qid]
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", fig.doc).strip("_").lower()
        path = photos_dir / f"{slug}.png"
        image.save(path)
        photo_paths.append(path)
        print(f"[fieldnote] wrote {path.name}")

    # --- calls -----------------------------------------------------------
    call_paths = render_calls(calls_dir)
    for path in call_paths:
        print(f"[fieldnote] wrote {path.name}")

    return {
        "manuals": manual_paths,
        "photos": photo_paths,
        "calls": call_paths,
    }


# ---------------------------------------------------------------------------
# Collision check
# ---------------------------------------------------------------------------


def _prose_corpus() -> str:
    parts = [f.answer for f in TEXT_FACTS]
    for fact in TEXT_FACTS:
        parts.extend(fact.paragraphs)
    for fig in FIGURE_FACTS:
        parts.append(fig.caption)
    for fact in AUDIO_FACTS:
        for _speaker, line in fact.script:
            parts.append(line)
    return " ".join(parts)


def check_collisions() -> list[tuple[str, str, str]]:
    """Return [(qid, answer, where_it_leaked)] for picture-only answers that leak.

    Matching is token-aware, so an answer of "18" does not collide with the
    "187V" in another paragraph, but an answer of "14" does collide with a
    caption that reads "Figure 14".
    """
    from ..eval.metrics import contains_answer

    corpus = _prose_corpus()
    leaks: list[tuple[str, str, str]] = []
    for fig in FIGURE_FACTS:
        if not fig.answer:
            continue
        if contains_answer(fig.answer, corpus):
            leaks.append((fig.qid, fig.answer, "prose/caption/transcript"))
    return leaks


def verify_figure_answers(chunks) -> list[tuple[str, str, str]]:
    """Check that every picture-only answer survives the real OCR pipeline.

    This runs against the *ingested* chunks - the crops as they were cut out
    of the rendered manual page - not against a freshly rendered figure. The
    two are not the same: a page render downsamples the figure, and a value
    that reads fine on its own can be unreadable once it has been through a
    PDF page.
    """
    from ..eval.metrics import contains_answer
    from ..schema import Modality

    problems: list[tuple[str, str, str]] = []
    region_text: list[str] = []
    photo_text: list[str] = []
    for chunk in chunks:
        if chunk.modality is not Modality.IMAGE:
            continue
        text = chunk.text or ""
        if chunk.region_label == "full_page" or not text:
            continue
        if chunk.source_kind.value == "job_photo":
            photo_text.append(text)
        else:
            region_text.append(text)

    for fig in FIGURE_FACTS:
        pool = photo_text if fig.kind == "photo" else region_text
        if not pool:
            continue
        text = " | ".join(pool)
        if not contains_answer(fig.answer, text):
            problems.append((fig.qid, fig.answer, text[:300]))
    return problems
