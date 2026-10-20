"""Store factory + the indexer that turns chunks into vectors."""

from __future__ import annotations

from pathlib import Path

from ..config import settings
from ..encode.registry import get_audio_encoder, get_image_encoder, get_text_encoder
from ..schema import Chunk, Modality
from .base import SPACE_FOR_MODALITY, IndexedRecord, MultiSpaceStore

SPACE_DIMS = {"text": 384, "image": 512, "audio": 512}


def build_store(backend: str | None = None, db_path: str | Path | None = None) -> MultiSpaceStore:
    backend = (backend or settings.store_backend).lower()
    dims = {s: SPACE_DIMS[s] for s in SPACE_DIMS}

    if backend == "sqlite":
        from .sqlite_store import SqliteSpaceStore

        db_path = Path(db_path or (settings.index_dir / "fieldnote.db"))
        spaces = {name: SqliteSpaceStore(name, dim, db_path) for name, dim in dims.items()}
    elif backend == "pgvector":
        from .pgvector_store import PgVectorSpaceStore

        spaces = {
            name: PgVectorSpaceStore(name, dim, settings.pg_dsn) for name, dim in dims.items()
        }
    elif backend == "qdrant":
        from .qdrant_store import QdrantSpaceStore

        spaces = {
            name: QdrantSpaceStore(name, dim, settings.qdrant_url, settings.qdrant_collection)
            for name, dim in dims.items()
        }
    else:
        raise ValueError(f"unknown store backend: {backend}")
    return MultiSpaceStore(spaces)


def encode_chunks(chunks: list[Chunk]) -> list[IndexedRecord]:
    """Encode a chunk list with the encoder that owns each chunk's modality.

    Image chunks are embedded from their pixels by CLIP. Audio chunks are
    embedded from their waveform by CLAP - and *also* from their transcript
    by the text encoder, because a support call is retrieved by what was
    said, not by how it sounded. Audio is not the modality that suffers from
    being flattened; a chart is.

    Image chunks get no lexical projection. That is the whole point.
    """
    records: list[IndexedRecord] = []

    text_chunks = [c for c in chunks if c.modality is Modality.TEXT]
    audio_chunks = [c for c in chunks if c.modality is Modality.AUDIO and c.audio_path]

    # The text space holds lexical projections: prose and transcripts.
    lexical = text_chunks + audio_chunks
    if lexical:
        enc = get_text_encoder()
        vectors = enc.encode([c.text for c in lexical])
        for chunk, vec in zip(lexical, vectors, strict=False):
            records.append(IndexedRecord(chunk=chunk, space="text", vector=vec))

    image_chunks = [c for c in chunks if c.modality is Modality.IMAGE and c.crop_path]
    if image_chunks:
        enc = get_image_encoder()
        vectors = enc.encode([c.crop_path for c in image_chunks])  # type: ignore[list-item]
        for chunk, vec in zip(image_chunks, vectors, strict=False):
            records.append(IndexedRecord(chunk=chunk, space="image", vector=vec))

    if audio_chunks:
        enc = get_audio_encoder()
        vectors = enc.encode(
            [(c.audio_path, c.start_sec, c.end_sec) for c in audio_chunks]  # type: ignore[misc]
        )
        for chunk, vec in zip(audio_chunks, vectors, strict=False):
            records.append(IndexedRecord(chunk=chunk, space="audio", vector=vec))

    return records


__all__ = [
    "IndexedRecord",
    "MultiSpaceStore",
    "SPACE_FOR_MODALITY",
    "build_store",
    "encode_chunks",
]
