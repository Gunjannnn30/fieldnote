"""Explaining an answer to someone who does not speak HVAC.

The retrieval engine is only half the product. The other half is that the
person reading the answer - a dispatcher, a service manager, somebody who has
never held a manifold gauge - understands what it means and where it came from.

This module turns a fragment of HVAC documentation into a sentence a
non-specialist can act on, and it defines the vocabulary in plain words so the
interface can point at what a term means instead of assuming the reader knows.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

GLOSSARY: dict[str, str] = {
    "rtu": "rooftop unit - a single box on the roof that does all the heating, cooling and ventilation for a building",
    "rooftop unit": "a single box on the roof that heats, cools and ventilates a building",
    "hvac": "heating, ventilation and air conditioning - the equipment and trade that keeps a building at a comfortable temperature",
    "compressor": "the pump at the heart of the system that moves the refrigerant around; it is what makes the noise you hear",
    "condenser": "the outside coil where the hot refrigerant dumps its heat and turns back into a liquid",
    "evaporator": "the inside coil where cold refrigerant absorbs heat from the air and boils into a gas",
    "expansion valve": "the restriction that drops the refrigerant's pressure so it can get cold",
    "txv": "thermostatic expansion valve - the valve that meters refrigerant into the evaporator",
    "refrigerant": "the fluid that carries heat around the system; R-410A is a common modern one",
    "charge": "the correct amount of refrigerant in the system - too little starves it, too much can flood it",
    "superheat": "how far the refrigerant gas is above the temperature it should be boiling at; too high means a starving evaporator",
    "subcooling": "how far the liquid refrigerant is below the temperature it should be condensing at; too high means an overcharge",
    "cutout": "a safety switch that shuts the machine down when a limit is reached, to prevent damage",
    "high pressure": "the pressure of the hot side of the system, and the thing most likely to trip a unit on a hot day",
    "low pressure": "the pressure of the cold side; too low usually means the refrigerant charge is low or a line is blocked",
    "cutout pressure": "the pressure at which a safety switch shuts the system down",
    "discharge pressure": "the pressure on the hot side, coming out of the compressor",
    "suction pressure": "the pressure on the cold side, entering the compressor",
    "pressure": "how hard the refrigerant is being pushed; measured in psi",
    "psig": "pounds per square inch, gauge pressure - measured against the open air",
    "psi": "pounds per square inch - how hard something is pushing",
    "voltage": "the electrical push; measured in volts",
    "amps": "how much electrical current is flowing; measured in amperes",
    "amperage": "how much electrical current is flowing",
    "nameplate": "the sticker on the equipment with its model number, voltage and refrigerant",
    "data plate": "the sticker on the equipment with its model number, voltage and refrigerant",
    "model number": "the code that identifies which exact machine this is",
    "wiring diagram": "the page that shows how the wires are supposed to be connected",
    "field supply": "the electricity coming from the building to the unit",
    "disconnect": "the switch that isolates a unit from the building's power",
    "economizer": "the part that lets outside air in when it is cooler and drier than the return air",
    "blower": "the fan that moves the air",
    "condenser fan": "the fan that blows air across the outside coil",
    "filter": "the part that catches dust in the return air",
    "contactor": "the switch that turns the compressor on and off",
    "capacitor": "the small can that helps the motor start",
    "fault code": "the code the unit's control board shows when something is wrong",
    "control board": "the electronics box that decides what the unit should be doing",
    "ambient temperature": "the temperature of the outside air",
    "superheat adjustment": "turning a valve to set how much refrigerant the evaporator gets",
    "rooftop": "on the roof of the building",
    "unit": "one piece of equipment",
    "refrigerant pressure": "how hard the refrigerant is being pushed around the system",
}

# Terms that need a longer explanation, keyed by what the interface shows.
_UNIT_MEANINGS: dict[str, str] = {
    "psi": "pounds per square inch - a measure of how hard the refrigerant is being pushed",
    "v": "volts - the electrical push that makes the motors run",
    "a": "amps - how much electricity the motors are drawing",
    "cfm": "cubic feet per minute - how much air the blower moves",
    "deg f": "degrees Fahrenheit",
    "f": "degrees Fahrenheit",
    "minutes": "how long the step takes",
    "hours": "how long the step takes",
    "lb": "pounds",
}

# The question tells us what kind of value is being asked for.
_QUESTION_KINDS: list[tuple[str, str]] = [
    ("pressure", "pressure"),
    ("voltage", "voltage"),
    ("temp", "temperature"),
    ("temperature", "temperature"),
    ("deg f", "temperature"),
    ("degrees", "temperature"),
    ("amp", "current"),
    ("airflow", "airflow"),
    ("cfm", "airflow"),
    ("torque", "torque"),
    ("clearance", "distance"),
    ("charge", "weight"),
    ("weight", "weight"),
    ("model", "model"),
    ("fault code", "code"),
    ("code", "code"),
    ("setpoint", "setting"),
    ("target", "setting"),
    ("rating", "rating"),
    ("disconnect", "rating"),
    ("minutes", "duration"),
    ("duration", "duration"),
    ("how long", "duration"),
    ("how many", "count"),
    ("filters", "count"),
]


def find_terms(text: str) -> list[tuple[str, str]]:
    """The glossary terms present in a piece of text, longest first."""
    if not text:
        return []
    lowered = text.lower()
    found: list[tuple[str, str]] = []
    for term, definition in GLOSSARY.items():
        if re.search(rf"\b{re.escape(term)}\b", lowered):
            found.append((term, definition))
    found.sort(key=lambda t: -len(t[0]))
    # Drop a term that is contained in a longer one already matched.
    kept: list[tuple[str, str]] = []
    for term, definition in found:
        if any(term != other and term in other for other, _ in found):
            continue
        kept.append((term, definition))
    return kept


def _answer_kind(question: str) -> str | None:
    """What kind of value is the question asking for?

    Word boundaries matter: "nameplate" contains "amp", and a nameplate
    question is not a current-draw question.
    """
    q = (question or "").lower()
    for needle, kind in _QUESTION_KINDS:
        pattern = r"\b" + re.escape(needle).replace(r"\ ", r"\s+")
        if re.search(pattern, q):
            return kind
    return None


# An identifier such as NP-42, LP-2 or R-410A. The value is the whole
# identifier, not the number hiding inside it.
_IDENTIFIER_RE = re.compile(r"\b[A-Z]{1,5}-[A-Z0-9]{1,6}\b")
# A number that stands on its own - not the "42" inside "NP-42".
_STANDALONE_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9-])-?\d+(?:\.\d+)?")


def _value(answer: str) -> str | None:
    """The value in a fragment: an identifier if there is one, else a number."""
    if not answer:
        return None
    identifier = _IDENTIFIER_RE.search(answer)
    if identifier:
        return identifier.group()
    number = _STANDALONE_NUMBER_RE.search(answer)
    return number.group() if number else None


def _numeric(answer: str) -> str | None:
    """A standalone number, ignoring numbers that are part of an identifier."""
    if not answer:
        return None
    number = _STANDALONE_NUMBER_RE.search(answer)
    return number.group() if number else None


_UNIT_PATTERN = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*"
    r"(PSIG|PSI|VAC|VOLTS?|AMPS?|CFM|DEG\s?F|°F|IN\.?\s?W\.?\s?C\.?|IN\.?\s?LB|"
    r"LBS?|LB|MINUTES?|MIN|HOURS?|HRS?|HR|%|V(?![A-Za-z]))",
    re.I,
)


def _unit_of(answer: str) -> str | None:
    """The unit the value is measured in, if the fragment says so."""
    if not answer:
        return None
    match = _UNIT_PATTERN.search(answer)
    if not match:
        return None
    unit = re.sub(r"\s+", " ", match.group(2)).lower()
    return {"volts": "v", "volt": "v", "amps": "a", "amp": "a", "hrs": "hours",
            "hr": "hours", "min": "minutes", "lbs": "lb", "in. w.c.": "in. w.c.",
            "in. w c.": "in. w.c.", "in. lb": "in. lb"}.get(unit, unit)


_EXPLANATIONS: dict[str, str] = {
    "pressure": (
        "The unit switches itself off when the refrigerant pressure reaches {value}. "
        "That is the safety limit printed on the chart - it is there to protect "
        "the compressor from damage."
    ),
    "voltage": (
        "This unit is wired for {value}. If the power at the site does not match, "
        "the machine will not run correctly."
    ),
    "temperature": (
        "The target here is {value}. Above that the equipment works harder than "
        "it is designed to, and it shuts down or reduces output."
    ),
    "current": (
        "The unit draws {value} of electrical current. Drawing more than this "
        "usually means a problem in the motors or the compressor."
    ),
    "airflow": (
        "The blower moves {value} of air. Too little means some rooms are not "
        "getting enough cooling."
    ),
    "torque": (
        "This fastener is tightened to {value}. Over- or under-tightening it is "
        "a common cause of problems on the next service call."
    ),
    "distance": (
        "There has to be {value} of clear space here, so the unit can breathe "
        "and be worked on."
    ),
    "weight": (
        "The system holds {value} of refrigerant. More or less than this and the "
        "system will not behave as designed."
    ),
    "model": (
        "This unit is {article} {value}. Everything about it - the parts, the settings, "
        "the procedure - follows from that number."
    ),
    "code": (
        "The control board is reporting {value}. That code is the unit telling "
        "you what it thinks is wrong."
    ),
    "setting": (
        "It should be set to {value}. This is a value the technician can adjust."
    ),
    "rating": (
        "The value here is {value}. It is a specification - the size of the "
        "part or the circuit the equipment expects."
    ),
    "duration": (
        "The step takes {value}."
    ),
    "count": (
        "The answer is {value}."
    ),
}


def explain(question: str, answer: str, context: str = "") -> str:
    """Turn a documentation fragment into a sentence a non-specialist can act on."""
    if not answer:
        return ""

    kind = _answer_kind(question)
    value = _value(answer)
    unit = _unit_of(answer)

    if kind and kind in _EXPLANATIONS and value:
        with_unit = f"{value} {unit}".strip() if unit else value
        article = "an" if with_unit[:1].lower() in "aeiou" or with_unit[:2].lower() in (
            "np", "lp", "hp", "mp"
        ) else "a"
        text = _EXPLANATIONS[kind].format(value=with_unit, article=article)
        # "0.5 in. w.c." already ends in a full stop.
        text = text.replace("..", ".")
        if kind in ("pressure", "voltage", "temperature", "current", "airflow", "torque",
                    "distance", "weight") and unit:
            meaning = _UNIT_MEANINGS.get(unit.split()[0]) or _UNIT_MEANINGS.get(unit)
            if meaning:
                text += f" ({meaning})."
        return text

    # No recognisable value: fall back to the fragment, lightly framed.
    fragment = " ".join((answer or "").split())
    if len(fragment) > 220:
        fragment = fragment[:217] + "..."
    return f"The documentation states: {fragment}"


def headline(question: str, answer: str) -> str:
    """A short, plain label for the answer - the first thing a reader sees."""
    kind = _answer_kind(question)
    value = _value(answer)
    unit = _unit_of(answer)
    if kind and value:
        with_unit = f"{value} {unit}".strip() if unit else value
        labels = {
            "pressure": "Pressure",
            "voltage": "Voltage",
            "temperature": "Temperature",
            "current": "Current draw",
            "airflow": "Airflow",
            "torque": "Torque",
            "distance": "Clearance",
            "weight": "Refrigerant charge",
            "model": "Model",
            "code": "Fault code",
            "setting": "Setting",
            "rating": "Rating",
            "duration": "Time",
            "count": "Count",
        }
        return f"{labels.get(kind, 'Value')}: {with_unit}"
    return " ".join((answer or "").split())[:80]
