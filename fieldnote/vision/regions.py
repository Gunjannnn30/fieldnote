"""Region detection inside a PDF page.

A manual page is not a single image. The chart on page 112 is a sub-region of
that page, and the answer a technician needs lives in the chart, not in the
prose above it. So we cut pages into regions and index each region separately.

Vector drawings, raster images and tables each expose their own geometry in
PyMuPDF; we union the overlapping ones and label what we find.
"""

from __future__ import annotations

from dataclasses import dataclass

import fitz  # PyMuPDF


@dataclass
class Region:
    """A rectangle of a page, in PDF points."""

    x0: float
    y0: float
    x1: float
    y1: float
    label: str = "figure"

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def as_rect(self) -> fitz.Rect:
        return fitz.Rect(self.x0, self.y0, self.x1, self.y1)

    def overlaps(self, other: "Region", threshold: float = 0.3) -> bool:
        ix0, iy0 = max(self.x0, other.x0), max(self.y0, other.y0)
        ix1, iy1 = min(self.x1, other.x1), min(self.y1, other.y1)
        inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
        smaller = min(self.area, other.area) or 1.0
        return inter / smaller > threshold

    def union(self, other: "Region") -> "Region":
        return Region(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
            self.label if self.label == other.label else "figure",
        )


def _long_axis_lines(drawings: list, rect: fitz.Rect) -> int:
    """Count long straight segments inside the rect - axes of a chart."""
    count = 0
    for d in drawings:
        r = d.get("rect")
        if r is None or not rect.intersects(r):
            continue
        for item in d.get("items", []):
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                if max(abs(p2.x - p1.x), abs(p2.y - p1.y)) > 0.6 * max(rect.width, rect.height):
                    count += 1
    return count


def detect_regions(page: "fitz.Page", min_area: float = 900.0) -> list[Region]:
    """Find chart / diagram / photo / table regions on a page."""
    regions: list[Region] = []

    # --- vector clusters (charts, wiring diagrams, callouts) ---------------
    try:
        clusters = page.cluster_drawings()
    except Exception:  # noqa: BLE001
        clusters = []
    drawings = page.get_drawings()
    for rect in clusters:
        if rect.is_empty or rect.get_area() < min_area:
            continue
        regions.append(Region(rect.x0, rect.y0, rect.x1, rect.y1, label="vector"))

    # --- raster images (scanned photos, rasterised charts) -----------------
    try:
        for info in page.get_image_info():
            bbox = info.get("bbox")
            if not bbox:
                continue
            x0, y0, x1, y1 = bbox
            if (x1 - x0) * (y1 - y0) < min_area:
                continue
            regions.append(Region(x0, y0, x1, y1, label="raster"))
    except Exception:  # noqa: BLE001
        pass

    # --- tables ------------------------------------------------------------
    try:
        for table in page.find_tables().tables:
            bbox = table.bbox
            if bbox is None:
                continue
            x0, y0, x1, y1 = bbox
            if (x1 - x0) * (y1 - y0) < min_area:
                continue
            regions.append(Region(x0, y0, x1, y1, label="table"))
    except Exception:  # noqa: BLE001
        pass

    # --- merge overlaps ----------------------------------------------------
    merged: list[Region] = []
    for reg in sorted(regions, key=lambda r: -r.area):
        hit = next((m for m in merged if m.overlaps(reg)), None)
        if hit is not None:
            merged[merged.index(hit)] = hit.union(reg)
        else:
            merged.append(reg)

    page_area = page.rect.get_area() or 1.0
    out: list[Region] = []
    for reg in merged:
        if reg.area < min_area:
            continue
        if reg.area / page_area > 0.93:
            # This is basically the whole page - it is not a figure.
            continue
        reg.label = _classify(page, reg, drawings)
        out.append(reg)
    return out


def _classify(page: "fitz.Page", region: Region, drawings: list) -> str:
    rect = region.as_rect()
    label = region.label if region.label != "vector" else "vector"

    if label == "table":
        return "table"

    if label == "raster":
        return "photo"

    axes = _long_axis_lines(drawings, rect)
    if axes >= 2:
        return "chart"

    # A wiring diagram is a dense cluster of short segments plus many labels.
    text_words = page.get_text("words", clip=rect)
    seg_count = 0
    for d in drawings:
        r = d.get("rect")
        if r is not None and rect.intersects(r):
            seg_count += len(d.get("items", []))
    if len(text_words) >= 8 and seg_count >= 12:
        return "wiring_diagram"

    return "diagram"
