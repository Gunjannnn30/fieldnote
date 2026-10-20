"""Text utilities: normalisation, tokenisation and lexical relevance.

Used by the evidence selector and by the answer synthesiser. Deliberately
simple and deterministic - no opaque scoring, because the eval table has to be
auditable.
"""

from __future__ import annotations

import re

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being", "of", "on",
    "in", "at", "to", "for", "with", "and", "or", "it", "this", "that", "these",
    "those", "what", "which", "who", "how", "why", "does", "do", "did", "can",
    "could", "would", "should", "there", "their", "they", "we", "you", "i",
    "from", "by", "about", "into", "over", "after", "before", "unit", "units",
    "show", "shown", "shows", "tell", "me", "my", "our", "has", "have", "had",
}

# Words that only describe the *question*, not the evidence. Removing them
# stops "labeled", "stamped" and "photo" from diluting the overlap score.
QUESTION_SCAFFOLD = {
    "labeled", "labelled", "label", "stamped", "indicated", "indicates", "state",
    "states", "read", "reads", "value", "values", "name", "names", "number",
    "figure", "page", "find", "given", "per", "according", "spec", "specs",
    "job", "site", "photo", "picture", "image", "shot", "call", "recorded",
    "exactly", "specifically", "shown", "displayed",
}

# HVAC / service-domain equivalences. Kept small and explicit so a reviewer
# can audit exactly what the matcher treats as "the same concept".
SYNONYMS: dict[str, set[str]] = {
    "cutout": {"cutout", "cut-out", "trip", "trips", "tripping", "switch", "shutoff", "shut-off", "out"},
    "pressure": {"pressure", "press", "psi", "psig", "discharge"},
    "highpressure": {"hp", "high", "high pressure", "high-pressure"},
    "lowpressure": {"lp", "low", "low pressure", "low-pressure"},
    "temperature": {"temperature", "temp", "degrees", "ambient", "outdoor", "deg"},
    "compressor": {"compressor", "comp"},
    "contactor": {"contactor", "contact"},
    "capacitor": {"capacitor", "cap"},
    "fuse": {"fuse", "fuses", "fused"},
    "breaker": {"breaker", "disconnect", "switch"},
    "wiring": {"wiring", "diagram", "schematic", "electrical"},
    "model": {"model", "models", "part", "partnumber", "part-number", "serial", "plate", "nameplate"},
    "refrigerant": {"refrigerant", "r410a", "r-410a", "410a", "r22", "r-22", "r32", "r-32"},
    "valve": {"valve", "txv", "eevee", "expansion"},
    "fan": {"fan", "blower", "motor"},
    "short": {"short", "shorting", "tripping", "cycling", "chugging"},
    "voltage": {"voltage", "volts", "v", "vac"},
    "amps": {"amps", "amp", "amperage", "current", "a"},
    "charge": {"charge", "charged", "supercharge", "subcool"},
    "superheat": {"superheat", "sh"},
    "subcool": {"subcool", "subcooling"},
    "roof": {"roof", "rooftop", "rtu"},
    "number": {"number", "no", "num"},
    "gauge": {"gauge", "gauges", "manifold"},
    "fault": {"fault", "faults", "code", "codes", "status"},
    "airflow": {"airflow", "cfm", "cubic feet"},
    "peak": {"peak", "maximum", "max", "highest"},
    "setpoint": {"setpoint", "set point", "target", "setting"},
}

_SYNONYM_LOOKUP: dict[str, set[str]] = {}
for _canonical, _words in SYNONYMS.items():
    for _w in _words:
        _SYNONYM_LOOKUP.setdefault(_w, set()).add(_canonical)

_NUM_RE = re.compile(r"(?<![\w-])-?\d+(?:,\d{3})*(?:\.\d+)?(?![\w])")


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def tokenize(text: str) -> list[str]:
    """Split on anything that is not a word character.

    Hyphens split: "high-pressure" -> ["high", "pressure"], "r-410a" -> ["r",
    "410a"]. Keeping the hyphen would make a compound HVAC term match nothing.
    """
    return re.findall(r"[a-z0-9][a-z0-9/°]*", text.lower())


def content_tokens(text: str) -> list[str]:
    return [t for t in tokenize(text) if t not in STOPWORDS and len(t) > 1]


def question_tokens(text: str) -> list[str]:
    return [
        t
        for t in tokenize(text)
        if t not in STOPWORDS and t not in QUESTION_SCAFFOLD and len(t) > 1
    ]


def expand(tokens: list[str]) -> set[str]:
    """Expand tokens with their canonical synonyms."""
    out: set[str] = set(tokens)
    for tok in tokens:
        for canonical in _SYNONYM_LOOKUP.get(tok, ()):  # noqa: B007
            out.add(canonical)
        for group in SYNONYMS.values():
            if tok in group:
                out.update(group)
    return out


def overlap_score(query: str, candidate: str) -> float:
    """Fraction of the query's content tokens that appear in the candidate.

    The question side drops question-scaffold words ("labeled", "stamped",
    "photo") so that they do not eat the score of an answer that is otherwise
    an exact match.
    """
    q = question_tokens(query)
    if not q:
        return 0.0
    q_exp = expand(q)
    c_exp = expand(content_tokens(candidate))
    if not c_exp:
        return 0.0
    hit = len(q_exp & c_exp)
    return hit / len(q_exp)


def numbers_in(text: str) -> list[str]:
    return _NUM_RE.findall(text.replace(",", ""))


def sentences(text: str) -> list[str]:
    """Split text into sentences without breaking on abbreviations.

    "0.5 in. w.c." is one value, not two sentences. A naive split on ". "
    turns the answer into "0.5 in." and throws the unit away, which is
    exactly the kind of quiet corruption this system exists to avoid.
    """
    out: list[str] = []
    for block in re.split(r"\n+", text):
        out.extend(_split_sentences(block))
    return [s.strip() for s in out if s.strip()]


_ABBREVIATIONS = {
    "in", "w", "c", "lb", "lbs", "oz", "ft", "no", "fig", "sec", "vol", "amp",
    "psi", "cfm", "deg", "hr", "min", "approx", "dr", "mr", "ms", "jr", "sr",
    "inc", "ltd", "co", "etc", "max", "min", "mfg", "gal", "sq", "sp",
}

_NUMBERED_LABEL = re.compile(r"(figure|table|fig|step|section|note|item)\s*\d+$", re.I)


def _split_sentences(block: str) -> list[str]:
    result: list[str] = []
    start = 0
    for match in re.finditer(r"[.!?]+[ \t]+", block):
        head = block[start : match.start()]
        if not head.strip():
            continue
        if _NUMBERED_LABEL.search(head):
            continue
        last_word = re.search(r"([A-Za-z]+)$", head)
        token = last_word.group(1).lower() if last_word else ""
        if token in _ABBREVIATIONS or len(token) == 1:
            continue
        result.append(head)
        start = match.end()
    result.append(block[start:])
    return result


def compress_number(value: str) -> str:
    """'385.0' -> '385', '1,200' -> '1200'."""
    v = value.replace(",", "")
    try:
        f = float(v)
    except ValueError:
        return value
    if f.is_integer():
        return str(int(f))
    return f"{f:g}"
