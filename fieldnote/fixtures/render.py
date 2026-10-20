"""Corpus renderers.

Turns the fixture spec into a corpus that behaves like the real thing:

* real PDF manuals with prose pages and **rasterised** figures - the charts are
  images, so there is no text layer hiding the answer;
* job-site photos carrying nameplates, gauge readings and fault codes;
* recorded support calls synthesised with the Windows speech engine, so
  Whisper has genuine audio to transcribe.

The charts and wiring diagrams are deliberately rendered as bitmaps. If they
were vector, the answer would leak into the PDF text layer and the whole
experiment would be theatre.
"""

from __future__ import annotations

import io
import math
import subprocess
import tempfile
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .spec import CALLS, FIGURE_FACTS, MANUALS, Figure

# ---------------------------------------------------------------------------
# matplotlib helpers
# ---------------------------------------------------------------------------


def _mpl():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _fig_to_pil(fig) -> Image.Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight", facecolor="white")
    plt_close = _mpl().close
    plt_close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

_R410A_T = [40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160]
_R410A_BUBBLE = [78, 93, 110, 129, 151, 176, 205, 237, 274, 316, 362, 396, 425]
_R410A_DEW = [55, 66, 79, 93, 110, 130, 152, 177, 205, 237, 273, 313, 357]


def render_r410a_pt_curve(params: dict) -> Image.Image:
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(7.6, 5.4))
    ax.plot(_R410A_T, _R410A_BUBBLE, color="#1f3b6e", lw=2.6, label="BUBBLE (LIQUID)")
    ax.plot(_R410A_T, _R410A_DEW, color="#b3452e", lw=2.6, label="DEW (VAPOR)")

    hp = params.get("hp_cutout", 385)
    lp = params.get("lp_cutout", 92)
    peak = params.get("peak", 425)

    # A white plate behind each label, and the label and its value drawn as
    # separate left-aligned texts. Centring a long label pushes half of it
    # outside the axes, and OCR then loses the front of it.
    plate = dict(facecolor="white", edgecolor="none", pad=1.5)

    ax.axhline(hp, color="#8a1c1c", ls="--", lw=1.8)
    ax.text(36, hp + 13, "HP CUTOUT", color="#8a1c1c", fontsize=12,
            fontweight="bold", ha="left", va="center", bbox=plate, zorder=5)
    ax.text(66, hp + 13, f"{hp} PSI", color="#8a1c1c", fontsize=12,
            fontweight="bold", ha="left", va="center", bbox=plate, zorder=5)

    ax.axhline(lp, color="#8a1c1c", ls="--", lw=1.8)
    ax.text(36, lp - 22, "LP CUTOUT", color="#8a1c1c", fontsize=12,
            fontweight="bold", ha="left", va="center", bbox=plate, zorder=5)
    ax.text(66, lp - 22, f"{lp} PSI", color="#8a1c1c", fontsize=12,
            fontweight="bold", ha="left", va="center", bbox=plate, zorder=5)

    ax.plot([160], [peak], marker="o", ms=9, color="#111111")
    ax.text(108, peak + 20, "PEAK", color="#111111", fontsize=12,
            fontweight="bold", ha="left", va="center", bbox=plate, zorder=5)
    ax.text(128, peak + 20, f"{peak} PSIG", color="#111111", fontsize=12,
            fontweight="bold", ha="left", va="center", bbox=plate, zorder=5)

    ax.set_title("R-410A PRESSURE-TEMPERATURE CURVE", fontsize=17, fontweight="bold")
    ax.set_xlabel("SATURATION TEMPERATURE (DEG F)", fontsize=13, fontweight="bold")
    ax.set_ylabel("PRESSURE (PSIG)", fontsize=13, fontweight="bold")
    ax.set_xlim(30, 168)
    ax.set_ylim(0, 470)
    ax.grid(True, ls=":", color="#999999", lw=0.8)
    ax.tick_params(labelsize=11)
    ax.legend(fontsize=11, loc="upper left")
    return _fig_to_pil(fig)


def render_txv_superheat_chart(params: dict) -> Image.Image:
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(7.6, 5.4))
    setpoint = params.get("setpoint", 18)
    loads = [25, 50, 75, 100]
    superheat = [10, 13, 16, 17]
    ax.plot(loads, superheat, color="#1f3b6e", lw=2.8, marker="o", ms=8)
    ax.axhline(setpoint, color="#8a1c1c", ls="--", lw=1.8)
    ax.annotate(
        f"SETPOINT {setpoint} DEG F",
        xy=(27, setpoint),
        xytext=(27, setpoint + 1.6),
        color="#8a1c1c",
        fontsize=15,
        fontweight="bold",
    )
    ax.set_title("TXV SUPERHEAT ADJUSTMENT BAND", fontsize=17, fontweight="bold")
    ax.set_xlabel("PERCENT OF RATED LOAD", fontsize=13, fontweight="bold")
    ax.set_ylabel("SUPERHEAT (DEG F)", fontsize=13, fontweight="bold")
    ax.set_xlim(20, 105)
    ax.set_ylim(0, 24)
    ax.grid(True, ls=":", color="#999999", lw=0.8)
    ax.tick_params(labelsize=11)
    return _fig_to_pil(fig)


def render_performance_chart(params: dict) -> Image.Image:
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(7.6, 5.4))
    temps = [70, 80, 90, 100, 110, 115]
    amps = [24.1, 25.6, 27.4, 29.9, 32.0, 32.5]
    ax.plot(temps, amps, color="#1f3b6e", lw=2.8, marker="s", ms=8)
    ax.plot([115], [32.5], marker="o", ms=10, color="#8a1c1c")
    ax.annotate(
        f"MAX AMPS {params.get('max_amps', 32.5)} A",
        xy=(112, 32.5),
        xytext=(58, 33.6),
        color="#8a1c1c",
        fontsize=15,
        fontweight="bold",
    )
    ax.set_title("5-TON UNIT PERFORMANCE", fontsize=17, fontweight="bold")
    ax.set_xlabel("OUTDOOR TEMPERATURE (DEG F)", fontsize=13, fontweight="bold")
    ax.set_ylabel("TOTAL POWER (AMPS)", fontsize=13, fontweight="bold")
    ax.set_xlim(65, 120)
    ax.set_ylim(20, 36)
    ax.grid(True, ls=":", color="#999999", lw=0.8)
    ax.tick_params(labelsize=11)
    return _fig_to_pil(fig)


def render_subcooling_chart(params: dict) -> Image.Image:
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(7.6, 5.4))
    target = params.get("target", 14)
    amb = [70, 85, 100, 115]
    sub = [10, 11, 12, 14]
    ax.plot(amb, sub, color="#1f3b6e", lw=2.8, marker="^", ms=8)
    ax.axhline(target, color="#8a1c1c", ls="--", lw=1.8)
    ax.annotate(
        f"TARGET {target} DEG F",
        xy=(71, target),
        xytext=(71, target + 1.6),
        color="#8a1c1c",
        fontsize=15,
        fontweight="bold",
    )
    ax.set_title("SUBLCOOLING VERIFICATION CHART", fontsize=17, fontweight="bold")
    ax.set_xlabel("OUTDOOR AMBIENT (DEG F)", fontsize=13, fontweight="bold")
    ax.set_ylabel("SUBLCOOLING (DEG F)", fontsize=13, fontweight="bold")
    ax.set_xlim(65, 120)
    ax.set_ylim(6, 20)
    ax.grid(True, ls=":", color="#999999", lw=0.8)
    ax.tick_params(labelsize=11)
    return _fig_to_pil(fig)


def render_capacity_table(params: dict) -> Image.Image:
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(9.2, 4.4))
    ax.axis("off")
    rows = [
        ["TONS", "MIN SUPPLY AIR", "MAX INDOOR AIR", "MAX OUTDOOR AIR"],
        ["3", "55 DEG F", "1200 CFM", "2000 CFM"],
        ["4", "55 DEG F", "1600 CFM", "2000 CFM"],
        ["5", "55 DEG F", "2000 CFM", "2000 CFM"],
        ["6", "55 DEG F", "2400 CFM", "2400 CFM"],
    ]
    table = ax.table(
        cellText=rows,
        colLabels=None,
        loc="center",
        cellLoc="center",
        colWidths=[0.13, 0.29, 0.29, 0.29],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(17)
    table.scale(1.3, 2.4)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#333333")
        cell.set_linewidth(1.4)
        if row == 0:
            cell.set_facecolor("#dfe6f0")
            cell.set_text_props(weight="bold")
    ax.set_title("COIL CAPACITY DATA 3 TO 6 TON", fontsize=17, fontweight="bold", pad=22)
    return _fig_to_pil(fig)


def render_wiring_diagram(params: dict) -> Image.Image:
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(7.8, 5.6))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 70)
    ax.axis("off")

    ax.add_patch(plt.Rectangle((6, 8), 88, 54, fill=False, lw=2.2, color="#1f3b6e"))
    ax.text(50, 64.5, "UNIT 7 FIELD WIRING DIAGRAM", ha="center", va="center",
            fontsize=16, fontweight="bold")

    ax.text(12, 57, f"FIELD SUPPLY: {params.get('supply', '240V 3PH 60HZ')}",
            fontsize=14, fontweight="bold", color="#111111")
    ax.text(12, 51, f"DISCONNECT: {params.get('disconnect', '60A')}",
            fontsize=14, fontweight="bold", color="#111111")
    ax.text(12, 45, f"HP SWITCH: {params.get('hp_switch', '600 PSI')}",
            fontsize=14, fontweight="bold", color="#111111")
    ax.text(12, 39, "COMP CONTACTOR COIL", fontsize=14, fontweight="bold", color="#111111")

    # a plausible ladder
    y = 32
    ax.plot([12, 88], [y, y], color="#333333", lw=1.6)
    for x, label in [(16, "L1"), (28, "L2"), (40, "L3"), (56, "T-STAT R"), (68, "T-STAT C"),
                     (80, "HP SW"), (90, "LPS")]:
        ax.plot([x, x], [y, y - 6], color="#333333", lw=1.6)
        ax.text(x, y + 2.4, label, ha="center", fontsize=11, fontweight="bold")
        ax.add_patch(plt.Rectangle((x - 3, y - 10), 6, 4, fill=False, lw=1.3, color="#666666"))
    ax.text(50, 14, "LOW VOLTAGE CONTROL", ha="center", fontsize=12, fontweight="bold")
    ax.text(50, 10, "SEE CONNECTION DIAGRAM ON PAGE 41", ha="center", fontsize=10)

    return _fig_to_pil(fig)


# ---------------------------------------------------------------------------
# Job site photos
# ---------------------------------------------------------------------------

_FONT_CANDIDATES = (
    "arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/calibri.ttf",
)


def _font(size: int, bold: bool = False):
    names = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/consolab.ttf" if bold else "C:/Windows/Fonts/consola.ttf",
    ]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def _noise(img: Image.Image, amount: int = 10) -> Image.Image:
    import numpy as np

    arr = np.asarray(img).astype("int16")
    rng = np.random.default_rng(11)
    noise = rng.normal(0, amount, arr.shape[:2])[:, :, None].astype("int16")
    arr = np.clip(arr + noise, 0, 255).astype("uint8")
    return Image.fromarray(arr)


def render_photo_nameplate(params: dict) -> Image.Image:
    """A job-site photo of a condenser data plate."""
    w, h = 1200, 900
    img = Image.new("RGB", (w, h), (68, 71, 74))
    d = ImageDraw.Draw(img)

    # sheet-metal background with a lighting gradient
    for y in range(h):
        shade = int(52 + 44 * (1 - abs(y - h / 2) / (h / 2)))
        d.line([(0, y), (w, y)], fill=(shade, shade + 3, shade + 6))

    # unit casing
    d.rectangle([90, 150, w - 90, h - 90], fill=(92, 96, 100), outline=(52, 55, 58), width=6)
    for x in range(110, w - 110, 34):
        d.line([(x, 170), (x, h - 110)], fill=(104, 108, 112), width=3)

    # data plate
    px0, py0, px1, py1 = 250, 300, w - 250, 640
    d.rectangle([px0, py0, px1, py1], fill=(214, 210, 198), outline=(120, 116, 106), width=4)
    d.rectangle([px0 + 6, py0 + 6, px1 - 6, py1 - 6], outline=(150, 146, 136), width=2)

    model = params.get("model", "NP-42")
    voltage = params.get("voltage", "460V")
    refrigerant = params.get("refrigerant", "R-410A")

    lines = [
        ("NORTHPOINT MANUFACTURING", 26, True),
        ("ROOF TOP PACKAGED UNIT", 20, False),
        ("", 10, False),
        (f"MODEL   {model}", 30, True),
        (f"VOLTAGE {voltage}  3 PH  60 HZ", 24, False),
        (f"REFRIGERANT {refrigerant}", 24, False),
        ("MAX AMPS  41.2   MCA  48.0   MOCP  60", 20, False),
        ("SERIAL  NP42-8817-04", 20, False),
    ]
    y = py0 + 28
    for text, size, bold in lines:
        if text:
            d.text((px0 + 26, y), text, fill=(24, 24, 26), font=_font(size, bold))
        y += size + 16

    # rivets
    for cx, cy in [(px0 + 16, py0 + 16), (px1 - 16, py0 + 16), (px0 + 16, py1 - 16), (px1 - 16, py1 - 16)]:
        d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=(140, 136, 128), outline=(90, 88, 82))

    img = _noise(img, 9)
    return img.filter(ImageFilter.GaussianBlur(0.6))


def render_photo_gauge(params: dict) -> Image.Image:
    """A job-site photo of a manifold gauge reading."""
    import numpy as np

    w, h = 1000, 1000
    img = Image.new("RGB", (w, h), (44, 46, 50))
    d = ImageDraw.Draw(img)
    for y in range(h):
        shade = int(38 + 30 * (1 - abs(y - h / 2) / (h / 2)))
        d.line([(0, y), (w, y)], fill=(shade, shade, shade + 4))

    cx, cy, r = 500, 470, 340
    d.ellipse([cx - r - 14, cy - r - 14, cx + r + 14, cy + r + 14], fill=(206, 208, 210))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(246, 246, 243), outline=(40, 42, 46), width=6)

    for i in range(0, 360, 20):
        a = math.radians(i - 210)
        inner = (cx + (r - 34) * math.cos(a), cy + (r - 34) * math.sin(a))
        outer = (cx + (r - 12) * math.cos(a), cy + (r - 12) * math.sin(a))
        d.line([inner, outer], fill=(30, 32, 36), width=4)
        if i % 60 == 0:
            val = int((i + 210) / 300 * 800)
            tx, ty = cx + (r - 66) * math.cos(a), cy + (r - 66) * math.sin(a)
            d.text((tx - 16, ty - 12), str(val), fill=(25, 27, 30), font=_font(24, True))

    reading = float(params.get("reading", 312))
    a = math.radians((reading / 800) * 300 - 210)
    tip = (cx + (r - 60) * math.cos(a), cy + (r - 60) * math.sin(a))
    d.line([(cx, cy), tip], fill=(178, 32, 32), width=9)
    d.ellipse([cx - 18, cy - 18, cx + 18, cy + 18], fill=(60, 62, 66))

    d.text((cx - 70, cy + 130), "PSI", fill=(30, 32, 36), font=_font(34, True))
    d.text((cx - 120, cy + 190), f"{reading:.0f} PSI", fill=(16, 16, 18), font=_font(40, True))
    d.text((cx - 130, cy - 230), "MANIFOLD GAUGE", fill=(60, 62, 66), font=_font(20))

    img = _noise(img, 8)
    return img.filter(ImageFilter.GaussianBlur(0.5))


def render_photo_fault_display(params: dict) -> Image.Image:
    """A job-site photo of a control board fault display."""
    w, h = 1000, 760
    img = Image.new("RGB", (w, h), (40, 42, 46))
    d = ImageDraw.Draw(img)
    for y in range(h):
        shade = int(34 + 26 * (1 - abs(y - h / 2) / (h / 2)))
        d.line([(0, y), (w, y)], fill=(shade, shade, shade + 4))

    d.rectangle([120, 120, w - 120, h - 110], fill=(38, 40, 44), outline=(84, 88, 94), width=8)
    d.rectangle([200, 190, w - 200, 400], fill=(18, 22, 26), outline=(64, 68, 72), width=4)
    d.text((235, 215), "UNIT 7", fill=(90, 190, 120), font=_font(26, True))
    d.text((235, 265), "STATUS", fill=(90, 190, 120), font=_font(22))
    code = params.get("code", "LP-2")
    d.text((235, 305), f"FAULT {code}", fill=(232, 96, 72), font=_font(48, True))

    d.rectangle([200, 450, w - 200, h - 170], fill=(30, 32, 36), outline=(70, 74, 78), width=3)
    d.text((230, 480), "POWER  24VAC   RUN  0.00 A", fill=(160, 166, 172), font=_font(22))
    d.text((230, 525), "MODE  COOL   SET  72 F", fill=(160, 166, 172), font=_font(22))

    img = _noise(img, 8)
    return img.filter(ImageFilter.GaussianBlur(0.5))


RENDERERS = {
    "r410a_pt_curve": render_r410a_pt_curve,
    "txv_superheat_chart": render_txv_superheat_chart,
    "performance_chart": render_performance_chart,
    "subcooling_chart": render_subcooling_chart,
    "capacity_table": render_capacity_table,
    "wiring_diagram": render_wiring_diagram,
    "photo_nameplate": render_photo_nameplate,
    "photo_gauge": render_photo_gauge,
    "photo_fault_display": render_photo_fault_display,
}


def render_figure(fig: Figure) -> Image.Image:
    return RENDERERS[fig.renderer](fig.params)


# ---------------------------------------------------------------------------
# Manual PDFs
# ---------------------------------------------------------------------------

_FILLER = [
    "This section is written for a technician who has completed the safety "
    "training for this product family and who has the service manual and the "
    "applicable parts catalogue on hand.",
    "Read the entire procedure before starting. Where a step refers to another "
    "section, complete that section first and record the result on the service "
    "report form.",
    "Use calibrated instruments. Instrument readings recorded during service "
    "become part of the permanent file for the unit and are used to establish "
    "the baseline for future work.",
    "Disconnect all electrical power, including any accessory circuit, before "
    "opening the electrical compartment or working inside the unit.",
    "Verify the operation of the safety controls after any adjustment. The "
    "pressure switches and the electrical circuits that they interrupt are "
    "protective devices and shall not be bypassed.",
    "Replace any component whose part number has been superseded with the "
    "current listed part. Parts that are not listed for this application are "
    "not to be fitted.",
    "Record the model and serial number of the unit, the condition reported by "
    "the owner, and the results of every measurement taken during the call.",
]


def _wrap(text: str, width: int = 92) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    length = 0
    for w in words:
        if length + len(w) + 1 > width:
            lines.append(" ".join(cur))
            cur, length = [], 0
        cur.append(w)
        length += len(w) + 1
    if cur:
        lines.append(" ".join(cur))
    return lines


def _add_text_page(doc: fitz.Document, heading: str, paragraphs: list[str], footer: str) -> None:
    page = doc.new_page(width=612, height=792)
    top = 54
    page.insert_textbox(fitz.Rect(60, top, 552, top + 30), heading, fontsize=15, fontname="hebo",
                         color=(0.08, 0.12, 0.22))
    y = top + 34
    for para in paragraphs:
        box = fitz.Rect(60, y, 552, 700)
        rc = page.insert_textbox(box, "\n".join(_wrap(para)), fontsize=10.5, fontname="helv",
                                  lineheight=1.35)
        used = box.height - rc if rc and rc > 0 else box.height
        y += used + 16
    # footer (excluded from text extraction by the ingester)
    page.insert_textbox(
        fitz.Rect(60, 740, 552, 780), footer, fontsize=8.5, fontname="helv", color=(0.4, 0.4, 0.4)
    )


def _add_figure_page(doc: fitz.Document, heading: str, image: Image.Image, caption: str, footer: str) -> None:
    page = doc.new_page(width=612, height=792)
    page.insert_textbox(
        fitz.Rect(60, 54, 552, 92), heading, fontsize=15, fontname="hebo", color=(0.08, 0.12, 0.22)
    )
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        image.save(tmp.name)
        tmp_name = tmp.name
    try:
        box = fitz.Rect(66, 120, 546, 600)
        page.insert_image(box, filename=tmp_name, keep_proportion=True)
    finally:
        Path(tmp_name).unlink(missing_ok=True)
    page.insert_textbox(
        fitz.Rect(60, 610, 552, 660), caption, fontsize=9.5, fontname="helv", color=(0.2, 0.2, 0.2)
    )
    page.insert_textbox(
        fitz.Rect(60, 740, 552, 780), footer, fontsize=8.5, fontname="helv", color=(0.4, 0.4, 0.4)
    )


def render_manual(spec, out_dir: Path, figures_by_qid: dict[str, Image.Image]) -> Path:
    doc = fitz.open()
    by_qid = {f.qid: f for f in FIGURE_FACTS}

    # cover
    page = doc.new_page(width=612, height=792)
    page.insert_textbox(
        fitz.Rect(80, 180, 532, 260), spec.title, fontsize=26, fontname="hebo", color=(0.06, 0.10, 0.20)
    )
    page.insert_textbox(
        fitz.Rect(80, 280, 532, 340),
        "Service and Installation Manual\nIssued for field service use",
        fontsize=13, fontname="helv", color=(0.3, 0.3, 0.3),
    )

    # contents
    page = doc.new_page(width=612, height=792)
    page.insert_textbox(fitz.Rect(60, 54, 552, 92), "Table of Contents", fontsize=15, fontname="hebo")
    toc = "\n".join(f"Section {i + 1}   {name}" for i, name in enumerate(spec.sections))
    page.insert_textbox(fitz.Rect(60, 110, 552, 600), toc, fontsize=11, fontname="helv", lineheight=1.6)

    from .spec import TEXT_FACTS

    text_by_qid = {f.qid: f for f in TEXT_FACTS}

    for page_spec in spec.pages:
        facts = [text_by_qid[q] for q in page_spec["text_facts"] if q in text_by_qid]
        figs = [by_qid[q] for q in page_spec["figures"] if q in by_qid]

        if facts:
            fact = facts[0]
            paragraphs = list(fact.paragraphs)
            paragraphs.append(_FILLER[len(paragraphs) % len(_FILLER)])
            _add_text_page(doc, fact.section, paragraphs, f"{spec.title}   |   {fact.section}")
            continue

        if figs:
            fig = figs[0]
            image = figures_by_qid[fig.qid]
            _add_figure_page(doc, fig.section, image, fig.caption, f"{spec.title}   |   {fig.section}")
            continue
    out_path = out_dir / spec.filename
    doc.save(str(out_path))
    doc.close()
    return out_path


# ---------------------------------------------------------------------------
# Support calls
# ---------------------------------------------------------------------------

_PS_SCRIPT = r"""
param([string]$TextFile, [string]$Path, [string]$Voice)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$text = [System.IO.File]::ReadAllText($TextFile, [System.Text.Encoding]::UTF8)
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($Voice) { $synth.SelectVoice($Voice) }
$synth.Rate = -1
$synth.SetOutputToWaveFile($Path)
$synth.Speak($text)
$synth.Dispose()
"""


def synthesize_call(script: list[tuple[str, str]], out_path: Path) -> bool:
    """Render a call script to a WAV using the Windows speech engine.

    The utterance is passed through a UTF-8 file rather than as a command line
    argument - the transcripts contain commas and parentheses that PowerShell
    would otherwise try to interpret.
    """
    voices = ["Microsoft Zira Desktop", "Microsoft David Desktop"]
    tmpdir = Path(tempfile.mkdtemp(prefix="fieldnote_call_"))
    ps1 = tmpdir / "speak.ps1"
    ps1.write_text(_PS_SCRIPT, encoding="utf-8")
    try:
        parts: list[Path] = []
        for i, (_speaker, line) in enumerate(script):
            part = tmpdir / f"part{i:02d}.wav"
            txt = tmpdir / f"part{i:02d}.txt"
            txt.write_text(line, encoding="utf-8")
            voice = voices[i % len(voices)]
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy", "Bypass",
                    "-File", str(ps1),
                    "-TextFile", str(txt),
                    "-Path", str(part),
                    "-Voice", voice,
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            if proc.returncode != 0 or not part.exists():
                print(f"[fieldnote] tts failed: {proc.stderr.strip()[:400]}")
                return False
            parts.append(part)

        # concatenate with a short silence between speakers
        import numpy as np
        import wave  # noqa: F401

        from ..audio_util import read_wav, write_wav

        chunks = []
        sr = 22050
        for part in parts:
            samples, s = read_wav(part)
            sr = s
            chunks.append(samples)
            chunks.append(np.zeros(int(0.35 * sr), dtype="float32"))
        merged = np.concatenate(chunks)
        write_wav(out_path, merged, sr)
        return True
    finally:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


def render_calls(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    made: list[Path] = []
    for call_id, script in CALLS.items():
        path = out_dir / f"{call_id}.wav"
        if synthesize_call(script, path):
            made.append(path)
        else:
            print(f"[fieldnote] failed to synthesise call {call_id}")
    return made
