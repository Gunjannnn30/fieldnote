"""Run the full evaluation and write the report.

    python scripts/run_eval.py

Reuses the manifest in ``data/artifacts/manifest.jsonl`` when it is current,
so repeated runs do not re-ingest the corpus.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fieldnote.config import settings  # noqa: E402
from fieldnote.eval.report import render  # noqa: E402
from fieldnote.eval.runner import run_full_eval  # noqa: E402
from fieldnote.ingest import ingest_corpus, read_manifest, summarize, write_manifest  # noqa: E402

manifest_path = settings.artifacts_dir / "manifest.jsonl"


def load_chunks():
    if manifest_path.exists():
        try:
            chunks = read_manifest(manifest_path)
            if chunks:
                print(f"[fieldnote] reusing manifest: {summarize(chunks)}")
                return chunks
        except Exception:  # noqa: BLE001
            pass
    print("[fieldnote] ingesting corpus...")
    t0 = time.perf_counter()
    chunks = ingest_corpus()
    print(f"[fieldnote] ingested in {time.perf_counter() - t0:.1f}s: {summarize(chunks)}")
    write_manifest(chunks, manifest_path)
    return chunks


def main() -> int:
    chunks = load_chunks()

    print("[fieldnote] building indexes (captioning the baseline, embedding both)...")
    t0 = time.perf_counter()
    report = run_full_eval(chunks, backend=settings.store_backend, k=settings.final_k)
    print(f"[fieldnote] eval finished in {time.perf_counter() - t0:.1f}s")

    text = render(report)
    out = settings.artifacts_dir / "eval_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    (settings.artifacts_dir / "eval_report.json").write_text(
        json.dumps(report.to_dict(), indent=2), encoding="utf-8"
    )
    print(text)
    print(f"\n[fieldnote] report written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
