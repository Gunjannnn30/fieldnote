"""Job-site photo ingestion.

A technician's photo of a failed part is a first-class document in this system.
It is embedded from its pixels, OCR'd for any nameplate or stamped value, and
cited back as an image.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..schema import BBox, Chunk, Modality, SourceKind
from ..vision.ocr import ocr_image, ocr_to_metadata


def ingest_image(
    image_path: str | Path,
    source_id: str,
    doc_title: str,
    out_dir: str | Path,
) -> list[Chunk]:
    from PIL import Image

    image_path = Path(image_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as im:
        width, height = im.size

    ocr = ocr_image(image_path)
    meta = ocr_to_metadata(ocr)
    meta["region_kind"] = "job_photo"

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", doc_title).strip("-").lower()[:60] or "photo"

    return [
        Chunk(
            chunk_id=f"{slug}-{source_id}",
            modality=Modality.IMAGE,
            source_id=source_id,
            source_kind=SourceKind.JOB_PHOTO,
            doc_title=doc_title,
            text=ocr.text,
            page=None,
            bbox=BBox(0, 0, width, height),
            crop_path=str(image_path),
            page_image_path=str(image_path),
            region_label="job_photo",
            metadata=meta,
        )
    ]
