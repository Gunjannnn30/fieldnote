"""PDF ingestion.

Each page produces three kinds of chunk:

* ``TEXT``   - the page's prose, so keyword questions hit the manual.
* ``IMAGE``  - one chunk per *figure region* (chart, wiring diagram, table),
  cropped out of the rendered page, OCR'd, and embedded from its pixels.
* ``IMAGE``  - the whole page as a fallback visual context.

The region crops are what let the answer layer say "page 112, this rectangle".
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF

from ..schema import BBox, Chunk, Modality, SourceKind
from ..vision.ocr import ocr_image, ocr_to_metadata
from ..vision.regions import detect_regions

DPI = 200
MIN_REGION_AREA_PT = 900.0
# Manuals repeat a running header/footer on every page. Excluding that band
# keeps the text index about content instead of about boilerplate, and stops
# page numbers from polluting the text space.
FOOTER_RESERVE_PT = 56.0


def chunk_text(text: str, max_chars: int = 900, overlap: int = 140) -> list[str]:
    """Group paragraphs into chunks of roughly `max_chars` with a little overlap."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        return []
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for para in paras:
        if size + len(para) > max_chars and buf:
            chunks.append("\n\n".join(buf))
            tail = buf[-1][-overlap:] if overlap else ""
            buf = [tail] if tail else []
            size = len(buf[0]) if buf else 0
        buf.append(para)
        size += len(para) + 2
    if buf:
        chunks.append("\n\n".join(buf))
    return [c.strip() for c in chunks if c.strip()]


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return s[:60] or "doc"


def ingest_pdf(
    pdf_path: str | Path,
    source_id: str,
    doc_title: str,
    out_dir: str | Path,
    *,
    dpi: int = DPI,
) -> list[Chunk]:
    """Extract text, page images and figure-region crops from a manual PDF."""
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    chunks: list[Chunk] = []
    doc = fitz.open(pdf_path)
    slug = _slug(doc_title)

    for page_index, page in enumerate(doc):
        page_no = page_index + 1
        page_key = f"{slug}-p{page_no:04d}"

        # ---------------- text ------------------------------------------
        content_rect = fitz.Rect(
            page.rect.x0, page.rect.y0, page.rect.x1, max(page.rect.y0 + 1, page.rect.y1 - FOOTER_RESERVE_PT)
        )
        # Blocks, not lines. A line-wrapped paragraph comes back with a
        # newline in the middle of a sentence, and a naive sentence splitter
        # then cuts "Install a 1/8 in. rated filter drier in the liquid line
        # between the condensing unit and the | evaporator on every 5-ton
        # R-410A circuit." in half - losing the value.
        page_text = _text_from_blocks(page, content_rect)
        for i, piece in enumerate(chunk_text(page_text)):
            chunks.append(
                Chunk(
                    chunk_id=f"{page_key}-t{i:02d}",
                    modality=Modality.TEXT,
                    source_id=source_id,
                    source_kind=SourceKind.MANUAL_PAGE,
                    doc_title=doc_title,
                    text=piece,
                    page=page_no,
                    region_label="page_text",
                    metadata={"char_len": len(piece)},
                )
            )

        # ---------------- page render ------------------------------------
        pix = page.get_pixmap(dpi=dpi)
        page_png = out_dir / f"{page_key}-page.png"
        pix.save(str(page_png))

        scale_x = pix.width / (page.rect.width or 1.0)
        scale_y = pix.height / (page.rect.height or 1.0)

        # ---------------- figure regions --------------------------------
        for r_index, region in enumerate(detect_regions(page, min_area=MIN_REGION_AREA_PT)):
            bbox_px = BBox(
                region.x0 * scale_x,
                region.y0 * scale_y,
                min(region.x1 * scale_x, pix.width),
                min(region.y1 * scale_y, pix.height),
            )
            if bbox_px.width < 24 or bbox_px.height < 24:
                continue
            crop_png = out_dir / f"{page_key}-r{r_index:02d}-{region.label}.png"
            try:
                _crop(pix, bbox_px, crop_png)
            except Exception:  # noqa: BLE001
                continue

            ocr = ocr_image(crop_png)
            meta = ocr_to_metadata(ocr)
            meta["region_kind"] = region.label
            meta["dpi"] = dpi
            label = _refine_region_label(ocr.text, region.label)
            meta["region_kind"] = label
            caption = _nearest_caption(page, region)
            if caption:
                meta["figure_caption"] = caption

            # Name the file after what it turned out to be.
            if label != region.label:
                renamed = out_dir / f"{page_key}-r{r_index:02d}-{label}.png"
                try:
                    crop_png.replace(renamed)
                    crop_png = renamed
                except OSError:
                    pass

            chunks.append(
                Chunk(
                    chunk_id=f"{page_key}-r{r_index:02d}",
                    modality=Modality.IMAGE,
                    source_id=source_id,
                    source_kind=SourceKind.MANUAL_REGION,
                    doc_title=doc_title,
                    text=ocr.text,
                    page=page_no,
                    bbox=bbox_px,
                    crop_path=str(crop_png),
                    page_image_path=str(page_png),
                    region_label=label,
                    metadata=meta,
                )
            )

        # ---------------- whole page as visual context --------------------
        chunks.append(
            Chunk(
                chunk_id=f"{page_key}-full",
                modality=Modality.IMAGE,
                source_id=source_id,
                source_kind=SourceKind.MANUAL_PAGE,
                doc_title=doc_title,
                text="",
                page=page_no,
                bbox=BBox(0, 0, pix.width, pix.height),
                crop_path=str(page_png),
                page_image_path=str(page_png),
                region_label="full_page",
                metadata={"dpi": dpi, "region_kind": "full_page"},
            )
        )

    doc.close()
    return chunks


_CHART_TOKENS = ("psi", "psig", "deg f", "temperature", "pressure", "cutout", "superheat",
                  "subcool", "bubble", "dew", "curve", "percent", "rated load", "ambient")
_WIRING_TOKENS = ("diagram", "wiring", "field supply", "disconnect", "contactor", "l1",
                  "l2", "l3", "t-stat", "hp sw", "lps", "low voltage", "24vac", "3ph")
_TABLE_TOKENS = ("cfm", "min supply air", "max indoor", "ton", "capacity", "c fm", "amps")


def _text_from_blocks(page: "fitz.Page", rect) -> str:
    """Rebuild a page's text from its blocks, keeping paragraphs intact."""
    try:
        blocks = page.get_text("blocks", clip=rect)
    except Exception:  # noqa: BLE001
        return page.get_text("text", clip=rect).strip()

    paragraphs: list[str] = []
    for block in sorted(blocks, key=lambda b: (round(b[1], 1), b[0])):
        try:
            text = block[4]
        except Exception:  # noqa: BLE001
            continue
        if not text or not text.strip():
            continue
        # Lines inside a block are a wrapped paragraph; join them with
        # spaces. Blocks are separated by a blank line.
        joined = " ".join(line.strip() for line in text.splitlines() if line.strip())
        if joined:
            paragraphs.append(joined)
    return "\n\n".join(paragraphs).strip()


def _nearest_caption(page: "fitz.Page", region) -> str:
    """Find the figure caption printed near a region on the page.

    The caption is the one piece of *readable* text that describes a figure:
    OCR of a chart comes back as "LPCUTOUT92PSI", while the caption says
    "R-410A pressure-temperature curve with safety cutouts". Attaching it
    gives the cross-encoder something a human would recognise.
    """
    try:
        blocks = page.get_text("blocks")
    except Exception:  # noqa: BLE001
        return ""

    best: tuple[float, str] = (float("inf"), "")
    for block in blocks:
        try:
            x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
        except Exception:  # noqa: BLE001
            continue
        text = " ".join(text.split())
        if not text or len(text) < 8:
            continue
        # The caption sits just below the figure, or just above it.
        below = y0 - region.y1
        above = region.y0 - y1
        if 0 <= below <= 72:
            distance = below
        elif 0 <= above <= 72:
            distance = above + 12
        else:
            continue
        # Must overlap the figure horizontally, or it belongs to another column.
        if x1 < region.x0 - 20 or x0 > region.x1 + 20:
            continue
        if distance < best[0]:
            best = (distance, text)
    return best[1]


def _refine_region_label(ocr_text: str, base_label: str) -> str:
    """Name the figure from what is actually printed inside it.

    Geometry alone cannot tell a chart from a wiring diagram when both are
    rasterised, but the text drawn inside them can.
    """
    if base_label == "table":
        return "table"
    text = (ocr_text or "").lower()
    if not text:
        return base_label if base_label not in ("photo",) else "figure"

    if sum(1 for tok in _WIRING_TOKENS if tok in text) >= 2:
        return "wiring_diagram"
    if sum(1 for tok in _TABLE_TOKENS if tok in text) >= 2:
        return "table"
    if sum(1 for tok in _CHART_TOKENS if tok in text) >= 2:
        return "chart"
    return base_label if base_label != "photo" else "figure"


def _crop(pix: "fitz.Pixmap", bbox: BBox, out_path: Path) -> None:
    """Crop a rendered page pixmap using pixel coordinates."""
    import numpy as np
    from PIL import Image

    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    img = Image.fromarray(arr[:, :, :3] if pix.n >= 3 else arr[:, :, 0])
    x0 = max(0, int(bbox.x0))
    y0 = max(0, int(bbox.y0))
    x1 = min(img.width, int(bbox.x1))
    y1 = min(img.height, int(bbox.y1))
    if x1 <= x0 or y1 <= y0:
        raise ValueError("empty crop")
    img.crop((x0, y0, x1, y1)).save(str(out_path))
