"""Grading and measurement for the eval harness.

Answers are short facts - a number, a part code, a voltage - because a
short, checkable answer is worth more than a plausible paragraph. The grader
is deliberately transparent:

1. normalised exact containment,
2. numeric match with tolerance,
3. token F1 for near misses.

Whisper writes "ninety seven degrees" where the fixture says "97 degrees", so
number words are folded to digits before comparison. Without that, a
correct answer would be scored wrong for a spelling difference.
"""

from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, field

from ..textutil import content_tokens

# ---------------------------------------------------------------------------
# number words
# ---------------------------------------------------------------------------

_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}


def _words_to_number(tokens: list[str]) -> int | None:
    total = 0
    current = 0
    seen = False
    for tok in tokens:
        if tok in _ONES:
            current += _ONES[tok]
            seen = True
        elif tok in _TENS:
            current += _TENS[tok]
            seen = True
        elif tok == "hundred":
            current = (current or 1) * 100
            seen = True
        elif tok == "thousand":
            total += (current or 1) * 1000
            current = 0
            seen = True
        else:
            break
    if not seen:
        return None
    return total + current


def fold_number_words(text: str) -> str:
    """Rewrite "ninety seven" as "97".

    Alphanumeric runs are kept whole. Splitting them would turn "XC14" into
    "xc 14" and manufacture a number where there is none.
    """
    words = re.findall(r"[a-z0-9]+|[^\s]", text.lower())
    out: list[str] = []
    i = 0
    while i < len(words):
        if words[i].isalpha():
            j = i
            while (
                j < len(words)
                and words[j].isalpha()
                and (
                    words[j] in _ONES
                    or words[j] in _TENS
                    or words[j] in ("hundred", "thousand")
                )
            ):
                j += 1
            if j > i:
                value = _words_to_number(words[i:j])
                if value is not None:
                    out.append(str(value))
                    i = j
                    continue
        out.append(words[i])
        i += 1
    return " ".join(out)


# ---------------------------------------------------------------------------
# normalisation
# ---------------------------------------------------------------------------

_UNIT_MAP = {
    "degrees fahrenheit": "f",
    "degree fahrenheit": "f",
    "degrees": "f",
    "degree": "f",
    "deg f": "f",
    "deg fahrenheit": "f",
    "f": "f",
    "psi": "psi",
    "psig": "psi",
    "vac": "vac",
    "volts": "v",
    "volt": "v",
    "celsius": "c",
}


def canonical(text: str, merge_units: bool = False) -> str:
    """Aggressive normalisation used for both sides of the comparison.

    ``merge_units`` glues a number to the unit that follows it, so that
    "55°F" and "55 DEG F" compare equal. It is kept optional because gluing
    breaks the other way: "385" must still match "385 PSI", and gluing turns
    that into "385psi", where "385" is no longer a whole word.
    """
    text = fold_number_words(text.lower())
    text = text.replace("name plate", "nameplate").replace("name  plate", "nameplate")
    text = re.sub(r"[^a-z0-9.%°\-/ ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"°", "", text)
    for unit, canon in _UNIT_MAP.items():
        text = re.sub(rf"\b{re.escape(unit)}\b", canon, text)
    if merge_units:
        text = re.sub(r"(\d)[\s.,]*(f|c|psi|vac|v|hz|cfm|kw|deg)\b", r"\1\2", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def squash(text: str) -> str:
    """Strip every space.

    OCR frequently drops the space in a run-together label: "240V 3PH 60HZ"
    comes back as "FIELDSUPPLY:240V3PH60HZ". Comparing the squashed forms
    recovers the match without loosening the token-boundary rule.
    """
    return re.sub(r"\s+", "", canonical(text))


_PURE_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")


# A number has to be its own token. "14" is not in "XC14", and "92" is not
# in "LPCUTOUT92PSI" - but after de-mangling the second one *is* "92", and
# the first one never was a value.
_NUM_TOKEN = re.compile(r"(?<![\w-])-?\d+(?:\.\d+)?(?![\w])")
_FUZZY_THRESHOLD = 0.6


@dataclass
class Grade:
    correct: bool
    mode: str
    score: float
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "correct": self.correct,
            "mode": self.mode,
            "score": round(self.score, 4),
            "detail": self.detail,
        }


def _numbers(text: str) -> list[float]:
    return [float(m) for m in _NUM_TOKEN.findall(text.replace(",", ""))]


def grade(expected: str, produced: str) -> Grade:
    """Grade one answer."""
    exp = canonical(expected)
    got = canonical(produced)
    if not exp:
        return Grade(False, "empty", 0.0, "empty expectation")

    # 1. containment, as a standalone token
    if _matches(expected, produced):
        return Grade(True, "exact", 1.0, f"{exp!r} in answer")

    # 2. numeric match - only when the expectation is a bare number.
    #    "24VAC" must not be satisfied by a stray "24" elsewhere in the text.
    exp_nums = _numbers(exp)
    got_nums = _numbers(got)
    if exp_nums and _PURE_NUMBER.match(exp):
        for target in exp_nums:
            for value in got_nums:
                if math.isclose(value, target, rel_tol=1e-6, abs_tol=1e-6):
                    return Grade(True, "numeric", 1.0, f"{value} == {target}")
                if abs(value - target) <= max(0.02, abs(target) * 0.005):
                    return Grade(True, "numeric_tol", 0.95, f"{value} ~= {target}")

    # 3. token F1
    exp_tokens = content_tokens(exp)
    got_tokens = content_tokens(got)
    if exp_tokens and got_tokens:
        common = 0
        remaining = list(got_tokens)
        for tok in exp_tokens:
            if tok in remaining:
                remaining.remove(tok)
                common += 1
        if common:
            precision = common / len(got_tokens)
            recall = common / len(exp_tokens)
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
            if f1 >= _FUZZY_THRESHOLD:
                return Grade(True, "fuzzy", f1, f"f1={f1:.2f}")

    return Grade(False, "miss", 0.0, f"expected {exp!r}")


def _boundary_pattern(exp: str) -> re.Pattern:
    """Match `exp` as a whole word.

    "18" must not match inside "187V", and "14" must not match inside
    "XC14". Without this the collision check and the grader both produce
    false positives that quietly inflate the baseline's score.

    Run-together OCR ("MODELNP-42") is handled upstream by the de-mangler, so
    the text reaching the grader has its word breaks back.
    """
    return re.compile(r"(?<!\w)" + re.escape(exp) + r"(?!\w)")


def _squash_pattern(exp: str) -> re.Pattern:
    return re.compile(re.escape(squash(exp)))


def _variants(text: str) -> set[str]:
    """The forms of `text` worth comparing: with and without glued units."""
    return {canonical(text), canonical(text, merge_units=True)}


def _matches(expected: str, produced: str) -> bool:
    """Does the produced text contain the expected answer as a whole word?"""
    if not canonical(expected):
        return False
    for exp in _variants(expected):
        for got in _variants(produced):
            if _boundary_pattern(exp).search(got):
                return True
    # The squashed form catches labels that OCR ran together
    # ("240V 3PH 60HZ" vs "240V3PH60HZ"). It is only safe for answers that
    # are not a bare number, because a bare number has no word break to
    # protect once the spaces are gone.
    if not _PURE_NUMBER.match(canonical(expected)):
        if _squash_pattern(squash(expected)).search(squash(canonical(produced))):
            return True
    return False


def contains_answer(expected: str, haystack: str) -> bool:
    """Is `expected` present in `haystack`? Used by the unanswerability check."""
    if not canonical(expected):
        return False
    if _matches(expected, haystack):
        return True
    exp = canonical(expected)
    exp_nums = _numbers(exp)
    if exp_nums and _PURE_NUMBER.match(exp):
        for value in _numbers(canonical(haystack)):
            for target in exp_nums:
                if math.isclose(value, target, rel_tol=1e-6, abs_tol=1e-6):
                    return True
    return False


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------


@dataclass
class LatencyStats:
    count: int = 0
    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    mean: float = 0.0
    max: float = 0.0
    samples: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "p50_ms": round(self.p50, 1),
            "p95_ms": round(self.p95, 1),
            "p99_ms": round(self.p99, 1),
            "mean_ms": round(self.mean, 1),
            "max_ms": round(self.max, 1),
        }


def latency_stats(samples: list[float]) -> LatencyStats:
    if not samples:
        return LatencyStats()
    ordered = sorted(samples)
    n = len(ordered)

    def percentile(p: float) -> float:
        if n == 1:
            return ordered[0]
        idx = min(n - 1, max(0, int(round((p / 100) * (n - 1)))))
        return ordered[idx]

    return LatencyStats(
        count=n,
        p50=percentile(50),
        p95=percentile(95),
        p99=percentile(99),
        mean=statistics.fmean(ordered),
        max=ordered[-1],
        samples=list(ordered),
    )
