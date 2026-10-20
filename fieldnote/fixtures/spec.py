"""Fixture specification: one source of truth for the corpus *and* the eval set.

The corpus is synthetic - we do not have 300 real HVAC manuals - but the
structure is faithful to the real thing:

* manuals whose prose carries the service procedures,
* charts, wiring diagrams and spec tables that live *only* as raster images,
* job-site photos carrying nameplate and gauge readings,
* recorded support calls carrying facts the paperwork never had.

Every question below is answered by exactly one piece of evidence, and the
generator that renders that evidence is named in the same record. That means
the ground truth cannot drift away from the corpus: change the spec and both
the corpus and the eval set change together.

The 15 ``image`` questions are the load-bearing ones - their answers appear in
*no* text chunk, *no* caption and *no* transcript. `fieldnote.eval.verify`
proves that at run time rather than asserting it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TextFact:
    """A fact that lives in manual prose."""

    qid: str
    question: str
    answer: str
    doc: str
    section: str
    paragraphs: list[str]


@dataclass
class AudioFact:
    """A fact that lives only in a recorded support call."""

    qid: str
    question: str
    answer: str
    call: str
    script: list[tuple[str, str]]


@dataclass
class Figure:
    """A fact that lives only inside a picture."""

    qid: str
    question: str
    answer: str
    doc: str
    section: str
    kind: str           # chart | wiring | table | photo
    renderer: str       # name of the render function
    params: dict = field(default_factory=dict)
    caption: str = ""   # printed under the figure; never contains the answer


@dataclass
class ManualSpec:
    title: str
    filename: str
    sections: list[str]
    pages: list[dict]   # {"text_facts": [...], "figures": [...]}


# ---------------------------------------------------------------------------
# Manual prose facts (21)
# ---------------------------------------------------------------------------

TEXT_FACTS: list[TextFact] = [
    TextFact(
        "T01",
        "What is the required filter differential pressure for the YSC072 economizer?",
        "0.5 in. w.c.",
        "Trane Precedent YSC072 Service Manual",
        "Economizer Setup",
        [
            "Before energising the economizer, verify that the filters are clean. The "
            "economizer control module compares the mixed-air temperature against the "
            "return-air temperature and will not enable the damper until the filter "
            "differential pressure has been verified. The required filter differential "
            "pressure for this unit is 0.5 in. w.c. measured across the bank at the "
            "design airflow.",
            "Check the differential pressure reading at the filter gauge before "
            "commissioning the economizer. A reading above the specified value "
            "indicates a loaded filter bank or a partially closed damper, and the "
            "economizer will remain in minimum position until the fault is cleared.",
        ],
    ),
    TextFact(
        "T02",
        "What supply air total external static pressure should the YSC072 be set to?",
        "0.75 in. w.c.",
        "Trane Precedent YSC072 Service Manual",
        "Airflow Setup",
        [
            "Set the supply air total external static pressure to 0.75 in. w.c. This "
            "value is the design point for the standard 3-ton to 6-ton configuration "
            "and is verified during the airflow test procedure in Section 6.",
        ],
    ),
    TextFact(
        "T03",
        "How long must the YSC072 be operated before the subcooling is checked?",
        "15 minutes",
        "Trane Precedent YSC072 Service Manual",
        "Refrigerant Charge",
        [
            "Operate the unit with the doors open and the economizer disabled for 15 "
            "minutes before reading the suction and liquid line gauges. The "
            "refrigerant charge must be allowed to migrate out of the condenser "
            "accumulator before the subcooling is calculated, otherwise the reading "
            "will be falsely low.",
        ],
    ),
    TextFact(
        "T04",
        "What is the required nitrogen purge duration before brazing on a R-410A line set?",
        "10 minutes",
        "Trane Precedent YSC072 Service Manual",
        "Brazing Procedures",
        [
            "Flow dry nitrogen through the line set at a minimum of 2 scfh for 10 "
            "minutes before the torch is lit. On R-410A circuits the purge must run "
            "continuously during the brazing operation, and the nitrogen flow must "
            "not be interrupted while the joint is hot.",
        ],
    ),
    TextFact(
        "T05",
        "What is the minimum clearance between the outdoor coil and an obstruction?",
        "12 inches",
        "Trane Precedent YSC072 Service Manual",
        "Service Clearances",
        [
            "Maintain a minimum clearance of 12 inches between the outdoor coil face "
            "and any obstruction such as a wall, fence or parapet. Where the "
            "clearance cannot be maintained, consult the application engineering "
            "group before the unit is installed.",
        ],
    ),
    TextFact(
        "T06",
        "What torque is specified for the YSC072 compressor terminal cover screws?",
        "12 in. lb",
        "Trane Precedent YSC072 Service Manual",
        "Compressor Replacement",
        [
            "Remove the compressor terminal cover and loosen the three connector "
            "screws. Torque the terminal cover screws to 12 in. lb when reinstalling "
            "the cover. Over-torquing the cover will crack the plastic housing and "
            "allow moisture into the terminal box.",
        ],
    ),
    TextFact(
        "T07",
        "What is the maximum supply air temperature drop in YSC072 dehumidification mode?",
        "20°F",
        "Trane Precedent YSC072 Service Manual",
        "Dehumidification",
        [
            "In dehumidification mode the unit controls the supply air leaving the "
            "evaporator to a maximum of 20°F below the mixed-air temperature. A "
            "larger split causes the coil to flood and the condensate drain to "
            "overflow.",
        ],
    ),
    TextFact(
        "T08",
        "What liquid line filter size is specified for a 5-ton R-410A 48TC circuit?",
        "1/8 in.",
        "Carrier WeatherMaster 48TC Service Manual",
        "Refrigerant Piping",
        [
            "Install a 1/8 in. rated filter drier in the liquid line between the "
            "condensing unit and the evaporator on every 5-ton R-410A circuit. The "
            "filter drier must be installed in the upright orientation with the "
            "inlet upstream of the outlet.",
        ],
    ),
    TextFact(
        "T09",
        "What branch circuit size is required for the 208V single-phase 3-ton 48TC?",
        "40A",
        "Carrier WeatherMaster 48TC Service Manual",
        "Electrical Data",
        [
            "The 208V single-phase 3-ton unit requires a 40A branch circuit with "
            "copper conductors sized per the National Electrical Code. The 240V "
            "three-phase configurations require a larger branch circuit; consult the "
            "electrical data table in this section for the specific unit.",
        ],
    ),
    TextFact(
        "T10",
        "What is the factory charge weight of the 3-ton Carrier 48TC using R-410A?",
        "8.5 lb",
        "Carrier WeatherMaster 48TC Service Manual",
        "Refrigerant Charge",
        [
            "The factory charge for the 3-ton unit using R-410A is 8.5 lb. Field "
            "added refrigerant must be weighed in and recorded on the unit data "
            "plate. Do not estimate the charge by feel or by sight.",
        ],
    ),
    TextFact(
        "T11",
        "How many filters does the Carrier 48TC filter rack accept?",
        "4",
        "Carrier WeatherMaster 48TC Service Manual",
        "Maintenance",
        [
            "The filter rack accepts 4 standard 2-inch pleated filters in the "
            "standard 48TC cabinet. Confirm that the filter retaining clips are "
            "fully engaged after each filter change.",
        ],
    ),
    TextFact(
        "T12",
        "What is the minimum acceptable voltage at the unit disconnect during startup?",
        "187V",
        "Carrier WeatherMaster 48TC Service Manual",
        "Startup",
        [
            "During startup the unit disconnect must show at least 187V on a 208V "
            "system. A lower reading indicates excessive voltage drop in the feeder "
            "or a loose connection and will cause the compressor contactor to "
            "chatter or drop out on the first call for cooling.",
        ],
    ),
    TextFact(
        "T13",
        "What is the required condensing temperature approach above ambient on the XC14?",
        "5°F",
        "Lennox XC14 Service Manual",
        "Condenser Operation",
        [
            "The condensing temperature should run 5°F above the outdoor ambient "
            "temperature at steady state. A higher approach indicates a dirty coil, a "
            "refrigerant overcharge, or a condenser fan running below speed.",
        ],
    ),
    TextFact(
        "T14",
        "What superheat range should a thermostatic expansion valve system hold at rated load?",
        "8°F to 12°F",
        "Lennox XC14 Service Manual",
        "Refrigerant Charge",
        [
            "A thermostatic expansion valve system should hold a superheat of 8°F to "
            "12°F at rated load. Readings below the band indicate a valve that is "
            "not sealing and is flooding the evaporator; readings above the band "
            "indicate a starving valve or a plugged filter drier.",
        ],
    ),
    TextFact(
        "T15",
        "What is the maximum ambient temperature for rated capacity on the XC14?",
        "125°F",
        "Lennox XC14 Service Manual",
        "Application Limits",
        [
            "The XC14 must not be used for rated capacity above a 125°F ambient "
            "temperature. Between 105°F and 125°F the unit applies a published "
            "capacity derate. Above 125°F the unit is outside its listed "
            "application limits.",
        ],
    ),
    TextFact(
        "T16",
        "What is the specified control voltage for the YK series controls?",
        "24V",
        "Johnson Controls YK Series Installation Manual",
        "Electrical Data",
        [
            "All YK series controls operate on 24V control power supplied from the "
            "factory control transformer. Field wiring to the thermostat and the "
            "control board must be Class 2 and must not be routed with the line "
            "voltage conductors.",
        ],
    ),
    TextFact(
        "T17",
        "What is the specified minimum duct static pressure the YK blower is rated for?",
        "0.25 in. w.c.",
        "Johnson Controls YK Series Installation Manual",
        "Blower Performance",
        [
            "The YK blower is rated down to a minimum duct static pressure of 0.25 "
            "in. w.c. Below this value the wheel will stall and the motor will "
            "overheat on continuous operation.",
        ],
    ),
    TextFact(
        "T18",
        "What is the recommended cooling temperature differential on the YSC072 controller?",
        "4°F",
        "Trane Precedent YSC072 Service Manual",
        "Thermostat Setup",
        [
            "Set the cooling temperature differential to 4°F for the standard "
            "YSC072 controller. A 2°F differential is acceptable in dry climates "
            "with a low latent load; do not exceed 5°F.",
        ],
    ),
    TextFact(
        "T19",
        "What is the maximum allowable pressure drop across the liquid line filter drier during a pull-down?",
        "2 psi",
        "Carrier WeatherMaster 48TC Service Manual",
        "Refrigerant Piping",
        [
            "During a full pull-down the pressure drop across the liquid line filter "
            "drier must not exceed 2 psi. A larger drop indicates a restricted drier "
            "or a kinked liquid line and will starve the evaporator during a pull-down.",
        ],
    ),
    TextFact(
        "T20",
        "What condensing temperature should be targeted on the XC14 when the outdoor temperature is 95°F?",
        "115°F",
        "Lennox XC14 Service Manual",
        "Condenser Operation",
        [
            "When the outdoor temperature is 95°F the target condensing temperature "
            "is 115°F. The readings are taken at the liquid line at the condenser "
            "outlet and are corrected for the distance between the tap and the unit.",
        ],
    ),
    TextFact(
        "T21",
        "What is the specified torque for the YK thermostat setpoint screw?",
        "6 in. lb",
        "Johnson Controls YK Series Installation Manual",
        "Thermostat Setup",
        [
            "Torque the setpoint screw on the YK thermostat to 6 in. lb after "
            "adjusting the heating and cooling setpoints. Turning the screw tighter "
            "than this will strip the brass insert in the thermostat housing.",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Audio facts (4) - these live in the recording, and only in the recording.
# ---------------------------------------------------------------------------

AUDIO_FACTS: list[AudioFact] = [
    AudioFact(
        "A01",
        "Which roof was the unit that kept tripping on high pressure located on?",
        "roof B",
        "call_unit7_hp_trip",
        [
            ("caller", "Hi, I've got a rooftop unit that keeps tripping on high pressure. It's been going for about a week now."),
            ("agent", "Thanks for calling. Can you give me the unit location so I can pull the record?"),
            ("caller", "It's on roof B, at the back of the building, next to the stairwell mechanical room."),
            ("agent", "I have the record open. Let me also confirm what you're seeing on the site."),
        ],
    ),
    AudioFact(
        "A02",
        "What temperature did the technician say it was outside during the support call?",
        "97°F",
        "call_unit7_hp_trip",
        [
            ("caller", "The thermostat was set to seventy two degrees and it was ninety seven degrees outside."),
            ("agent", "Understood. Has the unit been running continuously or cycling?"),
            ("caller", "It cycles. Runs for a few minutes and then shuts down again."),
        ],
    ),
    AudioFact(
        "A03",
        "What did the support line tell the technician to photograph and send back?",
        "the nameplate",
        "call_unit7_hp_trip",
        [
            ("agent", "I need to see the nameplate on the unit to confirm the model and the refrigerant type."),
            ("caller", "Okay, I will go photograph the nameplate and send it in."),
            ("agent", "Perfect. While you are up there, photograph the wiring label at the disconnect as well."),
        ],
    ),
    AudioFact(
        "A04",
        "What did the technician say had a brown crust on it?",
        "brown crust",
        "call_nameplate_mismatch",
        [
            ("caller", "While I was in the panel I could see the contactor has some rust on it."),
            ("agent", "Is the pitting on the contactor terminals or on the housing?"),
            ("caller", "It is on the terminals. There is a brown crust on two of them."),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Figure facts (15) - the answer exists ONLY inside the picture.
# ---------------------------------------------------------------------------

FIGURE_FACTS: list[Figure] = [
    # ---------------- charts (6) ----------------
    Figure(
        "I01",
        "What is the high-pressure cutout pressure labeled on the R-410A pressure-temperature curve?",
        "385",
        "Trane Precedent YSC072 Service Manual",
        "Refrigerant Pressure Curves",
        "chart",
        "r410a_pt_curve",
        {"refrigerant": "R-410A", "hp_cutout": 385, "lp_cutout": 92, "peak": 425},
        "Figure 14. R-410A pressure-temperature curve with safety cutouts.",
    ),
    Figure(
        "I02",
        "What is the low-pressure cutout pressure labeled on the R-410A pressure-temperature curve?",
        "92",
        "Trane Precedent YSC072 Service Manual",
        "Refrigerant Pressure Curves",
        "chart",
        "r410a_pt_curve",
        {"refrigerant": "R-410A", "hp_cutout": 385, "lp_cutout": 92, "peak": 425},
        "Figure 14. R-410A pressure-temperature curve with safety cutouts.",
    ),
    Figure(
        "I03",
        "What peak discharge pressure is labeled on the R-410A pressure-temperature curve?",
        "425",
        "Trane Precedent YSC072 Service Manual",
        "Refrigerant Pressure Curves",
        "chart",
        "r410a_pt_curve",
        {"refrigerant": "R-410A", "hp_cutout": 385, "lp_cutout": 92, "peak": 425},
        "Figure 14. R-410A pressure-temperature curve with safety cutouts.",
    ),
    Figure(
        "I04",
        "What superheat setpoint is labeled on the TXV superheat adjustment chart?",
        "18",
        "Carrier WeatherMaster 48TC Service Manual",
        "TXV Adjustment",
        "chart",
        "txv_superheat_chart",
        {"setpoint": 18},
        "Figure 22. TXV superheat adjustment band.",
    ),
    Figure(
        "I05",
        "What maximum amp draw is labeled on the 5-ton performance chart?",
        "32.5",
        "Carrier WeatherMaster 48TC Service Manual",
        "Performance Data",
        "chart",
        "performance_chart",
        {"tons": 5, "max_amps": 32.5},
        "Figure 31. 5-ton unit performance, amps versus outdoor temperature.",
    ),
    Figure(
        "I06",
        "What subcooling target is labeled on the subcooling verification chart?",
        "16",
        "Lennox XC14 Service Manual",
        "Charge Verification",
        "chart",
        "subcooling_chart",
        {"target": 16},
        "Figure 9. Subcooling verification at rated load.",
    ),
    # ---------------- wiring diagrams (3) ----------------
    Figure(
        "I07",
        "What field supply voltage is printed on the YSC072 unit 7 wiring diagram?",
        "240V 3PH 60HZ",
        "Trane Precedent YSC072 Service Manual",
        "Electrical Schematics",
        "wiring",
        "wiring_diagram",
        {"supply": "240V 3PH 60HZ", "disconnect": "60A", "hp_switch": "600 PSI"},
        "Figure 41. Field wiring diagram, 3-phase.",
    ),
    Figure(
        "I08",
        "What disconnect rating is printed on the YSC072 unit 7 wiring diagram?",
        "60A",
        "Trane Precedent YSC072 Service Manual",
        "Electrical Schematics",
        "wiring",
        "wiring_diagram",
        {"supply": "240V 3PH 60HZ", "disconnect": "60A", "hp_switch": "600 PSI"},
        "Figure 41. Field wiring diagram, 3-phase.",
    ),
    Figure(
        "I09",
        "What high-pressure switch setpoint is printed on the unit 7 wiring diagram?",
        "600 PSI",
        "Trane Precedent YSC072 Service Manual",
        "Electrical Schematics",
        "wiring",
        "wiring_diagram",
        {"supply": "240V 3PH 60HZ", "disconnect": "60A", "hp_switch": "600 PSI"},
        "Figure 41. Field wiring diagram, 3-phase.",
    ),
    # ---------------- spec tables (2) ----------------
    Figure(
        "I10",
        "What minimum supply air temperature is listed in the coil capacity table?",
        "55°F",
        "Carrier WeatherMaster 48TC Service Manual",
        "Coil Capacity Data",
        "table",
        "capacity_table",
        {"min_supply_air": "55°F"},
        "Table 7. Coil capacity, 3 to 6 ton.",
    ),
    Figure(
        "I11",
        "What maximum indoor airflow is listed in the 6-ton capacity table?",
        "2400 CFM",
        "Carrier WeatherMaster 48TC Service Manual",
        "Coil Capacity Data",
        "table",
        "capacity_table",
        {"min_supply_air": "55°F"},
        "Table 7. Coil capacity, 3 to 6 ton.",
    ),
    # ---------------- job site photos (4) ----------------
    Figure(
        "I12",
        "What model number is stamped on the nameplate in the job site photo?",
        "NP-42",
        "Job Photo - Unit 7 Nameplate",
        "Roof B Condenser",
        "photo",
        "photo_nameplate",
        {"model": "NP-42", "voltage": "460V", "refrigerant": "R-410A"},
        "Job site photo, roof B condensing unit data plate.",
    ),
    Figure(
        "I13",
        "What supply voltage is stamped on the data plate in the job site photo?",
        "460V",
        "Job Photo - Unit 7 Nameplate",
        "Roof B Condenser",
        "photo",
        "photo_nameplate",
        {"model": "NP-42", "voltage": "460V", "refrigerant": "R-410A"},
        "Job site photo, roof B condensing unit data plate.",
    ),
    Figure(
        "I14",
        "What pressure does the gauge in the job site photo read?",
        "312",
        "Job Photo - Suction Gauge",
        "Roof B Condenser",
        "photo",
        "photo_gauge",
        {"reading": 312, "unit": "PSI"},
        "Job site photo, suction pressure gauge reading.",
    ),
    Figure(
        "I15",
        "What fault code is displayed on the control board in the job site photo?",
        "LP-2",
        "Job Photo - Control Board",
        "Roof B Condenser",
        "photo",
        "photo_fault_display",
        {"code": "LP-2"},
        "Job site photo, unit control board fault display.",
    ),
]


# ---------------------------------------------------------------------------
# Manual layout
# ---------------------------------------------------------------------------

MANUALS: list[ManualSpec] = [
    ManualSpec(
        title="Trane Precedent YSC072 Service Manual",
        filename="trane_ysc072_service_manual.pdf",
        sections=[
            "Economizer Setup", "Airflow Setup", "Refrigerant Charge", "Brazing Procedures",
            "Service Clearances", "Compressor Replacement", "Dehumidification",
            "Thermostat Setup", "Refrigerant Pressure Curves", "Electrical Schematics",
        ],
        pages=[
            {"text_facts": ["T01"], "figures": []},
            {"text_facts": ["T02"], "figures": []},
            {"text_facts": ["T03"], "figures": []},
            {"text_facts": ["T04"], "figures": []},
            {"text_facts": ["T05"], "figures": []},
            {"text_facts": ["T06"], "figures": []},
            {"text_facts": ["T07"], "figures": []},
            {"text_facts": ["T18"], "figures": []},
            {"text_facts": [], "figures": ["I01", "I02", "I03"]},
            {"text_facts": [], "figures": ["I07", "I08", "I09"]},
        ],
    ),
    ManualSpec(
        title="Carrier WeatherMaster 48TC Service Manual",
        filename="carrier_48tc_service_manual.pdf",
        sections=[
            "Refrigerant Piping", "Electrical Data", "Refrigerant Charge", "Maintenance",
            "Startup", "TXV Adjustment", "Performance Data", "Coil Capacity Data",
        ],
        pages=[
            {"text_facts": ["T08"], "figures": []},
            {"text_facts": ["T09"], "figures": []},
            {"text_facts": ["T10"], "figures": []},
            {"text_facts": ["T11"], "figures": []},
            {"text_facts": ["T12"], "figures": []},
            {"text_facts": ["T19"], "figures": []},
            {"text_facts": [], "figures": ["I04"]},
            {"text_facts": [], "figures": ["I05"]},
            {"text_facts": [], "figures": ["I10", "I11"]},
        ],
    ),
    ManualSpec(
        title="Lennox XC14 Service Manual",
        filename="lennox_xc14_service_manual.pdf",
        sections=["Condenser Operation", "Refrigerant Charge", "Application Limits", "Charge Verification"],
        pages=[
            {"text_facts": ["T13"], "figures": []},
            {"text_facts": ["T14"], "figures": []},
            {"text_facts": ["T15"], "figures": []},
            {"text_facts": ["T20"], "figures": []},
            {"text_facts": [], "figures": ["I06"]},
        ],
    ),
    ManualSpec(
        title="Johnson Controls YK Series Installation Manual",
        filename="jk_yk_series_installation_manual.pdf",
        sections=["Electrical Data", "Blower Performance", "Thermostat Setup"],
        pages=[
            {"text_facts": ["T16"], "figures": []},
            {"text_facts": ["T17"], "figures": []},
            {"text_facts": ["T21"], "figures": []},
        ],
    ),
]


# Support calls. Each call holds one or more audio facts.
CALLS: dict[str, list[tuple[str, str]]] = {}
for _f in AUDIO_FACTS:
    CALLS.setdefault(_f.call, []).extend(_f.script)


PHOTO_FACTS: list[Figure] = [f for f in FIGURE_FACTS if f.kind == "photo"]


def all_facts() -> list[dict]:
    """Every question in the eval set, in a stable order."""
    out: list[dict] = []
    for f in TEXT_FACTS:
        out.append({
            "qid": f.qid,
            "question": f.question,
            "answer": f.answer,
            "modality_hint": "text",
            "kind": "text_answerable",
            "evidence": {"doc": f.doc, "section": f.section},
        })
    for f in AUDIO_FACTS:
        out.append({
            "qid": f.qid,
            "question": f.question,
            "answer": f.answer,
            "modality_hint": "audio",
            "kind": "text_answerable",
            "evidence": {"call": f.call},
        })
    for f in FIGURE_FACTS:
        out.append({
            "qid": f.qid,
            "question": f.question,
            "answer": f.answer,
            "modality_hint": "image",
            "kind": "picture_only",
            "evidence": {"doc": f.doc, "section": f.section, "renderer": f.renderer},
        })
    return out
