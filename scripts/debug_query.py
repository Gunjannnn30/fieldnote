"""Inspect a single query end to end.

    python scripts/debug_query.py "What is the high-pressure cutout pressure labeled on the R-410A pressure-temperature curve?"

Prints every retrieved candidate with the score trail, so a bad answer can be
traced to the stage that caused it.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fieldnote.config import settings  # noqa: E402
from fieldnote.eval.runner import build_fieldnote_system  # noqa: E402
from fieldnote.ingest import read_manifest  # noqa: E402


def main() -> int:
    question = sys.argv[1] if len(sys.argv) > 1 else (
        "What is the high-pressure cutout pressure labeled on the R-410A pressure-temperature curve?"
    )
    chunks = read_manifest(settings.artifacts_dir / "manifest.jsonl")
    system = build_fieldnote_system(chunks, db_path=str(settings.index_dir / "fieldnote.db"))

    t0 = time.perf_counter()
    result = system.retriever.search(question, k=settings.final_k)
    elapsed = (time.perf_counter() - t0) * 1000

    print(f"\nquestion: {question}")
    print(f"retrieval took {elapsed:.0f} ms   stages={ {k: round(v) for k, v in result.timings.items()} }")
    print(f"\nper-space hits: " + ", ".join(f"{k}={len(v)}" for k, v in result.per_space.items()))

    print("\nrank modality  page  fused  rerank  chunk")
    for i, cand in enumerate(result.candidates, start=1):
        c = cand.chunk
        print(
            f"{i:>4} {c.modality.value:<8} {str(c.page or '-'):>4}  "
            f"{cand.fused_score:.4f}  {(cand.rerank_score or 0):.4f}  {c.chunk_id}"
        )
        snippet = " ".join((c.text or "").split())[:130]
        if snippet:
            print(f"       text: {snippet}")

    answer = system.synthesizer.synthesize(question, result.candidates)
    print(f"\nANSWER: {answer.answer}")
    print(f"answerable: {answer.answerable}")

    from fieldnote.answer.units import chunk_relevance_map

    print("\nevidence units:")
    for unit in (result.units or [])[:10]:
        print(
            f"  {unit.score:.4f} ce={unit.ce_score:7.3f} rel={unit.chunk_relevance:.2f} "
            f"vq={unit.value_quality:.1f} [{unit.modality.value}] {unit.text!r}"
        )
        print(f"        phrase: {' '.join(unit.phrase.split())[:120]}")

    for cit in answer.citations:
        print(
            f"  cite {cit.modality.value} {cit.doc_title} p{cit.page} "
            f"region={cit.region_label} crop={bool(cit.crop_path)} audio={cit.audio_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
