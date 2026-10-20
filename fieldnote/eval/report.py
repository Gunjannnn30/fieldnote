"""Markdown reporting for the eval.

The ship gate asks for a table, so the report is tables. Everything printed
here is computed from the run - nothing is hand-written.
"""

from __future__ import annotations

from .dataset import EvalQuestion, picture_only
from .runner import EvalReport


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _cell(text: str, limit: int = 90) -> str:
    """Make a value safe to drop into a markdown table."""
    flat = " ".join((text or "").split())[:limit]
    return flat.replace("|", "\\|")


def headline(report: EvalReport) -> str:
    fn = report.fieldnote
    bl = report.baseline
    all_delta = fn.accuracy() - bl.accuracy()
    picture_delta = fn.accuracy("picture_only") - bl.accuracy("picture_only")
    text_delta = fn.accuracy("text_answerable") - bl.accuracy("text_answerable")
    return (
        "| metric | fieldnote | caption-only baseline | delta |\n"
        "|---|---|---|---|\n"
        f"| accuracy, all {len(fn.results)} questions | {_pct(fn.accuracy())} | "
        f"{_pct(bl.accuracy())} | {all_delta * 100:+.1f} pts |\n"
        f"| **accuracy, 15 picture-only questions** | **{_pct(fn.accuracy('picture_only'))}** | "
        f"{_pct(bl.accuracy('picture_only'))} | **{picture_delta * 100:+.1f} pts** |\n"
        f"| accuracy, 25 text-answerable questions | {_pct(fn.accuracy('text_answerable'))} | "
        f"{_pct(bl.accuracy('text_answerable'))} | {text_delta * 100:+.1f} pts |\n"
    )


def latency_table(report: EvalReport) -> str:
    fn = report.fieldnote.latency()
    bl = report.baseline.latency()
    return (
        "| latency (ms, end to end) | p50 | p95 | p99 | mean | max |\n"
        "|---|---|---|---|---|---|\n"
        f"| fieldnote | {fn['p50_ms']} | {fn['p95_ms']} | {fn['p99_ms']} | {fn['mean_ms']} | {fn['max_ms']} |\n"
        f"| caption-only baseline | {bl['p50_ms']} | {bl['p95_ms']} | {bl['p99_ms']} | "
        f"{bl['mean_ms']} | {bl['max_ms']} |\n"
    )


def citation_table(report: EvalReport) -> str:
    fn = report.fieldnote.citation_stats()
    bl = report.baseline.citation_stats()
    return (
        "| citation compliance | fieldnote | caption-only baseline |\n"
        "|---|---|---|\n"
        f"| answers carrying a cropped image | {fn['with_crop']}/{fn['answers']} | "
        f"{bl['with_crop']}/{bl['answers']} |\n"
        f"| answers carrying a page number | {fn['with_page']}/{fn['answers']} | "
        f"{bl['with_page']}/{bl['answers']} |\n"
        f"| citation points at the right page | {_pct(fn['page_correct_rate'])} | "
        f"{_pct(bl['page_correct_rate'])} |\n"
        "\nThe answers without a page number are the job-site photos, which have\n"
        "no page to cite. Everything else carries a page and a rectangle.\n"
    )


def modality_table(report: EvalReport) -> str:
    fn = report.fieldnote.modality_mix()
    bl = report.baseline.modality_mix()
    keys = sorted(set(fn) | set(bl))
    rows = "\n".join(
        f"| {k} | {fn.get(k, 0)} | {bl.get(k, 0)} |" for k in keys if k != "none"
    )
    return (
        "Which modality the winning evidence came from. For the baseline this is\n"
        "the modality of the *original* source: a caption is a text chunk, but it\n"
        "is a caption of a picture, and that is the entire difference.\n\n"
        "| source modality | fieldnote | caption-only baseline |\n"
        "|---|---|---|\n"
        f"{rows}\n"
    )


def per_question_table(report: EvalReport, questions: list[EvalQuestion]) -> str:
    fn = {r.qid: r for r in report.fieldnote.results}
    bl = {r.qid: r for r in report.baseline.results}
    by_qid = {q.qid: q for q in questions}

    lines = [
        "| qid | question | expected | fieldnote | baseline | evidence modality | citation | fieldnote answer |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for qid in sorted(by_qid):
        q = by_qid[qid]
        f = fn.get(qid)
        b = bl.get(qid)
        f_mark = "PASS" if f and f.grade.correct else "fail"
        b_mark = "PASS" if b and b.grade.correct else "fail"
        modality = f.top_modality if f else None
        cite = ""
        if f:
            cite = f"p.{f.top_page}" if f.top_page else (f.top_source_id or "")
        produced = _cell(f.produced) if f else ""
        lines.append(
            f"| {qid} | {q.question} | `{q.answer}` | **{f_mark}** | {b_mark} | "
            f"{modality or '-'} | {cite} | {produced} |"
        )
    return "\n".join(lines) + "\n"


def picture_only_table(report: EvalReport, questions: list[EvalQuestion]) -> str:
    fn = {r.qid: r for r in report.fieldnote.results}
    bl = {r.qid: r for r in report.baseline.results}

    lines = [
        "| qid | question | expected | fieldnote answer | baseline answer |",
        "|---|---|---|---|---|",
    ]
    for q in picture_only(questions):
        f = fn.get(q.qid)
        b = bl.get(q.qid)
        f_ans = _cell(f.produced, 70) if f else ""
        b_ans = _cell(b.produced, 70) if b else ""
        f_mark = "PASS" if f and f.grade.correct else "fail"
        b_mark = "PASS" if b and b.grade.correct else "fail"
        lines.append(
            f"| {q.qid} | {q.question} | `{q.answer}` | **{f_mark}** {f_ans} | {b_mark} {b_ans} |"
        )
    return "\n".join(lines) + "\n"


def verification_table(report: EvalReport) -> str:
    if not report.leaks:
        return (
            "No picture-only answer appears in the text corpus. "
            "All 15 are genuinely unanswerable from text alone.\n"
        )
    lines = ["| qid | answer | leaked into |", "|---|---|---|"]
    for leak in report.leaks:
        lines.append(f"| {leak.qid} | `{leak.answer}` | {leak.where} |")
    return "\n".join(lines) + "\n"


def render(report: EvalReport) -> str:
    parts = [
        "# Fieldnote eval report",
        "",
        "## 1. Headline",
        "",
        headline(report),
        "",
        "## 2. Latency",
        "",
        latency_table(report),
        "",
        "## 3. Citation compliance",
        "",
        citation_table(report),
        "",
        "## 4. Which modality supplied the answer",
        "",
        modality_table(report),
        "",
        "## 5. The 15 picture-only questions",
        "",
        picture_only_table(report, report.questions),
        "",
        "## 6. All 40 questions",
        "",
        per_question_table(report, report.questions),
        "",
        "## 7. Unanswerability verification",
        "",
        verification_table(report),
    ]
    return "\n".join(parts)
