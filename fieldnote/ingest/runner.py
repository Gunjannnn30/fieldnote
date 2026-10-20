"""Corpus walker.

Walks the corpus directory, dispatches by file type, and emits a manifest of
chunks. The manifest is the only thing the indexer needs - it can be inspected
and diffed without touching the vector store.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..config import settings
from ..schema import Chunk
from .audio import ingest_audio
from .images import ingest_image
from .pdf import ingest_pdf

PDF_EXT = {".pdf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}


def discover(corpus_dir: str | Path) -> dict[str, list[Path]]:
    corpus_dir = Path(corpus_dir)
    buckets: dict[str, list[Path]] = {"pdf": [], "image": [], "audio": [], "other": []}
    for path in sorted(corpus_dir.rglob("*")):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext in PDF_EXT:
            buckets["pdf"].append(path)
        elif ext in IMAGE_EXT:
            buckets["image"].append(path)
        elif ext in AUDIO_EXT:
            buckets["audio"].append(path)
        else:
            buckets["other"].append(path)
    return buckets


def ingest_corpus(
    corpus_dir: str | Path | None = None,
    out_dir: str | Path | None = None,
) -> list[Chunk]:
    corpus_dir = Path(corpus_dir or settings.corpus_dir)
    out_dir = Path(out_dir or settings.artifacts_dir / "pages")
    buckets = discover(corpus_dir)

    chunks: list[Chunk] = []

    for path in buckets["pdf"]:
        source_id = f"pdf:{path.stem}"
        title = path.stem.replace("_", " ").replace("-", " ").strip()
        chunks.extend(ingest_pdf(path, source_id, title, out_dir / path.stem))

    for path in buckets["image"]:
        source_id = f"img:{path.stem}"
        title = path.stem.replace("_", " ").replace("-", " ").strip()
        chunks.extend(ingest_image(path, source_id, title, out_dir / "photos"))

    for path in buckets["audio"]:
        source_id = f"aud:{path.stem}"
        title = path.stem.replace("_", " ").replace("-", " ").strip()
        chunks.extend(ingest_audio(path, source_id, title, out_dir / "audio"))

    if buckets["other"]:
        print(f"[fieldnote] skipped {len(buckets['other'])} unsupported files")
    return chunks


def write_manifest(chunks: list[Chunk], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")
    return path


def read_manifest(path: str | Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                chunks.append(Chunk.from_dict(json.loads(line)))
    return chunks


def summarize(chunks: list[Chunk]) -> dict:
    by_modality: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for c in chunks:
        by_modality[c.modality.value] = by_modality.get(c.modality.value, 0) + 1
        by_kind[c.source_kind.value] = by_kind.get(c.source_kind.value, 0) + 1
    return {
        "total": len(chunks),
        "by_modality": by_modality,
        "by_source_kind": by_kind,
        "sources": len({c.source_id for c in chunks}),
    }
