"""Fixture self-test.

Two checks, both about the honesty of the benchmark rather than about the
system under test:

1. **Collision** - no picture-only answer appears in the prose, the captions
   or the transcripts. If it did, the "unanswerable from text alone" claim
   would be false.
2. **Legibility** - every picture-only answer survives the real OCR pipeline
   on the *ingested* crop. A value that cannot be read off the page is not
   evidence, and an eval that fails on it measures the fixture, not the
   system.

    python scripts/verify_fixtures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fieldnote.config import settings  # noqa: E402
from fieldnote.fixtures.build import check_collisions, verify_figure_answers  # noqa: E402
from fieldnote.ingest import ingest_corpus  # noqa: E402


def main() -> int:
    ok = True

    leaks = check_collisions()
    if leaks:
        ok = False
        print("COLLISIONS - a picture-only answer is present in the text corpus:")
        for qid, answer, where in leaks:
            print(f"  {qid}: {answer!r} found in {where}")
    else:
        print("collisions      : none - every picture-only answer is absent from the text")

    print("ingesting corpus to check legibility...")
    chunks = ingest_corpus()
    problems = verify_figure_answers(chunks)
    if problems:
        ok = False
        print("ILLEGIBLE - the answer cannot be read off the rendered page:")
        for qid, answer, text in problems:
            print(f"  {qid}: expected {answer!r}")
            print(f"      ocr: {text[:260]}")
    else:
        print("legibility      : every picture-only answer is readable from the page")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
