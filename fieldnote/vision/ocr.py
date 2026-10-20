"""OCR that *preserves numbers*.

This is the file that the whole project is really about.

A caption of a pressure-temperature curve says "a line graph showing discharge
pressure rising with ambient temperature". Useless. The OCR of the same crop
says "HP CUTOUT 385 PSI / 100 120 140 160 / 250 300 350 400". The first
throws away the axis values the technician actually needs; the second keeps
them.

So Fieldnote stores the OCR string *and* the OCR geometry, which lets the
answer layer find the number that belongs to a label without a vision model
guessing.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..config import settings
from .demangle import demangle


@dataclass
class OcrItem:
    text: str
    score: float
    box: tuple[float, float, float, float]  # x0, y0, x1, y1 in crop pixels

    @property
    def cx(self) -> float:
        return (self.box[0] + self.box[2]) / 2

    @property
    def cy(self) -> float:
        return (self.box[1] + self.box[3]) / 2

    def to_dict(self) -> dict:
        return {"text": self.text, "score": self.score, "box": list(self.box)}


@dataclass
class OcrResult:
    items: list[OcrItem] = field(default_factory=list)
    text: str = ""

    @property
    def numbers(self) -> list[tuple[float, OcrItem]]:
        out: list[tuple[float, OcrItem]] = []
        for it in self.items:
            for m in re.finditer(r"-?\d+(?:\.\d+)?", it.text.replace(",", "")):
                try:
                    out.append((float(m.group()), it))
                except ValueError:
                    continue
        return out

    def to_dict(self) -> dict:
        return {"text": self.text, "items": [i.to_dict() for i in self.items]}


@functools.lru_cache(maxsize=1)
def _engine():
    if not settings.ocr_enabled:
        return None
    try:
        from rapidocr_onnxruntime import RapidOCR

        return RapidOCR()
    except Exception as exc:  # noqa: BLE001
        print(f"[fieldnote] OCR disabled ({exc})")
        return None


def ocr_image(path: str | Path, demangle_text: bool = True) -> OcrResult:
    """Run OCR over an image file and return text plus per-item geometry.

    The text is de-mangled on the way out: OCR does not know where words end,
    and "LPCUTOUT92PSI" is unreadable to a cross-encoder and to a human.
    """
    engine = _engine()
    if engine is None:
        return OcrResult()

    try:
        raw, _ = engine(str(path))
    except Exception:  # noqa: BLE001
        return OcrResult()

    if not raw:
        return OcrResult()

    items: list[OcrItem] = []
    for entry in raw:
        try:
            poly, text, score = entry[0], entry[1], entry[2]
            xs = [float(p[0]) for p in poly]
            ys = [float(p[1]) for p in poly]
            label = str(text).strip()
            if demangle_text:
                label = demangle(label)
            items.append(
                OcrItem(text=label, score=float(score), box=(min(xs), min(ys), max(xs), max(ys)))
            )
        except Exception:  # noqa: BLE001
            continue

    items.sort(key=lambda i: (round(i.cy / 8), i.box[0]))
    return OcrResult(items=items, text=" | ".join(i.text for i in items))


_NUM_RE = re.compile(r"(?<![\w-])-?\d+(?:\.\d+)?(?![\w])")


def find_label_value(
    result: OcrResult,
    labels: list[str],
    *,
    max_distance: float = 260.0,
    prefer: str = "right",
) -> tuple[str, float] | None:
    """Find the number that belongs to a label inside the picture.

    Manuals label things like ``HP CUTOUT`` with the value next to it. Searching
    for "the number closest to the label" in the OCR geometry gives an exact,
    deterministic extraction from the pixels - no vision model required.
    """
    if not result.items:
        return None

    label_items = []
    for it in result.items:
        norm = it.text.upper()
        for lab in labels:
            if lab.upper() in norm:
                label_items.append((it, lab))
                break
    if not label_items:
        return None

    best: tuple[str, float] | None = None
    best_dist = float("inf")
    for lab_item, _ in label_items:
        for value, num_item in result.numbers:
            if num_item is lab_item:
                continue
            if _NUM_RE.search(lab_item.text):
                continue
            if prefer == "right":
                dx = num_item.box[0] - lab_item.box[2]
                dy = abs(num_item.cy - lab_item.cy)
                if dx < -8 or dy > max_distance * 0.35:
                    continue
                dist = (dx**2 + dy**2) ** 0.5
            else:
                dx = abs(num_item.cx - lab_item.cx)
                dy = num_item.box[1] - lab_item.box[3]
                if dy < -8 or dx > max_distance:
                    continue
                dist = (dx**2 + dy**2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best = (f"{value:g}", dist)
    return best


def ocr_to_metadata(result: OcrResult, max_items: int = 60) -> dict:
    return {
        "ocr_text": result.text,
        "ocr_items": [i.to_dict() for i in result.items[:max_items]],
    }
