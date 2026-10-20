"""De-mangling OCR output.

Optical character recognition does not know where words end. A chart
annotation that reads ``HIGH PRESSURE CUTOUT 385 PSI`` comes back as
``HIGHPRESSURECUTOUT385PSI``, and a wiring diagram label as
``FIELDSUPPLY:240V3PH60HZ``.

That is not cosmetic. It is the difference between a token the cross-encoder
can read and a token it cannot, and between an answer of "92" and an answer
of "LPCUTOUT92PSI" that a human has to decode.

The splitter is deliberately conservative: a run-together token is only split
when *every* piece of it is either a known domain word or a number. Anything
it cannot fully account for is left exactly as it was found. Guessing would
corrupt the evidence, and corrupted evidence is worse than ugly evidence.
"""

from __future__ import annotations

import functools
import re

# HVAC and electrical service vocabulary, longest first at match time.
VOCABULARY: set[str] = {
    # units
    "PSI", "PSIG", "AMPS", "CFM", "VOLTS", "VOLT", "DEGF", "DEGC", "DEG", "HZ",
    "KW", "KVA", "LB", "IN", "PCT", "PH", "MCA", "MOCP", "SQUARE",
    # pressures and cuts
    "HIGH", "LOW", "PRESSURE", "CUTOUT", "TRIP", "SETPOINT", "TARGET", "PEAK",
    "MAX", "MIN", "SUPERHEAT", "SUBCOOLING", "SUBLCOOLING", "SUBCOOL", "TEMPERATURE",
    "AMBIENT", "SATURATION", "BUBBLE", "LIQUID", "DEW", "VAPOR", "DISCHARGE",
    "SUPERHEAT", "LOAD", "RATED", "PERCENT", "POWER", "TOTAL", "CAPACITY",
    # equipment
    "COMPRESSOR", "CONTACTOR", "COIL", "CONDENSER", "EVAPORATOR", "BLOWER",
    "FAN", "MOTOR", "VALVE", "TXV", "EXPANSION", "FILTER", "DRIER", "ACCUMULATOR",
    "REFRIGERANT", "R410A", "R22", "R32", "PUMP", "TANKS", "TANK",
    "COMP", "COMPRESSORS", "SWITCHES", "BREAKER", "FUSES", "FUSE",
    # electrical
    "FIELD", "SUPPLY", "DISCONNECT", "SWITCH", "WIRING", "DIAGRAM", "CONTROL",
    "LOW", "VOLTAGE", "CURRENT", "GROUND", "AUXILIARY", "STAT", "CONTACTOR",
    "LPS", "HPS", "UNIT", "PAGE", "SEE", "CONNECTION", "ON", "OF", "TO", "AND",
    "LOW", "HP", "LP", "SW", "L1", "L2", "L3", "PHASE", "CIRCUIT",
    # identification
    "MODEL", "NAMEPLATE", "NAME", "PLATE", "SERIAL", "NP", "PN", "PART",
    "VOLTAGE", "FAULT", "CODE", "STATUS", "GAUGE", "MANIFOLD", "READING",
    "PRESSURE", "DATA", "INFORMATION", "ROOFTOP", "PACKAGED", "MANUFACTURING",
    "OIL", "PACK", "CONDENSING", "UNIT", "TABLES", "TABLE", "ADJUSTMENT",
    "VERIFICATION", "BAND", "CHART", "CURVE", "PERFORMANCE", "COOLING", "HEATING",
    "EFFICIENCY", "RATED", "LOAD", "COIL", "DATA", "TONS", "TON", "AIR",
    "INDOOR", "OUTDOOR", "SUPPLY", "RETURN", "MIXED", "ENTERING", "LEAVING",
    "SUPERHEAT", "RANGE", "SET", "SETTING", "CHECK", "TEST", "PROCEDURE",
    "INSTALLED", "INSTALLATION", "SERVICE", "MANUAL", "FIGURE", "TABLE", "SHEET",
    "R", "C", "A", "W", "V", "F",
}

_SPLIT_PUNCT = re.compile(r"[^A-Za-z0-9.]+")
_NUM = re.compile(r"^\d+(?:\.\d+)?$")
_NUM_PREFIX = re.compile(r"^\d+(?:\.\d+)?")


_SINGLE_LETTERS = {"R", "C", "A", "W", "V", "F"}


def _is_number(token: str) -> bool:
    return bool(_NUM.match(token))


def _split_token(token: str) -> list[str] | None:
    """Split one run-together token, or return None if we cannot fully account for it.

    This is a search, not a greedy scan. Greedy longest-match takes "HPS" out
    of "HPSWITCH" and then dead-ends on "ITCH"; the search finds
    "HP" + "SWITCH" instead. Only a segmentation that covers the *whole* token
    is accepted - a partial split would silently corrupt the evidence.
    """
    if len(token) < 4:
        return None
    upper = token.upper()
    if not upper.replace(".", "").isalnum():
        return None

    @functools.lru_cache(maxsize=None)
    def solve(i: int) -> tuple[str, ...] | None:
        if i >= len(upper):
            return ()
        if upper[i] == ".":
            # A dot between a number and a word is a separator, not a value.
            return solve(i + 1)

        match = _NUM_PREFIX.match(upper[i:])
        if match:
            rest = solve(i + len(match.group()))
            if rest is not None:
                return (match.group(),) + rest

        for size in range(min(12, len(upper) - i), 0, -1):
            piece = upper[i : i + size]
            if piece not in VOCABULARY:
                continue
            if size == 1 and piece not in _SINGLE_LETTERS:
                continue
            rest = solve(i + size)
            if rest is not None:
                return (piece,) + rest
        return None

    parts = solve(0)
    if parts is None or len(parts) < 2:
        return None
    return list(parts)


_WORD_RE = re.compile(r"[A-Za-z0-9.]+(?:-[A-Za-z0-9.]+)*")


def demangle(text: str) -> str:
    """Insert the missing word breaks in run-together OCR text.

    Hyphens are preserved. They are part of the identifiers a technician has
    to read back - "NP-42", "LP-2" - and turning them into spaces would make
    the answer wrong rather than merely ugly.
    """
    if not text:
        return text

    words: list[str] = []
    for raw in text.split():
        rebuilt: list[str] = []
        for piece in _WORD_RE.findall(raw):
            if "-" in piece:
                sub = [_demangle_piece(p) for p in piece.split("-")]
                rebuilt.append("-".join(sub))
            else:
                rebuilt.append(_demangle_piece(piece))
        if rebuilt:
            words.append(" ".join(rebuilt))
    return " ".join(words)


def _demangle_piece(piece: str) -> str:
    if piece.isupper() and len(piece) >= 4:
        parts = _split_token(piece)
        if parts:
            return " ".join(parts)
    return piece


def demangle_items(items: list[dict]) -> list[dict]:
    """Demangle the text of every OCR item, keeping the original alongside."""
    out = []
    for item in items:
        new = dict(item)
        new["raw_text"] = item.get("text", "")
        new["text"] = demangle(item.get("text", ""))
        out.append(new)
    return out
